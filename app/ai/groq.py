import structlog
from groq import AsyncGroq
from typing import List

from app.ai.base import BaseLLMProvider, LLMMessage, LLMResponse, LLMProviderError
from app.config import Settings

logger = structlog.get_logger(__name__)


class GroqProvider(BaseLLMProvider):
    """Production-ready Groq LLM provider."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.groq_model
        
        logger.info(
            "groq_provider_initialized",
            model=self.model,
            timeout=settings.groq_timeout,
            max_retries=settings.groq_max_retries,
        )
        
        self.client = AsyncGroq(
            api_key=settings.groq_api_key,
            timeout=settings.groq_timeout,
            max_retries=settings.groq_max_retries,
        )

    async def generate(self, messages: List[LLMMessage], **kwargs) -> LLMResponse:
        groq_messages = [{"role": msg.role, "content": msg.content} for msg in messages]
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=groq_messages,
                **kwargs
            )
        except Exception as e:
            # Catch ALL Groq SDK errors (Authentication, RateLimit, Timeout, etc.)
            error_type = type(e).__name__
            error_msg = str(e)
            
            logger.error(
                "groq_api_error", 
                error_type=error_type, 
                error_message=error_msg
            )
            
            # Return a clean error to the user without crashing the server
            raise LLMProviderError(f"AI service error ({error_type}): {error_msg}") from e

        choice = response.choices[0]
        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=choice.message.content or "",
            model=self.model,
            usage=usage,
            metadata={"provider": "groq", "finish_reason": choice.finish_reason}
        )

    def get_provider_name(self) -> str:
        return "groq"