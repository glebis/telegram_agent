"""
Work summary service — format Claude work statistics for display.

Extracted from src/bot/handlers/claude_commands.py (#218).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def format_work_summary(stats: Optional[dict], locale: str = "en") -> str:
    """Format work statistics into human-readable summary.

    Args:
        stats: Dictionary with keys like duration, tool_counts, web_fetches,
               skills_used.
        locale: Locale code for i18n translations.

    Returns:
        HTML-formatted summary string, or empty string if no stats.
    """
    if not stats:
        return ""

    from ..core.i18n import t

    parts = []

    # Duration
    duration = stats.get("duration", "")
    if duration:
        parts.append(f"\u23f1\ufe0f {duration}")

    # Tool usage summary
    tool_counts = stats.get("tool_counts", {})
    if tool_counts:
        tool_summary = []
        if tool_counts.get("Read"):
            c = tool_counts["Read"]
            tool_summary.append("\U0001f4d6 " + t("claude.tool_reads", locale, count=c))
        if tool_counts.get("Write") or tool_counts.get("Edit"):
            c = tool_counts.get("Write", 0) + tool_counts.get("Edit", 0)
            tool_summary.append(
                "\u270d\ufe0f " + t("claude.tool_edits", locale, count=c)
            )
        if tool_counts.get("Grep") or tool_counts.get("Glob"):
            c = tool_counts.get("Grep", 0) + tool_counts.get("Glob", 0)
            tool_summary.append(
                "\U0001f50d " + t("claude.tool_searches", locale, count=c)
            )
        if tool_counts.get("Bash"):
            c = tool_counts["Bash"]
            tool_summary.append("\u26a1 " + t("claude.tool_commands", locale, count=c))

        if tool_summary:
            parts.append(" \u00b7 ".join(tool_summary))

    # Web activity
    web_fetches = stats.get("web_fetches", [])
    if web_fetches:
        c = len(web_fetches)
        parts.append("\U0001f310 " + t("claude.tool_web_fetches", locale, count=c))

    # Skills used
    skills = stats.get("skills_used", [])
    if skills:
        skills_str = ", ".join(skills)
        parts.append("\U0001f3af " + t("claude.tool_skills", locale, skills=skills_str))

    if not parts:
        return ""

    return "\n\n<i>" + " \u00b7 ".join(parts) + "</i>"
