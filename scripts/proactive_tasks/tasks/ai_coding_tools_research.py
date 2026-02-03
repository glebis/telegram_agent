#!/usr/bin/env python3
"""
AI Coding Tools Daily Research Task

Focused research on Claude Code, Cowork, OpenClaw, Moltbod, Clawdbot:
- News & updates
- Community buzz & discussions
- Technical deep dives
- **Primary focus: Real-world use cases and practical applications**

Outputs comprehensive report with executive summary.
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

CLAUDE_RESEARCH_TIMEOUT = 900  # 15 minutes for comprehensive research


class AICodingToolsResearchTask(BaseTask):
    """
    Daily research on AI coding tools with focus on use cases:
    1. Searches for news, updates, community discussions
    2. Runs Claude Code with web search to research comprehensively
    3. Enriches markdown with relevant images
    4. Generates mobile-friendly PDF
    5. Links to Obsidian daily page
    6. Sends PDF + summary via Telegram
    """

    @property
    def name(self) -> str:
        return "ai-coding-tools-research"

    @property
    def description(self) -> str:
        return "Daily research on Claude Code, Cowork, OpenClaw, Moltbod, Clawdbot with focus on use cases"

    def validate_config(self) -> List[str]:
        """Validate required configuration."""
        errors = []

        if not os.getenv("TELEGRAM_BOT_TOKEN"):
            errors.append("Missing TELEGRAM_BOT_TOKEN environment variable")

        tools = self.config.get("tools", [])
        if not tools:
            errors.append("No AI coding tools configured")

        if self.config.get("enrich_with_images", True):
            missing_google = [
                var for var in ("GOOGLE_API_KEY", "GOOGLE_SEARCH_CX")
                if not os.getenv(var)
            ]
            if missing_google:
                errors.append(
                    "Missing Google Custom Search credentials "
                    f"({', '.join(missing_google)}) for image enrichment "
                    "(set creds or disable enrich_with_images)"
                )

        return errors

    def _get_today_tools(self) -> str:
        """Get today's tools to research (can rotate or research all)."""
        tools = self.config.get("tools", [
            "Claude Code",
            "Cowork",
            "OpenClaw",
            "Moltbod",
            "Clawdbot"
        ])

        # Option 1: Research all tools daily
        if self.config.get("research_all_tools", True):
            return ", ".join(tools)

        # Option 2: Rotate through tools by day of year
        day_of_year = datetime.now().timetuple().tm_yday
        index = day_of_year % len(tools)
        return tools[index]

    def _get_output_paths(self) -> Dict[str, Path]:
        """Generate output file paths for today."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        vault_path = Path(self.config.get("vault_path", "~/Research/vault")).expanduser()
        research_folder = self.config.get("research_folder", "Research/AI-Coding-Tools")

        output_dir = vault_path / research_folder
        output_dir.mkdir(parents=True, exist_ok=True)

        return {
            "markdown": output_dir / f"{date_str}-ai-coding-tools.md",
            "pdf": output_dir / f"{date_str}-ai-coding-tools-mobile.pdf",
            "images_dir": output_dir / "images",
        }

    def _build_research_prompt(self, tools: str) -> str:
        """Build comprehensive research prompt focused on use cases."""
        today = datetime.now().strftime("%B %d, %Y")
        output_path = str(self._get_output_paths()["markdown"])

        return f"""You are conducting comprehensive daily research on AI coding tools: **{tools}**

Date: {today}

## Research Focus

Your PRIMARY focus is on **real-world use cases** - how people are actually using these tools in practice. Additionally cover:

1. **News & Updates** - releases, announcements, feature updates
2. **Community Buzz** - discussions on Twitter/X, Reddit, HackerNews, Discord
3. **Technical Deep Dives** - architecture, capabilities, integrations

## Tools to Research

{tools}

For each tool, find:
- Official repos/websites (search GitHub, official sites)
- Recent releases or announcements
- Community discussions and sentiment
- Technical documentation or architecture details

## Output Format

Create a comprehensive markdown document (~2000-3000 words) with:

### 1. Executive Summary (3-5 sentences)
Brief overview of the most important findings and trends.

### 2. Tool-by-Tool Analysis

For each tool, structure as:

#### [Tool Name]

**Overview** - What it is, current status, key info

**Recent Updates** (if any)
- Release notes, new features, announcements
- Link to sources

**Use Cases & Applications** ⭐ PRIMARY FOCUS
- How people are using it (specific examples)
- Workflows and integrations
- Problem-solving scenarios
- Real user stories from Twitter, Reddit, blogs
- Code examples or demos if available

**Community Buzz**
- What people are saying on social media
- Popular discussions or threads
- Sentiment analysis (excitement, concerns, etc.)

**Technical Insights**
- Architecture or design patterns
- API changes or new capabilities
- Integration with other tools

**Resources**
- GitHub repos
- Documentation
- Blog posts, tutorials
- Community channels

### 3. Cross-Tool Comparison (if relevant)
- How tools compare in capabilities
- Unique strengths of each
- Emerging patterns or trends

### 4. Key Takeaways
- 3-5 actionable insights
- Emerging trends to watch
- Recommended next steps for exploration

## Research Strategy

