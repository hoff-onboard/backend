import logging

from fastapi import APIRouter, HTTPException

from app.api.dependencies import PipelineDep, RepositoryDep
from app.application.query import run_query
from app.domain.workflows.models import CrawlResponse, QueryRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/query", response_model=CrawlResponse)
async def query(request: QueryRequest, pipeline: PipelineDep):
    try:
        return await run_query(
            pipeline,
            str(request.url),
            request.query,
            cookies=request.cookies,
            origins=request.origins,
            use_research=request.use_research,
        )
    except Exception as e:
        logger.exception("POST /query failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/workflows/{domain}")
async def get_workflows(domain: str, repo: RepositoryDep):
    doc = await repo.get_by_domain(domain)
    if not doc:
        raise HTTPException(status_code=404, detail="No workflows found for this domain")
    return doc


@router.delete("/workflows/{domain}/{workflow_name}")
async def delete_workflow(domain: str, workflow_name: str, repo: RepositoryDep):
    if not await repo.soft_delete(domain, workflow_name):
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"status": "deleted"}
