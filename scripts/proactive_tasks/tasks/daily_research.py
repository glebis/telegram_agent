#!/usr/bin/env python3
"""
Daily Research Task

Runs Claude with a research prompt, enriches with images,
generates mobile-friendly PDF, and delivers via Telegram.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from scripts.proactive_tasks.base_task import BaseTask, TaskResult

logger = logging.getLogger(__name__)

# Default timeout for Claude research (10 minutes)
CLAUDE_RESEARCH_TIMEOUT = 600


class DailyResearchTask(BaseTask):
    """
    Daily research task that:
    1. Selects a research topic (rotating through configured list)
    2. Runs Claude Code with web search to research the topic
    3. Enriches markdown with relevant images
    4. Generates mobile-friendly PDF
    5. Links to Obsidian daily page
    6. Sends PDF + summary via Telegram
    """

    @property
    def name(self) -> str:
        return "daily-research"

    @property
    def description(self) -> str:
        return "Claude-powered research on configurable topics with PDF delivery"

    def validate_config(self) -> List[str]:
        """Validate required configuration."""
        errors = []

        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            errors.append("Missing TELEGRAM_BOT_TOKEN environment variable")

        # Check for topics
        topics = self.config.get("topics", [])
        if not topics:
            errors.append("No research topics configured")

        return errors

    def _get_today_topic(self) -> str:
        """Select today's research topic (rotates through list by day of year)."""
        topics = self.config.get("topics", [])
        if not topics:
            return "AI and technology developments"

        day_of_year = datetime.now().timetuple().tm_yday
        index = day_of_year % len(topics)
        return topics[index]

    def _get_output_paths(self) -> Dict[str, Path]:
        """Generate output file paths for today."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        vault_path = Path(self.config.get("vault_path", "~/Research/vault")).expanduser()
        research_folder = self.config.get("research_folder", "Research/daily")

        output_dir = vault_path / research_folder
        output_dir.mkdir(parents=True, exist_ok=True)

        return {
            "markdown": output_dir / f"{date_str}-research.md",
            "pdf": output_dir / f"{date_str}-research-mobile.pdf",
            "images_dir": output_dir / "images",
        }

    def _build_research_prompt(self, topic: str) -> str:
        """Build the research prompt for Claude.

        Supports:
        1. Custom prompt file (prompt_file config option)
        2. Built-in default template

        Template variables:
        - {topic} - The research topic
        - {date} - Today's date
        - {output_path} - Path to save the report
        """
        today = datetime.now().strftime("%B %d, %Y")
        output_path = str(self._get_output_paths()["markdown"])

        # Check for custom prompt file
        prompt_file = self.config.get("prompt_file")
        if prompt_file:
            prompt_path = Path(prompt_file).expanduser()
            if prompt_path.exists():
                logger.info(f"Loading prompt from: {prompt_path}")
                template = prompt_path.read_text(encoding="utf-8")
                # Replace template variables
                return template.format(
                    topic=topic,
                    date=today,
                    output_path=output_path,
                )
            else:
                logger.warning(f"Prompt file not found: {prompt_path}, using default")

        # Default built-in prompt
        return f"""You are conducting daily research on: **{topic}**

Date: {today}

Please research this topic thoroughly using web search and provide a comprehensive report.

## Research Guidelines

1. **Search for recent developments** (2025-2026) on this topic
2. **Find specific examples, tools, or projects** that are noteworthy
3. **Include practical insights** that can be applied immediately
4. **Cite sources** where relevant

## Output Format

Write the research as a well-structured markdown document with:

1. **Executive Summary** (2-3 sentences)
2. **Key Developments** - What's new and noteworthy
3. **Notable Projects/Tools** - Specific examples with brief descriptions
4. **Practical Applications** - How to apply these insights
5. **Resources** - Links and references for further reading

Keep the report focused and actionable. Aim for 800-1500 words.

