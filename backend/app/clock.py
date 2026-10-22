from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock:
    """Manually controlled clock for tests and simulations."""

    def __init__(self, at: datetime):
        self._now = at.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._now

    def set(self, at: datetime) -> None:
        self._now = at.astimezone(timezone.utc)

    def advance(self, **kwargs: float) -> None:
        self._now += timedelta(**kwargs)


system_clock = SystemClock()


def get_clock() -> Clock:
    return system_clock
