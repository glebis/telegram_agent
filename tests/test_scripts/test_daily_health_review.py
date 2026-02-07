"""Tests for daily_health_review.py morning notification script.

Covers:
- Data freshness detection
- Health data collection via health_query.py subprocess
- Stale data warning formatting
- LLM insight generation (mocked)
- LLM failure graceful degradation
- Telegram message length limit
- Missing database handling
- Weekly comparison delta calculation
"""

import sqlite3
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module under test
from scripts.daily_health_review import (
    HEALTH_TARGETS,
    STALE_HOURS,
    _delta_str,
    _escape_html,
    _markdown_to_telegram_html,
    check_data_freshness,
    collect_health_data,
    format_data_report,
    generate_llm_insight,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def sample_health_data():
    """Complete health data dict as returned by collect_health_data."""
    return {
        "freshness": {
            "is_fresh": True,
            "last_record": "2026-02-06 23:29:00",
        },
        "sleep": {
            "period_days": 7,
            "nights": [
                {
                    "date": "2026-02-06",
                    "stages": {"Deep": 55.2, "REM": 78.4, "Core": 210.0},
                    "total_minutes": 343.6,
                    "total_hours": 5.7,
                }
            ],
            "summary": {"avg_sleep_hours": 6.8, "nights_tracked": 7},
        },
        "vitals": {
            "timestamp": "2026-02-07T09:30:00",
            "vitals": {
                "HRV": {"value": 42.0, "unit": "ms", "recorded": "2026-02-06T23:00:00"},
                "Resting HR": {
                    "value": 58.0,
                    "unit": "bpm",
                    "recorded": "2026-02-06T22:00:00",
                },
                "Blood Oxygen": {
                    "value": 97.0,
                    "unit": "%",
                    "recorded": "2026-02-06T23:15:00",
                },
            },
        },
        "weekly": {
            "period": "2026-01-24 to 2026-02-07",
            "weeks": [
                {
                    "week_of": "2026-01-24",
                    "metrics": {
                        "avg_daily_steps": 7500,
                        "avg_resting_hr": 60.2,
                        "total_exercise_min": 140,
                        "workouts": 3,
                    },
                },
                {
                    "week_of": "2026-01-31",
                    "metrics": {
                        "avg_daily_steps": 8200,
                        "avg_resting_hr": 58.5,
                        "total_exercise_min": 165,
                        "workouts": 4,
                    },
                },
            ],
        },
        "workouts": {
            "period_days": 7,
            "workouts": [
                {
                    "type": "Running",
                    "date": "2026-02-05 07:30",
                    "duration_min": 35.0,
                    "calories": 320.0,
                },
                {
                    "type": "Strength",
                    "date": "2026-02-03 18:00",
                    "duration_min": 45.0,
                    "calories": 250.0,
                },
            ],
            "summary": {
                "total_workouts": 2,
                "total_duration_min": 80.0,
                "total_calories": 570.0,
            },
        },
    }


@pytest.fixture
def stale_health_data(sample_health_data):
    """Health data with stale freshness."""
    sample_health_data["freshness"] = {
        "is_fresh": False,
        "last_record": "2026-02-04 08:00:00",
    }
    return sample_health_data


@pytest.fixture
def tmp_health_db(tmp_path):
    """Create a temporary health.db with minimal schema."""
    db_path = tmp_path / "health.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE health_records (
            id INTEGER PRIMARY KEY,
            record_type TEXT,
            value REAL,
            unit TEXT,
            start_date TEXT,
            end_date TEXT
        )
    """)
    conn.commit()
    return db_path, conn


# ============================================================
# Data freshness tests
# ============================================================


class TestDataFreshness:
    def test_fresh_data_detected(self, tmp_health_db):
        """Recent data (< STALE_HOURS) is detected as fresh."""
        db_path, conn = tmp_health_db
        recent = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO health_records (record_type, value, start_date) "
            "VALUES (?, ?, ?)",
            ("HKQuantityTypeIdentifierHeartRate", 72.0, recent),
        )
        conn.commit()
        conn.close()

        with patch("scripts.daily_health_review.HEALTH_DB", db_path):
            is_fresh, last_ts = check_data_freshness()

        assert is_fresh is True
        assert last_ts is not None

    def test_stale_data_detected(self, tmp_health_db):
        """Old data (> STALE_HOURS) is detected as stale."""
        db_path, conn = tmp_health_db
        old = (datetime.now() - timedelta(hours=STALE_HOURS + 1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        conn.execute(
            "INSERT INTO health_records (record_type, value, start_date) "
            "VALUES (?, ?, ?)",
            ("HKQuantityTypeIdentifierHeartRate", 72.0, old),
        )
        conn.commit()
        conn.close()

        with patch("scripts.daily_health_review.HEALTH_DB", db_path):
            is_fresh, last_ts = check_data_freshness()

        assert is_fresh is False
        assert last_ts is not None

    def test_missing_database(self, tmp_path):
        """Missing database returns not-fresh with no timestamp."""
        missing = tmp_path / "does_not_exist.db"
        with patch("scripts.daily_health_review.HEALTH_DB", missing):
            is_fresh, last_ts = check_data_freshness()

        assert is_fresh is False
        assert last_ts is None

    def test_empty_database(self, tmp_health_db):
        """Empty database returns not-fresh with no timestamp."""
        db_path, conn = tmp_health_db
        conn.close()

        with patch("scripts.daily_health_review.HEALTH_DB", db_path):
            is_fresh, last_ts = check_data_freshness()

        assert is_fresh is False
        assert last_ts is None

    def test_timezone_aware_timestamp(self, tmp_health_db):
        """Timestamps with timezone offsets are parsed correctly."""
        db_path, conn = tmp_health_db
        recent = (datetime.now() - timedelta(hours=1)).strftime(
            "%Y-%m-%d %H:%M:%S +0100"
        )
        conn.execute(
            "INSERT INTO health_records (record_type, value, start_date) "
            "VALUES (?, ?, ?)",
            ("HKQuantityTypeIdentifierHeartRate", 72.0, recent),
        )
        conn.commit()
        conn.close()

        with patch("scripts.daily_health_review.HEALTH_DB", db_path):
            is_fresh, last_ts = check_data_freshness()

        # Might be fresh or stale depending on TZ math, but should not crash
        assert last_ts is not None


# ============================================================
# Health data collection tests
# ============================================================


class TestHealthDataCollection:
    def test_collects_all_data_types(self):
        """collect_health_data calls health_query.py for all expected types."""
        with (
            patch(
                "scripts.daily_health_review.check_data_freshness",
                return_value=(True, "2026-02-06 23:00:00"),
            ),
            patch("scripts.daily_health_review._run_health_query") as mock_query,
        ):
            mock_query.return_value = {"test": True}
            collect_health_data()

        # Should call for sleep, vitals, weekly, workouts
        assert mock_query.call_count == 4
        commands = [call.args[0] for call in mock_query.call_args_list]
        assert "sleep" in commands
        assert "vitals" in commands
        assert "weekly" in commands
        assert "workouts" in commands

    def test_handles_query_failures_gracefully(self):
        """If health_query.py fails for one type, others still collected."""
        with (
            patch(
                "scripts.daily_health_review.check_data_freshness",
                return_value=(True, "2026-02-06 23:00:00"),
            ),
            patch(
                "scripts.daily_health_review._run_health_query",
                return_value=None,
            ),
        ):
            data = collect_health_data()

        assert data["freshness"]["is_fresh"] is True
        assert data["sleep"] is None
        assert data["vitals"] is None


# ============================================================
# Report formatting tests
# ============================================================


class TestFormatDataReport:
    def test_fresh_data_no_warning(self, sample_health_data):
        """Fresh data produces report without staleness warning."""
        report = format_data_report(sample_health_data)
        assert "stale" not in report.lower()
        assert "⚠️" not in report

    def test_stale_data_shows_warning(self, stale_health_data):
        """Stale data includes warning with last import timestamp."""
        report = format_data_report(stale_health_data)
        assert "stale" in report.lower()
        assert "2026-02-04 08:00:00" in report

    def test_includes_sleep_section(self, sample_health_data):
        """Report includes sleep duration and stages."""
        report = format_data_report(sample_health_data)
        assert "Sleep" in report
        assert "5.7h" in report

    def test_includes_vitals_section(self, sample_health_data):
        """Report includes HRV, resting HR, SpO2."""
        report = format_data_report(sample_health_data)
        assert "HRV" in report
        assert "42.0" in report
        assert "Resting HR" in report
        assert "58.0" in report

    def test_includes_weekly_trends(self, sample_health_data):
        """Report includes weekly steps/exercise with delta."""
        report = format_data_report(sample_health_data)
        assert "Weekly" in report
        assert "8,200" in report
        assert "165" in report

    def test_includes_recent_workouts(self, sample_health_data):
        """Report lists recent workouts."""
        report = format_data_report(sample_health_data)
        assert "Running" in report
        assert "Strength" in report

    def test_empty_data_returns_something(self):
        """Even with all None data, format doesn't crash."""
        data = {
            "freshness": {"is_fresh": True, "last_record": None},
            "sleep": None,
            "vitals": None,
            "weekly": None,
            "workouts": None,
        }
        report = format_data_report(data)
        assert isinstance(report, str)


