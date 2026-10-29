import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.dependencies import PipelineDep
from app.application.crawl import run_crawl, stream_crawl
from app.domain.workflows.models import CrawlRequest, CrawlResponse

router = APIRouter()


@router.post("/crawl", response_model=CrawlResponse)
async def crawl(request: CrawlRequest, pipeline: PipelineDep):
    try:
        return await run_crawl(
            pipeline,
            str(request.url),
            request.query,
            credentials=request.credentials,
            cookies_file=request.cookies_file,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stream/crawl")
async def stream_crawl_endpoint(
    pipeline: PipelineDep,
    url: str,
    query: str | None = None,
    credentials: str | None = None,
    cookies_file: str | None = None,
):
    """SSE endpoint that streams crawl progress events; credentials arrive as a JSON string."""
    creds = None
    if credentials:
        try:
            creds = json.loads(credentials)
        except json.JSONDecodeError:
            pass

    async def event_generator():
        async for event in stream_crawl(pipeline, url, query, creds, cookies_file):
            yield {"event": event["event"], "data": json.dumps(event["data"])}

    return EventSourceResponse(event_generator())
