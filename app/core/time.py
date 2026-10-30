"""Timezone-aware timestamps shared by persisted entities."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
