from celery import Celery

from app.config import settings

celery_app = Celery("british_auction", broker=settings.redis_url, include=["app.tasks.sweeper"])
celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    worker_hijack_root_logger=False,
    beat_schedule={
        "sweep-auction-statuses": {
            "task": "app.tasks.sweeper.sweep_auction_statuses",
            "schedule": float(settings.sweep_interval_seconds),
            # A sweep that waits longer than one interval is obsolete; the next one replaces it.
            "options": {"expires": float(settings.sweep_interval_seconds)},
        }
    },
)
