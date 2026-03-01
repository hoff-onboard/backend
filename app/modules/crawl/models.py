import re
from typing import Literal

from pydantic import BaseModel, HttpUrl, field_validator

from app.modules.branding.models import Brand

# Patterns that must never appear in a CSS selector value
_PLAYWRIGHT_PSEUDO_RE = re.compile(r":has-text\(|:text\(|>>|:visible", re.IGNORECASE)
_POSITIONAL_RE = re.compile(
    r":nth-child\(|:nth-of-type\(|:first-child|:last-child", re.IGNORECASE
)
_DYNAMIC_ID_RE = re.compile(
    r"\[id=['\"]?[:_]?[A-Za-z0-9_]*[:_][A-Za-z0-9_]{3,}['\"]?\]"
)
_REACT_ID_RE = re.compile(r"\[id=['\"]?:r\d+:['\"]?\]")
_HASH_CLASS_RE = re.compile(
    r"\.[a-zA-Z][\w]*-[a-zA-Z][\w]*-(?=[a-zA-Z0-9]*[0-9])(?=[a-zA-Z0-9]*[a-zA-Z])[a-zA-Z0-9]{4,}"
)


class Step(BaseModel):
    element: str
    text: str | None = None
    title: str
    description: str
    side: Literal["top", "bottom", "left", "right"] = "bottom"
    navigates: bool = True
    dynamic: bool = False

    @field_validator("element")
    @classmethod
    def reject_bad_selectors(cls, v: str) -> str:
        if _PLAYWRIGHT_PSEUDO_RE.search(v):
            raise ValueError(
                f"Selector contains Playwright pseudo-selector: {v!r}"
            )
        if _POSITIONAL_RE.search(v):
            raise ValueError(
                f"Selector contains positional pseudo-class: {v!r}"
            )
        if _DYNAMIC_ID_RE.search(v):
            raise ValueError(
                f"Selector contains dynamic/random ID: {v!r}"
            )
        if _REACT_ID_RE.search(v):
            raise ValueError(
                f"Selector contains React-style dynamic ID: {v!r}"
            )
        if _HASH_CLASS_RE.search(v):
            raise ValueError(
                f"Selector contains hash/random class name: {v!r}"
            )
        return v


class Workflow(BaseModel):
    name: str
    description: str
    steps: list[Step]


class WorkflowsResponse(BaseModel):
    workflows: list[Workflow]


class WorkflowSpec(BaseModel):
    name: str
    description: str


class DiscoveryResponse(BaseModel):
    workflows: list[WorkflowSpec]


class CrawlRequest(BaseModel):
    url: HttpUrl
    query: str | None = None
    credentials: dict[str, str] | None = None
    cookies_file: str | None = None


class QueryRequest(BaseModel):
    url: HttpUrl
    query: str
    cookies: list[dict] | None = None
    origins: list[dict] | None = None
    use_research: bool = False


class CrawlResponse(BaseModel):
    url: str
    brand: Brand
    workflows: list[Workflow]
