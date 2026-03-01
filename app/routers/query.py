import logging

from fastapi import APIRouter, HTTPException

from app.modules.crawl.models import CrawlResponse, QueryRequest
from app.services.query import run_query_agent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=CrawlResponse)
async def query(request: QueryRequest):
    try:
        return await run_query_agent(
            str(request.url),
            request.query,
            credentials=request.credentials,
            cookies_file=request.cookies_file,
        )
    except Exception as e:
        logger.exception("POST /query failed")
        raise HTTPException(status_code=500, detail=str(e))
