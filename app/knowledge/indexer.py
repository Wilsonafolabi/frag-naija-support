"""
Stage 26.3 - Knowledge Indexing.

Connects the ingestion pipeline (PreparedChunk) to the embedding model and the
Qdrant vector store. Indexing is idempotent and hash-aware:

- Unchanged chunks (same chunk_id + same content_hash) are skipped entirely and
  are NEVER re-embedded.
- New chunks are embedded and inserted.
- Changed chunks (same chunk_id, new content_hash) are re-embedded and updated.
- Obsolete chunks (present in the store, absent from the new document) are
  removed.

This module never touches the security guard or the retrieval path.
"""
from dataclasses import dataclass
from typing import Dict, List

from qdrant_client import models as qmodels

from app.knowledge.ingestion import PreparedChunk


@dataclass
class IndexResult:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0

    @property
    def total_written(self) -> int:
        return self.inserted + self.updated


class KnowledgeIndexer:
    def __init__(self, qdrant_client, embedder, collection_name: str):
        self.client = qdrant_client
        self.embedder = embedder
        self.collection = collection_name

    async def index_source(
        self, source_id: str, prepared_chunks: List[PreparedChunk]
    ) -> IndexResult:
        result = IndexResult()

        existing = await self._fetch_existing(source_id)
        new_map = {c.metadata["chunk_id"]: c for c in prepared_chunks}

        # Unchanged = same deterministic chunk_id AND same content hash.
        unchanged_ids = {
            cid
            for cid, chunk in new_map.items()
            if cid in existing and existing[cid] == chunk.metadata["content_hash"]
        }
        result.unchanged = len(unchanged_ids)

        # Only new or changed chunks get written (and embedded).
        to_write = [
            c for c in prepared_chunks if c.metadata["chunk_id"] not in unchanged_ids
        ]
        for chunk in to_write:
            if chunk.metadata["chunk_id"] in existing:
                result.updated += 1
            else:
                result.inserted += 1

        # Obsolete = in the store but gone from the new document.
        obsolete_ids = [cid for cid in existing if cid not in new_map]
        result.deleted = len(obsolete_ids)

        # Embed ONLY new/changed chunks (never unchanged).
        if to_write:
            vectors = await self.embedder.embed_documents([c.text for c in to_write])
            points = [
                qmodels.PointStruct(
                    id=chunk.metadata["chunk_id"],  # deterministic UUID
                    vector=vector,
                    payload={"text": chunk.text, "metadata": chunk.metadata},
                )
                for chunk, vector in zip(to_write, vectors)
            ]
            await self.client.upsert(
                collection_name=self.collection, points=points, wait=True
            )

        if obsolete_ids:
            await self.client.delete(
                collection_name=self.collection,
                points_selector=qmodels.PointIdsList(points=obsolete_ids),
            )

        return result

    async def _fetch_existing(self, source_id: str) -> Dict[str, str]:
        """Return {point_id: content_hash} for all points of this source."""
        existing: Dict[str, str] = {}
        offset = None
        while True:
            points, offset = await self.client.scroll(
                collection_name=self.collection,
                scroll_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="metadata.source_id",
                            match=qmodels.MatchValue(value=source_id),
                        )
                    ]
                ),
                limit=1000,
                with_payload=True,
                offset=offset,
            )
            for p in points:
                meta = (p.payload or {}).get("metadata", {})
                existing[str(p.id)] = meta.get("content_hash")
            if offset is None:
                break
        return existing