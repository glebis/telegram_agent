"""
Tests for the Gallery Service.

Tests cover:
- GalleryService initialization and default settings
- Paginated image retrieval (get_user_images_paginated)
- Single image retrieval by ID (get_image_by_id)
- Gallery page formatting (format_gallery_page)
- Image details formatting (format_image_details)
- Markdown to HTML conversion (_markdown_to_html)
- Edge cases: empty galleries, invalid JSON, missing data
- Error handling and database exceptions
- Global instance management (get_gallery_service)
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.gallery_service import GalleryService, get_gallery_service

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def gallery_service():
    """Create a fresh GalleryService instance for testing."""
    return GalleryService()


@pytest.fixture
def mock_image():
    """Create a mock Image model instance."""
    image = MagicMock()
    image.id = 1
    image.file_id = "file_123"
    image.created_at = datetime(2024, 1, 15, 10, 30, 0)
    image.mode_used = "artistic"
    image.preset_used = "vivid"
    image.analysis = json.dumps(
        {
            "description": "A beautiful sunset over the mountains with vibrant orange and purple hues"
        }
    )
    image.width = 1920
    image.height = 1080
    image.file_size = 2048000
    image.processing_status = "completed"
    image.chat = MagicMock()
    return image


@pytest.fixture
def mock_image_no_analysis():
    """Create a mock Image with no analysis data."""
    image = MagicMock()
    image.id = 2
    image.file_id = "file_456"
    image.created_at = datetime(2024, 1, 16, 14, 0, 0)
    image.mode_used = "default"
    image.preset_used = None
    image.analysis = None
    image.width = None
    image.height = None
    image.file_size = None
    image.processing_status = "completed"
    image.chat = MagicMock()
    return image


@pytest.fixture
def mock_image_invalid_json():
    """Create a mock Image with invalid JSON in analysis."""
    image = MagicMock()
    image.id = 3
    image.file_id = "file_789"
    image.created_at = datetime(2024, 1, 17, 9, 15, 0)
    image.mode_used = "technical"
    image.preset_used = None
    image.analysis = "not valid json {{{}"
    image.width = 800
    image.height = 600
    image.file_size = 512000
    image.processing_status = "completed"
    image.chat = MagicMock()
    return image


@pytest.fixture
def sample_image_data():
    """Create sample image data dictionary (as returned by service methods)."""
    return {
        "id": 1,
        "file_id": "file_123",
        "created_at": datetime(2024, 1, 15, 10, 30, 0),
        "mode_used": "artistic",
        "preset_used": "vivid",
        "full_description": "A beautiful sunset over the mountains",
        "short_description": "A beautiful sunset over the mountains",
        "analysis_data": {"description": "A beautiful sunset over the mountains"},
        "width": 1920,
        "height": 1080,
        "file_size": 2048000,
    }


@pytest.fixture
def sample_image_data_long_description():
    """Create sample image data with a long description (>50 chars)."""
    long_desc = "A beautiful sunset over the mountains with vibrant orange and purple hues reflecting on a calm lake"
    return {
        "id": 2,
        "file_id": "file_456",
        "created_at": datetime(2024, 1, 16, 14, 0, 0),
        "mode_used": "default",
        "preset_used": None,
        "full_description": long_desc,
        "short_description": long_desc[:50] + "...",
        "analysis_data": {"description": long_desc},
        "width": 1920,
        "height": 1080,
        "file_size": 3072000,
    }


# =============================================================================
# GalleryService Initialization Tests
# =============================================================================


class TestGalleryServiceInit:
    """Tests for GalleryService initialization."""

    def test_default_initialization(self):
        """Test that GalleryService initializes with default settings."""
        service = GalleryService()
        assert service.images_per_page == 10

    def test_images_per_page_attribute(self, gallery_service):
        """Test images_per_page attribute is accessible and correct."""
        assert hasattr(gallery_service, "images_per_page")
        assert gallery_service.images_per_page == 10


# =============================================================================
# get_user_images_paginated Tests
# =============================================================================


class TestGetUserImagesPaginated:
    """Tests for get_user_images_paginated method."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_images(self, gallery_service):
        """Test that empty list is returned when user has no images."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            # Setup mock session context manager
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            # Mock count query returning 0
            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 0

            # Mock images query returning empty
            mock_images_result = MagicMock()
            mock_images_result.scalars.return_value.all.return_value = []

            mock_session_instance.execute = AsyncMock(
                side_effect=[mock_count_result, mock_images_result]
            )

            images, total, pages = await gallery_service.get_user_images_paginated(
                user_id=123, page=1
            )

            assert images == []
            assert total == 0
            assert pages == 1

    @pytest.mark.asyncio
    async def test_returns_paginated_images(self, gallery_service, mock_image):
        """Test that paginated images are returned correctly."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            # Mock count query returning 1
            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 1

            # Mock images query returning one image
            mock_images_result = MagicMock()
            mock_images_result.scalars.return_value.all.return_value = [mock_image]

            mock_session_instance.execute = AsyncMock(
                side_effect=[mock_count_result, mock_images_result]
            )

            images, total, pages = await gallery_service.get_user_images_paginated(
                user_id=123, page=1
            )

            assert len(images) == 1
            assert total == 1
            assert pages == 1
            assert images[0]["id"] == 1
            assert images[0]["file_id"] == "file_123"
            assert images[0]["mode_used"] == "artistic"
            assert images[0]["preset_used"] == "vivid"

    @pytest.mark.asyncio
    async def test_respects_custom_per_page(self, gallery_service, mock_image):
        """Test that custom per_page value is respected."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 25

            mock_images_result = MagicMock()
            mock_images_result.scalars.return_value.all.return_value = [mock_image] * 5

            mock_session_instance.execute = AsyncMock(
                side_effect=[mock_count_result, mock_images_result]
            )

            images, total, pages = await gallery_service.get_user_images_paginated(
                user_id=123, page=1, per_page=5
            )

            assert len(images) == 5
            assert total == 25
            assert pages == 5  # 25 / 5 = 5 pages

    @pytest.mark.asyncio
    async def test_calculates_total_pages_correctly(self, gallery_service, mock_image):
        """Test that total pages calculation is correct with different totals."""
        test_cases = [
            (0, 10, 1),  # 0 images = 1 page (minimum)
            (5, 10, 1),  # 5 images / 10 per page = 1 page
            (10, 10, 1),  # 10 images / 10 per page = 1 page
            (11, 10, 2),  # 11 images / 10 per page = 2 pages
            (25, 10, 3),  # 25 images / 10 per page = 3 pages
            (100, 10, 10),  # 100 images / 10 per page = 10 pages
        ]

        for total_images, per_page, expected_pages in test_cases:
            with patch("src.services.gallery_service.get_db_session") as mock_session:
                mock_session_instance = AsyncMock()
                mock_session.return_value.__aenter__ = AsyncMock(
                    return_value=mock_session_instance
                )
                mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

                mock_count_result = MagicMock()
                mock_count_result.scalar.return_value = total_images

                mock_images_result = MagicMock()
                mock_images_result.scalars.return_value.all.return_value = []

                mock_session_instance.execute = AsyncMock(
                    side_effect=[mock_count_result, mock_images_result]
                )

                _, total, pages = await gallery_service.get_user_images_paginated(
                    user_id=123, page=1, per_page=per_page
                )

                assert total == total_images
                assert (
                    pages == expected_pages
                ), f"Expected {expected_pages} pages for {total_images} images"

    @pytest.mark.asyncio
    async def test_handles_null_analysis(self, gallery_service, mock_image_no_analysis):
        """Test handling of images with null analysis field."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 1

            mock_images_result = MagicMock()
            mock_images_result.scalars.return_value.all.return_value = [
                mock_image_no_analysis
            ]

            mock_session_instance.execute = AsyncMock(
                side_effect=[mock_count_result, mock_images_result]
            )

            images, _, _ = await gallery_service.get_user_images_paginated(
                user_id=123, page=1
            )

            assert len(images) == 1
            assert images[0]["analysis_data"] == {}
            assert images[0]["full_description"] == "No description available"
            assert images[0]["short_description"] == "No description available"

    @pytest.mark.asyncio
    async def test_handles_invalid_json_analysis(
        self, gallery_service, mock_image_invalid_json
    ):
        """Test handling of images with invalid JSON in analysis field."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 1

            mock_images_result = MagicMock()
            mock_images_result.scalars.return_value.all.return_value = [
                mock_image_invalid_json
            ]

            mock_session_instance.execute = AsyncMock(
                side_effect=[mock_count_result, mock_images_result]
            )

            images, _, _ = await gallery_service.get_user_images_paginated(
                user_id=123, page=1
            )

            assert len(images) == 1
            assert images[0]["analysis_data"] == {
                "description": "Analysis parsing error"
            }

    @pytest.mark.asyncio
    async def test_truncates_long_descriptions(self, gallery_service, mock_image):
        """Test that long descriptions are truncated to 50 characters."""
        # Modify mock image to have a long description
        long_desc = "A" * 100
        mock_image.analysis = json.dumps({"description": long_desc})

        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 1

            mock_images_result = MagicMock()
            mock_images_result.scalars.return_value.all.return_value = [mock_image]

            mock_session_instance.execute = AsyncMock(
                side_effect=[mock_count_result, mock_images_result]
            )

            images, _, _ = await gallery_service.get_user_images_paginated(
                user_id=123, page=1
            )

            assert images[0]["short_description"] == "A" * 50 + "..."
            assert images[0]["full_description"] == long_desc

    @pytest.mark.asyncio
    async def test_returns_default_mode_for_null_mode(
        self, gallery_service, mock_image
    ):
        """Test that 'default' is used when mode_used is None."""
        mock_image.mode_used = None

        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 1

            mock_images_result = MagicMock()
            mock_images_result.scalars.return_value.all.return_value = [mock_image]

            mock_session_instance.execute = AsyncMock(
                side_effect=[mock_count_result, mock_images_result]
            )

            images, _, _ = await gallery_service.get_user_images_paginated(
                user_id=123, page=1
            )

            assert images[0]["mode_used"] == "default"

    @pytest.mark.asyncio
    async def test_handles_database_exception(self, gallery_service):
        """Test that database exceptions are handled gracefully."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Database connection failed")
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            images, total, pages = await gallery_service.get_user_images_paginated(
                user_id=123, page=1
            )

            assert images == []
            assert total == 0
            assert pages == 1


