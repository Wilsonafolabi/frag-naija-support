from typing import Optional
from app.config import Settings
from langfuse import Langfuse
import structlog

logger = structlog.get_logger(__name__)

def get_langfuse_client(settings: Settings) -> Optional[Langfuse]:
    if not settings.langfuse_enabled:
        return None
        
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning("langfuse_enabled_but_missing_keys")
        return None
        
    try:
        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host
        )
        logger.info("langfuse_initialized", host=settings.langfuse_host)
        return client
    except Exception as e:
        logger.error("langfuse_init_failed", error=str(e))
        return None