Save the final report to: {output_path}
"""

    async def _run_claude_research(self, topic: str, output_path: Path) -> tuple[bool, str]:
        """Run Claude Code SDK to research the topic."""
        prompt = self._build_research_prompt(topic)
        model = self.config.get("model", "sonnet")
        timeout = self.config.get("timeout", CLAUDE_RESEARCH_TIMEOUT)

        # Tools Claude can use for research
        allowed_tools = self.config.get("allowed_tools", [
            "WebSearch",
            "WebFetch",
            "Read",
            "Write",
            "Glob",
            "Grep",
        ])

        # Build the subprocess script
        script = self._build_claude_script(prompt, model, allowed_tools, str(output_path))

        logger.info(f"Running Claude research on: {topic}")
        logger.info(f"Model: {model}, Timeout: {timeout}s")

        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-c", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(output_path.parent),
                env={**os.environ, "ANTHROPIC_API_KEY": ""},  # Use subscription
            )

            collected_text = []

            while True:
                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Claude research timed out after {timeout}s")
                    process.kill()
                    return False, "Research timed out"

                if not line:
                    break

                line = line.decode().strip()
                if not line:
                    continue

                try:
                    msg = json.loads(line)
                    msg_type = msg.get("type")
                    content = msg.get("content", "")

                    if msg_type == "text":
                        collected_text.append(content)
                        logger.debug(f"Claude: {content[:100]}...")
                    elif msg_type == "tool":
                        logger.info(f"Claude tool: {content}")
                    elif msg_type == "done":
                        cost = msg.get("cost", 0)
                        logger.info(f"Claude completed. Cost: ${cost:.4f}")
                    elif msg_type == "error":
                        logger.error(f"Claude error: {content}")
                        return False, content
                except json.JSONDecodeError:
                    logger.debug(f"Non-JSON output: {line}")

            await process.wait()

            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Claude subprocess failed: {error_msg}")
                return False, error_msg[:500]

            # Check if output file was created
            if output_path.exists():
                logger.info(f"Research saved to: {output_path}")
                return True, "\n".join(collected_text)
            else:
                # Claude might have output text but not saved - save it ourselves
                if collected_text:
                    full_text = "\n".join(collected_text)
                    output_path.write_text(full_text, encoding="utf-8")
                    logger.info(f"Saved collected text to: {output_path}")
                    return True, full_text
                return False, "No output generated"

        except Exception as e:
            logger.error(f"Claude research failed: {e}")
            return False, str(e)

    def _build_claude_script(
        self,
        prompt: str,
        model: str,
        allowed_tools: list,
        output_path: str,
    ) -> str:
        """Build the Python script to run Claude in subprocess."""
        prompt_escaped = json.dumps(prompt)
        tools_escaped = json.dumps(allowed_tools)
        cwd = str(Path(output_path).parent)

        return f'''
import asyncio
import json
import os
import sys

os.environ.pop("ANTHROPIC_API_KEY", None)

from claude_code_sdk import query, ClaudeCodeOptions
from claude_code_sdk.types import AssistantMessage, SystemMessage, ResultMessage, TextBlock, ToolUseBlock

async def run():
    prompt = {prompt_escaped}
    cwd = {json.dumps(cwd)}
    model = {json.dumps(model)}
    allowed_tools = {tools_escaped}

    options = ClaudeCodeOptions(
        cwd=cwd,
        allowed_tools=allowed_tools,
        model=model,
    )

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, SystemMessage):
                if message.subtype == "init" and message.data:
                    session_id = message.data.get("session_id")
                    print(json.dumps({{"type": "init", "session_id": session_id}}))
                    sys.stdout.flush()

            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(json.dumps({{"type": "text", "content": block.text}}))
                        sys.stdout.flush()
                    elif isinstance(block, ToolUseBlock):
                        tool_info = f"{{block.name}}: {{str(block.input)[:100]}}"
                        print(json.dumps({{"type": "tool", "content": tool_info}}))
                        sys.stdout.flush()

            elif isinstance(message, ResultMessage):
                print(json.dumps({{
                    "type": "done",
                    "session_id": message.session_id,
                    "turns": message.num_turns,
                    "cost": message.total_cost_usd,
                }}))
                sys.stdout.flush()

    except Exception as e:
        print(json.dumps({{"type": "error", "content": str(e)}}))
        sys.stdout.flush()
        sys.exit(1)

asyncio.run(run())
'''

    def _enrich_with_images(self, markdown_path: Path, images_dir: Path) -> bool:
        """Add relevant images to the research document."""
        if not self.config.get("enrich_with_images", True):
            return True

        settings = getattr(self, "_registry", {}).get("settings", {})
        image_search_script = Path(
            settings.get("skills", {}).get(
                "google_image_search",
                "~/.claude/skills/google-image-search/scripts/google_image_search.py"
            )
        ).expanduser()

        if not image_search_script.exists():
            logger.warning(f"Image search script not found: {image_search_script}")
            return True

        if not os.getenv("GOOGLE_API_KEY") or not os.getenv("GOOGLE_SEARCH_CX"):
            logger.warning("Missing Google API credentials, skipping image enrichment")
            return True

        try:
            logger.info(f"Enriching with images: {markdown_path}")
            images_dir.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    "/opt/homebrew/bin/python3.11",
                    str(image_search_script),
                    "--enrich-note", str(markdown_path),
                    "--output-dir", str(images_dir),
                    "--num-results", str(self.config.get("image_count", 3)),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                logger.warning(f"Image enrichment had issues: {result.stderr}")

            return True

        except Exception as e:
            logger.warning(f"Image enrichment failed (non-fatal): {e}")
            return True

    def _generate_pdf(self, markdown_path: Path, pdf_path: Path) -> bool:
        """Generate mobile-friendly PDF from markdown."""
        if not self.config.get("generate_pdf", True):
            return True

        settings = getattr(self, "_registry", {}).get("settings", {})
        pdf_script = Path(
            settings.get("skills", {}).get(
                "pdf_generation",
                "~/.claude/skills/pdf-generation/scripts/generate_pdf.py"
            )
        ).expanduser()

        if not pdf_script.exists():
            logger.warning(f"PDF generation script not found: {pdf_script}")
            return False

        try:
            logger.info(f"Generating PDF: {pdf_path}")

            cmd = [
                "/opt/homebrew/bin/python3.11",
                str(pdf_script),
                str(markdown_path),
                "-o", str(pdf_path),
                "--theme", "research",
            ]

            if self.config.get("pdf_mobile_friendly", True):
                cmd.append("--mobile")

            # Add TeX bin directory to PATH for xelatex
            env = os.environ.copy()
            tex_bin_paths = [
                "/Library/TeX/texbin",
                "/usr/local/texlive/2025basic/bin/universal-darwin",
                "/usr/local/texlive/2024basic/bin/universal-darwin",
            ]
            # Find first existing path and add to PATH
            for tex_path in tex_bin_paths:
                if Path(tex_path).exists():
                    env["PATH"] = f"{tex_path}:{env.get('PATH', '')}"
                    break

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )

            if result.returncode != 0:
                logger.error(f"PDF generation failed: {result.stderr}")
                logger.error(f"PDF stdout: {result.stdout}")
                return False

            if pdf_path.exists():
                logger.info(f"PDF generated successfully: {pdf_path}")
                return True
            else:
                logger.error(f"PDF file not created at: {pdf_path}")
                return False

        except Exception as e:
            logger.error(f"PDF generation failed: {e}")
            return False

    def _link_to_daily_page(self, markdown_path: Path, topic: str) -> bool:
        """Add link to today's Obsidian daily note. Creates note if it doesn't exist."""
        if not self.config.get("link_to_daily_page", True):
            return True

        vault_path = Path(self.config.get("vault_path", "~/Research/vault")).expanduser()
        daily_notes_path = vault_path / "Daily"
        today_str = datetime.now().strftime('%Y%m%d')  # YYYYMMDD format
        today_note = daily_notes_path / f"{today_str}.md"

        try:
            # Create daily note if it doesn't exist
            if not today_note.exists():
                daily_notes_path.mkdir(parents=True, exist_ok=True)
                weekday = datetime.now().strftime('%A')
                month_day = datetime.now().strftime('%B %d, %Y')

                # Create basic daily note template
                template = f"""---
