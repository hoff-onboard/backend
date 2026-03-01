import json
import tempfile

from fastapi import APIRouter, HTTPException

from app.modules.crawl.models import CrawlRequest, CrawlResponse, QueryRequest
from app.services.crawl import run_crawl_agent

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


@router.post("/query", response_model=CrawlResponse)
async def query(request: QueryRequest):
    try:
        cookies_file = None
        if request.cookies:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            json.dump(request.cookies, tmp)
            tmp.close()
            cookies_file = tmp.name

        return await run_crawl_agent(
            str(request.url),
            request.query,
            cookies_file=cookies_file,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
