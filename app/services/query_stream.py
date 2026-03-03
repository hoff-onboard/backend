"""Streaming query service that yields SSE events for a single query."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from collections.abc import AsyncIterator
from typing import Any

from browser_use import Agent

from app.agents.extraction.agent import run_extraction_agent
from app.config import get_settings
from app.modules.branding.extractor import extract_brand
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
from app.domain.workflows.models import CrawlResponse, WorkflowSpec
from app.modules.crawl.review import review_selectors
from app.modules.research.researcher import research_workflow

logger = logging.getLogger(__name__)

_MAX_SCREENSHOT_WIDTH = 1440


def _resize_screenshot_b64_sync(
    b64_data: str, max_width: int = _MAX_SCREENSHOT_WIDTH
) -> str:
    try:
        from PIL import Image

        raw = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(raw))
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        return b64_data


async def _resize_screenshot_b64(
    b64_data: str, max_width: int = _MAX_SCREENSHOT_WIDTH
) -> str:
    """Run CPU-heavy resize in a thread to avoid blocking the event loop."""
    return await asyncio.get_event_loop().run_in_executor(
        None, _resize_screenshot_b64_sync, b64_data, max_width
    )


def _format_thought(thought_obj) -> str:
    """Extract clean text from an AgentBrain object."""
    parts = []
    memory = getattr(thought_obj, "memory", None)
    next_goal = getattr(thought_obj, "next_goal", None)
    if memory:
        parts.append(str(memory).strip())
    if next_goal:
        parts.append(f"Next: {str(next_goal).strip()}")
    if parts:
        return " — ".join(parts)
    return str(thought_obj)


async def stream_query(
    url: str,
    query: str,
    cookies_file: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run a single-query pipeline and yield SSE events."""

    step_counter = 0
    screenshots: list[str] = []
    event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def on_step_end(agent: Agent) -> None:
        nonlocal step_counter
        step_counter += 1

        # Emit agent thought
        try:
            thoughts = agent.history.model_thoughts()
            if thoughts:
                clean = _format_thought(thoughts[-1])
                await event_queue.put(agent_thought_event(step_counter, clean, 0))
        except Exception:
            logger.debug("Could not extract agent thought at step %d", step_counter)

        # Capture screenshot via browser-use event bus
        try:
            from browser_use.browser.events import ScreenshotEvent

            evt = agent.browser_session.event_bus.dispatch(
                ScreenshotEvent(full_page=False)
            )
            await evt
            result = await evt.event_result(raise_if_any=False, raise_if_none=False)
            if result:
                resized = await _resize_screenshot_b64(str(result))
                screenshots.append(resized)
                await event_queue.put(screenshot_event(step_counter, resized, 0))
        except Exception as e:
            logger.warning(
                "Could not capture screenshot at step %d: %s", step_counter, e
            )

    try:
        settings = get_settings()

        # --- Phase: branding (async) ---
        yield phase_event("branding")
        brand_task = asyncio.create_task(extract_brand(url, cookies_file))

        # --- Phase: research ---
        yield phase_event("research")
        yield log_event(f"Researching: {query}")
        research = await research_workflow(url, query, settings, cookies_file)
        yield log_event(f"Research complete: {research.description[:80]}")

        # --- Phase: extraction ---
        spec = WorkflowSpec(name=query, description=research.description)
        yield phase_event("extraction", spec.name)
        yield log_event(f"Extracting flow: {query}")

        # Run extraction in a task so we can drain events concurrently
        extraction_task = asyncio.create_task(
            run_extraction_agent(
                url,
                spec,
                None,
                cookies_file,
                research_context=research,
                on_step_end=on_step_end,
            )
        )

        # Yield events as they arrive while extraction runs
        while not extraction_task.done():
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                yield event
            except asyncio.TimeoutError:
                continue

        workflow = extraction_task.result()

        # Drain any remaining queued events
        while not event_queue.empty():
            yield event_queue.get_nowait()

        # Review selectors
        if workflow:
            workflow = await review_selectors(workflow, settings)
            yield log_event("Selector review complete")

        # Await brand
        brand = await brand_task
        yield brand_event(brand.model_dump())

        if workflow:
            yield workflow_event(0, workflow.model_dump())
            yield log_event(f"Workflow complete: {workflow.name}")

        # Save to MongoDB
        workflows = [workflow] if workflow else []
        result = CrawlResponse(url=str(url), brand=brand, workflows=workflows)
        try:
            from app.services.workflows_repo import save_workflows

            await save_workflows(
                result, screenshots_map={0: screenshots} if screenshots else None
            )
        except Exception:
            logger.exception("Failed to save workflows to MongoDB")

        yield done_event()

    except Exception as exc:
        logger.exception("stream_query failed")
        yield error_event(str(exc))
        yield done_event()
