import logging
from collections.abc import Callable
from typing import Any

from browser_use import Agent, BrowserSession, Tools
from browser_use.dom.views import DEFAULT_INCLUDE_ATTRIBUTES

from app.agents.extraction.prompt import SYSTEM_PROMPT, build_task_prompt
from app.config import get_settings
from app.domain.workflows.models import Workflow, WorkflowSpec, WorkflowsResponse
from app.domain.research.models import ResearchContext
from app.modules.crawl.selector import register_resolve_selector
from app.modules.crawl.validate import validate_workflows
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

INCLUDE_ATTRIBUTES = DEFAULT_INCLUDE_ATTRIBUTES + ["href", "class", "data-testid"]


async def run_extraction_agent(
    url: str,
    spec: WorkflowSpec,
    credentials: dict[str, str] | None,
    cookies_file: str | None,
    research_context: ResearchContext | None = None,
    on_step_end: Callable[[Agent], Any] | None = None,
) -> Workflow | None:
    settings = get_settings()
    llm = get_llm(settings)

    task = build_task_prompt(
        url,
        spec.name,
        spec.description,
        research_steps=research_context.steps if research_context else None,
    )

    # Layer 1: register the resolve_selector custom action
    tools = Tools()
    register_resolve_selector(tools)

    browser_session = (
        BrowserSession(storage_state=cookies_file, user_data_dir=None, headless=True)
        if cookies_file
        else BrowserSession(headless=True)
    )

    agent_kwargs: dict = dict(
        task=task,
        llm=llm,
        extend_system_message=SYSTEM_PROMPT,
        output_model_schema=WorkflowsResponse,
        include_attributes=INCLUDE_ATTRIBUTES,
        tools=tools,
    )

    if credentials:
        agent_kwargs["sensitive_data"] = credentials
    agent_kwargs["browser_session"] = browser_session

    agent = Agent(**agent_kwargs)
    run_kwargs: dict = {}
    if on_step_end:
        run_kwargs["on_step_end"] = on_step_end
    history = await agent.run(**run_kwargs)

    raw = history.final_result()
    if not raw:
        logger.warning(
            "Extraction agent returned no result for workflow: %s", spec.name
        )
        return None

    # Layer 2: Pydantic field validator runs inside model_validate_json
    result = WorkflowsResponse.model_validate_json(raw)

    # Layer 3: post-processing validation (syntax + DOM presence)
    session = browser_session or agent.browser_session
    result = await validate_workflows(result, browser_session=session)

    if not result.workflows:
        logger.warning("No valid steps after validation for workflow: %s", spec.name)
        return None

    return result.workflows[0]