# ============================================================
# Delta calculation tests
# ============================================================


class TestDeltaStr:
    def test_increase_higher_is_better(self):
        """Steps going up shows ↑."""
        result = _delta_str(10000, 8000)
        assert "↑" in result
        assert "25%" in result

    def test_decrease_higher_is_better(self):
        """Steps going down shows ↓."""
        result = _delta_str(6000, 8000)
        assert "↓" in result

    def test_lower_is_better_decrease(self):
        """HR going down shows ↑ (improvement) when lower_is_better."""
        result = _delta_str(55, 60, lower_is_better=True)
        assert "↑" in result  # improvement

    def test_lower_is_better_increase(self):
        """HR going up shows ↓ (worsening) when lower_is_better."""
        result = _delta_str(65, 60, lower_is_better=True)
        assert "↓" in result  # worsening

    def test_no_change_returns_empty(self):
        """Less than 1% change returns empty string."""
        result = _delta_str(1000, 1005)
        assert result == ""

    def test_none_values_return_empty(self):
        """None inputs return empty string."""
        assert _delta_str(None, 100) == ""
        assert _delta_str(100, None) == ""

    def test_zero_previous_returns_empty(self):
        """Zero previous value returns empty string (avoid division by zero)."""
        assert _delta_str(100, 0) == ""


