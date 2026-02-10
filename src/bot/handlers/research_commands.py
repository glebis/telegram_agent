"""
Research commands.

Contains:
- /research <topic> - Execute a deep research session via Claude Code
- /research:help - Show research command help
"""

import logging
import re
import unicodedata
from datetime import date
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ...core.i18n import get_user_locale_from_update, t
from ...services.claude_code_service import (
    is_claude_code_admin,
)
from ...services.claude_subprocess import TimeoutConfig
from .base import initialize_user_chat
from .claude_commands import execute_claude_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vault output helpers
# ---------------------------------------------------------------------------

_RESEARCH_DIR = Path.home() / "Research" / "vault" / "Research" / "on-demand"


def _slugify(text: str, max_length: int = 60) -> str:
    """Convert text to a filesystem-safe slug.

    >>> _slugify("How do AI agents handle tool use?")
    'how-do-ai-agents-handle-tool-use'
    """
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    return text[:max_length].rstrip("-")


def _get_output_path(topic: str) -> str:
    """Return the full vault path for a research report."""
    today = date.today().isoformat()
    slug = _slugify(topic)
    return str(_RESEARCH_DIR / f"{today}-{slug}.md")


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def _build_research_system_prompt() -> str:
    """Build the research-mode system prompt that guides the 4-stage pipeline."""
    return """## RESEARCH MODE

You are conducting a deep research session. Follow this 4-stage pipeline:

### Stage 1 — PLANNING
- Break the topic into 3-5 focused sub-questions
- State your search strategy for each sub-question
- Identify what types of sources will be most valuable

### Stage 2 — SEARCH
- Use WebSearch for each sub-question (use current year 2026 in queries)
- Use WebFetch to read the most promising results in full
- Track ALL source URLs as you go — you will need them for citations
- Search for diverse perspectives: academic papers, industry blogs, official docs, recent news

### Stage 3 — SYNTHESIS
- Cross-reference information across sources
- Identify areas of consensus and disagreement
- Note any gaps in available information
- Distinguish established facts from opinions and speculation

### Stage 4 — REPORT
Write a comprehensive markdown report with this structure:

```markdown
---
created_date: '[[YYYYMMDD]]'
type: research
tags: [research, <relevant-tags>]
topic: "<original topic>"
---

# <Title>

## Executive Summary
<2-3 paragraph overview of key findings>

## Key Findings
<Bulleted list of the most important discoveries>

## Analysis
<Detailed analysis organized by sub-topic, with inline citations [1], [2], etc.>

## Practical Implications
<What this means in practice, actionable takeaways>

## Sources
[1] <URL> — <brief description>
[2] <URL> — <brief description>
...
```

### Post-Report Instructions
After writing the report to the specified vault path:
1. Generate a mobile-optimized PDF using the pdf-generation skill (use the same base filename with -mobile.pdf suffix)
2. Embed the note for vault semantic search: `source /Volumes/LaCie/DataLake/.venv/bin/activate && python3 ~/Research/vault/scripts/embed_note.py "<note_path>"`
3. Find related vault notes: `source /Volumes/LaCie/DataLake/.venv/bin/activate && python3 ~/Research/vault/scripts/vault_search.py "<topic keywords>" -f see-also -n 5`
4. Append a "See Also" section with wikilinks to the most relevant existing notes

### Important Guidelines
- Always use the FULL absolute vault path when referencing notes (the bot converts these to clickable links)
- Include the created_date frontmatter as a wikilink to the daily note (e.g. '[[20260201]]')
- Use inline citations [1], [2] throughout the analysis — never make claims without attribution
- Prefer recent sources (2024-2026) but include seminal older works when relevant
- If a sub-question yields insufficient results, note this explicitly rather than speculating"""


def _build_research_user_prompt(topic: str, output_path: str) -> str:
    """Build the user prompt that wraps the research topic."""
    today = date.today().isoformat()
    return (
        f"Research topic: {topic}\n\n"
        f"Date: {today}\n"
        f"Save report to: {output_path}\n"
        f"Save PDF to: {output_path.replace('.md', '-mobile.pdf')}\n\n"
        f"Begin the 4-stage research pipeline now."
    )


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


async def research_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /research command — deep research via Claude Code."""
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return

    # Parse :subcommand
    raw_text = update.message.text if update.message else ""
    subcommand = None
    remaining_text = ""

    if raw_text.startswith("/research:"):
        after = raw_text[len("/research:") :]
        parts = after.split(None, 1)
        if parts:
            subcommand = parts[0].lower()
            remaining_text = parts[1] if len(parts) > 1 else ""
    else:
        remaining_text = " ".join(context.args) if context.args else ""

    if subcommand == "help":
        await _research_help(update)
        return

    # Admin check
    locale = get_user_locale_from_update(update)
    if not await is_claude_code_admin(chat.id):
        if update.message:
            await update.message.reply_text(t("research.no_permission", locale))
        return

    topic = remaining_text.strip()

    if not topic:
        await _research_help(update)
        return

    logger.info(f"Research command from user {user.id}: topic={topic[:80]}")

    # Initialize user/chat
    await initialize_user_chat(
        user_id=user.id,
        chat_id=chat.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
    )

    await execute_research_prompt(update, context, topic)


async def execute_research_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    topic: str,
) -> None:
    """Build research prompts and execute via Claude Code."""
    output_path = _get_output_path(topic)
    system_prompt = _build_research_system_prompt()
    user_prompt = _build_research_user_prompt(topic, output_path)

    logger.info(f"Starting research: topic={topic[:60]}, output={output_path}")

    # Ensure the output directory exists
    _RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

    # Research tasks need longer timeouts:
    # - 30min per-message (web fetches can be slow)
    # - 60min overall session
    research_timeout = TimeoutConfig(
        message_timeout=1800,   # 30 minutes
        session_timeout=3600,   # 60 minutes
    )

    await execute_claude_prompt(
        update=update,
        context=context,
        prompt=user_prompt,
        force_new=True,
        system_prompt_prefix=system_prompt,
        timeout_config=research_timeout,
    )


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


async def _research_help(update: Update) -> None:
    """Show research command help."""
    locale = get_user_locale_from_update(update)
    if update.message:
        await update.message.reply_text(
            t("research.help_text", locale).strip(),
            parse_mode="HTML",
        )