# =============================================================================
# get_image_by_id Tests
# =============================================================================


class TestGetImageById:
    """Tests for get_image_by_id method."""

    @pytest.mark.asyncio
    async def test_returns_image_when_found(self, gallery_service, mock_image):
        """Test that image data is returned when image exists."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_image

            mock_session_instance.execute = AsyncMock(return_value=mock_result)

            result = await gallery_service.get_image_by_id(image_id=1, user_id=123)

            assert result is not None
            assert result["id"] == 1
            assert result["file_id"] == "file_123"
            assert result["mode_used"] == "artistic"
            assert result["width"] == 1920
            assert result["height"] == 1080

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, gallery_service):
        """Test that None is returned when image doesn't exist."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None

            mock_session_instance.execute = AsyncMock(return_value=mock_result)

            result = await gallery_service.get_image_by_id(image_id=999, user_id=123)

            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_user(self, gallery_service):
        """Test that None is returned when image belongs to different user."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            # Simulate that the query returns None due to user_id mismatch
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None

            mock_session_instance.execute = AsyncMock(return_value=mock_result)

            result = await gallery_service.get_image_by_id(image_id=1, user_id=999)

            assert result is None

    @pytest.mark.asyncio
    async def test_handles_null_analysis(self, gallery_service, mock_image_no_analysis):
        """Test handling of image with null analysis field."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_image_no_analysis

            mock_session_instance.execute = AsyncMock(return_value=mock_result)

            result = await gallery_service.get_image_by_id(image_id=2, user_id=123)

            assert result is not None
            assert result["analysis_data"] == {}
            assert result["full_description"] == "No description available"

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self, gallery_service, mock_image_invalid_json):
        """Test handling of image with invalid JSON analysis."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_image_invalid_json

            mock_session_instance.execute = AsyncMock(return_value=mock_result)

            result = await gallery_service.get_image_by_id(image_id=3, user_id=123)

            assert result is not None
            assert result["analysis_data"] == {"description": "Analysis parsing error"}

    @pytest.mark.asyncio
    async def test_includes_processing_time_and_similar_count(
        self, gallery_service, mock_image
    ):
        """Test that processing_time and similar_count are extracted from analysis."""
        mock_image.analysis = json.dumps(
            {"description": "Test image", "processing_time": 2.5, "similar_count": 3}
        )

        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_image

            mock_session_instance.execute = AsyncMock(return_value=mock_result)

            result = await gallery_service.get_image_by_id(image_id=1, user_id=123)

            assert result["processing_time"] == 2.5
            assert result["similar_count"] == 3

    @pytest.mark.asyncio
    async def test_handles_database_exception(self, gallery_service):
        """Test that database exceptions are handled gracefully."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock(
                side_effect=Exception("Database error")
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await gallery_service.get_image_by_id(image_id=1, user_id=123)

            assert result is None


