import logging
from collections.abc import Callable
from typing import Any

from browser_use import Agent, BrowserSession
from browser_use.dom.views import DEFAULT_INCLUDE_ATTRIBUTES

from app.agents.discovery.prompt import SYSTEM_PROMPT, build_task_prompt
from app.config import get_settings
from app.modules.crawl.models import DiscoveryResponse, WorkflowSpec
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

INCLUDE_ATTRIBUTES = DEFAULT_INCLUDE_ATTRIBUTES + ["href", "class", "data-testid"]


async def run_discovery_agent(
    url: str,
    query: str | None,
    credentials: dict[str, str] | None,
    cookies_file: str | None,
    on_step_end: Callable[[Agent], Any] | None = None,
) -> list[WorkflowSpec]:
    settings = get_settings()
    llm = get_llm(settings)
    task = build_task_prompt(url, query)

    browser_session = BrowserSession(storage_state=cookies_file, user_data_dir=None) if cookies_file else None

    agent_kwargs: dict = dict(
        task=task,
        llm=llm,
        extend_system_message=SYSTEM_PROMPT,
        output_model_schema=DiscoveryResponse,
        include_attributes=INCLUDE_ATTRIBUTES,
    )

    if credentials:
        agent_kwargs["sensitive_data"] = credentials
    if browser_session:
        agent_kwargs["browser_session"] = browser_session

    agent = Agent(**agent_kwargs)
    run_kwargs: dict = {}
    if on_step_end:
        run_kwargs["on_step_end"] = on_step_end
    history = await agent.run(**run_kwargs)

    raw = history.final_result()
    if not raw:
        raise RuntimeError("Discovery agent returned no result")

    return DiscoveryResponse.model_validate_json(raw).workflows
