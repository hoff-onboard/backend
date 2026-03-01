import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.agents.crawler.agent import run_workflow_agent
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
    brand_task = extract_brand(url, cookies_file)
    workflow_task = run_workflow_agent(url, query, credentials, cookies_file)

    brand, workflows = await asyncio.gather(brand_task, workflow_task)

    result = CrawlResponse(
        url=str(url),
        brand=brand,
        workflows=workflows.workflows,
    )

    _save_output(url, result)

    return result
