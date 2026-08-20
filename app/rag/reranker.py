import asyncio
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder
import structlog

logger = structlog.get_logger(__name__)


class LocalReranker:
    """
    Cross-encoder reranker for precise semantic ranking.
    Uses BAAI/bge-reranker-base by default.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        logger.info("loading_reranker_model", model=model_name)
        # CrossEncoder automatically handles device placement (CPU/GPU)
        self.model = CrossEncoder(model_name)

    async def rerank(
        self, 
        query: str, 
        documents: List[Dict[str, Any]], 
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        if not documents:
            return []

        # CrossEncoder expects pairs of [query, document_text]
        pairs = [[query, doc["text"]] for doc in documents]

        # Run in thread to avoid blocking the async event loop
        scores = await asyncio.to_thread(self.model.predict, pairs)

        # Attach the new rerank scores to the documents
        for doc, score in zip(documents, scores):
            doc["rerank_score"] = float(score)

        # Sort descending by the new rerank score
        documents.sort(key=lambda x: x["rerank_score"], reverse=True)

        return documents[:top_k]