from enum import Enum
from pydantic import BaseModel, Field

class IntentType(str, Enum):
    GENERAL_INQUIRY = "general_inquiry"
    TECHNICAL_SUPPORT = "technical_support"
    ACCOUNT_ISSUE = "account_issue"
    FINANCIAL_ACTION = "financial_action"
    HUMAN_REQUEST = "human_request"
    AMBIGUOUS = "ambiguous"
    CHITCHAT = "chitchat"

class IntentClassification(BaseModel):
    intent: IntentType
    confidence: float = Field(..., ge=0.0, le=1.0)
    requires_human: bool
    reason: str