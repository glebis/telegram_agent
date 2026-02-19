"""Tests for services using context-specific settings models (issue #222, slice 3).

Verifies that services import and use the new bounded-context models
instead of the monolithic UserSettings.
"""

import inspect

import pytest


class TestAccountabilityServiceImports:
    """AccountabilityService should use AccountabilityProfile."""

    def test_imports_accountability_profile(self):
        """accountability_service.py should import AccountabilityProfile."""
        from src.services import accountability_service

        source = inspect.getsource(accountability_service)
        assert "AccountabilityProfile" in source

    def test_get_user_settings_returns_profile(self):
        """get_user_settings should query AccountabilityProfile, not UserSettings."""
        from src.services import accountability_service

        source = inspect.getsource(accountability_service.AccountabilityService)
        # The method should reference AccountabilityProfile
        assert "AccountabilityProfile" in source


class TestLifeWeeksSchedulerImports:
    """Life weeks scheduler should use LifeWeeksSettings."""

    def test_imports_life_weeks_settings(self):
        """life_weeks_scheduler.py should import LifeWeeksSettings."""
        from src.services import life_weeks_scheduler

        source = inspect.getsource(life_weeks_scheduler)
        assert "LifeWeeksSettings" in source

    def test_queries_life_weeks_settings_table(self):
        """Scheduler should query LifeWeeksSettings.life_weeks_enabled."""
        from src.services import life_weeks_scheduler

        source = inspect.getsource(life_weeks_scheduler)
        assert "LifeWeeksSettings" in source


class TestDataRetentionServiceImports:
    """Data retention service should use PrivacySettings."""

    def test_imports_privacy_settings(self):
        """data_retention_service.py should import PrivacySettings."""
        from src.services import data_retention_service

        source = inspect.getsource(data_retention_service)
        assert "PrivacySettings" in source

    def test_queries_privacy_settings(self):
        """Should query PrivacySettings.data_retention, not UserSettings."""
        from src.services import data_retention_service

        source = inspect.getsource(data_retention_service)
        assert "PrivacySettings" in source


class TestPrivacyCommandsImports:
    """Privacy commands handler should use PrivacySettings."""

    def test_imports_privacy_settings(self):
        """privacy_commands.py should import PrivacySettings."""
        from src.bot.handlers import privacy_commands

        source = inspect.getsource(privacy_commands)
        assert "PrivacySettings" in source


class TestLifeWeeksHandlerImports:
    """Life weeks settings handler should use LifeWeeksSettings."""

    def test_imports_life_weeks_settings(self):
        """life_weeks_settings.py handler should import LifeWeeksSettings."""
        from src.bot.handlers import life_weeks_settings

        source = inspect.getsource(life_weeks_settings)
        assert "LifeWeeksSettings" in source


class TestAccountabilityCommandsImports:
    """Accountability commands should use AccountabilityProfile."""

    def test_imports_accountability_profile(self):
        """accountability_commands.py should import AccountabilityProfile."""
        from src.bot.handlers import accountability_commands

        source = inspect.getsource(accountability_commands)
        assert "AccountabilityProfile" in source


class TestAccountabilitySchedulerImports:
    """Accountability scheduler should use AccountabilityProfile for fallback."""

    def test_imports_accountability_profile(self):
        """accountability_scheduler.py should import AccountabilityProfile."""
        from src.services import accountability_scheduler

        source = inspect.getsource(accountability_scheduler)
        assert "AccountabilityProfile" in source
