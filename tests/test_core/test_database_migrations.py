"""Tests for inline ALTER TABLE migrations in init_database()."""

import os
import tempfile

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.database import init_database


def _tmp_db():
    """Create a temporary database file and return (path, url)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{path}"
    return path, url


# ---------------------------------------------------------------------------
# Columns that the migration code adds to *chats*
# ---------------------------------------------------------------------------
CHATS_MIGRATED_COLUMNS = [
    "tts_provider",
    "whisper_use_locale",
    "thinking_effort",
    "clean_responses",
]

# ---------------------------------------------------------------------------
# Columns that the migration code adds to *user_settings* (life weeks)
# ---------------------------------------------------------------------------
LIFE_WEEKS_COLUMNS = [
    "date_of_birth",
    "life_weeks_enabled",
    "life_weeks_day",
    "life_weeks_time",
    "life_weeks_reply_destination",
    "life_weeks_custom_path",
]

# ---------------------------------------------------------------------------
# Columns that the migration code adds to *user_settings* (partner)
# ---------------------------------------------------------------------------
PARTNER_COLUMNS = [
    "partner_personality",
    "partner_voice_override",
    "check_in_time",
    "struggle_threshold",
    "celebration_style",
    "auto_adjust_personality",
]


async def _get_column_names(engine, table_name):
    """Return a set of column names for *table_name* via PRAGMA."""
    async with engine.connect() as conn:
        result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        rows = result.fetchall()
        return {row[1] for row in rows}


async def _get_column_info(engine, table_name):
    """Return a dict mapping column name -> (type, notnull, default_value)."""
    async with engine.connect() as conn:
        result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        rows = result.fetchall()
        # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
        return {row[1]: (row[2], row[3], row[4]) for row in rows}


class TestDatabaseMigrations:
    """Verify the inline ALTER TABLE migrations in init_database()."""

    # ------------------------------------------------------------------
    # 1. Fresh database -- all columns present after init_database()
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_fresh_database_has_all_columns(self):
        """On a brand-new database, init_database() creates all tables with
        every column (via create_all) and the ALTER TABLE statements silently
        pass.  All expected columns must be present afterwards."""
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
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                chats_cols = await _get_column_names(engine, "chats")
                for col in CHATS_MIGRATED_COLUMNS:
                    assert col in chats_cols, f"Column '{col}' missing from chats table"

                us_cols = await _get_column_names(engine, "user_settings")
                for col in LIFE_WEEKS_COLUMNS + PARTNER_COLUMNS:
                    assert (
                        col in us_cols
                    ), f"Column '{col}' missing from user_settings table"
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    # ------------------------------------------------------------------
    # 2. Already-migrated database -- running init_database() again is safe
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_idempotent_double_init(self):
        """Calling init_database() twice must not raise -- the ALTER TABLE
        statements should silently pass when the columns already exist."""
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
                await init_database()
                # Second call -- must not crash
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                chats_cols = await _get_column_names(engine, "chats")
                for col in CHATS_MIGRATED_COLUMNS:
                    assert col in chats_cols

                us_cols = await _get_column_names(engine, "user_settings")
                for col in LIFE_WEEKS_COLUMNS + PARTNER_COLUMNS:
                    assert col in us_cols
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    # ------------------------------------------------------------------
    # 3. Legacy schema -- migration adds missing columns
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_migration_adds_missing_chats_columns(self):
        """Create a chats table *without* the migrated columns, then run
        init_database().  The ALTER TABLE statements should add them."""
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
                        "CREATE TABLE chats ("
                        "  id INTEGER PRIMARY KEY,"
                        "  chat_id INTEGER UNIQUE NOT NULL,"
                        "  user_id INTEGER NOT NULL REFERENCES users(id),"
                        "  chat_type VARCHAR(20) DEFAULT 'private',"
                        "  title VARCHAR(255),"
                        "  current_mode VARCHAR(50) DEFAULT 'default',"
                        "  current_preset VARCHAR(50),"
                        "  claude_mode BOOLEAN DEFAULT 0,"
                        "  claude_model VARCHAR(20),"
                        "  auto_forward_voice BOOLEAN DEFAULT 1,"
                        "  transcript_correction_level VARCHAR(20)"
                        "    DEFAULT 'vocabulary',"
                        "  show_model_buttons BOOLEAN DEFAULT 0,"
                        "  show_transcript BOOLEAN DEFAULT 1,"
                        "  pending_auto_forward_claude BOOLEAN DEFAULT 0,"
                        "  voice_response_mode VARCHAR(20) DEFAULT 'text_only',"
                        "  voice_name VARCHAR(20) DEFAULT 'diana',"
                        "  voice_emotion VARCHAR(20) DEFAULT 'cheerful',"
                        "  voice_verbosity VARCHAR(20) DEFAULT 'full',"
                        "  accountability_enabled BOOLEAN DEFAULT 0,"
                        "  partner_personality VARCHAR(50) DEFAULT 'supportive',"
                        "  partner_voice_override VARCHAR(50),"
                        "  check_in_time VARCHAR(10) DEFAULT '19:00',"
                        "  struggle_threshold INTEGER DEFAULT 3,"
                        "  celebration_style VARCHAR(50) DEFAULT 'moderate',"
                        "  auto_adjust_personality BOOLEAN DEFAULT 0,"
                        "  settings TEXT,"
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
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
            await engine.dispose()

            engine = create_async_engine(db_url, echo=False)
            chats_before = await _get_column_names(engine, "chats")
            us_before = await _get_column_names(engine, "user_settings")
            await engine.dispose()

            for col in CHATS_MIGRATED_COLUMNS:
                assert (
                    col not in chats_before
                ), f"Column '{col}' should NOT exist before migration"
            for col in LIFE_WEEKS_COLUMNS + PARTNER_COLUMNS:
                assert (
                    col not in us_before
                ), f"Column '{col}' should NOT exist before migration"

            with (
                patch("src.core.database.get_database_url", return_value=db_url),
                patch(
                    "src.core.vector_db.get_vector_db",
                    return_value=AsyncMock(initialize_vector_support=AsyncMock()),
                ),
            ):
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                chats_after = await _get_column_names(engine, "chats")
                for col in CHATS_MIGRATED_COLUMNS:
                    assert (
                        col in chats_after
                    ), f"Migration failed to add '{col}' to chats"

                us_after = await _get_column_names(engine, "user_settings")
                for col in LIFE_WEEKS_COLUMNS + PARTNER_COLUMNS:
                    assert (
                        col in us_after
                    ), f"Migration failed to add '{col}' to user_settings"
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    # ------------------------------------------------------------------
    # 4. Verify specific chat columns individually via PRAGMA
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_tts_provider_column_exists(self):
        """tts_provider column on chats exists with expected type."""
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
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                info = await _get_column_info(engine, "chats")
                assert "tts_provider" in info, "tts_provider column missing"
                col_type, notnull, dflt = info["tts_provider"]
                assert "VARCHAR" in col_type.upper(), f"Unexpected type: {col_type}"
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_whisper_use_locale_column_exists(self):
        """whisper_use_locale column on chats exists as BOOLEAN."""
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
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                info = await _get_column_info(engine, "chats")
                assert "whisper_use_locale" in info, "whisper_use_locale missing"
                col_type, notnull, _dflt = info["whisper_use_locale"]
                assert "BOOLEAN" in col_type.upper(), f"Unexpected type: {col_type}"
                assert notnull == 1, "whisper_use_locale should be NOT NULL"
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_thinking_effort_column_exists(self):
        """thinking_effort column on chats exists as VARCHAR."""
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
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                info = await _get_column_info(engine, "chats")
                assert "thinking_effort" in info, "thinking_effort missing"
                col_type, _notnull, _dflt = info["thinking_effort"]
                assert "VARCHAR" in col_type.upper(), f"Unexpected type: {col_type}"
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_clean_responses_column_exists(self):
        """clean_responses column on chats exists as BOOLEAN."""
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
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                info = await _get_column_info(engine, "chats")
                assert "clean_responses" in info, "clean_responses missing"
                col_type, notnull, _dflt = info["clean_responses"]
                assert "BOOLEAN" in col_type.upper(), f"Unexpected type: {col_type}"
                assert notnull == 1, "clean_responses should be NOT NULL"
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    # ------------------------------------------------------------------
    # 5. Verify life weeks columns on user_settings
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_life_weeks_columns_on_user_settings(self):
        """All life-weeks columns should exist on user_settings with
        correct types after init_database()."""
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
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                info = await _get_column_info(engine, "user_settings")
                # date_of_birth -- nullable VARCHAR
                assert "date_of_birth" in info
                assert "VARCHAR" in info["date_of_birth"][0].upper()
                # life_weeks_enabled -- BOOLEAN NOT NULL
                assert "life_weeks_enabled" in info
                assert "BOOLEAN" in info["life_weeks_enabled"][0].upper()
                # life_weeks_day -- nullable INTEGER
                assert "life_weeks_day" in info
                assert "INTEGER" in info["life_weeks_day"][0].upper()
                # life_weeks_time -- VARCHAR NOT NULL
                assert "life_weeks_time" in info
                assert "VARCHAR" in info["life_weeks_time"][0].upper()
                # life_weeks_reply_destination -- VARCHAR NOT NULL
                assert "life_weeks_reply_destination" in info
                assert "VARCHAR" in info["life_weeks_reply_destination"][0].upper()
                # life_weeks_custom_path -- nullable VARCHAR
                assert "life_weeks_custom_path" in info
                assert "VARCHAR" in info["life_weeks_custom_path"][0].upper()
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    # ------------------------------------------------------------------
    # 6. Verify partner columns on user_settings
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_partner_columns_on_user_settings(self):
        """All accountability-partner columns should exist on
        user_settings with correct types after init_database()."""
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
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                info = await _get_column_info(engine, "user_settings")
                # partner_personality -- VARCHAR NOT NULL
                assert "partner_personality" in info
                assert "VARCHAR" in info["partner_personality"][0].upper()
                # partner_voice_override -- nullable VARCHAR
                assert "partner_voice_override" in info
                assert "VARCHAR" in info["partner_voice_override"][0].upper()
                # check_in_time -- VARCHAR NOT NULL
                assert "check_in_time" in info
                assert "VARCHAR" in info["check_in_time"][0].upper()
                # struggle_threshold -- INTEGER NOT NULL
                assert "struggle_threshold" in info
                assert "INTEGER" in info["struggle_threshold"][0].upper()
                # celebration_style -- VARCHAR NOT NULL
                assert "celebration_style" in info
                assert "VARCHAR" in info["celebration_style"][0].upper()
                # auto_adjust_personality -- BOOLEAN
                assert "auto_adjust_personality" in info
                assert "BOOLEAN" in info["auto_adjust_personality"][0].upper()
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)

    # ------------------------------------------------------------------
    # 7. Legacy user_settings migration preserves existing data
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_legacy_user_settings_migration_preserves_data(self):
        """Pre-existing rows in user_settings should get the new columns
        populated with their defaults after init_database()."""
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
                        "CREATE TABLE chats ("
                        "  id INTEGER PRIMARY KEY,"
                        "  chat_id INTEGER UNIQUE NOT NULL,"
                        "  user_id INTEGER NOT NULL,"
                        "  chat_type VARCHAR(20) DEFAULT 'private',"
                        "  title VARCHAR(255),"
                        "  current_mode VARCHAR(50) DEFAULT 'default',"
                        "  current_preset VARCHAR(50),"
                        "  claude_mode BOOLEAN DEFAULT 0,"
                        "  claude_model VARCHAR(20),"
                        "  thinking_effort VARCHAR(10) DEFAULT 'medium',"
                        "  auto_forward_voice BOOLEAN DEFAULT 1,"
                        "  transcript_correction_level VARCHAR(20)"
                        "    DEFAULT 'vocabulary',"
                        "  show_model_buttons BOOLEAN DEFAULT 0,"
                        "  show_transcript BOOLEAN DEFAULT 1,"
                        "  clean_responses BOOLEAN DEFAULT 0,"
                        "  whisper_use_locale BOOLEAN DEFAULT 0,"
                        "  pending_auto_forward_claude BOOLEAN DEFAULT 0,"
                        "  voice_response_mode VARCHAR(20) DEFAULT 'text_only',"
                        "  voice_name VARCHAR(20) DEFAULT 'diana',"
                        "  voice_emotion VARCHAR(20) DEFAULT 'cheerful',"
                        "  voice_verbosity VARCHAR(20) DEFAULT 'full',"
                        "  tts_provider VARCHAR(20) DEFAULT '',"
                        "  accountability_enabled BOOLEAN DEFAULT 0,"
                        "  partner_personality VARCHAR(50) DEFAULT 'supportive',"
                        "  partner_voice_override VARCHAR(50),"
                        "  check_in_time VARCHAR(10) DEFAULT '19:00',"
                        "  struggle_threshold INTEGER DEFAULT 3,"
                        "  celebration_style VARCHAR(50) DEFAULT 'moderate',"
                        "  auto_adjust_personality BOOLEAN DEFAULT 0,"
                        "  settings TEXT,"
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
                        "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
                        "  updated_at DATETIME"
                        ")"
                    )
                )
                await conn.execute(
                    text(
                        "INSERT INTO user_settings (user_id, username)"
                        " VALUES (42, 'legacy_user')"
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
                await init_database()

            engine = create_async_engine(db_url, echo=False)
            try:
                async with engine.connect() as conn:
                    row = (
                        await conn.execute(
                            text(
                                "SELECT life_weeks_enabled, life_weeks_time,"
                                " partner_personality, check_in_time,"
                                " struggle_threshold"
                                " FROM user_settings WHERE user_id = 42"
                            )
                        )
                    ).fetchone()

                    assert row is not None, "Pre-existing row disappeared"
                    assert row[0] == 0, "life_weeks_enabled default"
                    assert row[1] == "09:00", "life_weeks_time default"
                    assert row[2] == "supportive", "partner_personality"
                    assert row[3] == "19:00", "check_in_time default"
                    assert row[4] == 3, "struggle_threshold default"
            finally:
                await engine.dispose()
        finally:
            os.unlink(db_path)
