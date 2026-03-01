"""In-memory job manager for streaming query jobs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from app.services.query_stream import stream_query

logger = logging.getLogger(__name__)

_jobs: dict[str, dict[str, Any]] = {}


def create_job(url: str, query: str, cookies_file: str | None = None) -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "running",
        "url": url,
        "query": query,
        "events": [],
        "subscribers": [],  # list of asyncio.Queue for each connected client
    }

    asyncio.create_task(_run_job(job_id, url, query, cookies_file))
    return job_id


async def _run_job(job_id: str, url: str, query: str, cookies_file: str | None) -> None:
    job = _jobs[job_id]
    try:
        async for event in stream_query(url, query, cookies_file):
            job["events"].append(event)
            for q in job["subscribers"]:
                await q.put(event)
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        err = {"event": "error", "data": {"message": str(exc)}}
        job["events"].append(err)
        for q in job["subscribers"]:
            await q.put(err)
    finally:
        job["status"] = "done"
        for q in job["subscribers"]:
            await q.put(None)


async def get_job_stream(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return

    # Create subscriber queue and register it BEFORE reading past events
    # This ensures no events are missed between replay and live listening
    sub_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    job["subscribers"].append(sub_queue)

    try:
        # Snapshot how many events exist right now
        replay_count = len(job["events"])

        # Replay past events
        for i in range(replay_count):
            yield job["events"][i]

        # If job already done and no more events will come
        if job["status"] == "done":
            # Drain anything that arrived in our queue during replay
            while not sub_queue.empty():
                item = sub_queue.get_nowait()
                if item is None:
                    return
                yield item
            return

        # Skip events we already replayed (they also went into our queue)
        skipped = 0
        while True:
            item = await sub_queue.get()
            if item is None:
                break
            if skipped < replay_count:
                skipped += 1
                continue
            yield item
    finally:
        if sub_queue in job["subscribers"]:
            job["subscribers"].remove(sub_queue)


def get_job(job_id: str) -> dict[str, Any] | None:
    return _jobs.get(job_id)
