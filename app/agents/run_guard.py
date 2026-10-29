"""Runs a browser-use agent with a step budget and loop detection.

Every step is a paid LLM call, and an agent that cannot find an element tends to
repeat the same goal until the budget runs out.
"""

import logging
from collections.abc import Callable
from typing import Any

from browser_use import Agent, BrowserSession
from browser_use.agent.views import AgentHistoryList

from app.config import Settings

logger = logging.getLogger(__name__)


class AgentStuckError(RuntimeError):
    pass


def _normalise(goal: str | None) -> str:
    return " ".join((goal or "").lower().split())


async def run_guarded(
    agent: Agent,
    settings: Settings,
    on_step_end: Callable[[Agent], Any] | None = None,
) -> AgentHistoryList:
    repeated_goal: str | None = None

    async def step_end(a: Agent) -> None:
        nonlocal repeated_goal
        if on_step_end:
            await on_step_end(a)
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


async def close_browser(session: BrowserSession) -> None:
    try:
        await session.kill()
    except Exception:
        logger.debug("Browser session already closed", exc_info=True)
