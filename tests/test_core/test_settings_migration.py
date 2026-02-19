"""Tests for settings table split migration (issue #222, slice 2).

Verifies that init_database() creates the new context-specific settings
tables and migrates data from the monolithic user_settings table.
"""

import os
import tempfile

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _tmp_db():
    """Create a temporary database file and return (path, url)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{path}"
    return path, url


async def _get_table_names(engine):
    """Return set of table names in database."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        return {row[0] for row in result.fetchall()}


async def _get_column_names(engine, table_name):
    """Return set of column names for a table."""
    async with engine.connect() as conn:
        result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        return {row[1] for row in result.fetchall()}


class TestNewTablesCreated:
    """init_database() should create the 4 new settings tables."""

    @pytest.mark.asyncio
    async def test_voice_settings_table_created(self):
        db_path, db_url = _tmp_db()
        try:
            from unittest.mock import AsyncMock, patch

            with (
                patch("src.core.database.get_database_url", return_value=db_url),
                patch(
                    "src.core.vector_db.get_vector_db",
                    return_value=AsyncMock(initialize_vector_support=AsyncMock()),
                ),
            ):
                from src.core.database import init_database

                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                tables = await _get_table_names(engine)
                assert "voice_settings" in tables
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_accountability_profiles_table_created(self):
        db_path, db_url = _tmp_db()
        try:
            from unittest.mock import AsyncMock, patch

            with (
                patch("src.core.database.get_database_url", return_value=db_url),
                patch(
                    "src.core.vector_db.get_vector_db",
                    return_value=AsyncMock(initialize_vector_support=AsyncMock()),
                ),
            ):
                from src.core.database import init_database

                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                tables = await _get_table_names(engine)
                assert "accountability_profiles" in tables
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_privacy_settings_table_created(self):
        db_path, db_url = _tmp_db()
        try:
            from unittest.mock import AsyncMock, patch

            with (
                patch("src.core.database.get_database_url", return_value=db_url),
                patch(
                    "src.core.vector_db.get_vector_db",
                    return_value=AsyncMock(initialize_vector_support=AsyncMock()),
                ),
            ):
                from src.core.database import init_database

                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                tables = await _get_table_names(engine)
                assert "privacy_settings" in tables
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_life_weeks_settings_table_created(self):
        db_path, db_url = _tmp_db()
        try:
            from unittest.mock import AsyncMock, patch

            with (
                patch("src.core.database.get_database_url", return_value=db_url),
                patch(
                    "src.core.vector_db.get_vector_db",
                    return_value=AsyncMock(initialize_vector_support=AsyncMock()),
                ),
            ):
                from src.core.database import init_database

                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                tables = await _get_table_names(engine)
                assert "life_weeks_settings" in tables
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)


