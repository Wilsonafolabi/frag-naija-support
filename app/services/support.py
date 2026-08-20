import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import BaseLLMProvider
from app.ai.prompts import build_support_prompt
from app.ai.intents import IntentType, IntentClassification
from app.config import get_settings
from app.knowledge.security import validate_retrieved_chunks
from app.rag.embeddings import LocalEmbedder
from app.rag.vector_store import QdrantStore
from app.rag.reranker import LocalReranker
from app.rag.sanitizer import sanitize_content
from app.services.intent_classifier import IntentClassifier
from app.repositories.chat_history import ChatHistoryRepository
from app.repositories.tickets import TicketRepository
import structlog

logger = structlog.get_logger(__name__)

class SupportResult(BaseModel):
    response: str
    sources: List[Dict[str, Any]]
    intent: Optional[IntentClassification]
    session_id: str
    ticket_id: Optional[str] = None

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def truncate_history_by_tokens(messages: List[dict], max_tokens: int) -> List[dict]:
    total_tokens = 0
    kept_messages = []
    for msg in reversed(messages):
        msg_tokens = estimate_tokens(msg["content"])
        if total_tokens + msg_tokens > max_tokens:
            break
        total_tokens += msg_tokens
        kept_messages.insert(0, msg)
    return kept_messages

