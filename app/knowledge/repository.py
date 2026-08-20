from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import (
    IngestionRun,
    IngestionStatus,
    KnowledgeSource,
    LifecycleStatus,
    SourceType,
    TrustLevel,
    new_id,
)


class KnowledgeSourceRepository:
    """Persistence layer for knowledge sources and ingestion runs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------- Sources ----------------
    async def register_source(
        self,
        name: str,
        location: str,
        source_type: SourceType = SourceType.DOCUMENT,
        trust_level: TrustLevel = TrustLevel.UNTRUSTED,
        lifecycle_status: LifecycleStatus = LifecycleStatus.ACTIVE,
        owner: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> KnowledgeSource:
        source = KnowledgeSource(
            id=new_id(),
            name=name,
            location=location,
            source_type=source_type,
            trust_level=trust_level,
            lifecycle_status=lifecycle_status,
            owner=owner,
            current_version=0,
        )
        if metadata is not None:
            source.extra_metadata = metadata
        self.db.add(source)
        await self.db.commit()
        await self.db.refresh(source)
        return source

    async def get_source(self, source_id: str) -> Optional[KnowledgeSource]:
        stmt = select(KnowledgeSource).where(KnowledgeSource.id == source_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_source_by_location(self, location: str) -> Optional[KnowledgeSource]:
        stmt = select(KnowledgeSource).where(KnowledgeSource.location == location)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sources(
        self,
        source_type: Optional[SourceType] = None,
        trust_level: Optional[TrustLevel] = None,
        lifecycle_status: Optional[LifecycleStatus] = None,
    ) -> List[KnowledgeSource]:
        stmt = select(KnowledgeSource)
        if source_type is not None:
            stmt = stmt.where(KnowledgeSource.source_type == source_type)
        if trust_level is not None:
            stmt = stmt.where(KnowledgeSource.trust_level == trust_level)
        if lifecycle_status is not None:
            stmt = stmt.where(KnowledgeSource.lifecycle_status == lifecycle_status)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def set_lifecycle_status(
        self, source_id: str, status: LifecycleStatus
    ) -> Optional[KnowledgeSource]:
        source = await self.get_source(source_id)
        if source is None:
            return None
        source.lifecycle_status = status
        await self.db.commit()
        return source

    # ---------------- Ingestion runs ----------------
    async def begin_ingestion(self, source_id: str, triggered_by: str = "manual") -> IngestionRun:
        source = await self.get_source(source_id)
        if source is None:
            raise ValueError(f"Unknown knowledge source: {source_id}")
        run = IngestionRun(
            id=new_id(),
            source_id=source.id,
            version=source.current_version + 1,
            status=IngestionStatus.PROCESSING,
            triggered_by=triggered_by,
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def get_run(self, run_id: str) -> Optional[IngestionRun]:
        stmt = select(IngestionRun).where(IngestionRun.id == run_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_runs(self, source_id: str, limit: int = 20) -> List[IngestionRun]:
        stmt = (
            select(IngestionRun)
            .where(IngestionRun.source_id == source_id)
            .order_by(IngestionRun.started_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def complete_ingestion(
        self,
        run_id: str,
        content_hash: str,
        chunks_extracted: int,
        chunks_stored: int,
        status: IngestionStatus = IngestionStatus.SUCCEEDED,
    ) -> Optional[IngestionRun]:
        run = await self.get_run(run_id)
        if run is None:
            return None
        run.status = status
        run.content_hash = content_hash
        run.chunks_extracted = chunks_extracted
        run.chunks_stored = chunks_stored
        run.finished_at = datetime.now(timezone.utc)

        source = await self.get_source(run.source_id)
        if source is not None:
            source.current_version = run.version
            source.content_hash = content_hash
            source.last_ingested_at = run.finished_at
            source.last_error = None
        await self.db.commit()
        return run

    async def fail_ingestion(self, run_id: str, error: str) -> Optional[IngestionRun]:
        run = await self.get_run(run_id)
        if run is None:
            return None
        run.status = IngestionStatus.FAILED
        run.error_message = error
        run.finished_at = datetime.now(timezone.utc)

        source = await self.get_source(run.source_id)
        if source is not None:
            source.last_error = error
        await self.db.commit()
        return run