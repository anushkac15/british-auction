"""Fan-out of Postgres NOTIFY events to SSE subscribers.

One background thread LISTENs on the `rfq_events` channel and hands each notification
to the asyncio loop, which wakes the subscribers of that RFQ. Events only carry the
RFQ id; clients refetch the (role-shaped) details, so nothing sensitive is broadcast.
"""

import asyncio
import logging
import threading
from collections import defaultdict

import psycopg
from sqlalchemy.engine import make_url

from app.services.activity import RFQ_EVENTS_CHANNEL

log = logging.getLogger(__name__)


def libpq_conninfo(sqlalchemy_url: str) -> str:
    return make_url(sqlalchemy_url).set(drivername="postgresql").render_as_string(hide_password=False)


class Broadcaster:
    def __init__(self) -> None:
        self._subs: dict[int, set[asyncio.Queue[int]]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, loop: asyncio.AbstractEventLoop, conninfo: str) -> None:
        self._loop = loop
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(conninfo,), name="rfq-listener", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def subscribe(self, rfq_id: int) -> asyncio.Queue[int]:
        queue: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
        self._subs[rfq_id].add(queue)
        return queue

    def unsubscribe(self, rfq_id: int, queue: asyncio.Queue[int]) -> None:
        self._subs[rfq_id].discard(queue)
        if not self._subs[rfq_id]:
            self._subs.pop(rfq_id, None)

    def _fanout(self, rfq_id: int) -> None:
        for queue in list(self._subs.get(rfq_id, ())):
            if queue.empty():  # coalesce bursts: one pending "changed" is enough
                queue.put_nowait(rfq_id)

    def _run(self, conninfo: str) -> None:
        while not self._stop.is_set():
            try:
                with psycopg.connect(conninfo, autocommit=True) as conn:
                    conn.execute(f"LISTEN {RFQ_EVENTS_CHANNEL}")
                    while not self._stop.is_set():
                        for note in conn.notifies(timeout=1.0):
                            if self._loop and note.payload.isdigit():
                                self._loop.call_soon_threadsafe(self._fanout, int(note.payload))
            except Exception:  # reconnect on any connection problem
                log.exception("RFQ event listener failed; retrying")
                self._stop.wait(2)


broadcaster = Broadcaster()
