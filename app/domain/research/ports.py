from typing import Protocol

from app.domain.research.models import ResearchContext


class ResearchProvider(Protocol):
    async def research(
        self,
        url: str,
        query: str,
        cookies_file: str | None = None,
    ) -> ResearchContext: ...
