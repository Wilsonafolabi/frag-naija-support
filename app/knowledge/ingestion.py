"""Document ingestion orchestration.

Loads, cleans, chunks and attaches full metadata to each chunk. This stage
returns PreparedChunk records — pushing embeddings to the vector store is a
separate stage and is intentionally NOT done here.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from app.knowledge.chunking import chunk_text
from app.knowledge.cleaning import clean_text
from app.knowledge.loaders import LoaderRegistry, default_registry
from app.knowledge.models import KnowledgeSource


@dataclass
class PreparedChunk:
    """A chunk ready to be embedded and stored, with full traceability metadata."""
    text: str
    metadata: dict


def prepare_chunks(
    source: KnowledgeSource,
    document_path: Path,
    loader_registry: LoaderRegistry = default_registry,
    target_chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> List[PreparedChunk]:
    """Load -> clean -> chunk -> attach metadata. Does NOT write to the vector store."""
    if not document_path.exists():
        raise FileNotFoundError(f"Document not found: {document_path}")

    raw_text = loader_registry.load(document_path)
    cleaned = clean_text(raw_text)

    chunks = chunk_text(
        cleaned,
        source_id=source.id,
        source_version=source.current_version,
        target_size=target_chunk_size,
        overlap=chunk_overlap,
    )

    now = datetime.now(timezone.utc).isoformat()
    prepared: List[PreparedChunk] = []
    for chunk in chunks:
        prepared.append(PreparedChunk(
            text=chunk.text,
            metadata={
                "source_id": source.id,
                "source_type": source.source_type.value,
                "document_name": source.name,
                "section": chunk.section,
                "source_version": source.current_version,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.index,
                "content_hash": chunk.content_hash,
                "created_at": now,
                "updated_at": now,
                "trust_level": source.trust_level.value,
                "source_location": source.location,
            },
        ))
    return prepared