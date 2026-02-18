"""
Combined Message Processor — backward-compatibility shim.

The actual implementation now lives in src/bot/processors/:
- router.py: Main class + process() routing logic
- media.py: Image and voice processing
- content.py: Video, document, contact, and poll processing
- text.py: Text, command, and sync helper methods
- collect.py: Collect mode queue and trigger handling

Refactored as part of #152 (break apart god objects).
"""

from .processors import (
    CombinedMessageProcessor,
    get_combined_processor,
    process_combined_message,
)

__all__ = [
    "CombinedMessageProcessor",
    "get_combined_processor",
    "process_combined_message",
]
