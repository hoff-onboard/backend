from typing import Protocol

from app.domain.workflows.models import CrawlResponse


class WorkflowRepository(Protocol):
    async def save(
        self,
        result: CrawlResponse,
        screenshots_map: dict[int, list[str]] | None = None,
    ) -> None: ...

    async def get_by_domain(self, domain: str) -> dict | None: ...

    async def soft_delete(self, domain: str, workflow_name: str) -> bool: ...
