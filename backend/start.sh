#!/bin/sh
set -e

alembic upgrade head

if [ "$SEED_DEMO_USERS" = "true" ]; then
    python -m app.seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}"