creation date: [[{today_str}]]
modification date: [[{today_str}]]
---


%% write here ↑ %%

### Current Phase Checkpoint

- [[Community Building — Current Phase]]


## do



- - -

← [[{int(today_str)-1}]] | [[{datetime.now().strftime('%Y-W%U')}]] | [[{int(today_str)+1}]] →


- - -
## log




## Research

## Notes

"""
                today_note.write_text(template, encoding="utf-8")
                logger.info(f"Created daily note: {today_note}")

            # Add research link with proper markdown formatting
            # Use relative path from Daily folder for wikilink
            relative_path = os.path.relpath(markdown_path, daily_notes_path)
            # Remove .md extension for wikilink
            wikilink_path = relative_path.replace('.md', '')

            content = today_note.read_text()

            import re
            # Format: - [[../Research/daily/2026-01-21-research|Creative coding and generative art techniques]]
            research_link = f"- [[{wikilink_path}|{topic}]]"

            # Check if link already exists
            if wikilink_path in content:
                logger.info(f"Research already linked in daily note")
                return True

            if "## Research" in content:
                # Insert link after ## Research header
                content = re.sub(
                    r"(## Research\n\n?)",
                    f"\\1{research_link}\n",
                    content,
                )
            else:
                content += f"\n\n## Research\n\n{research_link}\n"

            today_note.write_text(content, encoding='utf-8')
            logger.info(f"Linked research to daily note: {today_note}")
            return True

        except Exception as e:
            logger.warning(f"Failed to link to daily page (non-fatal): {e}")
            return True

    async def _send_telegram_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send message via Telegram."""
        task_config = getattr(self, "_task_config", {})
        telegram_config = task_config.get("telegram", {})

        if not telegram_config.get("enabled", True):
            return True

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = telegram_config.get("chat_id", 161427550)

        if not token:
            logger.error("Missing TELEGRAM_BOT_TOKEN")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                ) as resp:
                    if resp.status == 200:
                        logger.info("Telegram message sent")
                        return True
                    else:
                        logger.error(f"Telegram send failed: {await resp.text()}")
                        return False
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def _send_telegram_document(self, file_path: Path, caption: str = "") -> bool:
        """Send document via Telegram."""
        task_config = getattr(self, "_task_config", {})
        telegram_config = task_config.get("telegram", {})

        if not telegram_config.get("send_pdf", True):
            return True

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = telegram_config.get("chat_id", 161427550)

        if not token or not file_path.exists():
            return False

        try:
            async with aiohttp.ClientSession() as session:
                with open(file_path, 'rb') as f:
                    data = aiohttp.FormData()
                    data.add_field('chat_id', str(chat_id))
                    data.add_field('document', f, filename=file_path.name)
                    if caption:
                        data.add_field('caption', caption[:1024])
                        data.add_field('parse_mode', 'HTML')

                    async with session.post(
                        f"https://api.telegram.org/bot{token}/sendDocument",
                        data=data,
                    ) as resp:
                        if resp.status == 200:
                            logger.info(f"Telegram document sent: {file_path.name}")
                            return True
                        else:
                            logger.error(f"Telegram document send failed: {await resp.text()}")
                            return False
        except Exception as e:
            logger.error(f"Telegram document send failed: {e}")
            return False

    def _generate_summary(self, markdown_path: Path, topic: str) -> str:
        """Generate HTML summary for Telegram with key trends and note link."""
        today = datetime.now().strftime("%B %d, %Y")
        date_str = datetime.now().strftime("%Y-%m-%d")

        # Generate Telegram link to the note (without .md extension)
        note_link = f"Research/daily/{date_str}-research"

        if markdown_path.exists():
            content = markdown_path.read_text()

            # Extract executive summary (first non-frontmatter section)
            lines = content.split('\n')
            exec_summary = []
            in_frontmatter = False
            in_exec = False

            for line in lines:
                if line.strip() == '---':
                    in_frontmatter = not in_frontmatter
                    continue
                if in_frontmatter:
                    continue
                if '## Executive Summary' in line:
                    in_exec = True
                    continue
                if in_exec:
                    if line.startswith('##'):
                        break
                    if line.strip():
                        exec_summary.append(line.strip())

            # Extract key trends from headers
            key_trends = []
            for line in lines:
                if line.startswith('### ') and not line.startswith('### Key Articles'):
                    trend = line.replace('###', '').strip()
                    # Remove numbering
                    trend = trend.split('. ', 1)[-1] if '. ' in trend else trend
                    key_trends.append(trend)

            # Build summary text
            summary_text = ' '.join(exec_summary[:3])[:400]
            if len(summary_text) == 400:
                summary_text += "..."

            # Format key trends
            trends_text = ""
            if key_trends:
                trends_text = "\n\n<b>Key Trends:</b>\n" + "\n".join([f"• {t}" for t in key_trends[:5]])
        else:
            summary_text = "Research document generated."
            trends_text = ""

        return f"""<b>📊 Daily Research Report</b>
<i>{today}</i>

<b>Topic:</b> {topic}

{summary_text}{trends_text}

📄 Full report: {note_link}
📎 PDF attached below"""

    async def execute(self) -> TaskResult:
        """Execute the daily research task."""
        outputs = {}
        files = []
        errors = []

        # Get today's topic
        topic = self._get_today_topic()
        outputs["topic"] = topic
        logger.info(f"Today's research topic: {topic}")

        # Get output paths
        paths = self._get_output_paths()
        markdown_path = paths["markdown"]
        pdf_path = paths["pdf"]
        images_dir = paths["images_dir"]

        # Step 1: Run Claude research
        success, result_text = await self._run_claude_research(topic, markdown_path)
        if not success:
            return TaskResult(
                success=False,
                message="Claude research failed",
                errors=[result_text],
            )

        files.append(markdown_path)
        outputs["markdown_path"] = str(markdown_path)

        # Step 2: Enrich with images
        self._enrich_with_images(markdown_path, images_dir)

        # Step 3: Generate PDF
        if self._generate_pdf(markdown_path, pdf_path):
            files.append(pdf_path)
            outputs["pdf_path"] = str(pdf_path)
        else:
            errors.append("PDF generation failed (non-fatal)")

        # Step 4: Link to daily page
        self._link_to_daily_page(markdown_path, topic)

        # Step 5: Send via Telegram
        summary = self._generate_summary(markdown_path, topic)
        await self._send_telegram_message(summary)

        if pdf_path.exists():
            await self._send_telegram_document(
                pdf_path,
                caption=f"<b>Daily Research:</b> {topic}"
            )

        return TaskResult(
            success=True,
            message=f"Research completed: {topic}",
            outputs=outputs,
            files=files,
            errors=errors,
        )


# Allow running directly for testing
if __name__ == "__main__":
    import asyncio
    import sys

    project_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(project_root))

    from dotenv import load_dotenv
    load_dotenv(Path.home() / ".env")
    load_dotenv(project_root / ".env")
    load_dotenv(project_root / ".env.local")

    logging.basicConfig(level=logging.INFO)

    task = DailyResearchTask(config={
        "topics": ["AI agents and autonomous systems"],
        "model": "sonnet",
        "timeout": 600,
        "enrich_with_images": False,  # Skip for testing
        "generate_pdf": True,
        "pdf_mobile_friendly": True,
        "vault_path": "~/Research/vault",
        "link_to_daily_page": True,
        "research_folder": "Research/daily",
    })

    result = asyncio.run(task.run())
    print(f"\nResult: {json.dumps(result.to_dict(), indent=2)}")
