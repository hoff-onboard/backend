"""Backward-compatible re-export. Canonical location: app.domain.workflows.models"""

from app.domain.workflows.models import (
    CrawlRequest,
    CrawlResponse,
    DiscoveryResponse,
    QueryRequest,
    Step,
    Workflow,
    WorkflowSpec,
    WorkflowsResponse,
)

__all__ = [
    "CrawlRequest",
    "CrawlResponse",
    "DiscoveryResponse",
    "QueryRequest",
    "Step",
    "Workflow",
    "WorkflowSpec",
    "WorkflowsResponse",
]