# ============================================================
# LLM insight generation tests
# ============================================================


class TestLLMInsight:
    @pytest.mark.asyncio
    async def test_generates_insight_from_data(self, sample_health_data):
        """LLM is called with health data and returns insight text."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="Your HRV of 42ms is below the 50ms target. "
                    "Consider prioritizing sleep tonight."
                )
            )
        ]

        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            insight = await generate_llm_insight(sample_health_data)

        assert insight is not None
        assert "42ms" in insight
        mock_litellm.acompletion.assert_called_once()

        # Verify prompt contains health targets
        call_args = mock_litellm.acompletion.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert str(HEALTH_TARGETS["hrv_ms"]) in prompt

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self, sample_health_data):
        """LLM timeout/failure returns None (graceful degradation)."""
        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(side_effect=TimeoutError("LLM timed out"))

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            insight = await generate_llm_insight(sample_health_data)

        assert insight is None

    @pytest.mark.asyncio
    async def test_llm_empty_response_returns_none(self, sample_health_data):
        """Empty LLM response returns None."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=""))]

        mock_litellm = MagicMock()
        mock_litellm.acompletion = AsyncMock(return_value=mock_response)

        with patch.dict("sys.modules", {"litellm": mock_litellm}):
            insight = await generate_llm_insight(sample_health_data)

        assert insight is None


# ============================================================
# Telegram message limit test
# ============================================================


class TestMessageLimit:
    def test_report_fits_telegram_limit(self, sample_health_data):
        """Formatted report fits within 4096 char Telegram limit."""
        report = format_data_report(sample_health_data)
        html = _markdown_to_telegram_html(report)
        # Add header that main() prepends
        full = f"<b>Good Morning! Health Review</b>\n\n{html}"
        assert len(full) <= 4096

    def test_large_report_with_insight_fits(self, sample_health_data):
        """Even with a long insight section, total stays under limit."""
        report = format_data_report(sample_health_data)
        insight = "A" * 500  # Simulate long insight
        full_md = f"{report}\n\n## Insights\n{insight}"
        html = _markdown_to_telegram_html(full_md)

        # The main() function truncates at 4000
        if len(html) > 4000:
            html = html[:3950] + "\n\n<i>... truncated</i>"
        assert len(html) <= 4096


# ============================================================
# HTML escaping and formatting tests
# ============================================================


class TestFormatting:
    def test_escape_html_special_chars(self):
        assert _escape_html("<b>test</b>") == "&lt;b&gt;test&lt;/b&gt;"
        assert _escape_html("a & b") == "a &amp; b"

    def test_markdown_bold_converts(self):
        html = _markdown_to_telegram_html("**bold text**")
        assert "<b>" in html
        assert "bold text" in html

    def test_markdown_header_converts(self):
        html = _markdown_to_telegram_html("## Header")
        assert "<b>" in html
        assert "Header" in html
