"""CallbackData model for persisting inline keyboard callback mappings."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class CallbackData(Base, TimestampMixin):
    """Persisted callback data for inline keyboard buttons."""

    __tablename__ = "callback_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    short_id: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    data_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'file_id' or 'generic'
    payload: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON for generic, raw string for file_id
    accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<CallbackData(short_id='{self.short_id}', type='{self.data_type}')>"
