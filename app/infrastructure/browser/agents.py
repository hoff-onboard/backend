"""browser-use agents behind the WorkflowDiscoverer and WorkflowExtractor ports."""

import logging
from typing import Any

from browser_use import Agent, BrowserSession, Tools
from browser_use.dom.views import DEFAULT_INCLUDE_ATTRIBUTES

from app.config import Settings
from app.domain.research.models import ResearchContext
from app.domain.workflows.models import (
    DiscoveryResponse,
    Workflow,
    WorkflowSpec,
    WorkflowsResponse,
)
from app.domain.workflows.ports import (
    StepCallback,
    WorkflowDiscoverer,
    WorkflowExtractor,
)
from app.infrastructure.browser.agent_runtime import (
    close_browser,
    new_browser_session,
    run_guarded,
)
from app.infrastructure.browser.selector import register_resolve_selector
from app.infrastructure.browser.validate import validate_workflows
from app.infrastructure.llm.factory import get_llm
from app.infrastructure.prompts import discovery, extraction

logger = logging.getLogger(__name__)

INCLUDE_ATTRIBUTES = DEFAULT_INCLUDE_ATTRIBUTES + ["href", "class", "data-testid"]


def _agent_options(
    settings: Settings, url: str, session: BrowserSession, credentials: dict[str, str] | None
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "llm": get_llm(settings),
        "include_attributes": INCLUDE_ATTRIBUTES,
        "browser_session": session,
        # browser-use only auto-opens a URL when the task text contains exactly one, and our prompts contain several
        "initial_actions": [{"navigate": {"url": url, "new_tab": False}}],
    }
    if credentials:
        options["sensitive_data"] = credentials
    return options


class BrowserUseDiscoverer(WorkflowDiscoverer):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def discover(
        self,
        url: str,
        query: str | None,
        *,
        cookies_file: str | None = None,
        credentials: dict[str, str] | None = None,
        on_step: StepCallback | None = None,
    ) -> list[WorkflowSpec]:
        session = new_browser_session(cookies_file)
        agent = Agent(
            task=discovery.build_task_prompt(url, query),
            extend_system_message=discovery.SYSTEM_PROMPT,
            output_model_schema=DiscoveryResponse,
            **_agent_options(self._settings, url, session, credentials),
        )
        try:
            history = await run_guarded(agent, self._settings, on_step)
        finally:
            await close_browser(session)

        raw = history.final_result()
        if not raw:
            raise RuntimeError("Discovery agent returned no result")
        return DiscoveryResponse.model_validate_json(raw).workflows


class BrowserUseExtractor(WorkflowExtractor):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def extract(
        self,
        url: str,
        spec: WorkflowSpec,
        *,
        cookies_file: str | None = None,
        credentials: dict[str, str] | None = None,
        research: ResearchContext | None = None,
        on_step: StepCallback | None = None,
    ) -> Workflow | None:
        # Layer 1 of the selector pipeline: the agent picks elements, resolve_selector builds the CSS
        tools = Tools()
        register_resolve_selector(tools)

        session = new_browser_session(cookies_file)
        agent = Agent(
            task=extraction.build_task_prompt(
                url,
                spec.name,
                spec.description,
                research_steps=research.steps if research else None,
            ),
            extend_system_message=extraction.SYSTEM_PROMPT,
            output_model_schema=WorkflowsResponse,
            tools=tools,
            **_agent_options(self._settings, url, session, credentials),
        )
        try:
            history = await run_guarded(agent, self._settings, on_step)
            raw = history.final_result()
            if not raw:
                logger.warning("Extraction agent returned no result for workflow: %s", spec.name)
                return None

            # Layer 2: the Step field validator runs inside model_validate_json
            result = WorkflowsResponse.model_validate_json(raw)
            # Layer 3: syntax and DOM-presence checks against the still-open browser
            result = await validate_workflows(result, browser_session=session)
        finally:
            await close_browser(session)

        if not result.workflows:
            logger.warning("No valid steps after validation for workflow: %s", spec.name)
            return None
        return result.workflows[0]
