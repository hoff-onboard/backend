"""Composition root: the only place that picks concrete adapters for the ports.

Tests override these with FastAPI's dependency_overrides.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.application.pipeline import Pipeline
from app.config import get_settings
from app.domain.workflows.ports import WorkflowRepository
from app.infrastructure.browser.agents import BrowserUseDiscoverer, BrowserUseExtractor
from app.infrastructure.browser.brand_extractor import PlaywrightBrandExtractor
from app.infrastructure.browser.storage_state import TempFileSessionStore
from app.infrastructure.llm.research import LLMResearchProvider
from app.infrastructure.llm.selector_review import LLMSelectorReviewer
from app.infrastructure.persistence.json_archive import JsonFileArchive
from app.infrastructure.persistence.mongodb.workflow_repo import MongoWorkflowRepository


@lru_cache
def get_workflow_repo() -> WorkflowRepository:
    return MongoWorkflowRepository()


@lru_cache
def get_pipeline() -> Pipeline:
    settings = get_settings()
    return Pipeline(
        research=LLMResearchProvider(settings),
        branding=PlaywrightBrandExtractor(),
        discoverer=BrowserUseDiscoverer(settings),
        extractor=BrowserUseExtractor(settings),
        reviewer=LLMSelectorReviewer(settings),
        repository=get_workflow_repo(),
        sessions=TempFileSessionStore(),
        archive=JsonFileArchive(),
    )


PipelineDep = Annotated[Pipeline, Depends(get_pipeline)]
RepositoryDep = Annotated[WorkflowRepository, Depends(get_workflow_repo)]
