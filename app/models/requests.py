from pydantic import BaseModel, HttpUrl


class CrawlRequest(BaseModel):
    url: HttpUrl
    query: str | None = None
    credentials: dict[str, str] | None = None
    cookies_file: str | None = None
