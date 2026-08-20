import json
from typing import List
from app.ai.base import BaseLLMProvider, LLMMessage, LLMResponse

class MockLLMProvider(BaseLLMProvider):
    def __init__(self, default_response: str = "This is a mock response from the Frag Naija support assistant."):
        self.default_response = default_response
        self.call_count = 0

    async def generate(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        self.call_count += 1
        
        # If JSON mode is requested, return a mock classification
        if kwargs.get("response_format", {}).get("type") == "json_object":
            content = json.dumps({
                "intent": "general_inquiry",
                "confidence": 0.99,
                "requires_human": False,
                "reason": "Mock classification"
            })
        else:
            content = self.default_response

        return LLMResponse(
            content=content,
            model="mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            metadata={"mock": True, "call_count": self.call_count},
        )

    def get_provider_name(self) -> str:
        return "mock"