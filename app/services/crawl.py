import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.agents.crawler.agent import run_workflow_agent
from app.config import get_settings
from app.modules.branding.extractor import extract_brand
from app.modules.crawl.models import CrawlResponse
from app.modules.skills.generator import generate_all_skills_md
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path("outputs")

# Used to turn workflow names into safe filenames
_UNSAFE_CHARS = re.compile(r"[^\w\s-]")
_WHITESPACE = re.compile(r"[\s]+")


def _slugify(name: str) -> str:
    slug = _UNSAFE_CHARS.sub("", name.lower())
    return _WHITESPACE.sub("_", slug).strip("_")


def _save_output(url: str, result: CrawlResponse) -> None:
    OUTPUTS_DIR.mkdir(exist_ok=True)
    domain = urlparse(url).hostname or "unknown"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    prefix = f"{domain}_{timestamp}"

    # Save the JSON response
    (OUTPUTS_DIR / f"{prefix}.json").write_text(
        result.model_dump_json(indent=2)
    )

    # Save one SKILLS.md per workflow
    for name, md in result.skills.items():
        slug = _slugify(name)
        (OUTPUTS_DIR / f"{prefix}_{slug}_SKILLS.md").write_text(md)


async def run_crawl_agent(
    url: str,
    query: str | None = None,
    credentials: dict[str, str] | None = None,
    cookies_file: str | None = None,
) -> CrawlResponse:
    brand_task = extract_brand(url, cookies_file)
    workflow_task = run_workflow_agent(url, query, credentials, cookies_file)

    brand, workflows = await asyncio.gather(brand_task, workflow_task)

    settings = get_settings()
    llm = get_llm(settings)
    skills = await generate_all_skills_md(llm, url, brand, workflows.workflows)

    result = CrawlResponse(
        url=str(url),
        brand=brand,
        workflows=workflows.workflows,
        skills=skills,
    )

    _save_output(url, result)

    return result
