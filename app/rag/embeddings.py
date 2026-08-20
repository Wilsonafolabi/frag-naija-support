import asyncio
from typing import List

from sentence_transformers import SentenceTransformer
import structlog

logger = structlog.get_logger(__name__)


class LocalEmbedder:
    """
    Generates vector embeddings locally using sentence-transformers.
    Uses the FULL FP32 BAAI/bge-small-en-v1.5 model (no quantization).
    Applies the BGE asymmetric query prefix and L2 normalization.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        logger.info("loading_embedding_model", model=model_name)
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name

        if hasattr(self.model, "get_embedding_dimension"):
            self.dimension = self.model.get_embedding_dimension()
        else:
            self.dimension = self.model.get_sentence_embedding_dimension()

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embeds knowledge-base chunks (no prefix)."""
        return await asyncio.to_thread(self._embed_sync, texts)

    async def embed_query(self, text: str) -> List[float]:
        """Embeds a user query with the BGE instruction prefix."""
        if "bge" in self.model_name.lower():
            text = f"Represent this sentence for searching relevant passages: {text}"

        result = await asyncio.to_thread(self._embed_sync, [text])
        return result[0]

    def _embed_sync(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(
            texts,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        if hasattr(embeddings, "tolist"):
            return embeddings.tolist()
        return [list(vector) for vector in embeddings]