import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qmodels
from app.config import Settings
import structlog

logger = structlog.get_logger(__name__)

class QdrantStore:
    def __init__(self, settings: Settings, client: Optional[AsyncQdrantClient] = None):
        self.settings = settings
        # Allow tests to inject an in-memory client
        self.client = client or AsyncQdrantClient(
            url=settings.qdrant_url or "http://localhost:6333",
            api_key=settings.qdrant_api_key,
        )
        self.collection = settings.qdrant_collection

    async def ensure_collection(self, vector_size: int):
        collections = await self.client.get_collections()
        if self.collection not in [c.name for c in collections.collections]:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE)
            )

    async def search(
        self, 
        query_vector: List[float], 
        limit: int = 5, 
        score_threshold: float = 0.0, 
        query_filter: Optional[qmodels.Filter] = None
    ) -> List[Dict[str, Any]]:
        try:
            # Modern Qdrant API with optional filtering
            response = await self.client.query_points(
                collection_name=self.collection,
                query=query_vector,
                limit=limit,
                query_filter=query_filter,
                with_payload=True
            )
            
            hits = response.points
            results = []
            for hit in hits:
                if hit.score < score_threshold:
                    continue
                    
                payload = hit.payload or {}
                if not isinstance(payload, dict):
                    payload = dict(payload)
                    
                # If metadata is nested (Stage 26), use it. 
                # If flattened (legacy tests), fallback to the whole payload.
                metadata = payload.get("metadata", payload)
                if not isinstance(metadata, dict):
                    metadata = {}
                    
                results.append({
                    "text": payload.get("text", ""),
                    "score": hit.score,
                    "metadata": metadata
                })
            return results
        except Exception as e:
            logger.error("qdrant_search_failed", error=str(e))
            return []

    async def upsert(self, points: List[qmodels.PointStruct]):
        try:
            await self.client.upsert(
                collection_name=self.collection,
                points=points,
                wait=True
            )
        except Exception as e:
            logger.error("qdrant_upsert_failed", error=str(e))
            raise

    async def upsert_chunks(self, chunks: List[Any], vectors: List[List[float]]):
        """Helper method used by legacy tests and older ingestion paths."""
        points = []
        for chunk, vector in zip(chunks, vectors):
            # Handle both dicts and Pydantic models / dataclasses safely
            if isinstance(chunk, dict):
                chunk_dict = dict(chunk)
            elif hasattr(chunk, "model_dump"):  # Pydantic V2
                chunk_dict = chunk.model_dump()
            elif hasattr(chunk, "dict"):        # Pydantic V1
                chunk_dict = chunk.dict()
            else:
                chunk_dict = vars(chunk)
                
            # FIX: Flatten nested metadata to the root level for legacy filter compatibility.
            # This ensures FieldCondition(key="status") works correctly in older tests.
            if "metadata" in chunk_dict and isinstance(chunk_dict["metadata"], dict):
                meta = chunk_dict.pop("metadata")
                chunk_dict.update(meta)
                
            # Fallback to a random UUID if the chunk doesn't have an ID
            chunk_id = chunk_dict.get("id") or chunk_dict.get("chunk_id") or str(uuid.uuid4())
            
            points.append(qmodels.PointStruct(
                id=chunk_id,
                vector=vector,
                payload=chunk_dict
            ))
        await self.upsert(points)