#!/usr/bin/env python3
"""Stage 26.3 - Knowledge Ingestion Orchestrator (idempotent)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import async_sessionmaker
from qdrant_client import AsyncQdrantClient, models as qmodels

from app.db.session import engine
from app.config import get_settings
from app.knowledge.repository import KnowledgeSourceRepository
from app.knowledge.ingestion import prepare_chunks
from app.knowledge.indexer import KnowledgeIndexer
from app.knowledge.models import (
    SourceType, TrustLevel, LifecycleStatus, IngestionStatus,
)
from app.rag.embeddings import LocalEmbedder
import structlog

# Import Base and all models so SQLAlchemy knows about them for table creation
from app.models.chat import Base
import app.models.ticket
import app.knowledge.models

logger = structlog.get_logger(__name__)


async def ingest_file(file_path: Path):
    settings = get_settings()
    
    # 1. Ensure database tables exist (idempotent)
    logger.info("checking_database_tables")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Initialize Embedder and Qdrant
    embedder = LocalEmbedder(settings.embedding_model)

    qdrant_client = AsyncQdrantClient(
        url=settings.qdrant_url or "http://localhost:6333",
        api_key=settings.qdrant_api_key,
    )

    collections = await qdrant_client.get_collections()
    if settings.qdrant_collection not in [c.name for c in collections.collections]:
        await qdrant_client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(
                size=embedder.dimension, distance=qmodels.Distance.COSINE
            ),
        )

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as db:
        repo = KnowledgeSourceRepository(db)

        source = await repo.get_source_by_location(str(file_path))
        if not source:
            logger.info("registering_new_source", file=file_path.name)
            source = await repo.register_source(
                name="Frag Naija Investor Pitch Deck 2026",
                location=str(file_path),
                source_type=SourceType.DOCUMENT,
                trust_level=TrustLevel.OFFICIAL,
                lifecycle_status=LifecycleStatus.ACTIVE,
            )

        run = await repo.begin_ingestion(source.id, triggered_by="cli_ingest_script")
        logger.info("ingestion_started", run_id=run.id, version=run.version)

        try:
            chunks = prepare_chunks(source, file_path)
            logger.info("chunks_prepared", count=len(chunks))

            indexer = KnowledgeIndexer(qdrant_client, embedder, settings.qdrant_collection)
            index_result = await indexer.index_source(source.id, chunks)
            logger.info(
                "index_result",
                inserted=index_result.inserted,
                updated=index_result.updated,
                deleted=index_result.deleted,
                unchanged=index_result.unchanged,
            )

            await repo.complete_ingestion(
                run_id=run.id,
                content_hash=chunks[0].metadata["content_hash"] if chunks else "",
                chunks_extracted=len(chunks),
                chunks_stored=index_result.total_written,
                status=IngestionStatus.SUCCEEDED,
            )
            logger.info("ingestion_complete", source=source.name)

        except Exception as e:
            logger.error("ingestion_failed", error=str(e))
            await repo.fail_ingestion(run.id, str(e))
            raise
        finally:
            await qdrant_client.close()


if __name__ == "__main__":
    path = Path("data/knowledge/fragnaija_pitch_deck.md")
    if not path.exists():
        print(f"Error: {path} not found. Please create it first.")
        sys.exit(1)
    asyncio.run(ingest_file(path))