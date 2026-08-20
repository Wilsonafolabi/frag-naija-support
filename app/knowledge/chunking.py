"""Paragraph-aware, section-aware text chunking.

Chunk IDs are deterministic: the same (source_id, version, section, index)
always produces the same UUID5. This enables idempotent re-ingestion and
duplicate detection without re-embedding.
"""
import re
import uuid
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Chunk:
    text: str
    section: Optional[str]
    index: int
    chunk_id: str
    content_hash: str


def stable_chunk_id(source_id: str, version: int, section: Optional[str], index: int) -> str:
    key = f"{source_id}|v{version}|{section or '__none__'}|{index}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, key))


def detect_section(first_line: str) -> Optional[str]:
    """Return a section name if the line looks like a heading, else None."""
    line = first_line.strip()
    if not line or len(line) > 200:
        return None
    if line.startswith("#"):
        return line.lstrip("#").strip()
    if line.isupper() and len(line.split()) <= 8:
        return line
    return None


def chunk_text(
    text: str,
    source_id: str,
    source_version: int,
    target_size: int = 800,
    overlap: int = 100,
) -> List[Chunk]:
    """Split text into overlapping paragraph-aware chunks with stable IDs."""
    from app.knowledge.hashing import compute_content_hash

    if not text or not text.strip():
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: List[Chunk] = []
    current_text = ""
    current_section: Optional[str] = None
    chunk_index = 0

    def flush() -> None:
        nonlocal current_text, chunk_index
        if not current_text.strip():
            return
        cid = stable_chunk_id(source_id, source_version, current_section, chunk_index)
        chunks.append(Chunk(
            text=current_text.strip(),
            section=current_section,
            index=chunk_index,
            chunk_id=cid,
            content_hash=compute_content_hash(current_text.strip()),
        ))
        chunk_index += 1

    for para in paragraphs:
        first_line = para.split("\n")[0].strip()
        section = detect_section(first_line)
        if section:
            # Section break -> flush current chunk first
            flush()
            current_text = ""
            current_section = section

        if len(current_text) + len(para) + 2 > target_size and current_text:
            flush()
            # Overlap: carry the tail of the previous chunk forward
            current_text = current_text[-overlap:] if len(current_text) > overlap else ""

        current_text = (current_text + "\n\n" + para).strip()

    flush()
    return chunks