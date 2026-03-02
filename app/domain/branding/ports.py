from typing import Protocol

from app.domain.branding.models import Brand


class BrandExtractor(Protocol):
    async def extract(self, url: str, cookies_file: str | None = None) -> Brand: ...
