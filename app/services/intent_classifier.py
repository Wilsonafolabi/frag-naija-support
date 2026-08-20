import json
from app.ai.base import BaseLLMProvider, LLMMessage
from app.ai.intents import IntentClassification, IntentType
import structlog

logger = structlog.get_logger(__name__)

INTENT_SYSTEM_PROMPT = """You are an intent classifier for Frag Naija customer support.
Analyze the user's message and classify their intent.

Categories:
- general_inquiry: Questions about rules, tournaments, how things work.
- technical_support: Bugs, lag, app crashes.
- account_issue: Login problems, profile updates.
- financial_action: Requests to place wagers, process refunds, deposit/withdraw money.
- human_request: User explicitly asks for a human, agent, real person, or support staff.
- ambiguous: The message is unclear or lacks context.
- chitchat: Greetings, thanks, non-support talk.

Return STRICT JSON with this exact schema:
{
  "intent": "general_inquiry",
  "confidence": 0.95,
  "requires_human": false,
  "reason": "User is asking about tournament rules."
}

Rules:
- requires_human MUST be true for technical_support, account_issue, financial_action, and human_request.
- requires_human MUST be true if confidence < 0.7.
- NEVER authorize or claim you can perform financial or account actions.
"""

class IntentClassifier:
    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm_provider = llm_provider

    async def classify(self, message: str) -> IntentClassification:
        messages = [
            LLMMessage(role="system", content=INTENT_SYSTEM_PROMPT),
            LLMMessage(role="user", content=message)
        ]
        
        try:
            response = await self.llm_provider.generate(
                messages, 
                response_format={"type": "json_object"}
            )
            data = json.loads(response.content)
            return IntentClassification(**data)
        except Exception as e:
            logger.error("intent_classification_failed", error=str(e))
            return IntentClassification(
                intent=IntentType.AMBIGUOUS,
                confidence=0.0,
                requires_human=True,
                reason=f"Classification failed: {str(e)}"
            )