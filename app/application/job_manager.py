"""In-memory job manager: runs a streaming query as a background task and fans its events out to SSE clients."""

import asyncio
import logging
import uuid
from contextlib import aclosing
from typing import Any

from app.application.pipeline import Pipeline
from app.application.query import stream_query
from app.domain.workflows.events import done_event, error_event

logger = logging.getLogger(__name__)

_jobs: dict[str, dict[str, Any]] = {}


def create_job(
    pipeline: Pipeline,
    url: str,
    query: str,
    cookies: list[dict] | None = None,
    origins: list[dict] | None = None,
) -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "running",
        "url": url,
        "query": query,
        "events": [],
        "subscribers": [],  # one asyncio.Queue per connected client
    }
    cookies_file = pipeline.sessions.write(cookies, origins)
    _jobs[job_id]["task"] = asyncio.create_task(_run_job(pipeline, job_id, url, query, cookies_file))
    return job_id


def cancel_job(job_id: str) -> bool:
    """Stop a running job. Returns False if it was already finished."""
    job = _jobs[job_id]
    if job["status"] == "done":
        return False
    job["task"].cancel()
    return True


def get_job(job_id: str) -> dict[str, Any] | None:
    return _jobs.get(job_id)


async def _publish(job: dict[str, Any], event: dict[str, Any]) -> None:
    job["events"].append(event)
    for q in job["subscribers"]:
        await q.put(event)


async def _run_job(
    pipeline: Pipeline, job_id: str, url: str, query: str, cookies_file: str | None
) -> None:
    job = _jobs[job_id]
    try:
        async with aclosing(stream_query(pipeline, url, query, cookies_file)) as events:
            async for event in events:
                await _publish(job, event)
    except asyncio.CancelledError:
        logger.info("Job %s stopped by user", job_id)
        await _publish(job, error_event("Stopped by user"))
        await _publish(job, done_event())
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        await _publish(job, error_event(str(exc)))
    finally:
        pipeline.sessions.remove(cookies_file)
        job["status"] = "done"
        for q in job["subscribers"]:
            await q.put(None)


async def get_job_stream(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return

    # Subscribe before replaying so no event is missed between replay and live listening
    sub_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    job["subscribers"].append(sub_queue)

    try:
        replay_count = len(job["events"])
        for i in range(replay_count):
            yield job["events"][i]

        if job["status"] == "done":
            while not sub_queue.empty():
                item = sub_queue.get_nowait()
                if item is None:
                    return
                yield item
            return

        # The queue only holds events published after we subscribed, so none repeat the replay
        while True:
            item = await sub_queue.get()
            if item is None:
                break
            yield item
    finally:
        if sub_queue in job["subscribers"]:
            job["subscribers"].remove(sub_queue)
