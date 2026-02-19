"""KeyboardBuilder port -- abstracts inline & reply keyboard construction."""

from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class KeyboardBuilder(Protocol):
    """Builds keyboard markup objects for the messaging platform."""

    def build_inline_keyboard(self, rows: List[List[Dict[str, str]]]) -> Any:
        """Build an inline keyboard from rows of {text, callback_data} dicts."""
        ...

    def build_reply_keyboard(
        self,
        rows: List[List[str]],
        resize_keyboard: bool = True,
        one_time_keyboard: bool = False,
    ) -> Any:
        """Build a reply keyboard from rows of button-text strings."""
        ...
