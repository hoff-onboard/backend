import json
import logging
import tempfile

from fastapi import APIRouter, HTTPException

from app.modules.crawl.models import CrawlResponse, QueryRequest
from app.services.query import run_query_agent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=CrawlResponse)
async def query(request: QueryRequest):
    try:
        cookies_file = None
        if request.cookies:
            storage_state = {
                "cookies": request.cookies,
                "origins": request.origins or [],
            }
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            json.dump(storage_state, tmp)
            tmp.close()
            cookies_file = tmp.name

        return await run_query_agent(
            str(request.url),
            request.query,
            cookies_file=cookies_file,
        )
    except Exception as e:
        logger.exception("POST /query failed")
        raise HTTPException(status_code=500, detail=str(e))
