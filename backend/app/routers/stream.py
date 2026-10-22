import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.events import broadcaster

router = APIRouter(tags=["stream"])

KEEPALIVE_SECONDS = 15


@router.get("/rfqs/{rfq_id}/stream")
async def stream_rfq(rfq_id: int, request: Request) -> StreamingResponse:
    """Server-sent events: emits `changed` whenever the RFQ's bids, close time or status change.

    The payload is only the RFQ id, so no authentication is needed; clients refetch
    the role-shaped details over the normal REST endpoint.
    """
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
