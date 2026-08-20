from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field


class LLMMessage(BaseModel):
    role: str = Field(..., description="The role of the message sender (system, user, assistant)")
    content: str = Field(..., description="The content of the message")


class LLMResponse(BaseModel):
    content: str = Field(..., description="The generated response content")
    model: str = Field(..., description="The model that generated the response")
    usage: Optional[Dict[str, int]] = Field(None, description="Token usage information")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""
    pass


class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        pass