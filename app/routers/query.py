import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_workflow_repo
from app.domain.workflows.models import CrawlResponse, QueryRequest
from app.domain.workflows.ports import WorkflowRepository
from app.services.query import run_query_agent
from app.services.storage_state import remove_storage_state, write_storage_state

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=CrawlResponse)
async def query(request: QueryRequest):
    cookies_file = write_storage_state(request.cookies, request.origins)
    try:
        return await run_query_agent(
            str(request.url),
            request.query,
            cookies_file=cookies_file,
            use_research=request.use_research,
        )
    except Exception as e:
        logger.exception("POST /query failed")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        remove_storage_state(cookies_file)


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
