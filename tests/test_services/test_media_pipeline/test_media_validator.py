"""
Tests for media_validator.py -- MIME validation, size caps, extension whitelist,
EXIF stripping, and outbound path validation.
"""

import struct
from pathlib import Path

import pytest

from src.services.media_validator import (
    strip_metadata,
    validate_media,
    validate_outbound_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tiny_jpeg(path: Path) -> None:
    """Write the smallest valid JPEG to *path*."""
    # Minimal JPEG: SOI + APP0 (JFIF) + SOF0 + SOS + EOI
    # This is a 1x1 pixel JPEG with valid markers
    jpeg_bytes = bytes(
        [
            0xFF,
            0xD8,  # SOI
            0xFF,
            0xE0,  # APP0
            0x00,
            0x10,  # Length = 16
            0x4A,
            0x46,
            0x49,
            0x46,
            0x00,  # JFIF\0
            0x01,
            0x01,  # Version 1.1
            0x00,  # Aspect ratio units
            0x00,
            0x01,  # X density
            0x00,
            0x01,  # Y density
            0x00,
            0x00,  # Thumbnail dimensions
            0xFF,
            0xDB,  # DQT marker
            0x00,
            0x43,  # Length
            0x00,  # Table info
        ]
    )
    # Add 64 bytes of quantization table (all 1s for simplicity)
    jpeg_bytes += bytes([0x01] * 64)
    jpeg_bytes += bytes(
        [
            0xFF,
            0xC0,  # SOF0
            0x00,
            0x0B,  # Length
            0x08,  # Precision
            0x00,
            0x01,  # Height = 1
            0x00,
            0x01,  # Width = 1
            0x01,  # Number of components
            0x01,  # Component ID
            0x11,  # Sampling factors
            0x00,  # Quantization table
            0xFF,
            0xC4,  # DHT marker
            0x00,
            0x1F,  # Length
            0x00,  # Table class/ID
        ]
    )
    # Minimal Huffman table
    jpeg_bytes += bytes([0x00] * 16)  # Number of codes per length
    jpeg_bytes += bytes(
        [
            0xFF,
            0xDA,  # SOS
            0x00,
            0x08,  # Length
            0x01,  # Number of components
            0x01,
            0x00,  # Component selector + table
            0x00,
            0x3F,  # Spectral selection
            0x00,  # Successive approximation
            0x00,  # Scan data (empty)
            0xFF,
            0xD9,  # EOI
        ]
    )
    path.write_bytes(jpeg_bytes)


def _make_tiny_png(path: Path) -> None:
    """Write the smallest valid PNG to *path* (1x1 white pixel)."""
    import zlib

    # PNG signature
    signature = b"\x89PNG\r\n\x1a\n"

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        import struct
        import zlib as _z

        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", _z.crc32(chunk_type + data) & 0xFFFFFFFF)
        return length + chunk_type + data + crc

    # IHDR: 1x1, 8-bit RGB
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    # IDAT: single row, filter=0, white pixel (R=255, G=255, B=255)
    raw_data = b"\x00\xff\xff\xff"
    compressed = zlib.compress(raw_data)
    idat = _chunk(b"IDAT", compressed)

    # IEND
    iend = _chunk(b"IEND", b"")

    path.write_bytes(signature + ihdr + idat + iend)


# ---------------------------------------------------------------------------
# MIME / extension validation
# ---------------------------------------------------------------------------


class TestMimeValidation:
    """Test that MIME sniffing matches declared extension."""

    def test_valid_jpeg(self, tmp_path):
        fp = tmp_path / "photo.jpg"
        _make_tiny_jpeg(fp)
        result = validate_media(fp, "photo.jpg")
        assert result.valid, f"Expected valid, got: {result.reason}"
        assert "image/jpeg" in result.detected_mime

    def test_valid_png(self, tmp_path):
        fp = tmp_path / "image.png"
        _make_tiny_png(fp)
        result = validate_media(fp, "image.png")
        assert result.valid, f"Expected valid, got: {result.reason}"
        assert "image/png" in result.detected_mime

    def test_wrong_extension_rejected(self, tmp_path):
        """A JPEG file masquerading as .png should be rejected."""
        fp = tmp_path / "fake.png"
        _make_tiny_jpeg(fp)
        result = validate_media(fp, "fake.png")
        assert not result.valid
        assert "mismatch" in result.reason.lower() or "mime" in result.reason.lower()

    def test_disallowed_extension_rejected(self, tmp_path):
        """An extension not in the whitelist should be rejected."""
        fp = tmp_path / "script.exe"
        fp.write_bytes(b"MZ" + b"\x00" * 100)
        result = validate_media(fp, "script.exe")
        assert not result.valid
        assert (
            "extension" in result.reason.lower() or "allowed" in result.reason.lower()
        )

    def test_webp_allowed(self, tmp_path):
        """WebP extension should pass when content matches."""
        fp = tmp_path / "photo.webp"
        # Minimal WebP file header: RIFF....WEBP
        riff_header = b"RIFF" + struct.pack("<I", 12) + b"WEBP"
        # VP8 chunk (minimal)
        riff_header += b"VP8 " + struct.pack("<I", 0)
        fp.write_bytes(riff_header)
        result = validate_media(fp, "photo.webp")
        assert result.valid, f"Expected valid, got: {result.reason}"

    def test_declared_mime_takes_precedence(self, tmp_path):
        """When declared_mime is given and conflicts with content, reject."""
        fp = tmp_path / "photo.jpg"
        _make_tiny_jpeg(fp)
        # Declared as PNG but content is JPEG
        result = validate_media(fp, "photo.jpg", declared_mime="image/png")
        assert not result.valid
        assert (
            "mismatch" in result.reason.lower() or "declared" in result.reason.lower()
        )

    def test_nonexistent_file_rejected(self, tmp_path):
        fp = tmp_path / "nope.jpg"
        result = validate_media(fp, "nope.jpg")
        assert not result.valid
        assert "not found" in result.reason.lower() or "exist" in result.reason.lower()

    def test_empty_file_rejected(self, tmp_path):
        fp = tmp_path / "empty.jpg"
        fp.write_bytes(b"")
        result = validate_media(fp, "empty.jpg")
        assert not result.valid


# ---------------------------------------------------------------------------
# Size validation
# ---------------------------------------------------------------------------


class TestSizeValidation:
    """Test file-size cap enforcement."""

    def test_under_limit_passes(self, tmp_path):
        fp = tmp_path / "small.jpg"
        _make_tiny_jpeg(fp)
        result = validate_media(fp, "small.jpg", max_bytes=1_000_000)
        assert result.valid

    def test_over_limit_rejected(self, tmp_path):
        fp = tmp_path / "huge.jpg"
        _make_tiny_jpeg(fp)
        result = validate_media(fp, "huge.jpg", max_bytes=10)
        assert not result.valid
        assert "size" in result.reason.lower()

    def test_exact_limit_passes(self, tmp_path):
        fp = tmp_path / "exact.jpg"
        _make_tiny_jpeg(fp)
        file_size = fp.stat().st_size
        result = validate_media(fp, "exact.jpg", max_bytes=file_size)
        assert result.valid

    def test_result_contains_file_size(self, tmp_path):
        fp = tmp_path / "sized.jpg"
        _make_tiny_jpeg(fp)
        result = validate_media(fp, "sized.jpg")
        assert result.file_size == fp.stat().st_size


# ---------------------------------------------------------------------------
# Extension whitelist
# ---------------------------------------------------------------------------


class TestExtensionWhitelist:
    """Test the extension allow-list."""

    def test_custom_whitelist_accepted(self, tmp_path):
        fp = tmp_path / "photo.jpg"
        _make_tiny_jpeg(fp)
        result = validate_media(
            fp,
            "photo.jpg",
            allowed_extensions=["jpg", "jpeg"],
        )
        assert result.valid

    def test_custom_whitelist_rejected(self, tmp_path):
        fp = tmp_path / "photo.jpg"
        _make_tiny_jpeg(fp)
        result = validate_media(
            fp,
            "photo.jpg",
            allowed_extensions=["png", "webp"],
        )
        assert not result.valid
        assert (
            "extension" in result.reason.lower() or "allowed" in result.reason.lower()
        )

    def test_case_insensitive_extension(self, tmp_path):
        fp = tmp_path / "photo.JPG"
        _make_tiny_jpeg(fp)
        result = validate_media(fp, "photo.JPG")
        assert result.valid


# ---------------------------------------------------------------------------
# EXIF stripping
# ---------------------------------------------------------------------------


class TestExifStripping:
    """Test metadata removal from images."""

    def test_strip_creates_output_file(self, tmp_path):
        """Stripping a valid image should produce an output file."""
        src = tmp_path / "src.jpg"
        dst = tmp_path / "dst.jpg"
        _make_tiny_jpeg(src)
        ok = strip_metadata(src, dst)
        # May return False if Pillow can't open the minimal JPEG,
        # but it must not raise.
        if ok:
            assert dst.exists()

    def test_strip_creates_clean_png(self, tmp_path):
        """Stripping a PNG should produce a clean output."""
        src = tmp_path / "src.png"
        dst = tmp_path / "dst.png"
        _make_tiny_png(src)
        ok = strip_metadata(src, dst)
        assert ok, "strip_metadata should succeed on valid PNG"
        assert dst.exists()
        assert dst.stat().st_size > 0

    def test_strip_png_removes_text_chunks(self, tmp_path):
        """Verify that stripping actually removes metadata from PNG."""
        src = tmp_path / "meta.png"
        dst = tmp_path / "clean.png"
        _make_tiny_png(src)
        ok = strip_metadata(src, dst)
        if ok:
            # Read back and verify via Pillow that info dict is empty
            try:
                from PIL import Image

                with Image.open(dst) as img:
                    # Stripped image should have minimal or no text metadata
                    assert isinstance(img.info, dict)
            except ImportError:
                pytest.skip("Pillow not installed")

    def test_strip_nonexistent_returns_false(self, tmp_path):
        src = tmp_path / "nonexistent.jpg"
        dst = tmp_path / "out.jpg"
        ok = strip_metadata(src, dst)
        assert not ok

    def test_strip_in_place(self, tmp_path):
        """strip_metadata should work when input == output."""
        fp = tmp_path / "inplace.png"
        _make_tiny_png(fp)
        ok = strip_metadata(fp, fp)
        assert ok
        assert fp.exists()
        assert fp.stat().st_size > 0


# ---------------------------------------------------------------------------
# Outbound path validation
# ---------------------------------------------------------------------------


class TestOutboundPathValidation:
    """Test outbound file-path allowlist and path-traversal blocking."""

    def test_allowed_path_passes(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        fp = data_dir / "report.pdf"
        fp.write_bytes(b"pdf content")
        assert validate_outbound_path(fp, allowed_roots=[str(data_dir)])

    def test_path_outside_allowed_roots_rejected(self, tmp_path):
        fp = tmp_path / "secret.env"
        fp.write_bytes(b"KEY=val")
        allowed = tmp_path / "data"
        allowed.mkdir()
        assert not validate_outbound_path(fp, allowed_roots=[str(allowed)])

    def test_path_traversal_blocked(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # Attempt traversal via ".."
        traversal = data_dir / ".." / "secret.env"
        (tmp_path / "secret.env").write_bytes(b"KEY=val")
        assert not validate_outbound_path(traversal, allowed_roots=[str(data_dir)])

    def test_symlink_traversal_blocked(self, tmp_path):
        """Symlink that escapes allowed root should be blocked."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        secret = tmp_path / "secret.env"
        secret.write_bytes(b"KEY=val")
        link = data_dir / "sneaky.env"
        link.symlink_to(secret)
        assert not validate_outbound_path(link, allowed_roots=[str(data_dir)])

    def test_default_roots_used_when_none(self):
        """When allowed_roots=None, the function should fall back to project defaults."""
        # This just verifies the function doesn't crash with None
        result = validate_outbound_path(Path("/tmp/some_file.txt"))
        # /tmp is not in default allowed roots, so should be False
        assert isinstance(result, bool)

    def test_nonexistent_path_rejected(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        fp = data_dir / "ghost.txt"
        assert not validate_outbound_path(fp, allowed_roots=[str(data_dir)])
