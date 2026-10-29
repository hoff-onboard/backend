import json
import logging

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.domain.workflows.models import QueryRequest
from app.services.job_manager import cancel_job, create_job, get_job, get_job_stream
from app.services.storage_state import write_storage_state

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/jobs")
async def start_job(request: QueryRequest):
    cookies_file = write_storage_state(request.cookies, request.origins)
    job_id = create_job(str(request.url), request.query, cookies_file)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": job["status"],
        "url": job["url"],
        "query": job["query"],
    }


@router.post("/jobs/{job_id}/cancel")
async def cancel(job_id: str):
    if not get_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, "cancelled": cancel_job(job_id)}


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        async for event in get_job_stream(job_id):
            yield {
                "event": event["event"],
                "data": json.dumps(event["data"]),
            }

    return EventSourceResponse(event_generator())
