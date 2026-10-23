# Database Schema (PostgreSQL 16)

Migrations: [`0001_initial.py`](../backend/alembic/versions/0001_initial.py),
[`0002_user_passwords.py`](../backend/alembic/versions/0002_user_passwords.py),
[`0003_fix_check_constraint_names.py`](../backend/alembic/versions/0003_fix_check_constraint_names.py),
[`0004_rfqs_buyer_index.py`](../backend/alembic/versions/0004_rfqs_buyer_index.py).
All timestamps are `TIMESTAMPTZ` stored in UTC. Enums are `VARCHAR` + `CHECK` constraints.

```mermaid
erDiagram
  users ||--o{ rfqs : "creates (buyer)"
  rfqs ||--|| auction_configs : has
  rfqs ||--o{ bids : receives
  users ||--o{ bids : "places (supplier)"
  rfqs ||--o{ activity_logs : records
  bids |o--o{ activity_logs : "referenced by"

  users {
    int id PK
    varchar name
    varchar email UK
    varchar role "BUYER | SUPPLIER"
    varchar password_hash "nullable, scrypt"
  }
  rfqs {
    int id PK
    varchar reference_id UK
    varchar name
    int buyer_id FK
    date pickup_date
    timestamptz bid_start_at
    timestamptz original_bid_close_at
    timestamptz bid_close_at "current, moves with extensions"
    timestamptz forced_close_at
    varchar status "cached: UPCOMING | ACTIVE | CLOSED | FORCE_CLOSED"
    timestamptz created_at
  }
  auction_configs {
    int rfq_id PK,FK
    int trigger_window_minutes "X, 1..60"
    int extension_minutes "Y, 1..60"
    varchar trigger_type "ANY_BID | ANY_RANK_CHANGE | L1_CHANGE"
  }
  bids {
    int id PK
    int rfq_id FK
    int supplier_id FK
    varchar carrier_name
    numeric freight_charges "NUMERIC(12,2)"
    numeric origin_charges "NUMERIC(12,2)"
    numeric destination_charges "NUMERIC(12,2)"
    numeric total_price "GENERATED: sum of charges"
    int transit_time_days
    date quote_validity_date
    timestamptz created_at
  }
  activity_logs {
    int id PK
    int rfq_id FK
    varchar event_type
    text reason "never contains supplier names"
    int supplier_id FK "nullable, the actor"
    int bid_id FK "nullable"
    timestamptz old_close_at
    timestamptz new_close_at
    timestamptz created_at
  }
```

## Constraints

| Table | Constraint | Purpose |
|---|---|---|
| users | `UNIQUE (lower(email))` | One account per email, case-insensitive |
| rfqs | `original_bid_close_at > bid_start_at` | Valid auction window |
| rfqs | `forced_close_at > original_bid_close_at` | Forced close later than the planned close |
| rfqs | `bid_close_at > bid_start_at` | |
| rfqs | `bid_close_at <= forced_close_at` | Extensions never pass the forced close; **equality allowed** for a capped extension |
| rfqs | `bid_close_at >= original_bid_close_at` | Close time only ever moves forward |
| rfqs | `UNIQUE (reference_id)` | |
| auction_configs | `trigger_window_minutes BETWEEN 1 AND 60`, `extension_minutes BETWEEN 1 AND 60` | Sensible X / Y |
| bids | each charge `>= 0`, `transit_time_days > 0` | |
| activity_logs | `UNIQUE (rfq_id, event_type) WHERE event_type IN ('RFQ_CREATED','AUCTION_STARTED','EXTENSION_CAPPED','CLOSED','FORCE_CLOSED')` | At most one `EXTENSION_CAPPED` (and one of each lifecycle event) per RFQ; inserts use `ON CONFLICT DO NOTHING` |

## Indexes

- `bids (rfq_id, supplier_id, created_at DESC)`: serves the latest-bid-per-supplier query.
- `activity_logs (rfq_id, created_at)`: activity timeline.
- `rfqs (status)`: the sweeper's "due transitions" scan.
- `rfqs (buyer_id)`: a buyer's own RFQ list.

## Latest bid per supplier

```sql
SELECT DISTINCT ON (supplier_id) *
FROM bids
WHERE rfq_id = :rfq_id
ORDER BY supplier_id, created_at DESC, id DESC;
```

Ranking then sorts these by `(total_price ASC, created_at ASC, id ASC)`: on equal totals the earlier bid
keeps the better rank.
