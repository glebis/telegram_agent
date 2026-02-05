"""Tests for life_weeks_image service."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image

from src.services.life_weeks_image import (
    MAX_YEARS,
    WEEKS_PER_YEAR,
    calculate_weeks_lived,
    generate_from_dob,
    generate_life_weeks_grid,
)


class TestCalculateWeeksLived:
    """Test weeks lived calculation."""

    def test_calculate_weeks_lived_known_date(self):
        """Test calculation with known date 1984-04-25."""
        dob = "1984-04-25"
        weeks = calculate_weeks_lived(dob)

        # Calculate expected weeks
        dob_dt = datetime(1984, 4, 25)
        expected_weeks = (datetime.now() - dob_dt).days // 7

        assert weeks == expected_weeks

    def test_calculate_weeks_lived_recent_date(self):
        """Test calculation with recent date."""
        # 100 days ago
        days_ago = 100
        dob = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        weeks = calculate_weeks_lived(dob)

        expected_weeks = days_ago // 7
        assert weeks == expected_weeks

    def test_calculate_weeks_lived_newborn(self):
        """Test calculation for newborn (0-6 days old)."""
        dob = datetime.now().strftime("%Y-%m-%d")
        weeks = calculate_weeks_lived(dob)
        assert weeks == 0

    def test_calculate_weeks_lived_one_week_old(self):
        """Test calculation for 1 week old baby."""
        dob = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        weeks = calculate_weeks_lived(dob)
        assert weeks == 1

    def test_calculate_weeks_lived_centenarian(self):
        """Test calculation for someone 100 years old."""
        # 100 years ago
        dob = (datetime.now() - timedelta(days=365 * 100)).strftime("%Y-%m-%d")
        weeks = calculate_weeks_lived(dob)

        # Approximately 100 * 52 = 5200 weeks
        assert 5180 <= weeks <= 5220  # Allow some variance for leap years

    def test_calculate_weeks_lived_invalid_format(self):
        """Test error handling for invalid date format."""
        with pytest.raises(ValueError, match="Invalid date format"):
            calculate_weeks_lived("invalid-date")

    def test_calculate_weeks_lived_invalid_date_values(self):
        """Test error handling for invalid date values."""
        with pytest.raises(ValueError, match="Invalid date format"):
            calculate_weeks_lived("2025-13-45")  # Invalid month and day

    def test_calculate_weeks_lived_leap_year(self):
        """Test calculation accounts for leap years."""
        # Feb 29, 2000 was a leap year
        dob = "2000-02-29"
        weeks = calculate_weeks_lived(dob)

        dob_dt = datetime(2000, 2, 29)
        expected_weeks = (datetime.now() - dob_dt).days // 7
        assert weeks == expected_weeks


class TestGenerateLifeWeeksGrid:
    """Test grid image generation."""

    def test_generate_grid_creates_file(self, tmp_path, monkeypatch):
        """Test that grid generation creates a PNG file."""
        # Mock the output directory (includes Research subdirectory)
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)

        # Monkey patch Path.home() to return tmp_path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        weeks = 2000
        dob = "1984-04-25"
        output_path = generate_life_weeks_grid(weeks, dob)

        assert output_path.exists()
        assert output_path.suffix == ".png"
        assert output_path.parent == test_vault_dir

    def test_generate_grid_valid_image(self, tmp_path, monkeypatch):
        """Test that generated file is a valid PNG image."""
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        weeks = 1500
        dob = "1990-01-01"
        output_path = generate_life_weeks_grid(weeks, dob)

        # Try to open with PIL
        img = Image.open(output_path)
        assert img.format == "PNG"
        assert img.mode == "RGBA"

    def test_generate_grid_correct_dimensions(self, tmp_path, monkeypatch):
        """Test that image has correct dimensions."""
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        weeks = 2000
        dob = "1984-04-25"
        output_path = generate_life_weeks_grid(weeks, dob)

        img = Image.open(output_path)
        width, height = img.size

        # Check dimensions are reasonable (1200×1800 plus padding)
        assert 1100 <= width <= 1300
        assert 2000 <= height <= 2200

    def test_generate_grid_negative_weeks_raises_error(self):
        """Test that negative weeks raises ValueError."""
        with pytest.raises(ValueError, match="weeks_lived must be non-negative"):
            generate_life_weeks_grid(-1, "1984-04-25")

    def test_generate_grid_invalid_max_age_raises_error(self):
        """Test that invalid max_age raises ValueError."""
        with pytest.raises(ValueError, match="max_age must be between"):
            generate_life_weeks_grid(2000, "1984-04-25", max_age=0)

        with pytest.raises(ValueError, match="max_age must be between"):
            generate_life_weeks_grid(2000, "1984-04-25", max_age=150)

    def test_generate_grid_zero_weeks(self, tmp_path, monkeypatch):
        """Test generation for newborn (0 weeks)."""
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        weeks = 0
        dob = datetime.now().strftime("%Y-%m-%d")
        output_path = generate_life_weeks_grid(weeks, dob)

        assert output_path.exists()
        img = Image.open(output_path)
        assert img.format == "PNG"

    def test_generate_grid_full_life(self, tmp_path, monkeypatch):
        """Test generation for someone at max age."""
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        weeks = WEEKS_PER_YEAR * MAX_YEARS  # Full 90 years
        dob = "1934-01-01"
        output_path = generate_life_weeks_grid(weeks, dob)

        assert output_path.exists()
        img = Image.open(output_path)
        assert img.format == "PNG"

    def test_generate_grid_beyond_max_age(self, tmp_path, monkeypatch):
        """Test generation for someone beyond max age (should still work)."""
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        weeks = WEEKS_PER_YEAR * MAX_YEARS + 100  # 100 weeks beyond
        dob = "1920-01-01"
        output_path = generate_life_weeks_grid(weeks, dob)

        assert output_path.exists()
        img = Image.open(output_path)
        assert img.format == "PNG"


class TestGenerateFromDob:
    """Test convenience function generate_from_dob."""

    def test_generate_from_dob_creates_file(self, tmp_path, monkeypatch):
        """Test that convenience function works end-to-end."""
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        dob = "1984-04-25"
        output_path = generate_from_dob(dob)

        assert output_path.exists()
        assert output_path.suffix == ".png"

    def test_generate_from_dob_calculates_weeks_correctly(self, tmp_path, monkeypatch):
        """Test that convenience function calculates weeks correctly."""
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        dob = "2000-01-01"

        output_path = generate_from_dob(dob)
        assert output_path.exists()

        # We can't easily verify the content, but we can verify it was created
        img = Image.open(output_path)
        assert img.format == "PNG"

    def test_generate_from_dob_invalid_date_raises_error(self):
        """Test that invalid date raises ValueError."""
        with pytest.raises(ValueError, match="Invalid date format"):
            generate_from_dob("not-a-date")

    def test_generate_from_dob_custom_max_age(self, tmp_path, monkeypatch):
        """Test custom max_age parameter."""
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        dob = "1990-05-15"
        output_path = generate_from_dob(dob, max_age=80)

        assert output_path.exists()
        img = Image.open(output_path)
        assert img.format == "PNG"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_date_on_leap_day(self, tmp_path, monkeypatch):
        """Test generation for someone born on leap day."""
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        dob = "2000-02-29"
        weeks = calculate_weeks_lived(dob)
        output_path = generate_life_weeks_grid(weeks, dob)

        assert output_path.exists()
        img = Image.open(output_path)
        assert img.format == "PNG"

    def test_multiple_generations_same_day(self, tmp_path, monkeypatch):
        """Test that multiple generations on same day create different files."""
        test_vault_dir = tmp_path / "Research" / "vault" / "temp_images"
        test_vault_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        dob = "1984-04-25"
        path1 = generate_from_dob(dob)
        path2 = generate_from_dob(dob)

        # Both should exist (second overwrites first with same name)
        assert path1 == path2
        assert path1.exists()

    def test_directory_creation(self, tmp_path, monkeypatch):
        """Test that directory is created if it doesn't exist."""
        # Don't create the directory beforehand
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        dob = "1984-04-25"
        output_path = generate_from_dob(dob)

        assert output_path.exists()
        assert output_path.parent.exists()
        assert output_path.parent.name == "temp_images"
