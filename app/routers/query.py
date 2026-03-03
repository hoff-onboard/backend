import json
import logging
import tempfile

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_workflow_repo
from app.domain.workflows.models import CrawlResponse, QueryRequest
from app.domain.workflows.ports import WorkflowRepository
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
            tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
            json.dump(storage_state, tmp)
            tmp.close()
            cookies_file = tmp.name

        return await run_query_agent(
            str(request.url),
            request.query,
            cookies_file=cookies_file,
            use_research=request.use_research,
        )
    except Exception as e:
        logger.exception("POST /query failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{domain}")
async def get_workflows(
    domain: str,
    repo: WorkflowRepository = Depends(get_workflow_repo),
):
    doc = await repo.get_by_domain(domain)
    if not doc:
        raise HTTPException(
            status_code=404, detail="No workflows found for this domain"
        )
    return doc


@router.delete("/workflows/{domain}/{workflow_name}")
async def delete_workflow(
    domain: str,
    workflow_name: str,
    repo: WorkflowRepository = Depends(get_workflow_repo),
):
    deleted = await repo.soft_delete(domain, workflow_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"status": "deleted"}
