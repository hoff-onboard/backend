import logging

from browser_use import Agent, BrowserSession, Tools
from browser_use.dom.views import DEFAULT_INCLUDE_ATTRIBUTES

from app.agents.crawler.prompt import SYSTEM_PROMPT, build_task_prompt
from app.config import get_settings
from app.modules.crawl.models import WorkflowsResponse
from app.modules.crawl.selector import register_resolve_selector
from app.modules.crawl.validate import validate_workflows
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

INCLUDE_ATTRIBUTES = DEFAULT_INCLUDE_ATTRIBUTES + ["href", "class", "data-testid"]


async def run_workflow_agent(
    url: str,
    query: str | None,
    credentials: dict[str, str] | None,
    cookies_file: str | None,
) -> WorkflowsResponse:
    settings = get_settings()
    llm = get_llm(settings)

    task = build_task_prompt(
        url,
        query,
        credential_keys=list(credentials.keys()) if credentials else None,
    )

    # Layer 1: register the resolve_selector custom action
    tools = Tools()
    register_resolve_selector(tools)

    browser_session = BrowserSession(storage_state=cookies_file) if cookies_file else None

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

    if browser_session:
        agent_kwargs["browser_session"] = browser_session

    agent = Agent(**agent_kwargs)
    history = await agent.run()

    raw = history.final_result()
    if not raw:
        raise RuntimeError("Agent returned no result")

    # Layer 2: Pydantic field validator runs inside model_validate_json
    result = WorkflowsResponse.model_validate_json(raw)

    # Layer 3: post-processing validation (syntax + DOM presence)
    session = browser_session or agent.browser_session
    result = await validate_workflows(result, browser_session=session)

    return result
