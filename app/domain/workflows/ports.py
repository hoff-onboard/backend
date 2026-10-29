from collections.abc import Awaitable, Callable
from typing import Protocol

from app.domain.research.models import ResearchContext
from app.domain.workflows.models import AgentStep, CrawlResponse, Workflow, WorkflowSpec

StepCallback = Callable[[AgentStep], Awaitable[None]]


class WorkflowRepository(Protocol):
    async def save(
        self,
        result: CrawlResponse,
        screenshots_map: dict[int, list[str]] | None = None,
    ) -> None: ...

    async def get_by_domain(self, domain: str) -> dict | None: ...

    async def soft_delete(self, domain: str, workflow_name: str) -> bool: ...


class WorkflowDiscoverer(Protocol):
    """Finds which workflows a site offers."""

    async def discover(
        self,
        url: str,
        query: str | None,
        *,
        cookies_file: str | None = None,
        credentials: dict[str, str] | None = None,
        on_step: StepCallback | None = None,
    ) -> list[WorkflowSpec]: ...


class WorkflowExtractor(Protocol):
    """Walks one workflow on a site and returns its steps, or None if it found none."""

    async def extract(
        self,
        url: str,
        spec: WorkflowSpec,
        *,
        cookies_file: str | None = None,
        credentials: dict[str, str] | None = None,
        research: ResearchContext | None = None,
        on_step: StepCallback | None = None,
    ) -> Workflow | None: ...


class SelectorReviewer(Protocol):
    """Marks steps whose selector targets user-specific data as dynamic."""

    async def review(self, workflow: Workflow) -> Workflow: ...


class BrowserSessionStore(Protocol):
    """Holds a user's cookies for the duration of a run; `write` returns a handle the agents load."""

    def write(self, cookies: list[dict] | None, origins: list[dict] | None) -> str | None: ...

    def remove(self, handle: str | None) -> None: ...


class ResultArchive(Protocol):
    def write(self, result: CrawlResponse) -> None: ...
