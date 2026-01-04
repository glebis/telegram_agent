"""
PDF Plugin - Converts PDFs to markdown using marker-pdf.

Commands:
- /pdf:convert URL - Convert PDF to markdown and send back
- /pdf:save URL - Convert PDF, save to Sources folder, link to daily note
"""

import logging
import os
import re
import subprocess
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse, unquote

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from src.plugins.base import BasePlugin, PluginMetadata, PluginCapabilities

logger = logging.getLogger(__name__)


class PDFPlugin(BasePlugin):
    """PDF to Markdown conversion plugin using marker-pdf."""

    def __init__(self, plugin_dir: Path):
        super().__init__(plugin_dir)
        self._vault_path: Optional[Path] = None
        self._sources_folder: str = "Sources"
        self._daily_folder: str = "Daily"
        self._temp_dir: Path = Path("/tmp/telegram_agent_pdf")
        self._marker_timeout: int = 300

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="pdf",
            version="1.0.0",
            description="PDF to Markdown conversion using marker-pdf",
            author="Telegram Agent",
            requires=[],
            dependencies=[],
            priority=60,
            enabled_by_default=True,
        )

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            services=["pdf_converter"],
            commands=["/pdf:convert", "/pdf:save"],
            callbacks=["pdf:*"],
            api_routes=False,
            message_handler=False,
        )

    async def on_load(self, container) -> bool:
        """Load plugin configuration."""
        logger.info("Loading PDF plugin...")

        # Get configuration
        vault_path = self.get_config_value("vault_path", "~/Research/vault")
        self._vault_path = Path(vault_path).expanduser()
        self._sources_folder = self.get_config_value("sources_folder", "Sources")
        self._daily_folder = self.get_config_value("daily_folder", "Daily")
        self._marker_timeout = self.get_config_value("marker_timeout_seconds", 300)

        temp_dir = self.get_config_value("temp_dir", "/tmp/telegram_agent_pdf")
        self._temp_dir = Path(temp_dir)
        self._temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"PDF plugin loaded: vault={self._vault_path}, sources={self._sources_folder}")
        return True

    async def on_activate(self, app) -> bool:
        """Activate plugin."""
        logger.info("Activating PDF plugin...")

        # Verify marker is installed
        try:
            result = subprocess.run(
                ["which", "marker_single"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                logger.error("marker_single not found in PATH")
                return False
            logger.info(f"Found marker_single at: {result.stdout.strip()}")
        except Exception as e:
            logger.error(f"Failed to verify marker installation: {e}")
            return False

        return True

    def get_command_handlers(self) -> List:
        """Return command handlers for this plugin."""
        return [
            CommandHandler("pdf", self._handle_pdf_command),
        ]

    async def _handle_pdf_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /pdf commands."""
        if not update.message or not update.effective_chat:
            return

        message = update.message
        chat_id = update.effective_chat.id
        text = message.text or ""

        # Parse command: /pdf:convert URL or /pdf:save URL
        parts = text.split(maxsplit=1)
        if not parts:
            await message.reply_text("Usage: /pdf:convert URL or /pdf:save URL")
            return

        command = parts[0].lower()
        url = parts[1].strip() if len(parts) > 1 else ""

        # Extract URL from message if not in command
        if not url:
            await message.reply_text("Please provide a PDF URL.\nUsage: /pdf:convert URL")
            return

        # Validate URL
        if not self._is_valid_url(url):
            await message.reply_text(f"Invalid URL: {url}")
            return

        if command in ["/pdf:convert", "/pdf"]:
            await self._convert_and_send(update, context, url)
        elif command == "/pdf:save":
            await self._convert_and_save(update, context, url)
        else:
            await message.reply_text("Unknown command. Use /pdf:convert or /pdf:save")

    def _is_valid_url(self, url: str) -> bool:
        """Validate URL format."""
        try:
            result = urlparse(url)
            return all([result.scheme in ("http", "https"), result.netloc])
        except Exception:
            return False

    def _extract_filename_from_url(self, url: str) -> str:
        """Extract a clean filename from URL."""
        parsed = urlparse(url)
        path = unquote(parsed.path)
        filename = Path(path).stem

        # Clean up filename
        filename = re.sub(r'[^\w\s-]', '', filename)
        filename = re.sub(r'\s+', '-', filename)

        if not filename:
            filename = "document"

        return filename[:100]  # Limit length

    async def _download_pdf(self, url: str) -> Optional[Path]:
        """Download PDF from URL to temp directory."""
        try:
            filename = self._extract_filename_from_url(url)
            pdf_path = self._temp_dir / f"{filename}.pdf"

            logger.info(f"Downloading PDF from {url} to {pdf_path}")

            # Download with proper headers
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            req = urllib.request.Request(url, headers=headers)

            with urllib.request.urlopen(req, timeout=60) as response:
                with open(pdf_path, 'wb') as f:
                    f.write(response.read())

            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                logger.info(f"Downloaded PDF: {pdf_path.stat().st_size} bytes")
                return pdf_path
            else:
                logger.error("Downloaded file is empty")
                return None

        except Exception as e:
            logger.error(f"Failed to download PDF: {e}")
            return None

    async def _convert_pdf_to_markdown(self, pdf_path: Path) -> Optional[str]:
        """Convert PDF to markdown using marker_single."""
        try:
            output_dir = self._temp_dir / "output"
            output_dir.mkdir(exist_ok=True)

            logger.info(f"Converting PDF: {pdf_path}")

            # Run marker_single
            result = subprocess.run(
                [
                    "marker_single",
                    str(pdf_path),
                    "--output_dir", str(output_dir),
                    "--output_format", "markdown",
                    "--disable_image_extraction",  # Keep it simple for now
                ],
                capture_output=True,
                text=True,
                timeout=self._marker_timeout,
                cwd=str(self._temp_dir)
            )

            if result.returncode != 0:
                logger.error(f"marker_single failed: {result.stderr}")
                return None

            # Find output markdown file
            md_files = list(output_dir.glob("**/*.md"))
            if not md_files:
                logger.error("No markdown output found")
                return None

            md_path = md_files[0]
            markdown_content = md_path.read_text()

            logger.info(f"Converted to markdown: {len(markdown_content)} chars")

            # Cleanup
            for f in output_dir.glob("**/*"):
                if f.is_file():
                    f.unlink()

            return markdown_content

        except subprocess.TimeoutExpired:
            logger.error(f"PDF conversion timed out after {self._marker_timeout}s")
            return None
        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return None

    async def _convert_and_send(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str
    ) -> None:
        """Convert PDF and send markdown back to user."""
        message = update.message
        if not message:
            return

        # Send status
        status_msg = await message.reply_text(f"Converting PDF...\n{url}")

        try:
            # Download
            pdf_path = await self._download_pdf(url)
            if not pdf_path:
                await status_msg.edit_text("Failed to download PDF")
                return

            # Convert
            markdown = await self._convert_pdf_to_markdown(pdf_path)
            if not markdown:
                await status_msg.edit_text("Failed to convert PDF")
                return

            # Send result
            if len(markdown) <= 4000:
                await status_msg.edit_text(f"**Converted PDF:**\n\n{markdown[:4000]}")
            else:
                # Send as file
                md_filename = self._extract_filename_from_url(url) + ".md"
                md_path = self._temp_dir / md_filename
                md_path.write_text(markdown)

                await status_msg.edit_text(f"Converted {len(markdown)} chars. Sending as file...")
                await message.reply_document(
                    document=open(md_path, 'rb'),
                    filename=md_filename,
                    caption=f"Converted from: {url}"
                )

                md_path.unlink()  # Cleanup

            # Cleanup PDF
            if pdf_path.exists():
                pdf_path.unlink()

        except Exception as e:
            logger.error(f"PDF convert error: {e}", exc_info=True)
            await status_msg.edit_text(f"Error: {str(e)[:200]}")

    async def _convert_and_save(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, url: str
    ) -> None:
        """Convert PDF and save to Obsidian vault."""
        message = update.message
        if not message:
            return

        status_msg = await message.reply_text(f"Converting and saving PDF...\n{url}")

        try:
            # Download
            pdf_path = await self._download_pdf(url)
            if not pdf_path:
                await status_msg.edit_text("Failed to download PDF")
                return

            # Convert
            markdown = await self._convert_pdf_to_markdown(pdf_path)
            if not markdown:
                await status_msg.edit_text("Failed to convert PDF")
                return

            # Generate filename with date prefix
            today = datetime.now().strftime("%Y%m%d")
            base_name = self._extract_filename_from_url(url)
            filename = f"{today}-{base_name}.md"

            # Create frontmatter
            frontmatter = f"""---
created_date: '[[{today}]]'
source: {url}
type: pdf-source
tags:
  - source
  - pdf
---

"""
            full_content = frontmatter + markdown

            # Save to Sources folder
            sources_path = self._vault_path / self._sources_folder
            sources_path.mkdir(parents=True, exist_ok=True)

            output_path = sources_path / filename
            output_path.write_text(full_content)

            logger.info(f"Saved PDF to vault: {output_path}")

            # Link to daily note
            daily_note_path = self._vault_path / self._daily_folder / f"{today}.md"
            link_text = f"\n- [[{self._sources_folder}/{filename}|{base_name}]] - PDF source\n"

            if daily_note_path.exists():
                # Append to existing daily note
                with open(daily_note_path, 'a') as f:
                    f.write(link_text)
                logger.info(f"Appended link to daily note: {daily_note_path}")
            else:
                # Create minimal daily note
                daily_content = f"# {today}\n\n## Sources\n{link_text}"
                daily_note_path.parent.mkdir(parents=True, exist_ok=True)
                daily_note_path.write_text(daily_content)
                logger.info(f"Created daily note: {daily_note_path}")

            # Send confirmation
            relative_path = f"{self._sources_folder}/{filename}"
            await status_msg.edit_text(
                f"Saved to vault:\n"
                f"**{relative_path}**\n\n"
                f"Linked to daily note: [[{today}]]\n"
                f"Content: {len(markdown)} chars"
            )

            # Cleanup
            if pdf_path.exists():
                pdf_path.unlink()

        except Exception as e:
            logger.error(f"PDF save error: {e}", exc_info=True)
            await status_msg.edit_text(f"Error: {str(e)[:200]}")

    def get_callback_prefix(self) -> str:
        """Return callback prefix for this plugin."""
        return "pdf"

    async def handle_callback(self, query, action: str, params: List[str], context) -> bool:
        """Handle PDF-related callbacks."""
        # Not implemented yet - could add inline buttons for convert/save
        return False

    async def on_deactivate(self) -> None:
        """Deactivate plugin."""
        logger.info("Deactivating PDF plugin...")

    async def on_unload(self) -> None:
        """Unload plugin and cleanup temp files."""
        logger.info("Unloading PDF plugin...")

        # Cleanup temp directory
        try:
            for f in self._temp_dir.glob("*"):
                if f.is_file():
                    f.unlink()
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
