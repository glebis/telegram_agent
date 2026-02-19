"""Tests for domain port protocols.

Verifies that the protocol interfaces exist and can be implemented
by concrete classes (structural subtyping).
"""

from typing import Any, Dict, List, Optional, Tuple


def test_file_downloader_protocol_exists():
    """FileDownloader protocol can be imported."""
    from src.domain.ports.file_downloader import FileDownloader

    assert FileDownloader is not None


def test_file_downloader_structural_subtyping():
    """A class matching FileDownloader's shape is a structural subtype."""
    from src.domain.ports.file_downloader import FileDownloader

    class FakeDownloader:
        async def download_file(self, file_id: str) -> Tuple[bytes, Dict[str, Any]]:
            return b"fake", {"file_size": 4}

    obj: FileDownloader = FakeDownloader()
    assert isinstance(obj, FileDownloader)


def test_keyboard_builder_protocol_exists():
    """KeyboardBuilder protocol can be imported."""
    from src.domain.ports.keyboard_builder import KeyboardBuilder

    assert KeyboardBuilder is not None


def test_keyboard_builder_structural_subtyping():
    """A class matching KeyboardBuilder's shape is a structural subtype."""
    from src.domain.ports.keyboard_builder import KeyboardBuilder

    class FakeBuilder:
        def build_inline_keyboard(
            self, rows: List[List[Dict[str, str]]]
        ) -> Any:
            return {"inline_keyboard": rows}

        def build_reply_keyboard(
            self,
            rows: List[List[str]],
            resize_keyboard: bool = True,
            one_time_keyboard: bool = False,
        ) -> Any:
            return {"keyboard": rows}

    obj: KeyboardBuilder = FakeBuilder()
    assert isinstance(obj, KeyboardBuilder)


def test_poll_sender_protocol_exists():
    """PollSender protocol can be imported."""
    from src.domain.ports.poll_sender import PollSender

    assert PollSender is not None


def test_poll_sender_structural_subtyping():
    """A class matching PollSender's shape is a structural subtype."""
    from src.domain.ports.poll_sender import PollSender

    class FakeSender:
        async def send_poll(
            self,
            chat_id: int,
            question: str,
            options: List[str],
            is_anonymous: bool = False,
            allows_multiple_answers: bool = False,
        ) -> Dict[str, Any]:
            return {"poll_id": "123", "message_id": 1}

    obj: PollSender = FakeSender()
    assert isinstance(obj, PollSender)
