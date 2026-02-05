from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import src.services.image_service as image_service
from src.services.image_service import ImageService


def make_png_bytes() -> bytes:
    # minimal 1x1 PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc````\x00\x00\x00\x05\x00\x01"
        b"\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@pytest.fixture(autouse=True)
def reset_limits(monkeypatch):
    monkeypatch.setattr(image_service, "MAX_IMAGE_BYTES", 1024)
    monkeypatch.setattr(
        image_service, "ALLOWED_IMAGE_EXTS", {"jpg", "jpeg", "png", "webp"}
    )
    yield


def test_validate_image_disallows_empty():
    svc = ImageService()
    with pytest.raises(ValueError):
        svc._validate_image(b"")


def test_validate_image_disallows_oversize():
    svc = ImageService()
    big = b"x" * 1500
    with pytest.raises(ValueError):
        svc._validate_image(big)


def test_validate_image_disallows_extension():
    svc = ImageService()
    data = make_png_bytes()
    with pytest.raises(ValueError):
        svc._validate_image(data, "file.gif")


def test_validate_image_allows_whitelisted_extension():
    svc = ImageService()
    data = make_png_bytes()
    svc._validate_image(data, "pic.png")  # should not raise


class DummyLLM:
    async def analyze_image(self, image_data, mode: str, preset=None):
        return {"analysis": "ok"}


class DummyEmbed:
    async def generate_embedding(self, image_data):
        return b"emb"


@pytest.mark.asyncio
async def test_process_image_rejects_disallowed_ext(monkeypatch):
    svc = ImageService()
    svc.llm_service = DummyLLM()
    svc.embedding_service = DummyEmbed()
    data = make_png_bytes()

    async def fake_download(self, bot, fid):
        return data, {
            "file_path": "foo.gif",
            "file_size": len(data),
            "file_unique_id": "u",
        }

    monkeypatch.setattr(ImageService, "_download_image", fake_download)
    monkeypatch.setattr(
        ImageService, "_save_original", AsyncMock(return_value=Path("/tmp/o.png"))
    )
    monkeypatch.setattr(
        ImageService,
        "_process_image",
        AsyncMock(return_value=(Path("/tmp/p.png"), {"dimensions": (1, 1)})),
    )

    bot = MagicMock()
    with pytest.raises(ValueError):
        await svc.process_image(bot=bot, file_id="file")


@pytest.mark.asyncio
async def test_process_image_allows_small_png(monkeypatch):
    svc = ImageService()
    svc.llm_service = DummyLLM()
    svc.embedding_service = DummyEmbed()
    data = make_png_bytes()

    async def fake_download(self, bot, fid):
        return data, {
            "file_path": "foo.png",
            "file_size": len(data),
            "file_unique_id": "u",
        }

    monkeypatch.setattr(ImageService, "_download_image", fake_download)
    monkeypatch.setattr(
        ImageService, "_save_original", AsyncMock(return_value=Path("/tmp/o.png"))
    )
    monkeypatch.setattr(
        ImageService,
        "_process_image",
        AsyncMock(return_value=(Path("/tmp/p.png"), {"dimensions": (1, 1)})),
    )

    bot = MagicMock()
    result = await svc.process_image(bot=bot, file_id="file")
    assert result["analysis"] == "ok"
    assert result["embedding_generated"] is True
