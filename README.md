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

The API container runs migrations and seeds demo accounts, all with the password `password123`:

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

Settings come from environment variables (or `backend/.env`): `DATABASE_URL`, `REDIS_URL`, `CORS_ORIGINS`,
`SWEEP_INTERVAL_SECONDS`, `SSE_ENABLED`, `SECRET_KEY` (signs login tokens; **set your own** outside local dev, e.g.
`python -c "import secrets; print(secrets.token_urlsafe(32))"`), and `TOKEN_TTL_MINUTES` (default 720).

## Tests

The tests run against **real PostgreSQL**, not SQLite, because they depend on `SELECT ... FOR UPDATE`, `DISTINCT ON`, partial
unique indexes, and generated columns. The suite creates `auction_test` if it's missing and migrates it with Alembic.

```bash
docker compose up -d postgres
cd backend && pytest                                   # or: docker compose exec api pytest
# custom DB: TEST_DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db pytest
```

The 71 tests cover:
- registration, login, duplicate emails, and tampered or expired tokens
- every trigger type and the rank-change cases below
- window boundaries, including a bid exactly at close being rejected
- the forced-close cap, with exactly one `EXTENSION_CAPPED` entry
- `CLOSED` vs `FORCE_CLOSED`
- Decimal precision (`0.10 + 0.20 = 0.30`)
- quote validity, transit time and create-form rules
- DB CHECK constraints
- the supplier view never leaking competitor names or non-L1 prices
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
| GET | `/api/rfqs` | any user | Listing: id/ref, name, lowest bid, current close, forced close, status (plus own rank for suppliers) |
| POST | `/api/rfqs` | buyer | Create an RFQ and its auction config |
| GET | `/api/rfqs/{id}` | any user | Details, shaped by role |
| POST | `/api/rfqs/{id}/bids` | supplier | Returns rank, extension info, and the new close time |
| GET | `/api/rfqs/{id}/stream` | anyone | SSE `changed` events (payload: RFQ id only) |

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
- Auth is email + password with stateless 12-hour tokens. Out of scope: email verification, password reset, and
  login rate limiting. Logging out clears the token in the browser; issued tokens stay valid until they expire.
- Neo4j and RabbitMQ aren't used: there's no graph-shaped data, and Redis covers the broker role.
