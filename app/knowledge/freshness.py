"""
Stage 26.6 - Knowledge Freshness Evaluation.

Evaluates the freshness status of a knowledge source based on its
lifecycle state, last error, and last successful ingestion timestamp.
"""
from datetime import datetime, timedelta, timezone

from app.knowledge.models import FreshnessStatus, KnowledgeSource


def evaluate_freshness(source: KnowledgeSource, stale_days: int = 30) -> FreshnessStatus:
    """
    Determine the freshness status of a knowledge source.
    
    Rules:
    - ARCHIVED sources are DISABLED.
    - Sources with a last_error are FAILED.
    - Sources ingested more than stale_days ago are STALE.
    - Sources never ingested are STALE.
    - Otherwise, FRESH.
    """
    if source.lifecycle_status.value == "archived":
        return FreshnessStatus.DISABLED
    if source.last_error:
        return FreshnessStatus.FAILED
    if source.last_ingested_at:
        age = datetime.now(timezone.utc) - source.last_ingested_at
        if age > timedelta(days=stale_days):
            return FreshnessStatus.STALE
        return FreshnessStatus.FRESH
    return FreshnessStatus.STALE