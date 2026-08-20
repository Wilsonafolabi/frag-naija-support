from sqlalchemy.ext.asyncio import AsyncSession
from app.models.ticket import SupportTicket

class TicketRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_ticket(self, session_id: str | None, user_id: str | None, category: str, summary: str, reason: str) -> str:
        ticket = SupportTicket(
            session_id=session_id,
            user_id=user_id,
            category=category,
            summary=summary,
            reason=reason
        )
        self.db.add(ticket)
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket.id