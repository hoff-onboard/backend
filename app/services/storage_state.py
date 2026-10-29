"""Temp storage-state files that carry a user's cookies into the browser agents.

They hold live session cookies, so every caller must remove them once the run ends.
"""

import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)


def write_storage_state(cookies: list[dict] | None, origins: list[dict] | None) -> str | None:
    if not cookies:
        return None
    fd, path = tempfile.mkstemp(prefix="hoff-cookies-", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"cookies": cookies, "origins": origins or []}, f)
    return path


def remove_storage_state(path: str | None) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("Could not remove storage state file %s", path)
