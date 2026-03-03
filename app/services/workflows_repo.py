"""Backward-compatible re-export. Canonical location: app.infrastructure.persistence.mongodb.workflow_repo

These free functions delegate to the MongoWorkflowRepository singleton so that
existing callers (services, routers) continue to work without changes.
"""

from app.api.dependencies import get_workflow_repo
from app.domain.workflows.models import CrawlResponse


async def save_workflows(
    result: CrawlResponse,
    screenshots_map: dict[int, list[str]] | None = None,
) -> None:
    repo = get_workflow_repo()
    await repo.save(result, screenshots_map)


async def get_workflows_by_domain(domain: str) -> dict | None:
    repo = get_workflow_repo()
    return await repo.get_by_domain(domain)


async def soft_delete_workflow(domain: str, workflow_name: str) -> bool:
    repo = get_workflow_repo()
    return await repo.soft_delete(domain, workflow_name)
