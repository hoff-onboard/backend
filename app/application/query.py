"""Query use case: turn one user question into one reviewed, saved workflow."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.application.pipeline import Pipeline, cancel_pending
from app.domain.workflows.events import (
    agent_thought_event,
    brand_event,
    done_event,
    error_event,
    log_event,
    phase_event,
    screenshot_event,
    workflow_event,
)
from app.domain.workflows.models import AgentStep, CrawlResponse, WorkflowSpec

logger = logging.getLogger(__name__)


async def run_query(
    pipeline: Pipeline,
    url: str,
    query: str,
    cookies: list[dict] | None = None,
    origins: list[dict] | None = None,
    use_research: bool = False,
) -> CrawlResponse:
    cookies_file = pipeline.sessions.write(cookies, origins)
    brand_task = asyncio.create_task(pipeline.branding.extract(url, cookies_file))
    try:
        research = await pipeline.research.research(url, query, cookies_file) if use_research else None
        spec = WorkflowSpec(name=query, description=research.description if research else "")
        workflow = await pipeline.extractor.extract(
            url, spec, cookies_file=cookies_file, research=research
        )
        if workflow:
            workflow = await pipeline.reviewer.review(workflow)
        brand = await brand_task
    finally:
        await cancel_pending(brand_task)
        pipeline.sessions.remove(cookies_file)

    result = CrawlResponse(url=url, brand=brand, workflows=[workflow] if workflow else [])
    pipeline.archive.write(result)
    await _save(pipeline, result)
    return result


async def stream_query(
    pipeline: Pipeline,
    url: str,
    query: str,
    cookies_file: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run the query pipeline, yielding SSE events as each phase and agent step completes."""
    screenshots: list[str] = []
    events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def on_step(step: AgentStep) -> None:
        if step.thought:
            await events.put(agent_thought_event(step.step, step.thought, 0))
        if step.screenshot_b64:
            screenshots.append(step.screenshot_b64)
            await events.put(screenshot_event(step.step, step.screenshot_b64, 0))

    brand_task: asyncio.Task | None = None
    extraction_task: asyncio.Task | None = None
    try:
        yield phase_event("branding")
        brand_task = asyncio.create_task(pipeline.branding.extract(url, cookies_file))

        yield phase_event("research")
        yield log_event(f"Researching: {query}")
        research = await pipeline.research.research(url, query, cookies_file)
        yield log_event(f"Research complete: {research.description[:80]}")

        spec = WorkflowSpec(name=query, description=research.description)
        yield phase_event("extraction", spec.name)
        yield log_event(f"Extracting flow: {query}")
        extraction_task = asyncio.create_task(
            pipeline.extractor.extract(
                url, spec, cookies_file=cookies_file, research=research, on_step=on_step
            )
        )
        while not extraction_task.done():
            try:
                yield await asyncio.wait_for(events.get(), timeout=0.5)
            except TimeoutError:
                continue
        workflow = extraction_task.result()
        while not events.empty():
            yield events.get_nowait()

        if workflow:
            workflow = await pipeline.reviewer.review(workflow)
            yield log_event("Selector review complete")

        brand = await brand_task
        yield brand_event(brand.model_dump())

        if workflow:
            yield workflow_event(0, workflow.model_dump())
            yield log_event(f"Workflow complete: {workflow.name}")

        result = CrawlResponse(url=url, brand=brand, workflows=[workflow] if workflow else [])
        await _save(pipeline, result, {0: screenshots} if screenshots else None)
        yield done_event()

    except Exception as exc:
        logger.exception("stream_query failed")
        yield error_event(str(exc))
        yield done_event()
    finally:
        # Also reached when the job is cancelled: stop child tasks so their browsers close
        await cancel_pending(extraction_task, brand_task)


async def _save(
    pipeline: Pipeline,
    result: CrawlResponse,
    screenshots_map: dict[int, list[str]] | None = None,
) -> None:
    try:
        await pipeline.repository.save(result, screenshots_map)
    except Exception:
        logger.exception("Failed to save workflows")
