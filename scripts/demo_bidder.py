"""Fire realistic bids at a demo RFQ so extensions and the forced close happen live.

    python -m app.seed --demo                # in backend/, prints the RFQ id
    python scripts/demo_bidder.py --rfq 1    # then watch http://localhost:5173/rfqs/1

Each supplier places an opening bid as soon as the auction starts. After that the script
stays quiet until the trigger window, then repeatedly has a non-L1 supplier undercut L1.
Each overtake changes the ranking, so the auction extends until it hits the forced close.
Standard library only.
"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

CENT = Decimal("0.01")

# Accounts created by `python -m app.seed`.
BUYER_EMAIL = "buyer@acme.test"
SUPPLIER_EMAILS = [
    "bluedart@suppliers.test",
    "maersk@suppliers.test",
    "dhl@suppliers.test",
    "gati@suppliers.test",
]


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, token: str | None = None, body: dict | None = None):
        req = urllib.request.Request(self.base + path, method=method)
        req.add_header("Accept", "application/json")
        if token is not None:
            req.add_header("Authorization", f"Bearer {token}")
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data=data, timeout=10) as res:
                return res.status, json.loads(res.read() or b"{}")
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"{}")


def ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def factor(rng: random.Random, lo: float, hi: float) -> Decimal:
    return Decimal(f"{rng.uniform(lo, hi):.4f}")


def split_total(total: Decimal) -> dict:
    freight = (total * Decimal("0.8")).quantize(CENT, ROUND_DOWN)
    origin = (total * Decimal("0.1")).quantize(CENT, ROUND_DOWN)
    return {
        "freight_charges": str(freight),
        "origin_charges": str(origin),
        "destination_charges": str(total - freight - origin),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rfq", type=int, required=True)
    # 127.0.0.1 rather than localhost: avoids a slow IPv6-first lookup on Windows.
    parser.add_argument("--api", default="http://127.0.0.1:8000/api")
    parser.add_argument("--seed", type=int, default=None, help="random seed for repeatable runs")
    parser.add_argument("--password", default="password123", help="password of the seeded accounts")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    api = Api(args.api)

    def log_in(email: str) -> dict:
        try:
            status, body = api.call("POST", "/auth/login", body={"email": email, "password": args.password})
        except urllib.error.URLError as err:
            raise SystemExit(f"Cannot reach the API: {err}") from None
        if status != 200:
            raise SystemExit(f"Cannot log in as {email}: {body.get('detail')}. Run `python -m app.seed` first.")
        return {**body["user"], "token": body["access_token"]}

    buyer = log_in(BUYER_EMAIL)
    suppliers = [log_in(email) for email in SUPPLIER_EMAILS]
    carriers = {s["id"]: f"{s['name'].split()[0]} Fleet" for s in suppliers}
    seen_events: set[int] = set()

    def fetch():
        code, body = api.call("GET", f"/rfqs/{args.rfq}", buyer["token"])
        if code != 200:
            raise SystemExit(f"Cannot load RFQ {args.rfq}: {body}")
        return body

    def print_new_events(rfq: dict) -> None:
        for event in reversed(rfq["activity"]):
            if event["id"] not in seen_events:
                seen_events.add(event["id"])
                stamp = ts(event["at"]).astimezone().strftime("%H:%M:%S")
                print(f"  [{stamp}] {event['event_type']:<16} {event['message']}")

    def bid(rfq: dict, supplier: dict, total: Decimal) -> None:
        validity = (date.fromisoformat(rfq["pickup_date"]) + timedelta(days=14)).isoformat()
        body = {
            "carrier_name": carriers[supplier["id"]],
            "transit_time_days": rng.randint(2, 6),
            "quote_validity_date": validity,
            **split_total(total),
        }
        code, res = api.call("POST", f"/rfqs/{args.rfq}/bids", supplier["token"], body)
        if code == 201:
            ext = res["extension"]
            note = f" -> extended to {ts(ext['new_close_at']).astimezone():%H:%M:%S}" if ext else ""
            print(f"{supplier['name']:<20} bid {total:>12,.2f}  now L{res['rank']}{note}")
        else:
            print(f"{supplier['name']:<20} bid {total:>12,.2f}  rejected ({code}): {res.get('detail')}")

    print(f"Driving RFQ {args.rfq} with {len(suppliers)} suppliers. Ctrl+C to stop.\n")
    while True:
        detail = fetch()
        rfq, now = detail["rfq"], ts(detail["server_now"])
        print_new_events(rfq)
        start, close, forced = ts(rfq["bid_start_at"]), ts(rfq["bid_close_at"]), ts(rfq["forced_close_at"])

        if now >= close:
            time.sleep(1.5)  # let the final status entry land, then report
            rfq = fetch()["rfq"]
            print_new_events(rfq)
            print(f"\nFinished: {rfq['status']} at {close.astimezone():%H:%M:%S}, "
                  f"{rfq['extension_count']} extension(s), L1 = {rfq['lowest_bid']}")
            return 0
        if now < start:
            wait = (start - now).total_seconds()
            print(f"Waiting {wait:.0f}s for bidding to open…")
            time.sleep(min(wait + 0.2, 5))
            continue

        latest = {row["supplier_id"]: Decimal(row["quote"]["total_price"]) for row in rfq["ranking"]}
        newcomers = [s for s in suppliers if s["id"] not in latest]
        if newcomers:
            for s in newcomers:
                bid(rfq, s, Decimal(rng.randint(95_000, 120_000)) + Decimal(rng.randint(0, 99)) / 100)
                time.sleep(rng.uniform(0.5, 1.5))
            continue

        window = timedelta(minutes=rfq["config"]["trigger_window_minutes"])
        remaining = close - now
        if remaining > window:
            # Outside the window: occasionally improve a price, otherwise wait for the window.
            if rng.random() < 0.3:
                s = rng.choice(suppliers)
                bid(rfq, s, (latest[s["id"]] * factor(rng, 0.985, 0.995)).quantize(CENT, ROUND_DOWN))
            time.sleep(min(max((remaining - window).total_seconds(), 1), rng.uniform(4, 8)))
            continue

        # Inside the window: a non-L1 supplier undercuts L1, which changes the ranking.
        l1_id = rfq["ranking"][0]["supplier_id"]
        challenger = rng.choice([s for s in suppliers if s["id"] != l1_id])
        l1_price = Decimal(rfq["lowest_bid"])
        undercut = (l1_price * factor(rng, 0.985, 0.997)).quantize(CENT, ROUND_DOWN)
        bid(rfq, challenger, undercut)
        capped = close >= forced
        time.sleep(rng.uniform(6, 12) if not capped else rng.uniform(10, 20))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
