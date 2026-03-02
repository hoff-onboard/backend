"""Streaming crawl service that yields SSE events."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
from collections.abc import AsyncIterator
from typing import Any

from browser_use import Agent

from app.agents.discovery.agent import run_discovery_agent
from app.agents.extraction.agent import run_extraction_agent
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

logger = logging.getLogger(__name__)

_MAX_SCREENSHOT_WIDTH = 800
_SCREENSHOT_EVERY_N_STEPS = 3


def _resize_screenshot_b64(
    b64_data: str, max_width: int = _MAX_SCREENSHOT_WIDTH
) -> str:
    """Resize a base64-encoded PNG screenshot to max_width, preserving aspect ratio."""
    try:
        from PIL import Image

        raw = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(raw))
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        # Pillow not installed; return as-is
        return b64_data


async def stream_crawl(
    url: str,
    query: str | None = None,
    credentials: dict[str, str] | None = None,
    cookies_file: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run the crawl pipeline and yield SSE events as they happen."""

    step_counter = 0
    current_flow_index: int | None = None
    event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def on_step_end(agent: Agent) -> None:
        nonlocal step_counter
        step_counter += 1

        # Emit agent thought
        try:
            thoughts = agent.history.model_thoughts()
            if thoughts:
                await event_queue.put(
                    agent_thought_event(
                        step_counter, str(thoughts[-1]), current_flow_index
                    )
                )
        except Exception:
            logger.debug("Could not extract agent thought at step %d", step_counter)

        # Emit screenshot every N steps
        if step_counter % _SCREENSHOT_EVERY_N_STEPS == 0:
            try:
                from browser_use.browser.events import ScreenshotEvent

                evt = agent.browser_session.event_bus.dispatch(
                    ScreenshotEvent(full_page=False)
                )
                await evt
                result = await evt.event_result(raise_if_any=False, raise_if_none=False)
                if result:
                    resized = _resize_screenshot_b64(str(result))
                    await event_queue.put(
                        screenshot_event(step_counter, resized, current_flow_index)
                    )
            except Exception:
                logger.debug("Could not capture screenshot at step %d", step_counter)

    try:
        # --- Phase: branding (start async) ---
        yield phase_event("branding")
        brand_task = asyncio.create_task(extract_brand(url, cookies_file))

        # --- Phase: discovery ---
        yield phase_event("discovery")
        yield log_event("Starting workflow discovery...")
        specs = await run_discovery_agent(
            url, query, credentials, cookies_file, on_step_end=on_step_end
        )

        # Drain any queued events from discovery
        while not event_queue.empty():
            yield event_queue.get_nowait()

        yield log_event(f"Discovered {len(specs)} workflow(s)")

        # --- Emit brand when ready ---
        brand = await brand_task
        yield brand_event(brand.model_dump())
        yield log_event("Brand extraction complete")

        # --- Phase: extraction (per workflow) ---
        for i, spec in enumerate(specs):
            current_flow_index = i
            step_counter = 0  # reset per flow
            yield phase_event("extraction", spec.name)
            yield log_event(f"Extracting flow: {spec.name}")

            workflow = await run_extraction_agent(
                url, spec, credentials, cookies_file, on_step_end=on_step_end
            )

            # Drain queued events
            while not event_queue.empty():
                yield event_queue.get_nowait()

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
