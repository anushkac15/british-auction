# British Auction RFQ System

A simplified RFQ (Request for Quotation) platform with British Auction bidding. Suppliers bid down openly,
bids near the end automatically extend the auction, and a forced close time is a hard stop.

**Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Celery + Redis, React + Vite + TypeScript, TanStack Query, Docker Compose.

- High-level design and architecture diagram: [docs/HLD.md](docs/HLD.md)
- Database schema: [docs/schema.md](docs/schema.md)

## Quick start (Docker)

```bash
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:3000 | Web app |
| http://localhost:8000/docs | API docs (OpenAPI) |

The app opens on a **Log in** page (`/login`). New users can sign up at **Register** (`/register`) as either a
**buyer** or a **supplier**. The account type is chosen once and decides what the user can do (`/register?role=supplier`
preselects supplier). Log out from the header.

The API container runs migrations and, because `docker-compose.yml` sets `SEED_DEMO_USERS=true`, seeds demo accounts,
all with the password `password123`. Deployed environments leave this unset, so no demo accounts exist there:

| Email | Role |
|---|---|
| `buyer@acme.test` | Buyer |
| `bluedart@suppliers.test`, `maersk@suppliers.test`, `dhl@suppliers.test`, `gati@suppliers.test` | Supplier |

### Live demo (about 6 minutes)

```bash
docker compose exec api python -m app.seed --demo      # prints the demo RFQ id
python scripts/demo_bidder.py --rfq <id>               # host Python 3.10+, standard library only
```

Open `http://localhost:3000/rfqs/<id>`. The demo RFQ starts in 10 seconds, closes after about 3 minutes, and force-closes after about 6 minutes, with
`X = 1 min`, `Y = 1 min`, and trigger "any rank change". The script places opening bids, then keeps undercutting
L1 inside the trigger window. You'll see the countdown jump on each extension, the extension reasons in the activity log,
a single "cap reached" entry, and finally **Force Closed**. Log in as a supplier in another browser (or a private window)
to see the restricted view.

## Local development (without Docker)

You need Postgres on `localhost:5432` (user/password `auction`, databases `auction` and `auction_test`). Redis is
only needed for Celery.

```bash
cd backend
python -m venv .venv && . .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head && python -m app.seed
uvicorn app.main:app --reload --port 8000
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo   # optional, needs Redis
celery -A app.tasks.celery_app beat --loglevel=info                 # optional

cd ../frontend
npm install && npm run dev                            # http://localhost:5173 (proxies /api to :8000)
```

Settings come from environment variables (or `backend/.env`):

| Variable | Default | Notes |
|---|---|---|
| `APP_ENV` | `development` | `production` refuses to start without a strong `SECRET_KEY` and hides `/docs` |
| `DATABASE_URL` | local Postgres | `postgres://` and `postgresql://` URLs from hosting providers are accepted as-is |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker |
| `SECRET_KEY` | dev-only value | Signs login tokens; at least 32 random characters in production, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `TOKEN_TTL_MINUTES` | `720` | Login lifetime |
| `LOGIN_MAX_FAILURES`, `LOGIN_LOCKOUT_SECONDS` | `5`, `900` | Failed logins per email before it is locked for the window |
| `LOGIN_THROTTLE_STORE` | `memory` | `redis` (set in both compose files) shares the failed-login count between API processes |
| `CORS_ORIGINS`, `SWEEP_INTERVAL_SECONDS`, `SSE_ENABLED` | | |
| `SEED_DEMO_USERS` | unset | `true` makes the container create the demo accounts on start |
| `PORT`, `WEB_CONCURRENCY` | `8000`, `2` | Port and number of API worker processes in the container |

## Deploying to a VM (e.g. Oracle Cloud Always Free)

