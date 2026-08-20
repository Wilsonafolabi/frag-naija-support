"""
Stage 26.5 - Knowledge Synchronization.

Provides a non-blocking, incremental synchronization mechanism for both documents
and approved websites. It compares content hashes to avoid unnecessary reprocessing,
identifies new/changed/removed content, and delegates vector updates to the
KnowledgeIndexer (which safely upserts/deletes without wiping the entire database).
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.knowledge.hashing import compute_content_hash
from app.knowledge.indexer import KnowledgeIndexer
from app.knowledge.ingestion import prepare_chunks
from app.knowledge.loaders import LoaderRegistry, default_registry
from app.knowledge.models import (
    IngestionStatus,
    KnowledgeSource,
    LifecycleStatus,
    SourceType,
)
from app.knowledge.repository import KnowledgeSourceRepository
from app.knowledge.website import CrawlPolicy, HttpClient, HttpxClient, WebsiteCrawler, page_to_chunks
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SyncReport:
    source_id: str
    source_name: str
    source_type: str
    pages_discovered: int = 0
    pages_changed: int = 0
    pages_unchanged: int = 0
    pages_removed: int = 0
    chunks_added: int = 0
    chunks_updated: int = 0
    chunks_removed: int = 0
    failures: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class KnowledgeSyncService:
    """Orchestrates incremental synchronization for all active knowledge sources."""

    def __init__(
        self,
        repo: KnowledgeSourceRepository,
        indexer: KnowledgeIndexer,
        loader_registry: LoaderRegistry = default_registry,
        http_client: Optional[HttpClient] = None,
    ):
        self.repo = repo
        self.indexer = indexer
        self.loader_registry = loader_registry
        self.http_client = http_client or HttpxClient()

    async def sync_all(self) -> List[SyncReport]:
        """Synchronizes all ACTIVE sources. Safe to run as a background task."""
        sources = await self.repo.list_sources(lifecycle_status=LifecycleStatus.ACTIVE)
        reports = []
        
        for source in sources:
            try:
                if source.source_type == SourceType.DOCUMENT:
                    report = await self._sync_document(source)
                elif source.source_type == SourceType.WEBSITE:
                    report = await self._sync_website(source)
                else:
                    continue # Skip FAQ/ARTICLE for now as per Stage 26.4 scope
                reports.append(report)
            except Exception as e:
                logger.error("sync_failed", source_id=source.id, error=str(e))
                reports.append(SyncReport(
                    source_id=source.id, source_name=source.name, 
                    source_type=source.source_type.value, failures=[str(e)]
                ))
                
        return reports

    async def _sync_document(self, source: KnowledgeSource) -> SyncReport:
        report = SyncReport(
            source_id=source.id, source_name=source.name, source_type=source.source_type.value
        )
        
        path = Path(source.location)
        if not path.exists():
            report.failures.append(f"File not found: {source.location}")
            return report

        try:
            text = self.loader_registry.load(path)
        except Exception as e:
            report.failures.append(f"Load failed: {e}")
            return report

        new_hash = compute_content_hash(text)
        report.pages_discovered = 1

        if new_hash == source.content_hash:
            report.pages_unchanged = 1
            return report

        # Content changed -> reprocess
        report.pages_changed = 1
        run = await self.repo.begin_ingestion(source.id, triggered_by="sync_service")
        
        try:
            chunks = prepare_chunks(source, path, self.loader_registry)
            index_result = await self.indexer.index_source(source.id, chunks)
            
            report.chunks_added = index_result.inserted
            report.chunks_updated = index_result.updated
            report.chunks_removed = index_result.deleted
            
            await self.repo.complete_ingestion(
                run.id, new_hash, len(chunks), index_result.total_written, IngestionStatus.SUCCEEDED
            )
        except Exception as e:
            report.failures.append(f"Index failed: {e}")
            await self.repo.fail_ingestion(run.id, str(e))
            
        return report

    async def _sync_website(self, source: KnowledgeSource) -> SyncReport:
        report = SyncReport(
            source_id=source.id, source_name=source.name, source_type=source.source_type.value
        )
        
        # Extract policy from source metadata or use defaults
        meta = source.extra_metadata
        policy = CrawlPolicy(
            allowed_domains=meta.get("allowed_domains", [source.location.split("/")[2]]),
            allowed_paths=meta.get("allowed_paths", []),
            max_pages=meta.get("max_pages", 10),
            respect_robots=meta.get("respect_robots", True),
        )
        
        crawler = WebsiteCrawler(self.http_client, policy)
        prev_page_hashes: Dict[str, str] = meta.get("page_hashes", {})
        
        try:
            # Crawl the seed URL
            result = await crawler.crawl([source.location], known_urls=set(prev_page_hashes.keys()))
        except Exception as e:
            report.failures.append(f"Crawl failed: {e}")
            return report

        report.pages_discovered = len(result.pages)
        report.pages_removed = len(result.removed)
        report.failures.extend([f.error for f in result.failures])
        
        new_page_hashes = {}
        all_chunks = []
        
        for page in result.pages:
            new_page_hashes[page.url] = page.content_hash
            if prev_page_hashes.get(page.url) == page.content_hash:
                report.pages_unchanged += 1
            else:
                report.pages_changed += 1
                # Generate chunks for new/changed pages
                chunks = page_to_chunks(source.id, page, source_version=source.current_version + 1)
                all_chunks.extend(chunks)
                
        # Index all new/changed chunks (Indexer handles deleting obsolete chunks for this source)
        if all_chunks or result.removed:
            run = await self.repo.begin_ingestion(source.id, triggered_by="sync_service")
            try:
                index_result = await self.indexer.index_source(source.id, all_chunks)
                report.chunks_added = index_result.inserted
                report.chunks_updated = index_result.updated
                report.chunks_removed = index_result.deleted
                
                # Update source metadata with new page hashes
                meta["page_hashes"] = new_page_hashes
                source.extra_metadata = meta
                
                await self.repo.complete_ingestion(
                    run.id, compute_content_hash(str(new_page_hashes)), 
                    len(all_chunks), index_result.total_written, IngestionStatus.SUCCEEDED
                )
            except Exception as e:
                report.failures.append(f"Index failed: {e}")
                await self.repo.fail_ingestion(run.id, str(e))

        # Deactivate removed pages if they were tracked as separate sources (optional based on architecture)
        # Here we just record them in the report as they are removed from the vector store by the indexer.
        
        return report