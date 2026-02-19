"""
Combined message processor package.

Splits the monolithic CombinedMessageProcessor into focused mixins:
- router: Main class + process() routing logic
- media: Image and voice processing
- content: Video, document, contact, and poll processing
- text: Text, command, and sync helper methods
- collect: Collect mode queue and trigger handling

Refactored as part of #152.
"""

from .router import (
    CombinedMessageProcessor,
    get_combined_processor,
    process_combined_message,
)

__all__ = [
    "CombinedMessageProcessor",
    "get_combined_processor",
    "process_combined_message",
]
