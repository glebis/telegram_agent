"""
Design Skills Service for Claude Code Integration

Integrates design guidance from:
- Impeccable Style (https://impeccable.style/)
- UI Skills (http://ui-skills.com)
- Rams.ai (https://www.rams.ai/)

Enhances Claude Code prompts with design principles and best practices.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


class DesignSkillsService:
    """Service for integrating design skills with Claude Code."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize design skills service."""
        if config_path is None:
            config_path = (
                Path(__file__).parent.parent.parent / "config" / "design_skills.yaml"
            )
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load design skills configuration."""
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading design skills config: {e}")
            return {"design_skills": {}, "integration": {}}

    def should_apply_design_skills(self, prompt: str) -> bool:
        """
        Determine if design skills should be applied based on prompt content.

        Args:
            prompt: User prompt to analyze

        Returns:
            True if design skills are relevant
        """
        triggers = self.config.get("integration", {}).get("triggers", [])
        prompt_lower = prompt.lower()

        # Check for design-related keywords
        design_keywords = [
            "ui",
            "interface",
            "design",
            "style",
            "component",
            "button",
            "form",
            "navigation",
            "layout",
            "accessibility",
            "accessible",
            "responsive",
            "web",
            "frontend",
            "css",
            "html",
        ]

        # Check triggers from config
        for trigger in triggers:
            if trigger.lower() in prompt_lower:
                return True

        # Check design keywords
        for keyword in design_keywords:
            if keyword in prompt_lower:
                return True

        return False

    def get_impeccable_style_prompt(self) -> str:
        """Get Impeccable Style design guidance prompt."""
        impeccable = self.config.get("design_skills", {}).get("impeccable_style", {})

        if not impeccable.get("enabled", False):
            return ""

        skills = impeccable.get("skills", [])
        if not skills:
            return ""

        prompt_parts = [
            "## Design Fluency (Impeccable Style)",
            "",
            "Apply these design principles:",
            "",
        ]

        for skill in skills:
            name = skill.get("name", "").replace("_", " ").title()
            skill_prompt = skill.get("prompt", "").strip()
            prompt_parts.append(f"### {name}")
            prompt_parts.append(skill_prompt)
            prompt_parts.append("")

        return "\n".join(prompt_parts)

    def get_ui_skills_prompt(self) -> str:
        """Get UI Skills constraints prompt."""
        ui_skills = self.config.get("design_skills", {}).get("ui_skills", {})

        if not ui_skills.get("enabled", False):
            return ""

        constraints = ui_skills.get("constraints", [])
        if not constraints:
            return ""

        prompt_parts = [
            "## UI Best Practices (UI Skills)",
            "",
            "Follow these constraints to avoid common UI pitfalls:",
            "",
        ]

        for constraint in constraints:
            name = constraint.get("name", "").replace("_", " ").title()
            rule = constraint.get("rule", "")
            rationale = constraint.get("rationale", "")

            prompt_parts.append(f"**{name}**: {rule}")
            if rationale:
                prompt_parts.append(f"  _Why: {rationale}_")
            prompt_parts.append("")

        return "\n".join(prompt_parts)

    def get_rams_ai_prompt(self) -> str:
        """Get Rams.ai review checklist prompt."""
        rams = self.config.get("design_skills", {}).get("rams_ai", {})

        if not rams.get("enabled", False):
            return ""

        checklist = rams.get("review_checklist", {})
        if not checklist:
            return ""

        prompt_parts = [
            "## Design Review Checklist (Rams.ai)",
            "",
            "Review your implementation against these criteria:",
            "",
        ]

        for category, items in checklist.items():
            category_name = category.replace("_", " ").title()
            prompt_parts.append(f"### {category_name}")

            for item in items:
                prompt_parts.append(f"- {item}")

            prompt_parts.append("")

        return "\n".join(prompt_parts)

    def get_enhanced_system_prompt(self) -> str:
        """
        Get complete design skills enhancement for system prompt.

        Returns:
            Enhanced system prompt with all design guidance
        """
        parts = []

        impeccable = self.get_impeccable_style_prompt()
        if impeccable:
            parts.append(impeccable)

        ui_skills = self.get_ui_skills_prompt()
        if ui_skills:
            parts.append(ui_skills)

        rams = self.get_rams_ai_prompt()
        if rams:
            parts.append(rams)

        if not parts:
            return ""

        return "\n\n".join(
            [
                "# DESIGN GUIDANCE",
                "",
                "When building user interfaces, follow these design principles and best practices:",
                "",
            ]
            + parts
        )

    def get_review_prompt(self) -> str:
        """
        Get a prompt for reviewing existing UI/design work.

        Returns:
            Review prompt based on Rams.ai checklist
        """
        rams = self.config.get("design_skills", {}).get("rams_ai", {})
        checklist = rams.get("review_checklist", {})

        if not checklist:
            return ""

        prompt_parts = [
            "Please review the UI implementation for:",
            "",
        ]

        for category, items in checklist.items():
            category_name = category.replace("_", " ").title()
            prompt_parts.append(f"**{category_name}**:")

            for item in items:
                prompt_parts.append(f"  - [ ] {item}")

            prompt_parts.append("")

        prompt_parts.append(
            "Identify any issues and offer specific fixes with code examples."
        )

        return "\n".join(prompt_parts)

    def format_design_context(
        self, prompt: str, include_review: bool = False
    ) -> tuple[str, bool]:
        """
        Format design context for a given prompt.

        Args:
            prompt: User's original prompt
            include_review: If True, add review checklist to the prompt

        Returns:
            Tuple of (enhanced_prompt, was_enhanced)
        """
        if not self.should_apply_design_skills(prompt):
            return prompt, False

        # Build enhanced prompt
        parts = [prompt]

        # Add review checklist if requested
        if include_review:
            review = self.get_review_prompt()
            if review:
                parts.append("\n\n---\n")
                parts.append(review)

        return "\n".join(parts), True


# Global instance
_design_skills_service: Optional[DesignSkillsService] = None


def get_design_skills_service() -> DesignSkillsService:
    """Get the global design skills service instance."""
    global _design_skills_service
    if _design_skills_service is None:
        _design_skills_service = DesignSkillsService()
    return _design_skills_service


def get_design_system_prompt() -> str:
    """
    Get design skills system prompt enhancement.

    Returns:
        Design guidance to add to system prompt
    """
    service = get_design_skills_service()
    return service.get_enhanced_system_prompt()
