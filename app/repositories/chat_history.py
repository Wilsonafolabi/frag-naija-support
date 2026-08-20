import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.chat import ChatSession, ChatMessage
from app.rag.sanitizer import sanitize_content

class ChatHistoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_session(self, session_id: Optional[str], user_id: Optional[str]) -> ChatSession:
        if session_id:
            stmt = select(ChatSession).where(ChatSession.id == session_id)
            if user_id:
                stmt = stmt.where(ChatSession.user_id == user_id)
            result = await self.db.execute(stmt)
            session = result.scalar_one_or_none()
            if session:
                return session

        new_session = ChatSession(id=str(uuid.uuid4()), user_id=user_id)
        self.db.add(new_session)
        await self.db.commit()
        await self.db.refresh(new_session)
        return new_session

    async def add_message(self, session_id: str, role: str, content: str):
        safe_content = sanitize_content(content)
        msg = ChatMessage(session_id=session_id, role=role, content=safe_content)
        self.db.add(msg)
        await self.db.commit()

    async def get_history(self, session_id: str, limit: int) -> List[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(reversed(result.scalars().all()))