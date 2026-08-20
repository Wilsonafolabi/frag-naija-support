from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    """Strict metadata schema for knowledge base documents."""
    
    source: str
    title: str
    category: str = "general"
    version: str = "1.0"
    status: Literal["official", "draft", "unknown"] = "unknown"
    
    # Use timezone-aware UTC datetimes to prevent Python 3.12+ deprecation warnings
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> dict:
        """Convert to Qdrant-safe JSON payload."""
        return {
            "source": self.source,
            "title": self.title,
            "category": self.category,
            "version": self.version,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class KnowledgeChunk(BaseModel):
    """Represents a single chunk of text from a knowledge document."""
    
    text: str
    metadata: DocumentMetadata
    chunk_index: int