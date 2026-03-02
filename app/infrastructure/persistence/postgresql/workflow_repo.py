"""PostgreSQL implementation of WorkflowRepository.

TODO: Implement when PostgreSQL support is needed.
Should mirror MongoWorkflowRepository's interface using SQLAlchemy async
or raw asyncpg queries.
"""

from app.domain.workflows.models import CrawlResponse


class PostgresWorkflowRepository:
    """Implements WorkflowRepository using SQLAlchemy async (PostgreSQL)."""

    async def save(
        self,
        result: CrawlResponse,
        screenshots_map: dict[int, list[str]] | None = None,
    ) -> None:
        raise NotImplementedError("PostgreSQL adapter not yet implemented")

    async def get_by_domain(self, domain: str) -> dict | None:
        raise NotImplementedError("PostgreSQL adapter not yet implemented")

    async def soft_delete(self, domain: str, workflow_name: str) -> bool:
        raise NotImplementedError("PostgreSQL adapter not yet implemented")