class TestDataMigration:
    """Existing user_settings rows should be copied to new tables."""

    @pytest.mark.asyncio
    async def test_voice_data_migrated(self):
        """Pre-existing voice data in user_settings should be copied to voice_settings."""
        db_path, db_url = _tmp_db()
        try:
            from unittest.mock import AsyncMock, patch

            # Create legacy schema with data
            engine = create_async_engine(db_url, echo=False)
            async with engine.begin() as conn:
                # Minimal tables to satisfy create_all
                await conn.execute(
                    text(
                        "CREATE TABLE users ("
                        "  id INTEGER PRIMARY KEY,"
                        "  user_id INTEGER UNIQUE NOT NULL,"
                        "  username VARCHAR(255),"
                        "  first_name VARCHAR(255),"
                        "  last_name VARCHAR(255),"
                        "  language_code VARCHAR(10),"
                        "  consent_given BOOLEAN DEFAULT 0,"
                        "  consent_given_at DATETIME,"
                        "  banned BOOLEAN DEFAULT 0,"
                        "  user_group VARCHAR(100),"
                        "  admin_notes VARCHAR(1000),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE TABLE user_settings ("
                        "  user_id BIGINT PRIMARY KEY,"
                        "  username VARCHAR(255),"
                        "  voice_enabled BOOLEAN DEFAULT 1,"
                        "  voice_model VARCHAR(50) DEFAULT 'diana',"
                        "  emotion_style VARCHAR(50) DEFAULT 'cheerful',"
                        "  response_mode VARCHAR(50) DEFAULT 'smart',"
                        "  check_in_times TEXT,"
                        "  reminder_style VARCHAR(50) DEFAULT 'gentle',"
                        "  timezone VARCHAR(50) DEFAULT 'UTC',"
                        "  privacy_level VARCHAR(50) DEFAULT 'private',"
                        "  data_retention VARCHAR(50) DEFAULT '1_year',"
                        "  health_data_consent BOOLEAN DEFAULT 0,"
                        "  partner_personality VARCHAR(50) DEFAULT 'supportive',"
                        "  partner_voice_override VARCHAR(50),"
                        "  check_in_time VARCHAR(10) DEFAULT '19:00',"
                        "  struggle_threshold INTEGER DEFAULT 3,"
                        "  celebration_style VARCHAR(50) DEFAULT 'moderate',"
                        "  auto_adjust_personality BOOLEAN DEFAULT 0,"
                        "  date_of_birth VARCHAR(10),"
                        "  life_weeks_enabled BOOLEAN DEFAULT 0,"
                        "  life_weeks_day INTEGER,"
                        "  life_weeks_time VARCHAR(10) DEFAULT '09:00',"
                        "  life_weeks_reply_destination VARCHAR(50)"
                        "    DEFAULT 'daily_note',"
                        "  life_weeks_custom_path VARCHAR(255),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO user_settings"
                        " (user_id, username, voice_model, emotion_style)"
                        " VALUES (42, 'testuser', 'austin', 'whisper')"
                    )
                )
            await engine.dispose()

            with (
                patch("src.core.database.get_database_url", return_value=db_url),
                patch(
                    "src.core.vector_db.get_vector_db",
                    return_value=AsyncMock(initialize_vector_support=AsyncMock()),
                ),
            ):
                from src.core.database import init_database

                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                async with engine.connect() as conn:
                    row = (
                        await conn.execute(
                            text(
                                "SELECT voice_model, emotion_style, voice_enabled,"
                                " response_mode"
                                " FROM voice_settings WHERE user_id = 42"
                            )
                        )
                    ).fetchone()
                    assert row is not None, "voice_settings row not migrated"
                    assert row[0] == "austin"
                    assert row[1] == "whisper"
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_accountability_data_migrated(self):
        """Pre-existing accountability data should be copied."""
        db_path, db_url = _tmp_db()
        try:
            from unittest.mock import AsyncMock, patch

            engine = create_async_engine(db_url, echo=False)
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "CREATE TABLE users ("
                        "  id INTEGER PRIMARY KEY,"
                        "  user_id INTEGER UNIQUE NOT NULL,"
                        "  username VARCHAR(255),"
                        "  first_name VARCHAR(255),"
                        "  last_name VARCHAR(255),"
                        "  language_code VARCHAR(10),"
                        "  consent_given BOOLEAN DEFAULT 0,"
                        "  consent_given_at DATETIME,"
                        "  banned BOOLEAN DEFAULT 0,"
                        "  user_group VARCHAR(100),"
                        "  admin_notes VARCHAR(1000),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE TABLE user_settings ("
                        "  user_id BIGINT PRIMARY KEY,"
                        "  username VARCHAR(255),"
                        "  voice_enabled BOOLEAN DEFAULT 1,"
                        "  voice_model VARCHAR(50) DEFAULT 'diana',"
                        "  emotion_style VARCHAR(50) DEFAULT 'cheerful',"
                        "  response_mode VARCHAR(50) DEFAULT 'smart',"
                        "  check_in_times TEXT,"
                        "  reminder_style VARCHAR(50) DEFAULT 'gentle',"
                        "  timezone VARCHAR(50) DEFAULT 'UTC',"
                        "  privacy_level VARCHAR(50) DEFAULT 'private',"
                        "  data_retention VARCHAR(50) DEFAULT '1_year',"
                        "  health_data_consent BOOLEAN DEFAULT 0,"
                        "  partner_personality VARCHAR(50) DEFAULT 'supportive',"
                        "  partner_voice_override VARCHAR(50),"
                        "  check_in_time VARCHAR(10) DEFAULT '19:00',"
                        "  struggle_threshold INTEGER DEFAULT 3,"
                        "  celebration_style VARCHAR(50) DEFAULT 'moderate',"
                        "  auto_adjust_personality BOOLEAN DEFAULT 0,"
                        "  date_of_birth VARCHAR(10),"
                        "  life_weeks_enabled BOOLEAN DEFAULT 0,"
                        "  life_weeks_day INTEGER,"
                        "  life_weeks_time VARCHAR(10) DEFAULT '09:00',"
                        "  life_weeks_reply_destination VARCHAR(50)"
                        "    DEFAULT 'daily_note',"
                        "  life_weeks_custom_path VARCHAR(255),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO user_settings"
                        " (user_id, partner_personality, struggle_threshold)"
                        " VALUES (42, 'tough_love', 5)"
                    )
                )
            await engine.dispose()

            with (
                patch("src.core.database.get_database_url", return_value=db_url),
                patch(
                    "src.core.vector_db.get_vector_db",
                    return_value=AsyncMock(initialize_vector_support=AsyncMock()),
                ),
            ):
                from src.core.database import init_database

                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                async with engine.connect() as conn:
                    row = (
                        await conn.execute(
                            text(
                                "SELECT partner_personality, struggle_threshold"
                                " FROM accountability_profiles WHERE user_id = 42"
                            )
                        )
                    ).fetchone()
                    assert row is not None, "accountability_profiles row not migrated"
                    assert row[0] == "tough_love"
                    assert row[1] == 5
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_privacy_data_migrated(self):
        """Pre-existing privacy data should be copied."""
        db_path, db_url = _tmp_db()
        try:
            from unittest.mock import AsyncMock, patch

            engine = create_async_engine(db_url, echo=False)
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "CREATE TABLE users ("
                        "  id INTEGER PRIMARY KEY,"
                        "  user_id INTEGER UNIQUE NOT NULL,"
                        "  username VARCHAR(255),"
                        "  first_name VARCHAR(255),"
                        "  last_name VARCHAR(255),"
                        "  language_code VARCHAR(10),"
                        "  consent_given BOOLEAN DEFAULT 0,"
                        "  consent_given_at DATETIME,"
                        "  banned BOOLEAN DEFAULT 0,"
                        "  user_group VARCHAR(100),"
                        "  admin_notes VARCHAR(1000),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE TABLE user_settings ("
                        "  user_id BIGINT PRIMARY KEY,"
                        "  username VARCHAR(255),"
                        "  voice_enabled BOOLEAN DEFAULT 1,"
                        "  voice_model VARCHAR(50) DEFAULT 'diana',"
                        "  emotion_style VARCHAR(50) DEFAULT 'cheerful',"
                        "  response_mode VARCHAR(50) DEFAULT 'smart',"
                        "  check_in_times TEXT,"
                        "  reminder_style VARCHAR(50) DEFAULT 'gentle',"
                        "  timezone VARCHAR(50) DEFAULT 'UTC',"
                        "  privacy_level VARCHAR(50) DEFAULT 'private',"
                        "  data_retention VARCHAR(50) DEFAULT '1_year',"
                        "  health_data_consent BOOLEAN DEFAULT 0,"
                        "  partner_personality VARCHAR(50) DEFAULT 'supportive',"
                        "  partner_voice_override VARCHAR(50),"
                        "  check_in_time VARCHAR(10) DEFAULT '19:00',"
                        "  struggle_threshold INTEGER DEFAULT 3,"
                        "  celebration_style VARCHAR(50) DEFAULT 'moderate',"
                        "  auto_adjust_personality BOOLEAN DEFAULT 0,"
                        "  date_of_birth VARCHAR(10),"
                        "  life_weeks_enabled BOOLEAN DEFAULT 0,"
                        "  life_weeks_day INTEGER,"
                        "  life_weeks_time VARCHAR(10) DEFAULT '09:00',"
                        "  life_weeks_reply_destination VARCHAR(50)"
                        "    DEFAULT 'daily_note',"
                        "  life_weeks_custom_path VARCHAR(255),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO user_settings"
                        " (user_id, privacy_level, data_retention,"
                        "  health_data_consent)"
                        " VALUES (42, 'shared', '6_months', 1)"
                    )
                )
            await engine.dispose()

            with (
                patch("src.core.database.get_database_url", return_value=db_url),
                patch(
                    "src.core.vector_db.get_vector_db",
                    return_value=AsyncMock(initialize_vector_support=AsyncMock()),
                ),
            ):
                from src.core.database import init_database

                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                async with engine.connect() as conn:
                    row = (
                        await conn.execute(
                            text(
                                "SELECT privacy_level, data_retention,"
                                " health_data_consent"
                                " FROM privacy_settings WHERE user_id = 42"
                            )
                        )
                    ).fetchone()
                    assert row is not None, "privacy_settings row not migrated"
                    assert row[0] == "shared"
                    assert row[1] == "6_months"
                    assert row[2] == 1
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_life_weeks_data_migrated(self):
        """Pre-existing life weeks data should be copied."""
        db_path, db_url = _tmp_db()
        try:
            from unittest.mock import AsyncMock, patch

            engine = create_async_engine(db_url, echo=False)
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "CREATE TABLE users ("
                        "  id INTEGER PRIMARY KEY,"
                        "  user_id INTEGER UNIQUE NOT NULL,"
                        "  username VARCHAR(255),"
                        "  first_name VARCHAR(255),"
                        "  last_name VARCHAR(255),"
                        "  language_code VARCHAR(10),"
                        "  consent_given BOOLEAN DEFAULT 0,"
                        "  consent_given_at DATETIME,"
                        "  banned BOOLEAN DEFAULT 0,"
                        "  user_group VARCHAR(100),"
                        "  admin_notes VARCHAR(1000),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE TABLE user_settings ("
                        "  user_id BIGINT PRIMARY KEY,"
                        "  username VARCHAR(255),"
                        "  voice_enabled BOOLEAN DEFAULT 1,"
                        "  voice_model VARCHAR(50) DEFAULT 'diana',"
                        "  emotion_style VARCHAR(50) DEFAULT 'cheerful',"
                        "  response_mode VARCHAR(50) DEFAULT 'smart',"
                        "  check_in_times TEXT,"
                        "  reminder_style VARCHAR(50) DEFAULT 'gentle',"
                        "  timezone VARCHAR(50) DEFAULT 'UTC',"
                        "  privacy_level VARCHAR(50) DEFAULT 'private',"
                        "  data_retention VARCHAR(50) DEFAULT '1_year',"
                        "  health_data_consent BOOLEAN DEFAULT 0,"
                        "  partner_personality VARCHAR(50) DEFAULT 'supportive',"
                        "  partner_voice_override VARCHAR(50),"
                        "  check_in_time VARCHAR(10) DEFAULT '19:00',"
                        "  struggle_threshold INTEGER DEFAULT 3,"
                        "  celebration_style VARCHAR(50) DEFAULT 'moderate',"
                        "  auto_adjust_personality BOOLEAN DEFAULT 0,"
                        "  date_of_birth VARCHAR(10),"
                        "  life_weeks_enabled BOOLEAN DEFAULT 0,"
                        "  life_weeks_day INTEGER,"
                        "  life_weeks_time VARCHAR(10) DEFAULT '09:00',"
                        "  life_weeks_reply_destination VARCHAR(50)"
                        "    DEFAULT 'daily_note',"
                        "  life_weeks_custom_path VARCHAR(255),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO user_settings"
                        " (user_id, date_of_birth, life_weeks_enabled,"
                        "  life_weeks_day, life_weeks_time)"
                        " VALUES (42, '1984-04-25', 1, 2, '10:30')"
                    )
                )
            await engine.dispose()

            with (
                patch("src.core.database.get_database_url", return_value=db_url),
                patch(
                    "src.core.vector_db.get_vector_db",
                    return_value=AsyncMock(initialize_vector_support=AsyncMock()),
                ),
            ):
                from src.core.database import init_database

                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                async with engine.connect() as conn:
                    row = (
                        await conn.execute(
                            text(
                                "SELECT date_of_birth, life_weeks_enabled,"
                                " life_weeks_day, life_weeks_time"
                                " FROM life_weeks_settings WHERE user_id = 42"
                            )
                        )
                    ).fetchone()
                    assert row is not None, "life_weeks_settings row not migrated"
                    assert row[0] == "1984-04-25"
                    assert row[1] == 1
                    assert row[2] == 2
                    assert row[3] == "10:30"
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_migration_idempotent(self):
        """Running init_database() twice should not duplicate rows."""
        db_path, db_url = _tmp_db()
        try:
            from unittest.mock import AsyncMock, patch

            engine = create_async_engine(db_url, echo=False)
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "CREATE TABLE users ("
                        "  id INTEGER PRIMARY KEY,"
                        "  user_id INTEGER UNIQUE NOT NULL,"
                        "  username VARCHAR(255),"
                        "  first_name VARCHAR(255),"
                        "  last_name VARCHAR(255),"
                        "  language_code VARCHAR(10),"
                        "  consent_given BOOLEAN DEFAULT 0,"
                        "  consent_given_at DATETIME,"
                        "  banned BOOLEAN DEFAULT 0,"
                        "  user_group VARCHAR(100),"
                        "  admin_notes VARCHAR(1000),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "CREATE TABLE user_settings ("
                        "  user_id BIGINT PRIMARY KEY,"
                        "  username VARCHAR(255),"
                        "  voice_enabled BOOLEAN DEFAULT 1,"
                        "  voice_model VARCHAR(50) DEFAULT 'diana',"
                        "  emotion_style VARCHAR(50) DEFAULT 'cheerful',"
                        "  response_mode VARCHAR(50) DEFAULT 'smart',"
                        "  check_in_times TEXT,"
                        "  reminder_style VARCHAR(50) DEFAULT 'gentle',"
                        "  timezone VARCHAR(50) DEFAULT 'UTC',"
                        "  privacy_level VARCHAR(50) DEFAULT 'private',"
                        "  data_retention VARCHAR(50) DEFAULT '1_year',"
                        "  health_data_consent BOOLEAN DEFAULT 0,"
                        "  partner_personality VARCHAR(50) DEFAULT 'supportive',"
                        "  partner_voice_override VARCHAR(50),"
                        "  check_in_time VARCHAR(10) DEFAULT '19:00',"
                        "  struggle_threshold INTEGER DEFAULT 3,"
                        "  celebration_style VARCHAR(50) DEFAULT 'moderate',"
                        "  auto_adjust_personality BOOLEAN DEFAULT 0,"
                        "  date_of_birth VARCHAR(10),"
                        "  life_weeks_enabled BOOLEAN DEFAULT 0,"
                        "  life_weeks_day INTEGER,"
                        "  life_weeks_time VARCHAR(10) DEFAULT '09:00',"
                        "  life_weeks_reply_destination VARCHAR(50)"
                        "    DEFAULT 'daily_note',"
                        "  life_weeks_custom_path VARCHAR(255),"
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO user_settings (user_id, voice_model)"
                        " VALUES (42, 'austin')"
                    )
                )
            await engine.dispose()

            with (
                patch("src.core.database.get_database_url", return_value=db_url),
                patch(
                    "src.core.vector_db.get_vector_db",
                    return_value=AsyncMock(initialize_vector_support=AsyncMock()),
                ),
            ):
                from src.core.database import init_database

                await init_database()
                # Second call must not crash or duplicate
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                async with engine.connect() as conn:
                    count = (
                        await conn.execute(
                            text("SELECT COUNT(*) FROM voice_settings WHERE user_id = 42")
                        )
                    ).scalar()
                    assert count == 1, f"Expected 1 row, got {count}"
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)
