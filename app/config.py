from functools import lru_cache
from typing import List, Optional, Dict

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "frag-naija-support-api"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    # CORS
    cors_origins: str = "http://localhost:3000"
    allowed_hosts: str = "*"

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://support:support@localhost:5432/support"

    # Conversation Memory
    max_history_turns: int = 10
    max_history_tokens: int = 2000

    # Qdrant
    qdrant_url: Optional[str] = None
    qdrant_api_key: Optional[str] = None
    qdrant_collection: str = "support_knowledge"

    # LLM Provider
    llm_provider: str = "mock"
    groq_api_key: Optional[str] = None
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout: float = 30.0
    groq_max_retries: int = 3

    # Local Embeddings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384

    # Retrieval & Reranking
    retrieval_candidate_k: int = 10
    retrieval_final_k: int = 3
    reranker_enabled: bool = False
    reranker_model: str = "BAAI/bge-reranker-base"

    # Langfuse
    langfuse_enabled: bool = False
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Stage 26.4: Controlled website crawling
    crawl_seed_urls: str = ""
    crawl_allowed_domains: str = ""
    crawl_allowed_paths: str = ""
    crawl_max_pages: int = 50
    crawl_max_response_bytes: int = 1_000_000
    crawl_respect_robots: bool = True

    # Stage 26.6 & 26.7: Knowledge Freshness & Priority
    knowledge_stale_days: int = 30
    knowledge_priority_map: str = "document:1,website:2,faq:3,article:4"

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        allowed = {"development", "test", "staging", "production"}
        normalized = value.lower()
        if normalized not in allowed:
            raise ValueError("ENVIRONMENT must be one of: development, test, staging, production")
        return normalized

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in allowed:
            raise ValueError("LOG_LEVEL must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL")
        return normalized

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        allowed = {"mock", "groq"}
        normalized = value.lower()
        if normalized not in allowed:
            raise ValueError("LLM_PROVIDER must be one of: mock, groq")
        return normalized

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> List[str]:
        if self.allowed_hosts == "*":
            return ["*"]
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def crawl_seed_urls_list(self) -> List[str]:
        return [u.strip() for u in self.crawl_seed_urls.split(",") if u.strip()]

    @property
    def crawl_allowed_domains_list(self) -> List[str]:
        return [d.strip() for d in self.crawl_allowed_domains.split(",") if d.strip()]

    @property
    def crawl_allowed_paths_list(self) -> List[str]:
        return [p.strip() for p in self.crawl_allowed_paths.split(",") if p.strip()]

    @property
    def priority_dict(self) -> Dict[str, int]:
        """Stage 26.7: Parse priority map string into a dictionary."""
        mapping: Dict[str, int] = {}
        for pair in self.knowledge_priority_map.split(","):
            if ":" in pair:
                k, v = pair.split(":", 1)
                try:
                    mapping[k.strip()] = int(v.strip())
                except ValueError:
                    pass
        return mapping

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def qdrant_configured(self) -> bool:
        return bool(self.qdrant_url)

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()