"""Policy layer on top of the repository. Enforces trust rules."""
from typing import Optional

from app.knowledge.models import (
    KnowledgeSource,
    LifecycleStatus,
    SourceType,
    TrustLevel,
)
from app.knowledge.repository import KnowledgeSourceRepository

# Trust levels that may ever be ACTIVE / retrievable. A future retrieval
# stage will consult this set; untrusted content can never be served.
RETRIEVABLE_TRUST_LEVELS = {TrustLevel.OFFICIAL, TrustLevel.APPROVED, TrustLevel.PARTNER}


class KnowledgePolicyError(ValueError):
    pass


class KnowledgeSourceService:
    def __init__(self, repo: KnowledgeSourceRepository):
        self.repo = repo

    async def register_source(
        self,
        name: str,
        location: str,
        source_type: SourceType = SourceType.DOCUMENT,
        trust_level: TrustLevel = TrustLevel.UNTRUSTED,
        lifecycle_status: LifecycleStatus = LifecycleStatus.ACTIVE,
        owner: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> KnowledgeSource:
        if trust_level == TrustLevel.UNTRUSTED and lifecycle_status == LifecycleStatus.ACTIVE:
            raise KnowledgePolicyError("Untrusted sources cannot be registered as ACTIVE.")
        return await self.repo.register_source(
            name=name,
            location=location,
            source_type=source_type,
            trust_level=trust_level,
            lifecycle_status=lifecycle_status,
            owner=owner,
            metadata=metadata,
        )

    async def activate(self, source_id: str) -> KnowledgeSource:
        source = await self.repo.get_source(source_id)
        if source is None:
            raise ValueError(f"Unknown knowledge source: {source_id}")
        if source.trust_level not in RETRIEVABLE_TRUST_LEVELS:
            raise KnowledgePolicyError(
                f"Source trust level '{source.trust_level.value}' cannot be activated."
            )
        activated = await self.repo.set_lifecycle_status(source_id, LifecycleStatus.ACTIVE)
        if activated is None:
            raise ValueError(f"Unknown knowledge source: {source_id}")
        return activated