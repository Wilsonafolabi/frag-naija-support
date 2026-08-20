import structlog
from app.ai.base import BaseLLMProvider, LLMResponse

logger = structlog.get_logger(__name__)


class MockLLMProvider(BaseLLMProvider):
    def __init__(self, settings):
        self.settings = settings
        self.call_count = 0

    async def generate(self, messages: list, **kwargs) -> LLMResponse:
        self.call_count += 1
        
        # FIX: Use dictionary access instead of object attributes
        user_message = next(
            (msg["content"] for msg in reversed(messages) if msg["role"] == "user"), 
            ""
        )
        
        content = f"Mock response to: {user_message[:50]}"
        return LLMResponse(
            content=content,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            provider="mock"
        )

    def get_provider_name(self) -> str:
        return "mock"