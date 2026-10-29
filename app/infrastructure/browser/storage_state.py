"""Temp storage-state files that carry a user's cookies into the agents' browsers.

They hold live session cookies, so every run must remove its file when it ends.
"""

import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)


class TempFileSessionStore:
    def write(self, cookies: list[dict] | None, origins: list[dict] | None) -> str | None:
        if not cookies:
            return None
        fd, path = tempfile.mkstemp(prefix="hoff-cookies-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump({"cookies": cookies, "origins": origins or []}, f)
        return path

    def remove(self, handle: str | None) -> None:
        if not handle:
            return
        try:
            os.remove(handle)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("Could not remove storage state file %s", handle)
