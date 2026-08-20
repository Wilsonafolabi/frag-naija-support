import json
from pathlib import Path
from datetime import datetime
from typing import List, Tuple
from pypdf import PdfReader
import structlog

from app.rag.models import DocumentMetadata, KnowledgeChunk

logger = structlog.get_logger(__name__)


def extract_text(file_path: Path) -> str:
    """Extracts text from .md, .txt, or .pdf files."""
    if file_path.suffix.lower() == ".pdf":
        reader = PdfReader(file_path)
        return "\n".join([page.extract_text() or "" for page in reader.pages])
    else:
        return file_path.read_text(encoding="utf-8")


def load_metadata(file_path: Path) -> DocumentMetadata:
    """Loads metadata from a sidecar JSON file if it exists, otherwise uses defaults."""
    json_path = file_path.with_suffix(".json")
    
    defaults = {
        "source": file_path.name,
        "title": file_path.stem.replace("_", " ").title(),
        "category": "general",
        "version": "1.0",
        "status": "unknown",
    }
    
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception as e:
            logger.error("failed_to_parse_metadata", file=json_path.name, error=str(e))

    return DocumentMetadata(
        source=defaults["source"],
        title=defaults["title"],
        category=defaults["category"],
        version=defaults["version"],
        status=defaults["status"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """Splits text into overlapping chunks."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


async def process_documents(
    kb_path: Path, chunk_size: int = 500
) -> Tuple[List[KnowledgeChunk], List[str]]:
    """Reads files, extracts metadata, and chunks the text."""
    all_chunks: List[KnowledgeChunk] = []
    all_texts: List[str] = []
    
    supported_extensions = {".md", ".txt", ".pdf"}
    
    for file_path in kb_path.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
            logger.info("processing_file", file=file_path.name)
            
            text = extract_text(file_path)
            metadata = load_metadata(file_path)
            text_chunks = chunk_text(text, chunk_size)
            
            for i, chunk in enumerate(text_chunks):
                all_chunks.append(
                    KnowledgeChunk(text=chunk, metadata=metadata, chunk_index=i)
                )
                all_texts.append(chunk)
                
    return all_chunks, all_texts