import logging

from app.clock import system_clock
from app.db import SessionLocal
from app.services.status import sweep
from app.tasks.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.sweeper.sweep_auction_statuses")
def sweep_auction_statuses() -> int:
    """Persist UPCOMING -> ACTIVE -> CLOSED / FORCE_CLOSED transitions and log them."""
    with SessionLocal() as db:
        changed = sweep(db, system_clock)
    if changed:
        log.info("Auction sweeper updated %d RFQ(s)", changed)
    return changed
