"""The ports a use case needs, bundled so the API layer can inject one object."""

import asyncio
from dataclasses import dataclass

from app.domain.branding.ports import BrandExtractor
from app.domain.research.ports import ResearchProvider
from app.domain.workflows.ports import (
    BrowserSessionStore,
    ResultArchive,
    SelectorReviewer,
    WorkflowDiscoverer,
    WorkflowExtractor,
    WorkflowRepository,
)


@dataclass(frozen=True)
class Pipeline:
    research: ResearchProvider
    branding: BrandExtractor
    discoverer: WorkflowDiscoverer
    extractor: WorkflowExtractor
    reviewer: SelectorReviewer
    repository: WorkflowRepository
    sessions: BrowserSessionStore
    archive: ResultArchive


async def cancel_pending(*tasks: asyncio.Task | None) -> None:
    """Cancel tasks still running and wait for them, so their browsers shut down."""
    live = [t for t in tasks if t is not None]
    for task in live:
        if not task.done():
            task.cancel()
    await asyncio.gather(*live, return_exceptions=True)
