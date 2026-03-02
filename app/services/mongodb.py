"""Backward-compatible re-export. Canonical location: app.infrastructure.persistence.mongodb.client"""

from app.infrastructure.persistence.mongodb.client import (
    close_db,
    ensure_indexes,
    get_db,
)

__all__ = ["close_db", "ensure_indexes", "get_db"]
