#!/usr/bin/env python3
"""Stage 26.4 - Controlled website ingestion for approved Frag Naija pages."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import async_sessionmaker
from qdrant_client import AsyncQdrantClient, models as qmodels

from app.config import get_settings
from app.db.session import engine
from app.knowledge.indexer import KnowledgeIndexer
from app.knowledge.models import IngestionStatus, LifecycleStatus, SourceType, TrustLevel
from app.knowledge.repository import KnowledgeSourceRepository
from app.knowledge.website import CrawlPolicy, HttpxClient, WebsiteCrawler, page_to_chunks
from app.rag.embeddings import LocalEmbedder
import structlog

logger = structlog.get_logger(__name__)


async def main():
    settings = get_settings()
    policy = CrawlPolicy(
        allowed_domains=settings.crawl_allowed_domains_list,
        allowed_paths=settings.crawl_allowed_paths_list,
        max_pages=settings.crawl_max_pages,
        max_response_bytes=settings.crawl_max_response_bytes,
        respect_robots=settings.crawl_respect_robots,
    )
    crawler = WebsiteCrawler(HttpxClient(user_agent=policy.user_agent), policy)
    result = await crawler.crawl(settings.crawl_seed_urls_list)
    logger.info("crawl_complete", pages=len(result.pages),
                failures=len(result.failures), removed=len(result.removed))

    embedder = LocalEmbedder(settings.embedding_model)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url or "http://localhost:6333",
                               api_key=settings.qdrant_api_key)
    cols = await qdrant.get_collections()
    if settings.qdrant_collection not in [c.name for c in cols.collections]:
        await qdrant.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=qmodels.VectorParams(size=embedder.dimension,
                                                distance=qmodels.Distance.COSINE))

    indexer = KnowledgeIndexer(qdrant, embedder, settings.qdrant_collection)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        repo = KnowledgeSourceRepository(db)

        for page in result.pages:
            source = await repo.get_source_by_location(page.canonical_url)
            if not source:
                source = await repo.register_source(
                    name=page.title or page.canonical_url, location=page.canonical_url,
                    source_type=SourceType.WEBSITE, trust_level=TrustLevel.APPROVED,
                    lifecycle_status=LifecycleStatus.ACTIVE)
            run = await repo.begin_ingestion(source.id, triggered_by="website_crawler")
            try:
                chunks = page_to_chunks(source.id, page, source_version=source.current_version + 1)
                res = await indexer.index_source(source.id, chunks)
                await repo.complete_ingestion(run.id, page.content_hash, len(chunks),
                                              res.total_written, IngestionStatus.SUCCEEDED)
            except Exception as e:
                await repo.fail_ingestion(run.id, str(e))

        for url in result.removed:
            source = await repo.get_source_by_location(url)
            if source:
                await indexer.index_source(source.id, [])  # delete all chunks
                await repo.set_lifecycle_status(source.id, LifecycleStatus.DEPRECATED)

    await qdrant.close()


if __name__ == "__main__":
    asyncio.run(main())