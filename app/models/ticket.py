import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.models.chat import Base

class SupportTicket(Base):
    __tablename__ = "support_tickets"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(50)) # e.g., 'security', 'financial_action', 'human_request'
    summary: Mapped[str] = mapped_column(Text)        # The user's message
    reason: Mapped[str] = mapped_column(String(255))  # Why it was escalated
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))