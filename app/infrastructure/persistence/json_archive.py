from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from app.domain.workflows.models import CrawlResponse
from app.domain.workflows.ports import ResultArchive


class JsonFileArchive(ResultArchive):
    """Writes each run's result to outputs/<domain>_<timestamp>.json for inspection."""

    def __init__(self, directory: Path = Path("outputs")) -> None:
        self._dir = directory

    def write(self, result: CrawlResponse) -> None:
        self._dir.mkdir(exist_ok=True)
        domain = urlparse(result.url).hostname or "unknown"
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
        (self._dir / f"{domain}_{timestamp}.json").write_text(result.model_dump_json(indent=2))