# =============================================================================
# format_gallery_page Tests
# =============================================================================


class TestFormatGalleryPage:
    """Tests for format_gallery_page method."""

    def test_formats_empty_gallery(self, gallery_service):
        """Test formatting of empty gallery."""
        result = gallery_service.format_gallery_page(
            images=[], page=1, total_pages=1, total_images=0
        )

        assert "Your Image Gallery" in result
        assert "No images found yet" in result
        assert "Send me some images" in result

    def test_formats_single_image_gallery(self, gallery_service, sample_image_data):
        """Test formatting of gallery with single image."""
        result = gallery_service.format_gallery_page(
            images=[sample_image_data], page=1, total_pages=1, total_images=1
        )

        assert "Your Image Gallery" in result
        assert "Page 1/1" in result
        assert "Total Images: 1" in result
        assert "Image 1" in result
        assert "Artistic - vivid" in result
        assert "2024-01-15" in result
        assert sample_image_data["short_description"] in result

    def test_formats_multiple_pages(self, gallery_service, sample_image_data):
        """Test formatting of gallery page with pagination info."""
        result = gallery_service.format_gallery_page(
            images=[sample_image_data], page=3, total_pages=5, total_images=50
        )

        assert "Page 3/5" in result
        assert "Total Images: 50" in result
        # Image number should reflect page offset
        assert "Image 21" in result  # (3-1) * 10 + 1 = 21

    def test_formats_image_without_preset(self, gallery_service, sample_image_data):
        """Test formatting when image has no preset."""
        sample_image_data["preset_used"] = None

        result = gallery_service.format_gallery_page(
            images=[sample_image_data], page=1, total_pages=1, total_images=1
        )

        # Should show mode without preset suffix
        assert "Artistic" in result
        assert " - " not in result.split("Artistic")[1].split("\n")[0]

    def test_formats_date_string_instead_of_datetime(
        self, gallery_service, sample_image_data
    ):
        """Test formatting when created_at is a string instead of datetime."""
        sample_image_data["created_at"] = "2024-01-15 10:30:00"

        result = gallery_service.format_gallery_page(
            images=[sample_image_data], page=1, total_pages=1, total_images=1
        )

        assert "2024-01-15 10:30:00" in result

    def test_html_formatting_in_output(self, gallery_service, sample_image_data):
        """Test that HTML tags are present in output."""
        result = gallery_service.format_gallery_page(
            images=[sample_image_data], page=1, total_pages=1, total_images=1
        )

        assert "<b>" in result
        assert "</b>" in result

    def test_formats_multiple_images(self, gallery_service, sample_image_data):
        """Test formatting of gallery with multiple images."""
        images = [
            sample_image_data.copy(),
            sample_image_data.copy(),
            sample_image_data.copy(),
        ]
        images[1]["id"] = 2
        images[2]["id"] = 3

        result = gallery_service.format_gallery_page(
            images=images, page=1, total_pages=1, total_images=3
        )

        assert "Image 1" in result
        assert "Image 2" in result
        assert "Image 3" in result


