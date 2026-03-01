import json
import logging
import tempfile

from fastapi import APIRouter, HTTPException

from app.modules.crawl.models import CrawlResponse, QueryRequest
from app.services.query import run_query_agent
from app.services.workflows_repo import get_workflows_by_domain

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


@router.get("/workflows/{domain}")
async def get_workflows(domain: str):
    doc = await get_workflows_by_domain(domain)
    if not doc:
        raise HTTPException(status_code=404, detail="No workflows found for this domain")
    return doc
