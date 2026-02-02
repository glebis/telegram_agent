"""Step 3: API keys - optional third-party service credentials."""

import questionary
from rich.console import Console

from scripts.setup_wizard.env_manager import EnvManager

API_KEYS = [
    ("OPENAI_API_KEY", "OpenAI API Key (image analysis)"),
    ("GROQ_API_KEY", "Groq API Key (voice transcription)"),
    ("ANTHROPIC_API_KEY", "Anthropic API Key (Claude Code)"),
]


def run(env: EnvManager, console: Console) -> bool:
    """Collect optional API keys. Returns True always (all optional)."""
    console.print("\n[bold]Step 3/6: API Keys[/bold] (all optional, Enter to skip)")

    for key_name, description in API_KEYS:
        existing = env.get(key_name)
        prompt = description
        if existing:
            prompt += " (already set, Enter to keep)"

        value = questionary.password(prompt).ask()
        if value is None:
            return True  # Ctrl+C on optional keys is not fatal
        if value:
            env.set(key_name, value)

    return True