# =============================================================================
# format_image_details Tests
# =============================================================================


class TestFormatImageDetails:
    """Tests for format_image_details method."""

    def test_formats_complete_image_details(self, gallery_service):
        """Test formatting of complete image details."""
        image_data = {
            "id": 1,
            "mode_used": "artistic",
            "preset_used": "vivid",
            "created_at": datetime(2024, 1, 15, 10, 30, 0),
            "width": 1920,
            "height": 1080,
            "processing_time": 2.5,
            "similar_count": 3,
            "full_description": "A beautiful sunset",
        }

        result = gallery_service.format_image_details(image_data)

        assert "Image Details" in result
        assert "Artistic - vivid" in result
        assert "2024-01-15 10:30" in result
        assert "1920" in result
        assert "1080" in result
        assert "2.5s" in result
        assert "3 found" in result
        assert "A beautiful sunset" in result

    def test_formats_without_optional_fields(self, gallery_service):
        """Test formatting when optional fields are missing."""
        image_data = {
            "id": 1,
            "mode_used": "default",
            "preset_used": None,
            "created_at": datetime(2024, 1, 15, 10, 30, 0),
            "width": None,
            "height": None,
            "processing_time": None,
            "similar_count": 0,
            "full_description": "Simple image",
        }

        result = gallery_service.format_image_details(image_data)

        assert "Image Details" in result
        assert "Default" in result
        # Should not contain size line when dimensions are None
        assert "Size:" not in result
        # Should not contain processing time when None
        assert "Processed in:" not in result
        # Should not contain similar count when 0
        assert "Similar Images:" not in result

    def test_formats_date_as_string(self, gallery_service):
        """Test formatting when created_at is a string."""
        image_data = {
            "mode_used": "default",
            "preset_used": None,
            "created_at": "2024-01-15 10:30:00",
            "width": None,
            "height": None,
            "processing_time": None,
            "similar_count": 0,
            "full_description": "Test",
        }

        result = gallery_service.format_image_details(image_data)

        assert "2024-01-15 10:30:00" in result

    def test_converts_markdown_in_description(self, gallery_service):
        """Test that markdown in description is converted to HTML."""
        image_data = {
            "mode_used": "default",
            "preset_used": None,
            "created_at": datetime(2024, 1, 15, 10, 30, 0),
            "width": None,
            "height": None,
            "processing_time": None,
            "similar_count": 0,
            "full_description": "This is **bold** and *italic* text",
        }

        result = gallery_service.format_image_details(image_data)

        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result


