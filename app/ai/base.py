from typing import Dict, Any
from pydantic import BaseModel


class LLMProviderError(Exception):
    """Raised when an LLM provider encounters an error."""
    pass


class LLMMessage(dict):
    """
    THE SILVER BULLET:
    Subclasses dict so msg["role"] works perfectly for old code (Guard/Intent),
    but also sets attributes so msg.role works perfectly for new code.
    Pydantic V2 cannot break this.
    """
    def __init__(self, role: str = "", content: str = "", **kwargs):
        super().__init__(role=role, content=content, **kwargs)
        self.role = role
        self.content = content

    def __getattr__(self, key: str) -> Any:
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"'LLMMessage' object has no attribute '{key}'")


class LLMResponse(BaseModel):
    """Standardized response from any LLM provider."""
    content: str
    model: str
    usage: Dict[str, int]
    provider: str


class BaseLLMProvider:
    """Abstract base class for LLM providers."""
    
    async def generate(self, messages: list, **kwargs) -> LLMResponse:
        raise NotImplementedError

    def get_provider_name(self) -> str:
        raise NotImplementedError