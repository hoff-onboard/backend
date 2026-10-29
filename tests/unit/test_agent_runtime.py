import types

import pytest

from app.config import Settings
from app.infrastructure.browser.agent_runtime import AgentStuckError, run_guarded


class FakeHistory:
    def __init__(self) -> None:
        self.history: list[str] = []
        self._thoughts: list = []

    def model_thoughts(self):
        return self._thoughts

    def is_done(self):
        return False


class FakeAgent:
    """Mimics browser-use's run loop: one goal per step, stop() ends it after the current step."""

    def __init__(self, goals: list[str]) -> None:
        self.goals = goals
        self.history = FakeHistory()
        self.stopped = False
        self.browser_session = None

    def stop(self):
        self.stopped = True

    async def run(self, max_steps, on_step_end):
        for goal in self.goals[:max_steps]:
            self.history.history.append(goal)
            self.history._thoughts.append(types.SimpleNamespace(next_goal=goal, memory="m"))
            await on_step_end(self)
            if self.stopped:
                break
        return self.history


async def test_stops_when_the_same_goal_repeats():
    agent = FakeAgent(["open menu", "Click 'Your profile'", "click  'your profile' ", "Click 'Your profile'", "next"])
    with pytest.raises(AgentStuckError, match="same goal 3 times"):
        await run_guarded(agent, Settings())
    assert len(agent.history.history) == 4


async def test_stops_at_the_step_budget():
    agent = FakeAgent([f"goal {i}" for i in range(40)])
    with pytest.raises(AgentStuckError, match="25-step limit"):
        await run_guarded(agent, Settings())
    assert len(agent.history.history) == 25


async def test_reports_each_step():
    reports = []

    async def on_step(step):
        reports.append(step)

    agent = FakeAgent(["a", "b"])
    with pytest.raises(AgentStuckError):  # the fake never finishes; budget is lowered to 2
        await run_guarded(agent, Settings(AGENT_MAX_STEPS=2), on_step)
    assert [r.step for r in reports] == [1, 2]
    assert reports[1].thought == "m — Next: b"
