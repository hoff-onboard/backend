"""FastAPI dependency injection — single place to wire adapters."""

from app.config import Settings, get_settings
from app.domain.workflows.ports import WorkflowRepository
from app.infrastructure.persistence.mongodb.workflow_repo import MongoWorkflowRepository

_workflow_repo: MongoWorkflowRepository | None = None


def get_workflow_repo() -> WorkflowRepository:
    """Return the active WorkflowRepository adapter.

    Swap this to PostgresWorkflowRepository (or an in-memory stub for tests)
    by changing the implementation here — no other code needs to change.
    """
    global _workflow_repo
    if _workflow_repo is None:
        _workflow_repo = MongoWorkflowRepository()
    return _workflow_repo


def get_app_settings() -> Settings:
    return get_settings()
