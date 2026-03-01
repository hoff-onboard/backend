from fastapi import APIRouter, HTTPException

from app.models.requests import CrawlRequest
from app.models.responses import CrawlResponse
from app.services.agent import run_crawl_agent

router = APIRouter()


@router.post("/crawl", response_model=CrawlResponse)
async def crawl(request: CrawlRequest):
    try:
        return await run_crawl_agent(
            str(request.url),
            request.query,
            credentials=request.credentials,
            cookies_file=request.cookies_file,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