1. **Start broad**: Use WebSearch to find official sites, GitHub repos, recent news
2. **Go deep on use cases**: Search Twitter/X, Reddit, HackerNews for "how I use [tool]", "building with [tool]", "[tool] workflow"
3. **Find examples**: Look for blog posts, demos, code examples showing real usage
4. **Check technical sources**: Documentation, release notes, technical discussions
5. **Synthesize**: Connect findings into a coherent narrative

## Citation Requirements

- Include links to all sources
- For social media: note platform and rough engagement
- For technical content: link to docs/repos
- For news: link to articles or announcements

## Important Notes

- Focus on 2025-2026 developments (current year)
- Prioritize concrete examples over generic descriptions
- Look for lesser-known use cases, not just official examples
- Include both individual user stories and enterprise applications

Save the final report to: {output_path}
"""

    async def _run_claude_research(self, tools: str, output_path: Path) -> tuple[bool, str]:
        """Run Claude Code SDK to research the tools."""
        prompt = self._build_research_prompt(tools)
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

        logger.info(f"Running Claude research on: {tools}")
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

    def _link_to_daily_page(self, markdown_path: Path, tools: str) -> bool:
        """Add link to today's Obsidian daily note."""
        if not self.config.get("link_to_daily_page", True):
            return True

        vault_path = Path(self.config.get("vault_path", "~/Research/vault")).expanduser()
        daily_notes_path = vault_path / "Daily"
        today_str = datetime.now().strftime('%Y%m%d')
        today_note = daily_notes_path / f"{today_str}.md"

        try:
            if not today_note.exists():
                daily_notes_path.mkdir(parents=True, exist_ok=True)
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

            relative_path = os.path.relpath(markdown_path, daily_notes_path)
            wikilink_path = relative_path.replace('.md', '')

            content = today_note.read_text()

            import re
            research_link = f"- [[{wikilink_path}|AI Coding Tools: {tools}]]"

            if wikilink_path in content:
                logger.info(f"Research already linked in daily note")
                return True

            if "## Research" in content:
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

    def _generate_summary(self, markdown_path: Path, tools: str) -> str:
        """Generate HTML summary for Telegram."""
        today = datetime.now().strftime("%B %d, %Y")
        date_str = datetime.now().strftime("%Y-%m-%d")

        note_link = f"Research/AI-Coding-Tools/{date_str}-ai-coding-tools"

        if markdown_path.exists():
            content = markdown_path.read_text()

            # Extract executive summary
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
                if '## Executive Summary' in line or '### 1. Executive Summary' in line:
                    in_exec = True
                    continue
                if in_exec:
                    if line.startswith('##') or line.startswith('###'):
                        break
                    if line.strip():
                        exec_summary.append(line.strip())

            # Extract key tools mentioned
            tool_sections = []
            for line in lines:
                if line.startswith('#### ') and any(t in line for t in ['Claude', 'Cowork', 'OpenClaw', 'Moltbod', 'Clawdbot']):
                    tool = line.replace('####', '').strip()
                    tool_sections.append(tool)

            summary_text = ' '.join(exec_summary[:3])[:400]
            if len(summary_text) == 400:
                summary_text += "..."

            tools_text = ""
            if tool_sections:
                tools_text = "\n\n<b>Tools Covered:</b>\n" + "\n".join([f"• {t}" for t in tool_sections[:5]])
        else:
            summary_text = "Research document generated."
            tools_text = ""

        return f"""<b>🤖 AI Coding Tools Daily Report</b>
<i>{today}</i>

<b>Focus:</b> {tools}

{summary_text}{tools_text}

📄 Full report: {note_link}
📎 PDF attached below"""

    async def execute(self) -> TaskResult:
        """Execute the AI coding tools research task."""
        outputs = {}
        files = []
        errors = []

        # Get today's tools
        tools = self._get_today_tools()
        outputs["tools"] = tools
        logger.info(f"Today's AI coding tools research: {tools}")

        # Get output paths
        paths = self._get_output_paths()
        markdown_path = paths["markdown"]
        pdf_path = paths["pdf"]
        images_dir = paths["images_dir"]

        # Step 1: Run Claude research
        success, result_text = await self._run_claude_research(tools, markdown_path)
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
        self._link_to_daily_page(markdown_path, tools)

        # Step 5: Send via Telegram
        summary = self._generate_summary(markdown_path, tools)
        await self._send_telegram_message(summary)

        if pdf_path.exists():
            await self._send_telegram_document(
                pdf_path,
                caption=f"<b>AI Coding Tools:</b> {tools}"
            )

        return TaskResult(
            success=True,
            message=f"AI coding tools research completed: {tools}",
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

    task = AICodingToolsResearchTask(config={
        "tools": ["Claude Code", "Cowork", "OpenClaw", "Moltbod", "Clawdbot"],
        "research_all_tools": True,
        "model": "opus",  # Use opus for comprehensive research
        "timeout": 900,  # 15 minutes
        "enrich_with_images": True,
        "image_count": 3,
        "generate_pdf": True,
        "pdf_mobile_friendly": True,
        "vault_path": "~/Research/vault",
        "link_to_daily_page": True,
        "research_folder": "Research/AI-Coding-Tools",
    })

    result = asyncio.run(task.run())
    print(f"\nResult: {json.dumps(result.to_dict(), indent=2)}")
