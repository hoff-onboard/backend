"""Crawl use case: discover every workflow a site offers, then extract each one."""

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
from app.domain.workflows.models import AgentStep, CrawlResponse

logger = logging.getLogger(__name__)


async def run_crawl(
    pipeline: Pipeline,
    url: str,
    query: str | None = None,
    credentials: dict[str, str] | None = None,
    cookies_file: str | None = None,
) -> CrawlResponse:
    brand_task = asyncio.create_task(pipeline.branding.extract(url, cookies_file))
    try:
        specs = await pipeline.discoverer.discover(
            url, query, cookies_file=cookies_file, credentials=credentials
        )
        outcomes = await asyncio.gather(
            *[
                pipeline.extractor.extract(
                    url, spec, cookies_file=cookies_file, credentials=credentials
                )
                for spec in specs
            ],
            return_exceptions=True,
        )
        brand = await brand_task
    finally:
        await cancel_pending(brand_task)

    workflows = []
    for spec, outcome in zip(specs, outcomes, strict=True):
        if isinstance(outcome, BaseException):
            logger.warning("Extraction failed for %r: %s", spec.name, outcome)
        elif outcome is not None:
            workflows.append(outcome)

    result = CrawlResponse(url=url, brand=brand, workflows=workflows)
    pipeline.archive.write(result)
    return result


async def stream_crawl(
    pipeline: Pipeline,
    url: str,
    query: str | None = None,
    credentials: dict[str, str] | None = None,
    cookies_file: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run the crawl pipeline, yielding SSE events; flows are extracted one after another."""
    flow_index: int | None = None
    events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def on_step(step: AgentStep) -> None:
        if step.thought:
            await events.put(agent_thought_event(step.step, step.thought, flow_index))
        if step.screenshot_b64:
            await events.put(screenshot_event(step.step, step.screenshot_b64, flow_index))

    brand_task: asyncio.Task | None = None
    try:
        yield phase_event("branding")
        brand_task = asyncio.create_task(pipeline.branding.extract(url, cookies_file))

        yield phase_event("discovery")
        yield log_event("Starting workflow discovery...")
        specs = await pipeline.discoverer.discover(
            url, query, cookies_file=cookies_file, credentials=credentials, on_step=on_step
        )
        while not events.empty():
            yield events.get_nowait()
        yield log_event(f"Discovered {len(specs)} workflow(s)")

        brand = await brand_task
        yield brand_event(brand.model_dump())
        yield log_event("Brand extraction complete")

        for i, spec in enumerate(specs):
            flow_index = i
            yield phase_event("extraction", spec.name)
            yield log_event(f"Extracting flow: {spec.name}")
            workflow = await pipeline.extractor.extract(
                url, spec, cookies_file=cookies_file, credentials=credentials, on_step=on_step
            )
            while not events.empty():
                yield events.get_nowait()
            if workflow:
                yield workflow_event(i, workflow.model_dump())
                yield log_event(f"Workflow complete: {workflow.name}")
            else:
                yield log_event(f"Extraction returned no result for: {spec.name}")

        yield log_event("Crawl complete!")
        yield done_event()

    except Exception as exc:
        logger.exception("stream_crawl failed")
        yield error_event(str(exc))
        yield done_event()
    finally:
        await cancel_pending(brand_task)
