import enum
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.chat import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class SourceType(str, enum.Enum):
    DOCUMENT = "document"
    WEBSITE = "website"
    FAQ = "faq"
    ARTICLE = "article"


class TrustLevel(str, enum.Enum):
    OFFICIAL = "official"
    APPROVED = "approved"
    PARTNER = "partner"
    UNTRUSTED = "untrusted"


class LifecycleStatus(str, enum.Enum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class IngestionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class FreshnessStatus(str, enum.Enum):
    """Stage 26.6: Freshness states for knowledge sources."""
    FRESH = "fresh"
    STALE = "stale"
    FAILED = "failed"
    DISABLED = "disabled"


class KnowledgeSource(Base):
    """A single versioned, trusted knowledge source."""
    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, values_callable=lambda e: [m.value for m in e], name="source_type"),
        default=SourceType.DOCUMENT,
    )
    trust_level: Mapped[TrustLevel] = mapped_column(
        SAEnum(TrustLevel, values_callable=lambda e: [m.value for m in e], name="trust_level"),
        default=TrustLevel.UNTRUSTED,
    )
    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(
        SAEnum(LifecycleStatus, values_callable=lambda e: [m.value for m in e], name="lifecycle_status"),
        default=LifecycleStatus.ACTIVE,
    )

    name: Mapped[str] = mapped_column(String(255))
    location: Mapped[str] = mapped_column(String(1024))
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Stage 26.7: Source priority (lower number = higher priority)
    priority: Mapped[int] = mapped_column(Integer, default=5)

    # Versioning + integrity
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Flexible metadata
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Quick visibility of the most recent failure
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    runs: Mapped[list["IngestionRun"]] = relationship(back_populates="source", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_knowledge_sources_type", "source_type"),
        Index("ix_knowledge_sources_trust", "trust_level"),
        Index("ix_knowledge_sources_lifecycle", "lifecycle_status"),
    )

    @property
    def extra_metadata(self) -> Dict[str, Any]:
        return json.loads(self.metadata_json) if self.metadata_json else {}

    @extra_metadata.setter
    def extra_metadata(self, value: Dict[str, Any]) -> None:
        self.metadata_json = json.dumps(value)


class IngestionRun(Base):
    """One ingestion attempt against a source (audit + failure tracking)."""
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_sources.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[IngestionStatus] = mapped_column(
        SAEnum(IngestionStatus, values_callable=lambda e: [m.value for m in e], name="ingestion_status"),
        default=IngestionStatus.PENDING,
    )

    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    chunks_extracted: Mapped[int] = mapped_column(Integer, default=0)
    chunks_stored: Mapped[int] = mapped_column(Integer, default=0)

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(100), default="manual")

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped["KnowledgeSource"] = relationship(back_populates="runs")

    __table_args__ = (Index("ix_ingestion_runs_status", "status"),)