# =============================================================================
# _markdown_to_html Tests
# =============================================================================


class TestMarkdownToHtml:
    """Tests for _markdown_to_html method."""

    def test_converts_bold_markdown(self, gallery_service):
        """Test conversion of **bold** to <b>bold</b>."""
        result = gallery_service._markdown_to_html("This is **bold** text")

        assert "<b>bold</b>" in result
        assert "**" not in result

    def test_converts_italic_markdown(self, gallery_service):
        """Test conversion of *italic* to <i>italic</i>."""
        result = gallery_service._markdown_to_html("This is *italic* text")

        assert "<i>italic</i>" in result
        assert result.count("*") == 0

    def test_converts_nested_formatting(self, gallery_service):
        """Test conversion of mixed bold and italic."""
        result = gallery_service._markdown_to_html("Both **bold** and *italic*")

        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result

    def test_escapes_html_characters(self, gallery_service):
        """Test that HTML special characters are escaped."""
        result = gallery_service._markdown_to_html("Use <script> and & symbols")

        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result
        assert "<script>" not in result

    def test_handles_numbered_lists_with_bold(self, gallery_service):
        """Test conversion of numbered list items with bold text."""
        result = gallery_service._markdown_to_html("1. **First item**: description")

        assert "<b>First item</b>" in result

    def test_handles_empty_string(self, gallery_service):
        """Test handling of empty string."""
        result = gallery_service._markdown_to_html("")

        assert result == ""

    def test_handles_plain_text(self, gallery_service):
        """Test that plain text passes through unchanged (except escaping)."""
        result = gallery_service._markdown_to_html("Plain text without formatting")

        assert result == "Plain text without formatting"


# =============================================================================
# Global Instance Tests
# =============================================================================


