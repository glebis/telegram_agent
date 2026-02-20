"""Tests for enriched health endpoint with subsystem breakdown.

TDD: RED → GREEN → REFACTOR for subsystem checks and error details.
"""

from unittest.mock import AsyncMock, patch

import pytest


class TestSubsystemHealth:
    """Slice 1: Individual subsystem health checks."""

    @pytest.mark.asyncio
    async def test_check_subsystem_database(self):
        from src.api.health import check_subsystem_health

        with patch(
            "src.api.health.check_database_health", new_callable=AsyncMock
        ) as mock_db:
            mock_db.return_value = True
            result = await check_subsystem_health("database")
            assert result["status"] == "ok"
            assert result["name"] == "database"

    @pytest.mark.asyncio
    async def test_check_subsystem_database_failure(self):
        from src.api.health import check_subsystem_health

        with patch(
            "src.api.health.check_database_health", new_callable=AsyncMock
        ) as mock_db:
            mock_db.return_value = False
            result = await check_subsystem_health("database")
            assert result["status"] == "error"
            assert result["name"] == "database"

    @pytest.mark.asyncio
    async def test_check_subsystem_bot(self):
        from src.api.health import check_subsystem_health

        with patch("src.api.health._is_bot_initialized") as mock_bot:
            mock_bot.return_value = True
            result = await check_subsystem_health("bot")
            assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_check_subsystem_bot_failure(self):
        from src.api.health import check_subsystem_health

        with patch("src.api.health._is_bot_initialized") as mock_bot:
            mock_bot.return_value = False
            result = await check_subsystem_health("bot")
            assert result["status"] == "error"


class TestEnrichedHealthPayload:
    """Slice 2: Full enriched health endpoint response."""

    @pytest.mark.asyncio
    async def test_enriched_payload_has_subsystems(self):
        from src.api.health import build_enriched_health

        with (
            patch(
                "src.api.health.check_database_health", new_callable=AsyncMock
            ) as mock_db,
            patch("src.api.health._is_bot_initialized") as mock_bot,
        ):
            mock_db.return_value = True
            mock_bot.return_value = True
            result = await build_enriched_health()

            assert "subsystems" in result
            assert isinstance(result["subsystems"], list)
            assert len(result["subsystems"]) >= 2  # At least database and bot

    @pytest.mark.asyncio
    async def test_enriched_payload_has_error_details_on_failure(self):
        from src.api.health import build_enriched_health

        with (
            patch(
                "src.api.health.check_database_health", new_callable=AsyncMock
            ) as mock_db,
            patch("src.api.health._is_bot_initialized") as mock_bot,
        ):
            mock_db.return_value = False
            mock_bot.return_value = True
            result = await build_enriched_health()

            assert result["status"] == "degraded"
            assert "error_details" in result
            assert "database" in result["error_details"]

    @pytest.mark.asyncio
    async def test_enriched_payload_healthy_has_no_errors(self):
        from src.api.health import build_enriched_health

        with (
            patch(
                "src.api.health.check_database_health", new_callable=AsyncMock
            ) as mock_db,
            patch("src.api.health._is_bot_initialized") as mock_bot,
        ):
            mock_db.return_value = True
            mock_bot.return_value = True
            result = await build_enriched_health()

            assert result["status"] == "healthy"
            assert result.get("error_details") is None or result["error_details"] == {}

    @pytest.mark.asyncio
    async def test_enriched_payload_has_error_counts(self):
        from src.api.health import build_enriched_health

        with (
            patch(
                "src.api.health.check_database_health", new_callable=AsyncMock
            ) as mock_db,
            patch("src.api.health._is_bot_initialized") as mock_bot,
        ):
            mock_db.return_value = True
            mock_bot.return_value = True
            result = await build_enriched_health()

            assert "error_counts" in result
            assert isinstance(result["error_counts"], dict)
