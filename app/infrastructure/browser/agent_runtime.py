"""Running a browser-use agent: its browser, a step budget with loop detection, and progress reports.

Every step is a paid LLM call, and an agent that cannot find an element tends to
repeat the same goal until the budget runs out.
"""

import asyncio
import base64
import io
import logging
from collections.abc import Awaitable, Callable

from browser_use import Agent, BrowserSession
from browser_use.agent.views import AgentHistoryList

from app.config import Settings
from app.domain.workflows.models import AgentStep
from app.domain.workflows.ports import StepCallback

logger = logging.getLogger(__name__)

_MAX_SCREENSHOT_WIDTH = 1440


class AgentStuckError(RuntimeError):
    pass


def new_browser_session(cookies_file: str | None) -> BrowserSession:
    if cookies_file:
        return BrowserSession(storage_state=cookies_file, user_data_dir=None, headless=True)
    return BrowserSession(headless=True)


async def close_browser(session: BrowserSession) -> None:
    try:
        await session.kill()
    except Exception:
        logger.debug("Browser session already closed", exc_info=True)


async def run_guarded(
    agent: Agent,
    settings: Settings,
    on_step: StepCallback | None = None,
) -> AgentHistoryList:
    """Run the agent within AGENT_MAX_STEPS, stopping early if it repeats one goal AGENT_MAX_REPEATS times."""
    repeated_goal: str | None = None
    report = _step_reporter(on_step)

    async def step_end(a: Agent) -> None:
        nonlocal repeated_goal
        await report(a)
        recent = a.history.model_thoughts()[-settings.AGENT_MAX_REPEATS :]
        goals = {_normalise(t.next_goal) for t in recent}
        if len(recent) == settings.AGENT_MAX_REPEATS and len(goals) == 1 and "" not in goals:
            repeated_goal = recent[-1].next_goal
            a.stop()

    history = await agent.run(max_steps=settings.AGENT_MAX_STEPS, on_step_end=step_end)

    if repeated_goal:
        raise AgentStuckError(
            f"Agent got stuck repeating the same goal {settings.AGENT_MAX_REPEATS} times: {repeated_goal}"
        )
    if not history.is_done() and len(history.history) >= settings.AGENT_MAX_STEPS:
        raise AgentStuckError(f"Agent hit the {settings.AGENT_MAX_STEPS}-step limit without finishing")
    return history


def _normalise(goal: str | None) -> str:
    return " ".join((goal or "").lower().split())


def _step_reporter(on_step: StepCallback | None) -> Callable[[Agent], Awaitable[None]]:
    count = 0

    async def report(agent: Agent) -> None:
        nonlocal count
        count += 1
        if on_step is None:
            return
        await on_step(
            AgentStep(step=count, thought=_latest_thought(agent), screenshot_b64=await _screenshot(agent))
        )

    return report


def _latest_thought(agent: Agent) -> str:
    try:
        thoughts = agent.history.model_thoughts()
    except Exception:
        return ""
    if not thoughts:
        return ""
    brain = thoughts[-1]
    parts = []
    if memory := getattr(brain, "memory", None):
        parts.append(str(memory).strip())
    if next_goal := getattr(brain, "next_goal", None):
        parts.append(f"Next: {str(next_goal).strip()}")
    return " — ".join(parts) or str(brain)


async def _screenshot(agent: Agent) -> str | None:
    try:
        from browser_use.browser.events import ScreenshotEvent

        evt = agent.browser_session.event_bus.dispatch(ScreenshotEvent(full_page=False))
        await evt
        result = await evt.event_result(raise_if_any=False, raise_if_none=False)
    except Exception as e:
        logger.warning("Could not capture screenshot: %s", e)
        return None
    if not result:
        return None
    # PIL resize is CPU-bound; keep it off the event loop
    return await asyncio.get_running_loop().run_in_executor(None, _shrink_png, str(result))


def _shrink_png(b64_data: str) -> str:
    try:
        from PIL import Image
    except ImportError:
        return b64_data
    img = Image.open(io.BytesIO(base64.b64decode(b64_data)))
    if img.width > _MAX_SCREENSHOT_WIDTH:
        ratio = _MAX_SCREENSHOT_WIDTH / img.width
        img = img.resize((_MAX_SCREENSHOT_WIDTH, int(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()