class SupportService:
    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        embedder: LocalEmbedder,
        store: QdrantStore,
        reranker: Optional[LocalReranker] = None,
        intent_classifier: Optional[IntentClassifier] = None,
        db_session: Optional[AsyncSession] = None,
        ticket_repo: Optional[TicketRepository] = None,
        max_history_turns: int = 10,
        max_history_tokens: int = 2000,
    ):
        self.llm_provider = llm_provider
        self.embedder = embedder
        self.store = store
        self.reranker = reranker
        self.intent_classifier = intent_classifier
        self.db_session = db_session
        self.history_repo = ChatHistoryRepository(db_session) if db_session else None
        self.ticket_repo = ticket_repo
        self.max_history_turns = max_history_turns
        self.max_history_tokens = max_history_tokens
        self.settings = get_settings()

    async def get_response(
        self, 
        user_message: str, 
        session_id: Optional[str] = None, 
        user_id: Optional[str] = None,
        trace = None
    ) -> SupportResult:
        
        intent_result = None
        final_docs = []
        current_session_id = session_id
        escalation_reason = None

        # 1. Load & Manage History
        history_messages = []
        if self.history_repo:
            session = await self.history_repo.get_or_create_session(session_id, user_id)
            current_session_id = session.id
            
            db_history = await self.history_repo.get_history(current_session_id, self.max_history_turns)
            history_messages = [{"role": m.role, "content": m.content} for m in db_history]
            history_messages = truncate_history_by_tokens(history_messages, self.max_history_tokens)

        async def save_and_return(response_text: str, intent: Optional[IntentClassification] = None, reason: Optional[str] = None) -> SupportResult:
            if self.history_repo and current_session_id:
                await self.history_repo.add_message(current_session_id, "user", user_message)
                await self.history_repo.add_message(current_session_id, "assistant", response_text)
            
            ticket_id = None
            if reason and self.ticket_repo:
                category = intent.intent.value if intent else "unknown"
                ticket_id = await self.ticket_repo.create_ticket(
                    session_id=current_session_id, user_id=user_id, category=category, 
                    summary=user_message[:500], reason=reason
                )
                
            return SupportResult(
                response=response_text, sources=[], intent=intent, 
                session_id=current_session_id or str(uuid.uuid4()), ticket_id=ticket_id
            )

        # 2. Intent Classification & Routing
        if self.intent_classifier:
            span_intent = trace.span(name="intent-classification", input=user_message) if trace else None
            intent_result = await self.intent_classifier.classify(user_message)
            if span_intent:
                span_intent.end(output=intent_result.intent.value)
            
            logger.info("intent_classified", intent=intent_result.intent, confidence=intent_result.confidence)
            
            if intent_result.intent == IntentType.AMBIGUOUS or intent_result.confidence < 0.7:
                reason = "Low confidence in intent classification" if intent_result.confidence < 0.7 else "Ambiguous intent"
                return await save_and_return("I'm not quite sure I understand. Could you please clarify your question?", intent_result, reason)
                
            if intent_result.intent == IntentType.FINANCIAL_ACTION:
                return await save_and_return("I cannot process financial transactions, refunds, or wagers. Please contact our human support team at support@fragnaija.com to resolve this.", intent_result, "Sensitive financial action requested")
                
            if intent_result.intent == IntentType.ACCOUNT_ISSUE:
                return await save_and_return("This requires assistance from our human support team. Please contact support@fragnaija.com regarding your account issue.", intent_result, "Account access required")
                
            if intent_result.intent == IntentType.HUMAN_REQUEST:
                return await save_and_return("I am connecting you with our human support team. Please email support@fragnaija.com or wait for an agent to review your ticket.", intent_result, "User explicitly requested human support")

            if intent_result.intent == IntentType.TECHNICAL_SUPPORT:
                return await save_and_return("I'm sorry you're experiencing technical issues. Our human support team has been notified. Please contact support@fragnaija.com for immediate assistance.", intent_result, "Technical issue requires human review")
                
            if intent_result.intent == IntentType.CHITCHAT:
                return await save_and_return("Hello! How can I help you with Frag Naija tournaments and rules today?", intent_result)

        # 3. RAG Pipeline
        try:
            span_rag = trace.span(name="rag-retrieval") if trace else None
            
            query_vector = await self.embedder.embed_query(user_message)
            fetch_limit = 10 if self.reranker else 5
            
            candidate_docs = await self.store.search(query_vector, limit=fetch_limit, score_threshold=0.0)
            
            if span_rag:
                span_rag.end(output=f"Retrieved {len(candidate_docs)} candidates")

            if candidate_docs:
                for doc in candidate_docs:
                    doc["text"] = sanitize_content(doc["text"])

                # Stage 26.8: Validate for adversarial content
                candidate_docs = validate_retrieved_chunks(candidate_docs)

                if self.reranker and len(candidate_docs) > 1:
                    logger.info("reranking_candidates", count=len(candidate_docs))
                    final_docs = await self.reranker.rerank(user_message, candidate_docs, top_k=5)
                else:
                    final_docs = candidate_docs[:5]

                # Stage 26.7: Sort by configured source priority
                priority_map = self.settings.priority_dict
                final_docs.sort(
                    key=lambda d: priority_map.get(
                        d.get("metadata", {}).get("source_type", "document"), 
                        5
                    )
                )
                
                # FIX: Remove duplicate chunks before sending to LLM
                seen_texts = set()
                unique_docs = []
                for doc in final_docs:
                    text = doc.get("text", "")
                    if text not in seen_texts:
                        seen_texts.add(text)
                        unique_docs.append(doc)
                final_docs = unique_docs
                
            else:
                escalation_reason = "Knowledge base insufficient (no context found)"

        except Exception as e:
            logger.warning("rag_pipeline_failed", error=str(e))
            if trace: trace.update(metadata={"rag_error": str(e)})

        # 4. Build Prompt & Generate
        messages = build_support_prompt(user_message, final_docs, history_messages)
        
        span_llm = trace.span(name="llm-generation", input="System Prompt + Context") if trace else None
        response = await self.llm_provider.generate(messages)
        
        if span_llm:
            span_llm.end(
                output=response.content[:200] + "...", 
                model=response.model,
                usage={
                    "input": response.usage.get("prompt_tokens"),
                    "output": response.usage.get("completion_tokens"),
                    "total": response.usage.get("total_tokens")
                }
            )
        
        if "I do not have that information in my current knowledge base" in response.content:
            escalation_reason = escalation_reason or "Knowledge base insufficient (fallback triggered)"

        # 5. Save to DB
        if self.history_repo and current_session_id:
            await self.history_repo.add_message(current_session_id, "user", user_message)
            await self.history_repo.add_message(current_session_id, "assistant", response.content)

        # 6. Create Ticket if Escalated
        ticket_id = None
        if escalation_reason and self.ticket_repo:
            category = intent_result.intent.value if intent_result else "unknown"
            ticket_id = await self.ticket_repo.create_ticket(
                session_id=current_session_id, user_id=user_id, category=category, 
                summary=user_message[:500], reason=escalation_reason
            )
            if trace: trace.update(metadata={"escalation_reason": escalation_reason, "ticket_id": ticket_id})

        # 7. Extract Sources (Robust metadata mapping)
        sources = []
        for doc in final_docs:
            meta = doc.get("metadata", {})
            if not isinstance(meta, dict):
                meta = {}
                
            sources.append({
                "title": meta.get("title") or meta.get("document_name", "Unknown"),
                "source": meta.get("source") or meta.get("source_location", "Unknown"),
                "status": meta.get("status") or meta.get("trust_level", "unknown"),
                "score": doc.get("rerank_score", doc.get("score"))
            })
            
        return SupportResult(
            response=response.content, sources=sources, intent=intent_result, 
            session_id=current_session_id or str(uuid.uuid4()), ticket_id=ticket_id
        )

    def get_provider_name(self) -> str:
        return self.llm_provider.get_provider_name()