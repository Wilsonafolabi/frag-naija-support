from typing import List, Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
import structlog

from app.services.support import SupportService
from app.api.deps import get_support_service, get_security_guard, get_ticket_repo, get_langfuse
from app.security.validator import SecureChatRequest
from app.security.rate_limit import limiter
from app.security.guard import SecurityGuard
from app.ai.prompts import SYSTEM_PROMPT
from app.repositories.tickets import TicketRepository
from langfuse import Langfuse

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

class SourceMetadata(BaseModel):
    title: str
    source: str
    status: str
    score: Optional[float] = None

class ChatResponse(BaseModel):
    response: str
    provider: str
    session_id: str
    sources: List[SourceMetadata] = []
    intent: Optional[str] = None
    confidence: Optional[float] = None
    requires_human: Optional[bool] = None
    ticket_id: Optional[str] = None

@router.post("/", response_model=ChatResponse)
@limiter.limit("100/minute")
async def chat(
    request: Request,
    chat_req: SecureChatRequest,
    support_service: SupportService = Depends(get_support_service),
    guard: SecurityGuard = Depends(get_security_guard),
    ticket_repo: TicketRepository = Depends(get_ticket_repo),
    langfuse_client: Optional[Langfuse] = Depends(get_langfuse),
) -> ChatResponse:
    
    trace = None
    if langfuse_client:
        trace = langfuse_client.trace(name="chat-request", session_id=chat_req.session_id, input=chat_req.message)
    
    # 1. Pre-flight Security Guard
    is_threat, reason = await guard.check_input(chat_req.message, trace=trace)
    if is_threat:
        logger.warning("security_event", event_type="request_blocked", reason=reason)
        
        if trace:
            trace.update(output="Blocked by Security Guard", metadata={"reason": reason})
            trace.score(name="security", value=0)
            langfuse_client.flush()  # <-- FORCE SEND
        
        ticket_id = await ticket_repo.create_ticket(
            session_id=chat_req.session_id, user_id=chat_req.user_id, category="security",
            summary=chat_req.message[:500], reason=f"Security threat detected: {reason}"
        )
        
        return ChatResponse(
            response="I cannot process this request.",
            provider=support_service.get_provider_name(),
            session_id=chat_req.session_id or "blocked",
            sources=[],
            intent="security_block",
            confidence=1.0,
            requires_human=True,
            ticket_id=ticket_id
        )

    # 2. Main Support Pipeline
    result = await support_service.get_response(
        chat_req.message, chat_req.session_id, chat_req.user_id, trace=trace
    )
    
    # 3. Post-flight Output Validation
    clean_response = guard.validate_output(result.response, SYSTEM_PROMPT)

    if trace:
        trace.update(output=clean_response)
        langfuse_client.flush()  # <-- FORCE SEND so it appears in the dashboard instantly

    response_data = {
        "response": clean_response,
        "provider": support_service.get_provider_name(),
        "session_id": result.session_id,
        "sources": [SourceMetadata(**s) for s in result.sources],
        "ticket_id": result.ticket_id
    }
    
    if result.intent:
        response_data["intent"] = result.intent.intent.value
        response_data["confidence"] = result.intent.confidence
        response_data["requires_human"] = result.intent.requires_human
        
    return ChatResponse(**response_data)