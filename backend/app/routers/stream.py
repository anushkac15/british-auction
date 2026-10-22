import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.db import SessionLocal
from app.deps import Credentials, user_from_credentials
from app.errors import not_found
from app.events import broadcaster
from app.models import Rfq
from app.services import views

router = APIRouter(tags=["stream"])

KEEPALIVE_SECONDS = 15


def _authorize(credentials: HTTPAuthorizationCredentials | None, rfq_id: int) -> None:
    # Own short-lived session: a request-scoped one would stay checked out for the whole stream.
    with SessionLocal() as db:
        user = user_from_credentials(db, credentials)
        rfq = db.get(Rfq, rfq_id)
        if rfq is None or not views.buyer_can_view(rfq, user):
            raise not_found("RFQ")


@router.get("/rfqs/{rfq_id}/stream")
async def stream_rfq(rfq_id: int, request: Request, credentials: Credentials = None) -> StreamingResponse:
    """Server-sent events: emits `changed` whenever the RFQ's bids, close time or status change.

    Requires the same bearer token as the REST API, and the same access rule as the detail
    endpoint (buyers: own RFQs only). The payload is only the RFQ id; clients refetch the
    role-shaped details over REST.
    """
    await run_in_threadpool(_authorize, credentials, rfq_id)
    queue = broadcaster.subscribe(rfq_id)

    async def events():
        try:
            yield f"event: ready\ndata: {json.dumps({'rfq_id': rfq_id})}\n\n"
            while not await request.is_disconnected():
                try:
                    await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                    yield f"event: changed\ndata: {json.dumps({'rfq_id': rfq_id})}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            broadcaster.unsubscribe(rfq_id, queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
