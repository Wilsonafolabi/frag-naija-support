import structlog
from groq import AsyncGroq

from app.ai.base import BaseLLMProvider, LLMResponse
from app.config import Settings

logger = structlog.get_logger(__name__)


class GroqProvider(BaseLLMProvider):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.model = settings.groq_model
        self.timeout = settings.groq_timeout
        self.max_retries = settings.groq_max_retries
        logger.info(
            "groq_provider_initialized",
            model=self.model,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

    async def generate(self, messages: list, **kwargs) -> LLMResponse:
        # FIX: Access dictionary keys with ["key"] instead of object attributes (.key)
        groq_messages = [
            {"role": msg["role"], "content": msg["content"]} 
            for msg in messages
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=groq_messages,
                timeout=self.timeout,
                max_retries=self.max_retries,
                **kwargs,
            )

            content = response.choices[0].message.content or ""
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }

            return LLMResponse(
                content=content,
                model=response.model,
                usage=usage,
                provider="groq",
            )
            
        except Exception as e:
            logger.error("groq_api_error", error=str(e))
            raise

    def get_provider_name(self) -> str:
        return "groq"