[`docker-compose.prod.yml`](docker-compose.prod.yml) runs the full stack on one server: PostgreSQL, Redis, the API,
the Celery worker and beat, the web app, and [Caddy](https://caddyserver.com) in front for HTTPS. Only ports 80 and
443 are published, there are no demo accounts, and every container restarts on failure or reboot. No domain is
needed: `<ip-with-dashes>.sslip.io` resolves to the server, and Caddy gets a real certificate for it.

On an Ubuntu VM with ports 80 and 443 open (in the cloud firewall *and* the VM's own `iptables`):

```bash
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER   # then log out and back in
git clone https://github.com/anushkac15/british-auction.git && cd british-auction
cat > .env <<EOF
SITE_ADDRESS=$(curl -s https://ifconfig.me | tr . -).sslip.io
POSTGRES_PASSWORD=$(openssl rand -hex 24)
SECRET_KEY=$(openssl rand -hex 32)
EOF
docker compose -f docker-compose.prod.yml up -d --build
grep SITE_ADDRESS .env                                  # open https://<that address>
```

- Update: `git pull && docker compose -f docker-compose.prod.yml up -d --build`
- Logs: `docker compose -f docker-compose.prod.yml logs -f api worker`
- Backups: [`scripts/backup_db.sh`](scripts/backup_db.sh) writes `backups/auction-<time>.sql.gz` and keeps 14 days; schedule it with `crontab -e`
  (the line is in the script). Restore into an empty database: `gunzip -c <file> | docker compose -f docker-compose.prod.yml exec -T postgres psql -U auction auction`

## Free demo on Render (no background worker)

[`render.yaml`](render.yaml) deploys a free demo with no card required:

```
React (static site) ──/api/*──► FastAPI ──► PostgreSQL   (data + LISTEN/NOTIFY for live updates)
                                   │
                                   └──────► Redis        (failed-login counts shared by API processes)
```

The Celery worker and beat schedule are **not** deployed here, because correctness never depends on them:

- Every list and detail response computes the status from the server clock (`resolve_status`), so it is never stale.
- Bids are accepted or rejected against the server clock inside the row lock, whatever the stored status says.
- Opening an RFQ persists any missed transition and writes its `AUCTION_STARTED` / `CLOSED` / `FORCE_CLOSED`
  entry, stamped with the time it actually happened.

What the worker adds is background consistency: stored statuses and log entries are updated within 15 seconds
even for RFQs nobody opens. The code stays in the repository, and `docker-compose.prod.yml` (and the local
`docker-compose.yml`) run it as a dedicated worker container.

1. Sign up at [render.com](https://render.com) with GitHub, choose **New → Blueprint**, and select this repository.
   Render creates the database, Redis, the API and the static site, and generates `SECRET_KEY`.
2. After the first deploy, check the API's URL. If it isn't `https://british-auction-api.onrender.com` (the name was taken),
   edit the `/api/*` rewrite on `british-auction-web` to point at the real URL.
3. Open the `british-auction-web` URL and register the first buyer and supplier.

Free-plan limits: the API sleeps after 15 idle minutes (the first request then takes 30–60 seconds), and the free
database is deleted after 30 days. If the live-update stream is cut by the proxy, the page falls back to polling
every 3 seconds.

## Tests

The tests run against **real PostgreSQL**, not SQLite, because they depend on `SELECT ... FOR UPDATE`, `DISTINCT ON`, partial
unique indexes, and generated columns. The suite creates `auction_test` if it's missing and migrates it with Alembic.

```bash
docker compose up -d postgres
cd backend && pytest                                   # or: docker compose exec api pytest
# custom DB: TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db pytest
```

The 94 tests cover:
- registration, login, duplicate emails, tampered or expired tokens, and locking an email after repeated failed logins
- production settings: weak secret keys rejected, provider database URLs accepted, and the Redis-backed login
  throttle shared between processes (logins allowed if Redis is down)
- the live-update stream rejecting anonymous users, unknown RFQs, and other buyers' RFQs
- every trigger type and the rank-change cases below
- window boundaries, including a bid exactly at close being rejected
- the forced-close cap, with exactly one `EXTENSION_CAPPED` entry
- `CLOSED` vs `FORCE_CLOSED`
- Decimal precision (`0.10 + 0.20 = 0.30`)
- quote validity, transit time and create-form rules
- DB CHECK constraints
- the supplier view never leaking competitor names or non-L1 prices, and buyers never seeing other buyers' RFQs
- sweeper idempotency
- multi-threaded concurrent bids, with no lost extensions and no overshoot of the forced close

The clock is injected (`app.clock`), so tests freeze time.

## Auction rules

### Bid acceptance
- A bid is accepted only when `bid_start_at <= now < bid_close_at`. This is checked **inside the locked transaction**
  and uses the server clock, never the cached status. A bid at exactly the close time is rejected.
- Each charge must be `>= 0` with at most 2 decimals, the transit time must be `> 0` days, and the quote must be valid on or after the
  pickup date.
- A supplier's new total must be **strictly lower** than their own previous total.

### Extensions
- A trigger is evaluated only when `now >= bid_close_at - X`, where `bid_close_at` is the current, possibly already extended, close time.
- When it fires: `new_close = min(bid_close_at + Y, forced_close_at)`. Extensions are measured from the current close
  time, not from the time of the bid.
- If the extension is shortened by the forced close, the log says "extended to the forced close (cap reached)".
- If the close time already equals the forced close, `EXTENSION_CAPPED` is logged **once per RFQ** and later triggers log
  nothing extra. A partial unique index enforces this in the database too.

### Rank-change definitions
Ranking: each supplier's latest bid, ordered by total price ascending. **On a tie, the earlier bid keeps the better rank.**
Triggers compare the ordered list of suppliers before and after the bid.

| Case | Any rank change | L1 change |
|---|---|---|
| First bid in an empty auction | Yes | Yes (no L1 before, then L1) |
| A supplier's first bid lands in last place | **Yes**: a new entrant changes the order | No |
| A supplier lowers their price but keeps the same position | **No**: the order is identical | No |
| A supplier lowers their price and overtakes someone (not L1) | Yes | No |
| A supplier becomes the new L1 | Yes | Yes |
| L1 lowers their own price | No | No |
| A supplier matches another's price | No: the earlier bid stays ahead | No |

"Bid received in last X minutes" fires on every accepted bid inside the window.

### Status
| Status | Condition (server time) |
|---|---|
| Upcoming | `now < bid_start_at` |
| Active | `bid_start_at <= now < bid_close_at` |
| Force Closed | `now >= bid_close_at` and `bid_close_at == forced_close_at` |
| Closed | `now >= bid_close_at` otherwise |

The stored `rfqs.status` is a cache. The Celery beat sweeper persists transitions and logs `AUCTION_STARTED` /
`CLOSED` / `FORCE_CLOSED`, stamped with the time the transition actually happened. A detail read also self-heals it.

## Role-based views

| | Buyer | Supplier |
|---|---|---|
| Auction list | Only RFQs they created; other buyers' RFQs return 404 | Every RFQ from every buyer, browsed by buyer: a list of buyers, then each buyer's RFQs (`/buyers/{id}`) |
| Ranking | All suppliers with names and full quotes (L1, L2, …) | Only their own row and rank ("L2 of 5") |
| Prices | Everything | Their own bids and the **current L1 price, without the name** |
| Activity log | Full | Competitors shown as "A competitor"; competitor prices hidden; extension reasons kept |
| Actions | Create RFQs | Place bids |

## API

Every response, including errors, contains `server_now`. Money values are JSON strings. Endpoints marked "buyer",
"supplier" or "any user" need an `Authorization: Bearer <access_token>` header from register or login.

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/api/auth/register` | anyone | `{name, email, password (8+ chars), role: BUYER \| SUPPLIER}`; returns `access_token` and `user` |
| POST | `/api/auth/login` | anyone | `{email, password}`; returns `access_token` and `user` |
| GET | `/api/auth/me` | any user | The logged-in account |
| GET | `/api/rfqs` | any user | Listing: id/ref, name, lowest bid, current close, forced close, status (plus own rank for suppliers). Filtered by role, see above |
| POST | `/api/rfqs` | buyer | Create an RFQ and its auction config |
| GET | `/api/rfqs/{id}` | owning buyer, any supplier | Details, shaped by role |
| POST | `/api/rfqs/{id}/bids` | supplier | Returns rank, extension info, and the new close time |
| GET | `/api/rfqs/{id}/stream` | owning buyer, any supplier | SSE `changed` events (payload: RFQ id only). Same bearer token and access rule as the detail endpoint; 401/404 otherwise |

## Create-form validation (API, mirrored in the UI)
- The start time is in the future (10 seconds of clock skew tolerated).
- The bid close is after the start, and the forced close is after the bid close.
- The pickup date is on or after the **forced close** date (UTC), because the forced close is the latest the auction can end.
- `1 <= X <= 60` and `1 <= Y <= 60` minutes, and X can't be longer than the auction itself.
- The reference ID is unique (409 otherwise), and the name is non-empty. Datetimes must include a timezone.

## Assumptions
- Ranking is by total price (freight + origin + destination). The earlier bid wins a tie.
- **Supplier visibility:** "suppliers submit bids openly" is read as suppliers seeing the live L1 price and their own
  rank, but not competitor identities or other prices. This is a deliberate reading of the brief: it keeps bidding transparent,
  so suppliers have a target to beat, while following common reverse-auction practice, which also limits collusion.
- The quote must still be valid on the pickup date.
- Money is `NUMERIC(12,2)` / `Decimal` end to end, in a single currency (shown as INR). Multi-currency is out of scope.
- A supplier's new bid must be strictly lower than their own previous bid.
- Extensions are measured from the current close time, not from the bid time.
- Any supplier can bid on any RFQ; there are no invitation lists.
- Auth is email + password with stateless 12-hour tokens. After 5 failed logins an email is locked for 15 minutes;
  the count lives in Redis, and if Redis is unreachable logins are allowed rather than blocked. Out of scope: email verification and password reset. Logging out clears the token
  in the browser; issued tokens stay valid until they expire.
- Neo4j and RabbitMQ aren't used: there's no graph-shaped data, and Redis covers the broker role.
