"""In-memory fakes for every port, so use cases run without browsers, LLMs or a database."""

import asyncio

import pytest

from app.application.pipeline import Pipeline
from app.domain.branding.models import Brand
from app.domain.research.models import ResearchContext
from app.domain.workflows.models import (
    AgentStep,
    CrawlResponse,
    Step,
    Workflow,
    WorkflowSpec,
)

BRAND = Brand(primary="#1F7A33", background="#FFFFFF", text="#111111", fontFamily="Inter", borderRadius="6px")


def make_workflow(name: str = "Create a repo") -> Workflow:
    return Workflow(
        name=name,
        description="",
        steps=[Step(element="a[href='/new']", title="New", description="Click New")],
    )


class FakeResearch:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def research(self, url, query, cookies_file=None):
        if self.error:
            raise self.error
        return ResearchContext(description=f"How to {query}", steps=["Open menu"])


class FakeBranding:
    def __init__(self, hang: bool = False) -> None:
        self.hang = hang
        self.cancelled = False

    async def extract(self, url, cookies_file=None):
        if self.hang:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return BRAND


class FakeExtractor:
    """Reports `steps` agent steps, then returns `result`; `hang` blocks until cancelled."""

    def __init__(self, result: Workflow | None = None, steps: int = 2, hang: bool = False) -> None:
        self.result = result if result is not None else make_workflow()
        self.steps = steps
        self.hang = hang
        self.cancelled = False
        self.calls: list[dict] = []

    async def extract(self, url, spec, *, cookies_file=None, credentials=None, research=None, on_step=None):
        self.calls.append({"spec": spec, "cookies_file": cookies_file, "research": research})
        for i in range(1, self.steps + 1):
            if on_step:
                await on_step(AgentStep(step=i, thought=f"thought {i}", screenshot_b64=f"img{i}"))
        if self.hang:
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        return self.result


class FakeDiscoverer:
    def __init__(self, specs: list[WorkflowSpec]) -> None:
        self.specs = specs

    async def discover(self, url, query, *, cookies_file=None, credentials=None, on_step=None):
        return self.specs


class FakeReviewer:
    async def review(self, workflow):
        return workflow.model_copy(update={"description": "reviewed"})


class InMemoryRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[CrawlResponse, dict | None]] = []
        self.docs: dict[str, dict] = {}

    async def save(self, result, screenshots_map=None):
        self.saved.append((result, screenshots_map))

    async def get_by_domain(self, domain):
        return self.docs.get(domain)

    async def soft_delete(self, domain, workflow_name):
        doc = self.docs.get(domain)
        return bool(doc and any(w["name"] == workflow_name for w in doc["workflows"]))


class FakeSessions:
    def __init__(self) -> None:
        self.live: set[str] = set()
        self.written = 0

    def write(self, cookies, origins):
        if not cookies:
            return None
        self.written += 1
        handle = f"session-{self.written}"
        self.live.add(handle)
        return handle

    def remove(self, handle):
        self.live.discard(handle)


class FakeArchive:
    def __init__(self) -> None:
        self.results: list[CrawlResponse] = []

    def write(self, result):
        self.results.append(result)


@pytest.fixture
def make_pipeline():
    def build(**overrides) -> Pipeline:
        parts = {
            "research": FakeResearch(),
            "branding": FakeBranding(),
            "discoverer": FakeDiscoverer([WorkflowSpec(name="Create a repo", description="")]),
            "extractor": FakeExtractor(),
            "reviewer": FakeReviewer(),
            "repository": InMemoryRepository(),
            "sessions": FakeSessions(),
            "archive": FakeArchive(),
        }
        parts.update(overrides)
        return Pipeline(**parts)

    return build
