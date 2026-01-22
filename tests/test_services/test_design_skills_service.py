"""Tests for design skills service."""

import pytest
from pathlib import Path

from src.services.design_skills_service import (
    DesignSkillsService,
    get_design_skills_service,
    get_design_system_prompt,
)


@pytest.fixture
def design_service():
    """Get design skills service instance."""
    return DesignSkillsService()


class TestDesignSkillsService:
    """Test design skills service functionality."""

    def test_service_initialization(self, design_service):
        """Test service initializes correctly."""
        assert design_service.config is not None
        assert "design_skills" in design_service.config
        assert "integration" in design_service.config

    def test_config_loading(self, design_service):
        """Test config loads with expected skills."""
        skills = design_service.config.get("design_skills", {})

        assert "impeccable_style" in skills
        assert "ui_skills" in skills
        assert "rams_ai" in skills

    def test_should_apply_design_skills_ui_keywords(self, design_service):
        """Test design skills detection with UI-related keywords."""
        test_cases = [
            ("build a login form", True),
            ("create a navigation component", True),
            ("design a button", True),
            ("style the interface", True),
            ("make it accessible", True),
            ("implement the API endpoint", False),
            ("write database migration", False),
        ]

        for prompt, expected in test_cases:
            result = design_service.should_apply_design_skills(prompt)
            assert result == expected, f"Failed for prompt: {prompt}"

    def test_should_apply_design_skills_triggers(self, design_service):
        """Test design skills detection with config triggers."""
        prompt = "building UI components for the dashboard"
        assert design_service.should_apply_design_skills(prompt) is True

    def test_get_impeccable_style_prompt(self, design_service):
        """Test Impeccable Style prompt generation."""
        prompt = design_service.get_impeccable_style_prompt()

        if prompt:  # If enabled in config
            assert "Design Fluency" in prompt or "Impeccable Style" in prompt
            assert len(prompt) > 0

    def test_get_ui_skills_prompt(self, design_service):
        """Test UI Skills prompt generation."""
        prompt = design_service.get_ui_skills_prompt()

        if prompt:  # If enabled in config
            assert "UI Best Practices" in prompt or "UI Skills" in prompt
            assert len(prompt) > 0

    def test_get_rams_ai_prompt(self, design_service):
        """Test Rams.ai prompt generation."""
        prompt = design_service.get_rams_ai_prompt()

        if prompt:  # If enabled in config
            assert "Design Review" in prompt or "Rams.ai" in prompt
            assert "accessibility" in prompt.lower() or len(prompt) == 0

    def test_get_enhanced_system_prompt(self, design_service):
        """Test complete enhanced system prompt."""
        prompt = design_service.get_enhanced_system_prompt()

        # Should contain at least one section if skills are enabled
        if prompt:
            assert "DESIGN" in prompt.upper()

    def test_get_review_prompt(self, design_service):
        """Test review prompt generation."""
        prompt = design_service.get_review_prompt()

        if prompt:
            assert "review" in prompt.lower()

    def test_format_design_context_enhancement(self, design_service):
        """Test design context formatting with enhancement."""
        original_prompt = "Build a responsive login form"
        enhanced, was_enhanced = design_service.format_design_context(original_prompt)

        assert was_enhanced is True
        assert original_prompt in enhanced

    def test_format_design_context_no_enhancement(self, design_service):
        """Test design context formatting without enhancement."""
        original_prompt = "Run database migration"
        enhanced, was_enhanced = design_service.format_design_context(original_prompt)

        assert was_enhanced is False
        assert enhanced == original_prompt

    def test_format_design_context_with_review(self, design_service):
        """Test design context with review checklist."""
        original_prompt = "Build a button component"
        enhanced, was_enhanced = design_service.format_design_context(
            original_prompt, include_review=True
        )

        if was_enhanced:
            # Should include review section if Rams.ai is enabled
            assert len(enhanced) >= len(original_prompt)


class TestGlobalInstance:
    """Test global instance management."""

    def test_get_design_skills_service(self):
        """Test global service getter."""
        service1 = get_design_skills_service()
        service2 = get_design_skills_service()

        # Should return the same instance
        assert service1 is service2

    def test_get_design_system_prompt(self):
        """Test global system prompt getter."""
        prompt = get_design_system_prompt()

        # Should return a string (may be empty if no skills enabled)
        assert isinstance(prompt, str)


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_config_file(self, tmp_path):
        """Test service handles missing config file gracefully."""
        nonexistent_path = tmp_path / "nonexistent.yaml"
        service = DesignSkillsService(config_path=str(nonexistent_path))

        # Should have empty config
        assert service.config == {"design_skills": {}, "integration": {}}

    def test_empty_prompt(self, design_service):
        """Test handling of empty prompt."""
        result = design_service.should_apply_design_skills("")
        assert result is False

    def test_case_insensitive_detection(self, design_service):
        """Test case-insensitive keyword detection."""
        prompts = [
            "Build a UI component",
            "BUILD A UI COMPONENT",
            "build a ui component",
        ]

        for prompt in prompts:
            assert design_service.should_apply_design_skills(prompt) is True
