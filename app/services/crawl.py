import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.agents.discovery.agent import run_discovery_agent
from app.agents.extraction.agent import run_extraction_agent
from app.modules.branding.extractor import extract_brand
from app.modules.crawl.models import CrawlResponse

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path("outputs")


def _save_output(url: str, result: CrawlResponse) -> None:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    domain = urlparse(url).hostname or "unknown"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    path = OUTPUTS_DIR / f"{domain}_{timestamp}.json"
    path.write_text(result.model_dump_json(indent=2))


async def run_crawl_agent(
    url: str,
    query: str | None = None,
    credentials: dict[str, str] | None = None,
    cookies_file: str | None = None,
) -> CrawlResponse:
    # Start branding immediately — runs while discovery + extraction happen
    brand_task = asyncio.create_task(extract_brand(url, cookies_file))

    # Phase 1: Discover which workflows exist on the site
    specs = await run_discovery_agent(url, query, credentials, cookies_file)

    # Phase 2: Extract each workflow in parallel
    extraction_results = await asyncio.gather(
        *[run_extraction_agent(url, spec, credentials, cookies_file) for spec in specs],
        return_exceptions=True,
    )

    workflows = []
    for spec, outcome in zip(specs, extraction_results):
        if isinstance(outcome, BaseException):
            logger.warning("Extraction failed for %r: %s", spec.name, outcome)
        elif outcome is not None:
            workflows.append(outcome)

    brand = await brand_task

    result = CrawlResponse(url=str(url), brand=brand, workflows=workflows)
    _save_output(url, result)

    return result
