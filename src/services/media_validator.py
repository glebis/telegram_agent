"""
Media Validator Service

Provides validation, MIME sniffing, size caps, extension whitelisting,
EXIF/metadata stripping, and outbound file path allowlisting.
"""

import logging
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Default allowed image extensions (also settable via ALLOWED_IMAGE_EXTS env)
DEFAULT_ALLOWED_EXTENSIONS: List[str] = ["jpg", "jpeg", "png", "webp"]

# Default max image size (6 MB, also settable via MAX_IMAGE_BYTES env)
DEFAULT_MAX_IMAGE_BYTES: int = 6_291_456

# Magic-byte signatures for common image formats
_SIGNATURES = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],  # Full check requires bytes 8-11 == "WEBP"
    "image/gif": [b"GIF87a", b"GIF89a"],
    "image/bmp": [b"BM"],
}

# Map from MIME to canonical extensions
_MIME_TO_EXTS = {
    "image/jpeg": {"jpg", "jpeg"},
    "image/png": {"png"},
    "image/webp": {"webp"},
    "image/gif": {"gif"},
    "image/bmp": {"bmp"},
}


@dataclass
class ValidationResult:
    """Structured media validation result."""

    valid: bool
    reason: str
    detected_mime: str = ""
    file_size: int = 0


