"""Privacy / GDPR settings — bounded context model.

Owns: privacy_level, data_retention, health_data_consent.
Split from UserSettings (issue #222).
"""

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class PrivacySettings(Base, TimestampMixin):
    """Per-user privacy and GDPR configuration."""

    __tablename__ = "privacy_settings"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    privacy_level: Mapped[str] = mapped_column(String(50), default="private")
    data_retention: Mapped[str] = mapped_column(String(50), default="1_year")
    health_data_consent: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    def __init__(self, **kwargs):
        defaults = {
            "privacy_level": "private",
            "data_retention": "1_year",
            "health_data_consent": False,
        }
        for k, v in defaults.items():
            kwargs.setdefault(k, v)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return (
            f"<PrivacySettings(user_id={self.user_id}, "
            f"privacy={self.privacy_level}, retention={self.data_retention})>"
        )
