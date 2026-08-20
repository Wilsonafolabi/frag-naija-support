from fastapi import Request, Depends
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.config import Settings
from app.ai.base import BaseLLMProvider
from app.ai.mock import MockLLMProvider
from app.ai.groq import GroqProvider
from app.services.support import SupportService
from app.services.intent_classifier import IntentClassifier
from app.rag.embeddings import LocalEmbedder
from app.rag.vector_store import QdrantStore
from app.rag.reranker import LocalReranker
from app.db.session import get_db
from app.security.guard import SecurityGuard
from app.repositories.tickets import TicketRepository
from app.observability.langfuse_tracer import get_langfuse_client
from langfuse import Langfuse

logger = structlog.get_logger(__name__)

def get_settings(request: Request) -> Settings:
    return request.app.state.settings

def get_llm_provider(settings: Settings = Depends(get_settings)) -> BaseLLMProvider:
    if settings.llm_provider.lower() == "groq" and settings.groq_api_key:
        return GroqProvider(settings)
    return MockLLMProvider()

def get_embedder(request: Request) -> LocalEmbedder:
    return request.app.state.embedder

def get_qdrant_store(request: Request) -> QdrantStore:
    return request.app.state.qdrant_store

def get_reranker(request: Request):
    return getattr(request.app.state, "reranker", None)

def get_intent_classifier(llm_provider: BaseLLMProvider = Depends(get_llm_provider)) -> IntentClassifier:
    return IntentClassifier(llm_provider)

def get_security_guard(llm_provider: BaseLLMProvider = Depends(get_llm_provider)) -> SecurityGuard:
    return SecurityGuard(llm_provider)

def get_ticket_repo(db: AsyncSession = Depends(get_db)) -> TicketRepository:
    return TicketRepository(db)

def get_langfuse(request: Request) -> Optional[Langfuse]:
    return request.app.state.langfuse_client

def get_support_service(
    settings: Settings = Depends(get_settings),
    llm_provider: BaseLLMProvider = Depends(get_llm_provider),
    embedder: LocalEmbedder = Depends(get_embedder),
    store: QdrantStore = Depends(get_qdrant_store),
    reranker = Depends(get_reranker),
    intent_classifier: IntentClassifier = Depends(get_intent_classifier),
    db: AsyncSession = Depends(get_db),
    ticket_repo: TicketRepository = Depends(get_ticket_repo)
) -> SupportService:
    return SupportService(
        llm_provider=llm_provider, 
        embedder=embedder, 
        store=store, 
        reranker=reranker,
        intent_classifier=intent_classifier,
        db_session=db,
        ticket_repo=ticket_repo,
        max_history_turns=settings.max_history_turns,
        max_history_tokens=settings.max_history_tokens
    )