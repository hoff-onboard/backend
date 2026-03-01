import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.agents.extraction.agent import run_extraction_agent
from app.config import get_settings
from app.modules.branding.extractor import extract_brand
from app.modules.crawl.models import CrawlResponse, WorkflowSpec
from app.modules.crawl.review import review_selectors
from app.modules.research.researcher import research_workflow

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path("outputs")


def _save_output(url: str, result: CrawlResponse) -> None:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    domain = urlparse(url).hostname or "unknown"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    path = OUTPUTS_DIR / f"{domain}_{timestamp}.json"
    path.write_text(result.model_dump_json(indent=2))


async def run_query_agent(
    url: str,
    query: str,
    credentials: dict[str, str] | None = None,
    cookies_file: str | None = None,
    use_research: bool = False,
) -> CrawlResponse:
    settings = get_settings()

    # Start branding immediately — runs throughout
    brand_task = asyncio.create_task(extract_brand(url, cookies_file))

    research = None
    if use_research:
        # Phase 1 (optional): Research — ask Gemini what this workflow looks like
        logger.info("Starting research for query=%r url=%r", query, url)
        research = await research_workflow(url, query, settings, cookies_file)
        logger.info("Research complete: description=%r steps=%s", research.description[:60], research.steps)

    # Phase 2: Single focused extraction, optionally guided by research
    description = research.description if research else ""
    spec = WorkflowSpec(name=query, description=description)
    logger.info("Starting extraction agent for workflow=%r (research=%s)", spec.name, use_research)
    workflow = await run_extraction_agent(
        url, spec, credentials, cookies_file, research_context=research
    )
    logger.info("Extraction complete: workflow=%s", workflow)

    # Phase 3: Review selectors — classify as structural vs dynamic
    if workflow:
        workflow = await review_selectors(workflow, settings)
        logger.info("Selector review complete")

    logger.info("Awaiting brand task...")
    brand = await brand_task
    logger.info("Brand complete: %s", brand)

    workflows = [workflow] if workflow else []
    result = CrawlResponse(url=str(url), brand=brand, workflows=workflows)
    _save_output(url, result)

    try:
        from app.services.workflows_repo import save_workflows
        await save_workflows(result)
    except Exception:
        logger.exception("Failed to save workflows to MongoDB")

    return result
