#!/usr/bin/env python3
"""Stage 26.5 - Manual Knowledge Synchronization Script."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import async_sessionmaker
from qdrant_client import AsyncQdrantClient, models as qmodels

from app.config import get_settings
from app.db.session import engine
from app.knowledge.indexer import KnowledgeIndexer
from app.knowledge.models import Base
from app.knowledge.repository import KnowledgeSourceRepository
from app.knowledge.sync import KnowledgeSyncService
from app.rag.embeddings import LocalEmbedder
import structlog

logger = structlog.get_logger(__name__)

async def main():
    settings = get_settings()
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    embedder = LocalEmbedder(settings.embedding_model)
    qdrant = AsyncQdrantClient(
        url=settings.qdrant_url or "http://localhost:6333",
        api_key=settings.qdrant_api_key,
    )
    
    cols = await qdrant.get_collections()
    if settings.qdrant_collection not in [c.name for c in cols.collections]:
        await qdrant.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(size=embedder.dimension, distance=qmodels.Distance.COSINE)
        )

    indexer = KnowledgeIndexer(qdrant, embedder, settings.qdrant_collection)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        repo = KnowledgeSourceRepository(db)
        sync_service = KnowledgeSyncService(repo, indexer)
        
        logger.info("starting_manual_sync")
        reports = await sync_service.sync_all()
        
        for r in reports:
            logger.info(
                "sync_report",
                source=r.source_name,
                discovered=r.pages_discovered,
                changed=r.pages_changed,
                unchanged=r.pages_unchanged,
                removed=r.pages_removed,
                chunks_added=r.chunks_added,
                chunks_updated=r.chunks_updated,
                chunks_removed=r.chunks_removed,
                failures=len(r.failures),
            )
            
    await qdrant.close()

if __name__ == "__main__":
    asyncio.run(main())