def _sniff_mime(file_path: Path) -> str:
    """
    Detect MIME type by reading file magic bytes.

    Falls back to ``mimetypes.guess_type`` when magic bytes are inconclusive.
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
    except OSError:
        return ""

    if not header:
        return ""

    # Check magic bytes
    for mime, sigs in _SIGNATURES.items():
        for sig in sigs:
            if header[: len(sig)] == sig:
                # Extra check for WebP: bytes 8-11 must be "WEBP"
                if mime == "image/webp":
                    if len(header) >= 12 and header[8:12] == b"WEBP":
                        return mime
                    continue
                return mime

    # Fallback to stdlib guess
    guessed, _ = mimetypes.guess_type(str(file_path))
    return guessed or "application/octet-stream"


def _ext_matches_mime(extension: str, detected_mime: str) -> bool:
    """Return True if *extension* is a canonical extension for *detected_mime*."""
    ext = extension.lower().lstrip(".")
    canonical_exts = _MIME_TO_EXTS.get(detected_mime, set())
    if canonical_exts:
        return ext in canonical_exts

    # For non-image types, use mimetypes stdlib for best-effort check
    guessed_exts = mimetypes.guess_all_extensions(detected_mime, strict=False)
    # Strip leading dot
    guessed_clean = {e.lstrip(".").lower() for e in guessed_exts}
    return ext in guessed_clean if guessed_clean else True  # permissive for unknown


def validate_media(
    file_path: Path,
    filename: str,
    declared_mime: Optional[str] = None,
    max_bytes: Optional[int] = None,
    allowed_extensions: Optional[List[str]] = None,
) -> ValidationResult:
    """
    Validate a media file.

    Checks:
    1. File exists and is non-empty.
    2. File size is within *max_bytes* (default ``DEFAULT_MAX_IMAGE_BYTES``).
    3. Extension is in the allowed list.
    4. MIME type detected from content matches the file extension.
    5. If *declared_mime* is given, detected MIME must match it.

    Args:
        file_path: Path to the file on disk.
        filename: Original filename (used for extension check).
        declared_mime: Optional MIME string declared by the sender.
        max_bytes: Maximum allowed file size. ``None`` uses the default.
        allowed_extensions: Override allowed extensions list.

    Returns:
        ``ValidationResult`` with ``valid=True`` on success.
    """
    file_path = Path(file_path)

    # ------------------------------------------------------------------
    # 1. Existence
    # ------------------------------------------------------------------
    if not file_path.exists():
        return ValidationResult(
            valid=False,
            reason="File not found",
            detected_mime="",
            file_size=0,
        )

    # ------------------------------------------------------------------
    # 2. Size
    # ------------------------------------------------------------------
    file_size = file_path.stat().st_size
    if file_size == 0:
        return ValidationResult(
            valid=False,
            reason="File is empty (0 bytes)",
            detected_mime="",
            file_size=0,
        )

    cap = max_bytes if max_bytes is not None else DEFAULT_MAX_IMAGE_BYTES
    if file_size > cap:
        return ValidationResult(
            valid=False,
            reason=f"File size {file_size} bytes exceeds limit of {cap} bytes",
            detected_mime="",
            file_size=file_size,
        )

    # ------------------------------------------------------------------
    # 3. Extension whitelist
    # ------------------------------------------------------------------
    ext = Path(filename).suffix.lstrip(".").lower()
    allowed = allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS
    allowed_lower = [e.lower() for e in allowed]

    if ext not in allowed_lower:
        return ValidationResult(
            valid=False,
            reason=f"Extension '.{ext}' not in allowed list: {allowed_lower}",
            detected_mime="",
            file_size=file_size,
        )

    # ------------------------------------------------------------------
    # 4. MIME sniffing
    # ------------------------------------------------------------------
    detected_mime = _sniff_mime(file_path)

    if not _ext_matches_mime(ext, detected_mime):
        return ValidationResult(
            valid=False,
            reason=(
                f"MIME type mismatch: file content detected as '{detected_mime}' "
                f"but extension is '.{ext}'"
            ),
            detected_mime=detected_mime,
            file_size=file_size,
        )

    # ------------------------------------------------------------------
    # 5. Declared MIME cross-check
    # ------------------------------------------------------------------
    if declared_mime:
        # Normalise comparison
        if detected_mime != declared_mime:
            return ValidationResult(
                valid=False,
                reason=(
                    f"Declared MIME '{declared_mime}' does not match "
                    f"detected MIME '{detected_mime}'"
                ),
                detected_mime=detected_mime,
                file_size=file_size,
            )

    return ValidationResult(
        valid=True,
        reason="",
        detected_mime=detected_mime,
        file_size=file_size,
    )


# ---------------------------------------------------------------------------
# EXIF / metadata stripping
# ---------------------------------------------------------------------------


def strip_metadata(input_path: Path, output_path: Path) -> bool:
    """
    Strip EXIF and other metadata from an image file using Pillow.

    Works for JPEG, PNG, WebP, and other Pillow-supported formats.
    The cleaned image is written to *output_path* (may be the same as
    *input_path* for in-place stripping).

    Returns ``True`` on success, ``False`` on any error.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        logger.warning("strip_metadata: input file not found: %s", input_path)
        return False

    try:
        from PIL import Image

        with Image.open(input_path) as img:
            # Create a clean copy without metadata
            clean = Image.new(img.mode, img.size)
            clean.putdata(list(img.getdata()))

            # Determine format from output extension
            fmt_map = {
                ".jpg": "JPEG",
                ".jpeg": "JPEG",
                ".png": "PNG",
                ".webp": "WEBP",
                ".gif": "GIF",
                ".bmp": "BMP",
            }
            ext = output_path.suffix.lower()
            fmt = fmt_map.get(ext, "PNG")

            clean.save(output_path, format=fmt)
            logger.debug(
                "Stripped metadata: %s -> %s (%s)",
                input_path,
                output_path,
                fmt,
            )
            return True

    except Exception as e:
        logger.error("strip_metadata failed: %s", e, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Upload MIME type validation (pre-download, Telegram metadata)
# ---------------------------------------------------------------------------

# Allowed MIME types per handler category.
# Keys are handler categories, values are sets of MIME type prefixes or
# exact MIME types that the handler accepts.
ALLOWED_MIME_TYPES: Dict[str, Set[str]] = {
    "voice": {
        "audio/ogg",
        "audio/mpeg",
        "audio/mp4",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/webm",
        "audio/aac",
        "audio/flac",
        "audio/x-m4a",
        "video/ogg",  # Telegram voice notes use video/ogg (opus codec)
    },
    "photo": {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/bmp",
        "image/tiff",
        "image/heic",
        "image/heif",
        "image/svg+xml",
    },
    "video": {
        "video/mp4",
        "video/quicktime",
        "video/x-msvideo",
        "video/webm",
        "video/mpeg",
        "video/3gpp",
        "video/x-matroska",
    },
    "document": {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/json",
        "application/xml",
        "application/zip",
        "application/x-tar",
        "application/gzip",
        "application/x-gzip",
        "text/plain",
        "text/csv",
        "text/html",
        "text/markdown",
        "text/x-python",
        "text/javascript",
        "text/css",
        "text/xml",
        "text/yaml",
        "text/x-yaml",
        "application/x-yaml",
        "application/octet-stream",  # Generic binary — allowed for documents
    },
}

# MIME prefix matching: for these categories, also accept any MIME starting
# with the given prefix (e.g. "audio/" matches "audio/x-custom").
_MIME_PREFIX_FALLBACKS: Dict[str, List[str]] = {
    "voice": ["audio/"],
    "photo": ["image/"],
    "video": ["video/"],
}


@dataclass
class MimeValidationResult:
    """Result of an upload MIME type validation check."""

    valid: bool
    reason: str
    mime_type: str = ""
    handler: str = ""


def validate_upload_mime_type(
    mime_type: Optional[str],
    file_name: Optional[str],
    handler: str,
) -> MimeValidationResult:
    """
    Validate that a Telegram file's declared MIME type is acceptable for *handler*.

    This runs **before** the file is downloaded, using only Telegram metadata.

    Args:
        mime_type: The MIME type reported by Telegram (may be ``None``).
        file_name: Original filename (used for extension-based fallback).
        handler: Handler category — one of ``"voice"``, ``"photo"``,
            ``"video"``, ``"document"``.

    Returns:
        ``MimeValidationResult`` with ``valid=True`` when the MIME type is
        acceptable or cannot be determined (permissive for missing metadata).
    """
    if handler not in ALLOWED_MIME_TYPES:
        # Unknown handler category — be permissive
        logger.debug("validate_upload_mime_type: unknown handler %r, allowing", handler)
        return MimeValidationResult(
            valid=True,
            reason="",
            mime_type=mime_type or "",
            handler=handler,
        )

    # ---------------------------------------------------------------
    # When Telegram does not provide a MIME type, try to infer from
    # the file extension.  If neither is available, allow the file
    # through (Telegram sometimes omits mime_type for voice notes).
    # ---------------------------------------------------------------
    effective_mime = mime_type
    if not effective_mime and file_name:
        guessed, _ = mimetypes.guess_type(file_name)
        if guessed:
            effective_mime = guessed
            logger.debug(
                "validate_upload_mime_type: inferred MIME %r from filename %r",
                effective_mime,
                file_name,
            )

    if not effective_mime:
        # No MIME and no filename — allow (Telegram voice notes may lack both)
        logger.debug(
            "validate_upload_mime_type: no MIME type available for handler %r, "
            "allowing by default",
            handler,
        )
        return MimeValidationResult(
            valid=True,
            reason="",
            mime_type="",
            handler=handler,
        )

    effective_mime_lower = effective_mime.lower()
    allowed = ALLOWED_MIME_TYPES[handler]

    # Exact match
    if effective_mime_lower in allowed:
        return MimeValidationResult(
            valid=True,
            reason="",
            mime_type=effective_mime_lower,
            handler=handler,
        )

    # Prefix match
    prefixes = _MIME_PREFIX_FALLBACKS.get(handler, [])
    for prefix in prefixes:
        if effective_mime_lower.startswith(prefix):
            return MimeValidationResult(
                valid=True,
                reason="",
                mime_type=effective_mime_lower,
                handler=handler,
            )

    # Extension cross-check: reject if declared MIME type doesn't match
    # expected handler at all.
    logger.warning(
        "MIME type validation failed: mime_type=%r is not allowed for "
        "handler=%r (file_name=%r)",
        effective_mime,
        handler,
        file_name,
    )
    return MimeValidationResult(
        valid=False,
        reason=(
            f"File type '{effective_mime}' is not accepted for {handler} processing. "
            f"Expected one of: {', '.join(sorted(allowed))}"
        ),
        mime_type=effective_mime_lower,
        handler=handler,
    )


# ---------------------------------------------------------------------------
# Outbound file-path allowlist
# ---------------------------------------------------------------------------

# Project root (telegram_agent/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Default directories from which outbound files may be sent
_DEFAULT_ALLOWED_ROOTS = [
    str(_PROJECT_ROOT / "data"),
    str(_PROJECT_ROOT / "logs"),
]


def validate_outbound_path(
    file_path: Path,
    allowed_roots: Optional[List[str]] = None,
) -> bool:
    """
    Validate that *file_path* is safe to send outbound.

    Resolves symlinks and ``..`` components, then checks that the resolved
    real path falls under one of the allowed root directories.

    Args:
        file_path: Path to the file the bot intends to send.
        allowed_roots: Override list of allowed root directories.
            Defaults to ``data/`` and ``logs/`` under project root.

    Returns:
        ``True`` if the path is under an allowed root and exists.
    """
    file_path = Path(file_path)

    # Resolve symlinks and normalise
    try:
        real = file_path.resolve(strict=True)
    except (OSError, ValueError):
        logger.warning("validate_outbound_path: cannot resolve %s", file_path)
        return False

    roots = allowed_roots if allowed_roots is not None else _DEFAULT_ALLOWED_ROOTS

    for root in roots:
        try:
            root_resolved = Path(root).resolve(strict=False)
            if (
                str(real).startswith(str(root_resolved) + os.sep)
                or real == root_resolved
            ):
                return True
        except (OSError, ValueError):
            continue

    logger.warning(
        "validate_outbound_path: %s is not under allowed roots %s",
        real,
        roots,
    )
    return False
