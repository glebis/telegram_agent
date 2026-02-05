"""
Life Weeks Image Generation Service

Generates 'Life in Weeks' grid visualization showing weeks lived since birth.
Inspired by Tim Urban's "Your Life in Weeks" from Wait But Why.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple, Union

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageFont import FreeTypeFont

logger = logging.getLogger(__name__)

# Constants for grid design
WEEKS_PER_YEAR = 52
MAX_YEARS = 90
CELL_SIZE = 20  # pixels
GRID_PADDING = 40  # pixels around the grid
TEXT_AREA_HEIGHT = 150  # pixels for text overlay at bottom

# Colors (RGBA)
FILLED_COLOR = (0, 123, 255, 204)  # Blue, 80% opacity
EMPTY_COLOR = (220, 220, 220, 76)  # Light gray, 30% opacity
GRID_LINE_COLOR = (100, 100, 100, 51)  # Dark gray, 20% opacity
TEXT_COLOR = (50, 50, 50, 255)  # Dark gray text
BACKGROUND_COLOR = (255, 255, 255, 255)  # White


def calculate_weeks_lived(date_of_birth: str) -> int:
    """
    Calculate the number of weeks lived since birth.

    Args:
        date_of_birth: Date string in YYYY-MM-DD format

    Returns:
        Number of complete weeks lived

    Raises:
        ValueError: If date_of_birth is invalid format
    """
    try:
        dob = datetime.strptime(date_of_birth, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format. Expected YYYY-MM-DD: {e}")

    now = datetime.now()
    delta = now - dob

    # Calculate complete weeks (floor division)
    weeks = delta.days // 7

    return weeks


def _calculate_grid_dimensions() -> Tuple[int, int]:
    """Calculate image dimensions based on grid size."""
    grid_width = (WEEKS_PER_YEAR * CELL_SIZE) + (2 * GRID_PADDING)
    grid_height = (MAX_YEARS * CELL_SIZE) + (2 * GRID_PADDING) + TEXT_AREA_HEIGHT
    return grid_width, grid_height


def _draw_grid_lines(draw: ImageDraw.ImageDraw, x_offset: int, y_offset: int) -> None:
    """Draw grid lines for visual separation."""
    # Vertical lines (every 4 weeks = 1 month approx)
    for col in range(0, WEEKS_PER_YEAR + 1, 4):
        x = x_offset + (col * CELL_SIZE)
        y1 = y_offset
        y2 = y_offset + (MAX_YEARS * CELL_SIZE)
        draw.line([(x, y1), (x, y2)], fill=GRID_LINE_COLOR, width=1)

    # Horizontal lines (every 5 years)
    for row in range(0, MAX_YEARS + 1, 5):
        y = y_offset + (row * CELL_SIZE)
        x1 = x_offset
        x2 = x_offset + (WEEKS_PER_YEAR * CELL_SIZE)
        draw.line([(x1, y), (x2, y)], fill=GRID_LINE_COLOR, width=1)


def _draw_cells(
    draw: ImageDraw.ImageDraw, x_offset: int, y_offset: int, weeks_lived: int
) -> None:
    """Draw filled and empty cells representing weeks."""
    total_cells = WEEKS_PER_YEAR * MAX_YEARS

    for cell_index in range(total_cells):
        # Calculate row and column
        row = cell_index // WEEKS_PER_YEAR
        col = cell_index % WEEKS_PER_YEAR

        # Calculate position
        x = x_offset + (col * CELL_SIZE)
        y = y_offset + (row * CELL_SIZE)

        # Determine color
        color = FILLED_COLOR if cell_index < weeks_lived else EMPTY_COLOR

        # Draw rectangle (leave 1px margin for grid lines)
        draw.rectangle([x + 1, y + 1, x + CELL_SIZE - 1, y + CELL_SIZE - 1], fill=color)


def _draw_text_overlay(
    draw: ImageDraw.ImageDraw,
    image_width: int,
    image_height: int,
    weeks_lived: int,
    date_of_birth: str,
) -> None:
    """Draw text information at the bottom of the image."""
    # Calculate derived values
    years_lived = weeks_lived / WEEKS_PER_YEAR
    total_weeks = WEEKS_PER_YEAR * MAX_YEARS
    percentage = (weeks_lived / total_weeks) * 100

    # Calculate age
    dob = datetime.strptime(date_of_birth, "%Y-%m-%d")
    age_years = (datetime.now() - dob).days / 365.25

    # Try to load a nice font, fall back to default
    font_large: Union[FreeTypeFont, ImageFont.ImageFont]
    font_medium: Union[FreeTypeFont, ImageFont.ImageFont]
    font_small: Union[FreeTypeFont, ImageFont.ImageFont]

    try:
        font_large = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
        font_medium = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    except Exception:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Text area starts after grid
    text_y_start = image_height - TEXT_AREA_HEIGHT + 20

    # Main stat: Week number
    week_text = f"Week {weeks_lived:,}"
    draw.text(
        (image_width // 2, text_y_start),
        week_text,
        fill=TEXT_COLOR,
        font=font_large,
        anchor="mt",
    )

    # Secondary stats
    age_text = f"Age: {age_years:.1f} years ({years_lived:.1f} years in weeks)"
    draw.text(
        (image_width // 2, text_y_start + 60),
        age_text,
        fill=TEXT_COLOR,
        font=font_medium,
        anchor="mt",
    )

    # Progress bar
    progress_text = f"{percentage:.1f}% of {MAX_YEARS}-year lifespan"
    draw.text(
        (image_width // 2, text_y_start + 95),
        progress_text,
        fill=TEXT_COLOR,
        font=font_small,
        anchor="mt",
    )


def generate_life_weeks_grid(
    weeks_lived: int, date_of_birth: str, max_age: int = MAX_YEARS
) -> Path:
    """
    Generate a 'Life in Weeks' grid visualization.

    Args:
        weeks_lived: Number of weeks lived
        date_of_birth: Birth date in YYYY-MM-DD format (for age calculation)
        max_age: Maximum age to display (default 90 years)

    Returns:
        Path to the generated PNG image

    Raises:
        ValueError: If parameters are invalid
    """
    if weeks_lived < 0:
        raise ValueError("weeks_lived must be non-negative")

    if max_age < 1 or max_age > 120:
        raise ValueError("max_age must be between 1 and 120")

    # Calculate dimensions
    image_width, image_height = _calculate_grid_dimensions()

    # Create image
    image = Image.new("RGBA", (image_width, image_height), BACKGROUND_COLOR)
    draw = ImageDraw.ImageDraw(image)

    # Calculate grid offset
    x_offset = GRID_PADDING
    y_offset = GRID_PADDING

    # Draw components
    _draw_grid_lines(draw, x_offset, y_offset)
    _draw_cells(draw, x_offset, y_offset, weeks_lived)
    _draw_text_overlay(draw, image_width, image_height, weeks_lived, date_of_birth)

    # Save to temp_images directory
    vault_temp_dir = Path.home() / "Research" / "vault" / "temp_images"
    vault_temp_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d")
    output_path = vault_temp_dir / f"life-weeks-{timestamp}.png"

    image.save(output_path, "PNG")
    logger.info(f"Generated life weeks grid: {output_path}")

    return output_path


def generate_from_dob(date_of_birth: str, max_age: int = MAX_YEARS) -> Path:
    """
    Convenience function to generate grid directly from date of birth.

    Args:
        date_of_birth: Date string in YYYY-MM-DD format
        max_age: Maximum age to display (default 90 years)

    Returns:
        Path to the generated PNG image
    """
    weeks_lived = calculate_weeks_lived(date_of_birth)
    return generate_life_weeks_grid(weeks_lived, date_of_birth, max_age)