class TestGlobalInstance:
    """Tests for global instance management."""

    def test_get_gallery_service_creates_instance(self):
        """Test that get_gallery_service creates an instance if needed."""
        import src.services.gallery_service as gs

        gs._gallery_service = None

        service = get_gallery_service()

        assert service is not None
        assert isinstance(service, GalleryService)

    def test_get_gallery_service_returns_same_instance(self):
        """Test that get_gallery_service returns the same instance."""
        service1 = get_gallery_service()
        service2 = get_gallery_service()

        assert service1 is service2

    def test_get_gallery_service_singleton_pattern(self):
        """Test that the singleton pattern works correctly."""
        import src.services.gallery_service as gs

        # Reset the global instance
        gs._gallery_service = None

        # First call creates instance
        service1 = get_gallery_service()
        assert gs._gallery_service is service1

        # Second call returns same instance
        service2 = get_gallery_service()
        assert service2 is service1
        assert gs._gallery_service is service1


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_page_zero_treated_as_negative_offset(self, gallery_service):
        """Test behavior when page=0 (results in negative offset)."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 0

            mock_images_result = MagicMock()
            mock_images_result.scalars.return_value.all.return_value = []

            mock_session_instance.execute = AsyncMock(
                side_effect=[mock_count_result, mock_images_result]
            )

            # Page 0 would create offset of -10, but query should still work
            images, total, pages = await gallery_service.get_user_images_paginated(
                user_id=123, page=0
            )

            # Should handle gracefully (likely returning page 1 behavior)
            assert isinstance(images, list)
            assert isinstance(total, int)
            assert isinstance(pages, int)

    @pytest.mark.asyncio
    async def test_very_large_page_number(self, gallery_service):
        """Test behavior with very large page number."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = 5

            mock_images_result = MagicMock()
            mock_images_result.scalars.return_value.all.return_value = []

            mock_session_instance.execute = AsyncMock(
                side_effect=[mock_count_result, mock_images_result]
            )

            images, total, pages = await gallery_service.get_user_images_paginated(
                user_id=123, page=999999
            )

            # Should return empty list for page beyond available data
            assert images == []
            assert total == 5
            assert pages == 1

    def test_format_gallery_with_special_characters_in_description(
        self, gallery_service
    ):
        """Test gallery formatting with special characters in description."""
        image_data = {
            "id": 1,
            "mode_used": "default",
            "preset_used": None,
            "created_at": datetime(2024, 1, 15, 10, 30, 0),
            "short_description": "Image with <script> & 'quotes' \"double\"",
        }

        # Should not raise an exception
        result = gallery_service.format_gallery_page(
            images=[image_data], page=1, total_pages=1, total_images=1
        )

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_handles_none_count_result(self, gallery_service):
        """Test handling when count query returns None."""
        with patch("src.services.gallery_service.get_db_session") as mock_session:
            mock_session_instance = AsyncMock()
            mock_session.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            mock_session.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_count_result = MagicMock()
            mock_count_result.scalar.return_value = None  # Could happen in edge cases

            mock_images_result = MagicMock()
            mock_images_result.scalars.return_value.all.return_value = []

            mock_session_instance.execute = AsyncMock(
                side_effect=[mock_count_result, mock_images_result]
            )

            images, total, pages = await gallery_service.get_user_images_paginated(
                user_id=123, page=1
            )

            # Should handle None as 0
            assert images == []
            assert total == 0
            assert pages == 1

    def test_format_details_with_zero_processing_time(self, gallery_service):
        """Test formatting when processing_time is 0."""
        image_data = {
            "mode_used": "default",
            "preset_used": None,
            "created_at": datetime(2024, 1, 15, 10, 30, 0),
            "width": 100,
            "height": 100,
            "processing_time": 0,  # Zero but not None
            "similar_count": 0,
            "full_description": "Test",
        }

        result = gallery_service.format_image_details(image_data)

        # Zero is falsy, so should not show processing time
        assert "Processed in:" not in result

    def test_format_details_with_get_method_fallback(self, gallery_service):
        """Test that .get() method handles missing keys gracefully."""
        # Missing processing_time and similar_count entirely
        image_data = {
            "mode_used": "default",
            "preset_used": None,
            "created_at": datetime(2024, 1, 15, 10, 30, 0),
            "width": None,
            "height": None,
            "full_description": "Test",
        }

        # Should not raise KeyError
        result = gallery_service.format_image_details(image_data)

        assert isinstance(result, str)
        assert "Processed in:" not in result
        assert "Similar Images:" not in result
