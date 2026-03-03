import json
import logging
import tempfile

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.domain.workflows.models import QueryRequest
from app.services.job_manager import create_job, get_job, get_job_stream

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/jobs")
async def start_job(request: QueryRequest):
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
