import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from browser_use import Agent, BrowserSession, Tools
from browser_use.dom.views import DEFAULT_INCLUDE_ATTRIBUTES

from app.config import get_settings
from app.models.responses import CrawlResponse, WorkflowsResponse
from app.services.branding import extract_brand
from app.services.llm import get_llm
from app.services.prompt import SYSTEM_PROMPT, build_task_prompt
from app.services.selector import register_resolve_selector
from app.services.validate import validate_workflows

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path("outputs")

INCLUDE_ATTRIBUTES = DEFAULT_INCLUDE_ATTRIBUTES + ["href", "class", "data-testid"]


def _save_output(url: str, result: CrawlResponse) -> Path:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    domain = urlparse(url).hostname or "unknown"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    path = OUTPUTS_DIR / f"{domain}_{timestamp}.json"
    path.write_text(result.model_dump_json(indent=2))
    return path


async def _run_workflow_agent(
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


async def run_crawl_agent(
    url: str,
    query: str | None = None,
    credentials: dict[str, str] | None = None,
    cookies_file: str | None = None,
) -> CrawlResponse:
    # Run branding extraction and workflow agent in parallel
    brand_task = extract_brand(url, cookies_file)
    workflow_task = _run_workflow_agent(url, query, credentials, cookies_file)

    brand, workflows = await asyncio.gather(brand_task, workflow_task)

    result = CrawlResponse(
        url=str(url),
        brand=brand,
        workflows=workflows.workflows,
    )

    _save_output(url, result)

    return result
