"""
Poll Response Model - Stores user responses to polls with embeddings for analysis.

This model captures:
- Raw poll data (question, options, selected answer)
- Contextual metadata (time, location, current activity)
- Vector embeddings for semantic search and clustering
- Links to trails and todos for automatic updates
"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text

from .base import Base


class PollResponse(Base):
    """Store poll responses with rich context for trend analysis."""

    __tablename__ = "poll_responses"

    id = Column(Integer, primary_key=True, index=True)

    # Telegram metadata
    chat_id = Column(Integer, nullable=False, index=True)
    poll_id = Column(String, nullable=False, unique=True, index=True)
    message_id = Column(Integer, nullable=True)

    # Poll content
    question = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)  # List of option strings
    selected_option_id = Column(Integer, nullable=False)
    selected_option_text = Column(Text, nullable=False)

    # Categorization
    poll_type = Column(
        String, nullable=False, index=True
    )  # emotion, decision, activity, energy, focus, blocker, satisfaction, progress
    poll_category = Column(
        String, nullable=True, index=True
    )  # work, personal, health, learning, creative, social

    # Temporal context
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    day_of_week = Column(Integer, nullable=True)  # 0=Monday, 6=Sunday
    hour_of_day = Column(Integer, nullable=True)  # 0-23

    # Contextual metadata (optional, can be enriched later)
    context_metadata = Column(
        JSON, nullable=True
    )  # {current_trail, recent_todos, location, weather, etc}

    # Vector embedding for semantic search
    embedding = Column(Text, nullable=True)  # Stored as JSON array string

    # Analysis flags
    processed_for_trails = Column(
        Integer, default=0
    )  # Boolean: has this been used to update trails?
    processed_for_todos = Column(
        Integer, default=0
    )  # Boolean: has this been used to update todos?
    processed_for_insights = Column(
        Integer, default=0
    )  # Boolean: has this been analyzed for insights?

    # Derived insights (populated by analysis jobs)
    sentiment_score = Column(Float, nullable=True)  # -1.0 to 1.0
    energy_level = Column(Float, nullable=True)  # 0.0 to 1.0
    tags = Column(JSON, nullable=True)  # Auto-generated tags

    def __repr__(self):
        return f"<PollResponse(id={self.id}, type={self.poll_type}, question='{self.question[:50]}...', answer='{self.selected_option_text}')>"

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "poll_id": self.poll_id,
            "question": self.question,
            "options": self.options,
            "selected_option_id": self.selected_option_id,
            "selected_option_text": self.selected_option_text,
            "poll_type": self.poll_type,
            "poll_category": self.poll_category,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "day_of_week": self.day_of_week,
            "hour_of_day": self.hour_of_day,
            "context_metadata": self.context_metadata,
            "sentiment_score": self.sentiment_score,
            "energy_level": self.energy_level,
            "tags": self.tags,
        }


class PollTemplate(Base):
    """Poll template for scheduled delivery."""

    __tablename__ = "poll_templates"

    id = Column(Integer, primary_key=True, index=True)

    # Template content
    question = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)  # List of option strings
    poll_type = Column(String, nullable=False, index=True)
    poll_category = Column(String, nullable=True)

    # Scheduling
    schedule_times = Column(JSON, nullable=True)  # ["09:00", "13:00", "18:00"]
    schedule_days = Column(JSON, nullable=True)  # [0, 1, 2, 3, 4] for Mon-Fri
    min_interval_hours = Column(Integer, default=4)  # Minimum hours between uses
    priority = Column(Integer, default=5)  # 1-10, higher = more frequent

    # State
    is_active = Column(Integer, default=1)  # Boolean
    last_sent_at = Column(DateTime, nullable=True)
    times_sent = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<PollTemplate(id={self.id}, type={self.poll_type}, question='{self.question[:50]}...')>"
