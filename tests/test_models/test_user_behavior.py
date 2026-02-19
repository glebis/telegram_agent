"""
Tests for User model domain behavior methods.

These test pure domain logic on model instances — no database needed.
"""

import pytest

from src.models.user import User


class TestUserGetLocale:
    """Tests for User.get_locale()."""

    def test_returns_language_code(self):
        user = User(user_id=1, language_code="ru")
        assert user.get_locale() == "ru"

    def test_returns_default_when_none(self):
        user = User(user_id=1, language_code=None)
        assert user.get_locale() == "en"

    def test_returns_default_when_empty(self):
        user = User(user_id=1, language_code="")
        assert user.get_locale() == "en"

    def test_custom_default(self):
        user = User(user_id=1, language_code=None)
        assert user.get_locale(default="de") == "de"


class TestUserGetDisplayName:
    """Tests for User.get_display_name()."""

    def test_first_and_last(self):
        user = User(user_id=1, first_name="John", last_name="Doe")
        assert user.get_display_name() == "John Doe"

    def test_first_only(self):
        user = User(user_id=1, first_name="John", last_name=None)
        assert user.get_display_name() == "John"

    def test_username_fallback(self):
        user = User(user_id=1, first_name=None, last_name=None, username="johndoe")
        assert user.get_display_name() == "johndoe"

    def test_user_id_fallback(self):
        user = User(user_id=42, first_name=None, last_name=None, username=None)
        assert user.get_display_name() == "User 42"

    def test_first_name_empty_string(self):
        user = User(user_id=1, first_name="", last_name=None, username="johndoe")
        assert user.get_display_name() == "johndoe"

    def test_last_name_only(self):
        user = User(user_id=1, first_name=None, last_name="Doe", username=None)
        assert user.get_display_name() == "Doe"


class TestUserHasConsent:
    """Tests for User.has_consent()."""

    def test_false_by_default(self):
        user = User(user_id=1)
        assert user.has_consent() is False

    def test_true_when_given(self):
        user = User(user_id=1, consent_given=True)
        assert user.has_consent() is True


class TestUserIsBanned:
    """Tests for User.is_banned()."""

    def test_false_by_default(self):
        user = User(user_id=1)
        assert user.is_banned() is False

    def test_true_when_banned(self):
        user = User(user_id=1, banned=True)
        assert user.is_banned() is True
