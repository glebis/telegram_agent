"""
Cross-context callback interfaces (Protocols).

Services that need functionality from another bounded context should
depend on one of these Protocols rather than importing the concrete
implementation directly.  The concrete adapter is wired at construction
time (constructor injection) with a default fallback for backward
compatibility.
"""

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class VoiceSynthesizer(Protocol):
    """Abstraction over voice synthesis (lives in the *voice* context)."""

    async def synthesize_mp3(
        self,
        text: str,
        *,
        voice: str = "diana",
        emotion: str = "cheerful",
    ) -> bytes: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Abstraction over embedding generation (lives in the *ai* context)."""

    async def generate_embedding(self, data: bytes) -> Optional[bytes]: ...
