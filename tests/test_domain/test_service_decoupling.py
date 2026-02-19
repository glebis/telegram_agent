"""Tests that services depend on domain ports, not Telegram types.

RED-GREEN: These tests verify that service modules do NOT import
from the telegram package.
"""

import ast
import importlib
import inspect
from pathlib import Path


SERVICE_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "services"


def _get_telegram_imports(filepath: Path) -> list[str]:
    """Parse a Python file and return all 'from telegram...' import lines."""
    source = filepath.read_text()
    tree = ast.parse(source, filename=str(filepath))
    results = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "telegram" or node.module.startswith("telegram."):
                line = ast.get_source_segment(source, node) or f"line {node.lineno}"
                results.append(line)
    return results


# ---- image_service.py ----

def test_image_service_no_telegram_imports():
    """image_service.py must not import from telegram."""
    hits = _get_telegram_imports(SERVICE_DIR / "image_service.py")
    assert hits == [], f"Forbidden telegram imports in image_service.py: {hits}"


def test_image_service_process_image_accepts_file_downloader():
    """process_image should accept a FileDownloader, not a Bot."""
    from src.services.image_service import ImageService

    sig = inspect.signature(ImageService.process_image)
    params = list(sig.parameters.keys())
    assert "file_downloader" in params or "bot" not in params, (
        "process_image still has a 'bot' parameter"
    )


# ---- poll_service.py ----

def test_poll_service_no_telegram_imports():
    """poll_service.py must not import from telegram."""
    hits = _get_telegram_imports(SERVICE_DIR / "poll_service.py")
    assert hits == [], f"Forbidden telegram imports in poll_service.py: {hits}"


def test_poll_service_send_poll_accepts_poll_sender():
    """send_poll should accept a PollSender, not a Bot."""
    from src.services.poll_service import PollService

    sig = inspect.signature(PollService.send_poll)
    params = list(sig.parameters.keys())
    assert "poll_sender" in params or "bot" not in params, (
        "send_poll still has a 'bot' parameter"
    )


# ---- keyboard_service.py ----

def test_keyboard_service_no_telegram_imports():
    """keyboard_service.py must not import from telegram."""
    hits = _get_telegram_imports(SERVICE_DIR / "keyboard_service.py")
    assert hits == [], f"Forbidden telegram imports in keyboard_service.py: {hits}"


# ---- srs_service.py ----

def test_srs_service_no_telegram_imports():
    """srs_service.py must not import from telegram."""
    hits = _get_telegram_imports(SERVICE_DIR / "srs_service.py")
    assert hits == [], f"Forbidden telegram imports in srs_service.py: {hits}"


# ---- message_buffer.py ----

def test_message_buffer_no_telegram_imports():
    """message_buffer.py must not import from telegram."""
    hits = _get_telegram_imports(SERVICE_DIR / "message_buffer.py")
    assert hits == [], f"Forbidden telegram imports in message_buffer.py: {hits}"


# ---- accountability_scheduler.py ----

def test_accountability_scheduler_no_telegram_imports():
    """accountability_scheduler.py must not import from telegram."""
    hits = _get_telegram_imports(SERVICE_DIR / "accountability_scheduler.py")
    assert hits == [], (
        f"Forbidden telegram imports in accountability_scheduler.py: {hits}"
    )
