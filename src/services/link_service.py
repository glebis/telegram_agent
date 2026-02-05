"""
Link capture service using Firecrawl API
Fetches web pages and saves them to Obsidian vault
"""

import logging
import os
import re
import shutil
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import requests
import yaml

logger = logging.getLogger(__name__)

# Track recently captured files (message_id -> file_path) for routing
# Using OrderedDict with max size to prevent memory leaks
_recent_captures: OrderedDict = OrderedDict()
MAX_TRACKED_CAPTURES = 100


def track_capture(message_id: int, data: Union[str, Dict]) -> None:
    """Track a captured file/info for potential re-routing.

    Args:
        message_id: The Telegram message ID to associate with this capture
        data: Either a file path string or a dict with capture info
    """
    _recent_captures[message_id] = data
    # Trim old entries
    while len(_recent_captures) > MAX_TRACKED_CAPTURES:
        _recent_captures.popitem(last=False)


def get_tracked_capture(message_id: int) -> Optional[Union[str, Dict]]:
    """Get the tracked capture data for a message ID.

    Returns:
        Either a file path string or a dict with capture info, or None if not found
    """
    return _recent_captures.get(message_id)


class LinkService:
    """Service for capturing web links and saving to Obsidian"""

    def __init__(self):
        self.api_key = os.getenv("FIRECRAWL_API_KEY")
        self.base_url = "https://api.firecrawl.dev/v1"
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load routing configuration"""
        config_path = Path(__file__).parent.parent.parent / "config" / "routing.yaml"
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading routing config: {e}")
            return self._default_config()

    def _default_config(self) -> Dict:
        """Default configuration if file not found"""
        return {
            "obsidian": {
                "vault_path": "~/Brains/brain",
                "destinations": {"inbox": "inbox/"},
            },
            "links": {
                "default_destination": "inbox",
                "firecrawl": {"max_content_length": 10000},
            },
        }

    def _get_vault_path(self) -> Path:
        """Get expanded vault path"""
        vault_path = self.config.get("obsidian", {}).get("vault_path", "~/Brains/brain")
        return Path(vault_path).expanduser()

    def _get_destination_path(self, destination: str) -> Path:
        """Get full path for a destination"""
        vault = self._get_vault_path()
        destinations = self.config.get("obsidian", {}).get("destinations", {})
        rel_path = destinations.get(destination, "inbox/")
        return vault / rel_path

    async def scrape_url(self, url: str) -> Tuple[bool, Dict]:
        """
        Scrape a URL using Firecrawl API

        Returns:
            Tuple of (success, result_dict)
            result_dict contains: title, content, url, error (if failed)
        """
        if not self.api_key:
            logger.error("FIRECRAWL_API_KEY not configured")
            return False, {"error": "Firecrawl API key not configured"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {"url": url, "formats": ["markdown"], "onlyMainContent": True}

        try:
            logger.info(f"Scraping URL: {url}")
            response = requests.post(
                f"{self.base_url}/scrape",
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                result_data = data.get("data", {})

                title = result_data.get("metadata", {}).get("title", "Untitled")
                content = result_data.get("markdown", "")

                # Truncate if too long
                max_length = (
                    self.config.get("links", {})
                    .get("firecrawl", {})
                    .get("max_content_length", 10000)
                )
                if len(content) > max_length:
                    content = content[:max_length] + "\n\n... (truncated)"

                logger.info(f"Successfully scraped: {title}")
                return True, {
                    "title": title,
                    "content": content,
                    "url": url,
                    "metadata": result_data.get("metadata", {}),
                }
            else:
                error_msg = (
                    f"Firecrawl API error {response.status_code}: {response.text}"
                )
                logger.error(error_msg)
                return False, {"error": error_msg, "url": url}

        except requests.Timeout:
            logger.error(f"Timeout scraping {url}")
            return False, {"error": "Request timed out", "url": url}
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return False, {"error": str(e), "url": url}

    def _sanitize_filename(self, title: str) -> str:
        """Create safe filename from title"""
        # Remove or replace invalid characters
        safe = re.sub(r'[<>:"/\\|?*]', "", title)
        safe = re.sub(r"\s+", " ", safe).strip()
        # Limit length
        if len(safe) > 100:
            safe = safe[:100]
        return safe or "Untitled"

    async def save_to_obsidian(
        self,
        title: str,
        content: str,
        url: str,
        destination: str = "inbox",
        extra_tags: Optional[list] = None,
    ) -> Tuple[bool, str]:
        """
        Save captured content to Obsidian vault

        Args:
            title: Page title
            content: Markdown content
            url: Source URL
            destination: Target destination (inbox, research, etc)
            extra_tags: Additional tags to add

        Returns:
            Tuple of (success, file_path or error message)
        """
        try:
            dest_path = self._get_destination_path(destination)
            dest_path.mkdir(parents=True, exist_ok=True)

            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = self._sanitize_filename(title)
            filename = f"{safe_title}_{timestamp}.md"
            file_path = dest_path / filename

            # Build tags
            tags = ["capture", "web"]
            if extra_tags:
                tags.extend(extra_tags)
            tags_str = ", ".join(tags)

            # Format note content
            note_content = f"""---
url: "{url}"
title: "{title}"
captured: "{datetime.now().isoformat()}"
source: telegram
tags: [{tags_str}]
---

# {title}

**Source:** [{url}]({url})
**Captured:** {datetime.now().strftime("%Y-%m-%d %H:%M")}

---

{content}
"""

            # Write file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(note_content)

            logger.info(f"Saved to Obsidian: {file_path}")
            return True, str(file_path)

        except Exception as e:
            logger.error(f"Error saving to Obsidian: {e}")
            return False, str(e)

    async def capture_link(
        self, url: str, destination: str = "inbox"
    ) -> Tuple[bool, Dict]:
        """
        Full workflow: scrape URL and save to Obsidian

        Returns:
            Tuple of (success, result_dict with title, path, or error)
        """
        # Scrape the URL
        success, scrape_result = await self.scrape_url(url)

        if not success:
            return False, scrape_result

        # Save to Obsidian
        save_success, save_result = await self.save_to_obsidian(
            title=scrape_result["title"],
            content=scrape_result["content"],
            url=url,
            destination=destination,
        )

        if save_success:
            return True, {
                "title": scrape_result["title"],
                "path": save_result,
                "url": url,
                "destination": destination,
            }
        else:
            return False, {"error": save_result, "url": url}

    async def move_to_destination(
        self, current_path: str, new_destination: str
    ) -> Tuple[bool, str]:
        """
        Move a captured file to a different destination

        Args:
            current_path: Current file path
            new_destination: Target destination (inbox, research, daily, etc)

        Returns:
            Tuple of (success, new_path or error message)
        """
        try:
            current = Path(current_path)
            if not current.exists():
                return False, f"File not found: {current_path}"

            dest_path = self._get_destination_path(new_destination)
            dest_path.mkdir(parents=True, exist_ok=True)

            new_path = dest_path / current.name
            shutil.move(str(current), str(new_path))

            logger.info(f"Moved file from {current_path} to {new_path}")
            return True, str(new_path)

        except Exception as e:
            logger.error(f"Error moving file: {e}")
            return False, str(e)


# Global service instance
_link_service: Optional[LinkService] = None


def get_link_service() -> LinkService:
    """Get the global link service instance"""
    global _link_service
    if _link_service is None:
        _link_service = LinkService()
    return _link_service
