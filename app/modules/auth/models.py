"""Revocable sessions store a token digest, never the browser token."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Session(Base):
    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
