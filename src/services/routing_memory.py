"""
Routing memory service - learns and remembers where content should go
Stores routing preferences in a human-readable markdown file
"""

import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)


class RoutingMemory:
    """Learns routing preferences from user choices"""

    def __init__(self, vault_path: Optional[str] = None):
        self.config = self._load_config()
        vault = vault_path or self.config.get("obsidian", {}).get("vault_path", "~/Brains/brain")
        self.vault_path = Path(vault).expanduser()
        self.memory_file = self.vault_path / "meta" / "telegram-routing.md"
        self._ensure_memory_file()

    def _load_config(self) -> Dict:
        """Load routing configuration"""
        config_path = Path(__file__).parent.parent.parent / "config" / "routing.yaml"
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading routing config: {e}")
            return {}

    def _ensure_memory_file(self) -> None:
        """Create memory file if it doesn't exist"""
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.exists():
            initial_content = """---
description: Telegram bot routing memory - tracks where content gets saved
updated: {date}
---

# Routing Memory

This file tracks routing preferences learned from your choices.
The bot uses this to suggest default destinations for similar content.

## Domains

<!-- Format: domain -> destination (count) -->

## Content Types

<!-- Format: type -> destination (count) -->
- links -> inbox (default)
- voice -> daily (default)
- images -> inbox (default)

## Recent Routes

<!-- Last 20 routing decisions -->

""".format(date=datetime.now().strftime("%Y-%m-%d"))
            with open(self.memory_file, "w", encoding="utf-8") as f:
                f.write(initial_content)
            logger.info(f"Created routing memory file: {self.memory_file}")

    def _parse_memory(self) -> Dict:
        """Parse the memory file into structured data"""
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                content = f.read()

            memory = {
                "domains": {},
                "content_types": {},
                "recent": []
            }

            # Parse domains section
            domains_match = re.search(
                r"## Domains\n(.*?)(?=\n## |\Z)",
                content,
                re.DOTALL
            )
            if domains_match:
                for line in domains_match.group(1).strip().split("\n"):
                    match = re.match(r"- (\S+) -> (\S+) \((\d+)\)", line)
                    if match:
                        domain, dest, count = match.groups()
                        memory["domains"][domain] = {"destination": dest, "count": int(count)}

            # Parse content types section
            types_match = re.search(
                r"## Content Types\n(.*?)(?=\n## |\Z)",
                content,
                re.DOTALL
            )
            if types_match:
                for line in types_match.group(1).strip().split("\n"):
                    match = re.match(r"- (\S+) -> (\S+)(?: \((\d+|default)\))?", line)
                    if match:
                        ctype, dest, count = match.groups()
                        count_val = 0 if count == "default" or count is None else int(count)
                        memory["content_types"][ctype] = {"destination": dest, "count": count_val}

            # Parse recent routes
            recent_match = re.search(
                r"## Recent Routes\n(.*?)(?=\n## |\Z)",
                content,
                re.DOTALL
            )
            if recent_match:
                for line in recent_match.group(1).strip().split("\n"):
                    if line.startswith("- ") and " | " in line:
                        memory["recent"].append(line[2:])

            return memory

        except Exception as e:
            logger.error(f"Error parsing memory file: {e}")
            return {"domains": {}, "content_types": {}, "recent": []}

    def _save_memory(self, memory: Dict) -> None:
        """Save structured data back to memory file"""
        try:
            # Build domains section
            domains_lines = ["<!-- Format: domain -> destination (count) -->"]
            for domain, info in sorted(memory["domains"].items(), key=lambda x: -x[1]["count"]):
                domains_lines.append(f"- {domain} -> {info['destination']} ({info['count']})")

            # Build content types section
            types_lines = ["<!-- Format: type -> destination (count) -->"]
            for ctype, info in memory["content_types"].items():
                count_str = "default" if info["count"] == 0 else str(info["count"])
                types_lines.append(f"- {ctype} -> {info['destination']} ({count_str})")

            # Build recent section (keep last 20)
            recent_lines = ["<!-- Last 20 routing decisions -->"]
            for item in memory["recent"][-20:]:
                recent_lines.append(f"- {item}")

            content = f"""---
description: Telegram bot routing memory - tracks where content gets saved
updated: {datetime.now().strftime("%Y-%m-%d")}
---

# Routing Memory

This file tracks routing preferences learned from your choices.
The bot uses this to suggest default destinations for similar content.

## Domains

{chr(10).join(domains_lines)}

## Content Types

{chr(10).join(types_lines)}

## Recent Routes

{chr(10).join(recent_lines)}

"""
            with open(self.memory_file, "w", encoding="utf-8") as f:
                f.write(content)

        except Exception as e:
            logger.error(f"Error saving memory file: {e}")

    def get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:
            return "unknown"

    def get_suggested_destination(
        self,
        url: Optional[str] = None,
        content_type: str = "links"
    ) -> str:
        """Get suggested destination based on history"""
        memory = self._parse_memory()

        # Check domain-specific routing first
        if url:
            domain = self.get_domain(url)
            if domain in memory["domains"]:
                dest = memory["domains"][domain]["destination"]
                logger.info(f"Suggesting {dest} for domain {domain} (learned)")
                return dest

        # Fall back to content type default
        if content_type in memory["content_types"]:
            return memory["content_types"][content_type]["destination"]

        return "inbox"

    def record_route(
        self,
        destination: str,
        content_type: str = "links",
        url: Optional[str] = None,
        title: Optional[str] = None
    ) -> None:
        """Record a routing decision to learn from"""
        memory = self._parse_memory()

        # Update domain count
        if url:
            domain = self.get_domain(url)
            if domain not in memory["domains"]:
                memory["domains"][domain] = {"destination": destination, "count": 0}

            memory["domains"][domain]["count"] += 1
            # Update destination if this is a new choice
            memory["domains"][domain]["destination"] = destination

        # Update content type count
        if content_type not in memory["content_types"]:
            memory["content_types"][content_type] = {"destination": "inbox", "count": 0}
        memory["content_types"][content_type]["count"] += 1
        memory["content_types"][content_type]["destination"] = destination

        # Add to recent
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        domain = self.get_domain(url) if url else "n/a"
        title_short = (title[:40] + "...") if title and len(title) > 40 else (title or "untitled")
        memory["recent"].append(f"{timestamp} | {content_type} | {domain} | {destination} | {title_short}")

        self._save_memory(memory)
        logger.info(f"Recorded route: {content_type} from {domain} -> {destination}")


# Global service instance
_routing_memory: Optional[RoutingMemory] = None


def get_routing_memory() -> RoutingMemory:
    """Get the global routing memory instance"""
    global _routing_memory
    if _routing_memory is None:
        _routing_memory = RoutingMemory()
    return _routing_memory
