import json
import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.services.crawl_stream import stream_crawl

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/stream/crawl")
async def stream_crawl_endpoint(
    url: str,
    query: str | None = None,
    credentials: str | None = None,
    cookies_file: str | None = None,
):
    """SSE endpoint that streams crawl progress events."""

    # Parse credentials if provided as JSON string
    creds = None
    if credentials:
        try:
            creds = json.loads(credentials)
        except json.JSONDecodeError:
            pass

    async def event_generator():
        async for event in stream_crawl(url, query, creds, cookies_file):
            yield {
                "event": event["event"],
                "data": json.dumps(event["data"]),
            }

    return EventSourceResponse(event_generator())
