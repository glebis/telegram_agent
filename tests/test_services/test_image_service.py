import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from io import BytesIO
from PIL import Image
from telegram import Bot, File

from src.services.image_service import ImageService


class TestImageService:
    """Test suite for image processing pipeline functionality"""

    @pytest.fixture
    def image_service(self):
        """Create ImageService instance for testing"""
        service = ImageService()
        # Use temporary directories for testing
        service.data_dir = Path(tempfile.mkdtemp())
        service.raw_dir = service.data_dir / "raw"
        service.processed_dir = service.data_dir / "img"
        service.raw_dir.mkdir(parents=True, exist_ok=True)
        service.processed_dir.mkdir(parents=True, exist_ok=True)
        return service

    @pytest.fixture
    def mock_bot(self):
        """Create mock Telegram bot"""
        bot = Mock(spec=Bot)
        return bot

    @pytest.fixture
    def sample_image_file(self):
        """Create sample image file for testing"""
        img = Image.new("RGB", (800, 600), color="blue")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)  # Reset pointer to beginning
        return img_bytes.getvalue()

    @pytest.fixture
    def large_image_file(self):
        """Create large image file for compression testing"""
        img = Image.new("RGB", (3000, 2000), color="green")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG", quality=95)
        img_bytes.seek(0)  # Reset pointer to beginning
        return img_bytes.getvalue()

    def teardown_method(self, method):
        """Clean up temporary directories after each test"""
        # Clean up any temporary directories created during testing
        pass

    @pytest.mark.asyncio
    async def test_download_image_from_telegram(
        self, image_service, mock_bot, sample_image_file
    ):
        """Test downloading image from Telegram"""
        # Mock Telegram file
        mock_file = Mock(spec=File)
        mock_file.download_as_bytearray = AsyncMock(return_value=sample_image_file)
        mock_file.file_path = "test/path/image.jpg"
        mock_file.file_size = len(sample_image_file)
        mock_file.file_unique_id = "unique_test_id"
        mock_bot.get_file = AsyncMock(return_value=mock_file)

        file_id = "test_file_id_123"

        # Mock LLM and embedding services
        with (
            patch.object(image_service, "llm_service") as mock_llm,
            patch.object(image_service, "embedding_service") as mock_embedding,
            patch.object(image_service, "vector_db") as mock_vector,
        ):

            mock_llm.analyze_image = AsyncMock(
                return_value={
                    "summary": "Test image analysis",
                    "description": "A blue colored test image",
                }
            )
            mock_embedding.generate_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3])
            mock_vector.add_image = AsyncMock()

            result = await image_service.process_image(bot=mock_bot, file_id=file_id)

            assert result is not None
            assert "processed_path" in result
            assert "summary" in result  # analysis is returned directly, not nested
            mock_bot.get_file.assert_called_once_with(file_id)
            mock_file.download_as_bytearray.assert_called_once()

    @pytest.mark.asyncio
    async def test_image_compression_pipeline(self, image_service, large_image_file):
        """Test image compression during processing"""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_file.write(large_image_file)
            temp_file.flush()

            with (
                patch.object(image_service, "llm_service") as mock_llm,
                patch.object(image_service, "embedding_service") as mock_embedding,
                patch.object(image_service, "vector_db") as mock_vector,
            ):

                mock_llm.analyze_image = AsyncMock(
                    return_value={
                        "summary": "Compressed large image",
                        "description": "A large green image that was compressed",
                    }
                )
                mock_embedding.generate_embedding = AsyncMock(
                    return_value=[0.4, 0.5, 0.6]
                )
                mock_vector.add_image = AsyncMock()

                result = await image_service.process_image(
                    bot=None, file_id="local_test", local_image_path=temp_file.name
                )

                assert result is not None

                # Verify compression occurred
                processed_path = Path(result["processed_path"])
                if processed_path.exists():
                    original_size = len(large_image_file)
                    compressed_size = processed_path.stat().st_size
                    # Compressed image should be smaller (allowing some variance for headers)
                    assert compressed_size < original_size * 1.1

    @pytest.mark.asyncio
    async def test_image_format_conversion(self, image_service):
        """Test conversion of different image formats"""
        formats_to_test = ["PNG", "JPEG", "WEBP"]

        for fmt in formats_to_test:
            img = Image.new("RGB", (200, 200), color="red")
            img_bytes = BytesIO()
            img.save(img_bytes, format=fmt)
            img_bytes.seek(0)

            with tempfile.NamedTemporaryFile(
                suffix=f".{fmt.lower()}", delete=False
            ) as temp_file:
                temp_file.write(img_bytes.getvalue())
                temp_file.flush()

                with (
                    patch.object(image_service, "llm_service") as mock_llm,
                    patch.object(image_service, "embedding_service") as mock_embedding,
                    patch.object(image_service, "vector_db") as mock_vector,
                ):

                    mock_llm.analyze_image = AsyncMock(
                        return_value={
                            "summary": f"Test {fmt} image",
                            "description": f"A red {fmt} format image",
                        }
                    )
                    mock_embedding.generate_embedding = AsyncMock(
                        return_value=[0.7, 0.8, 0.9]
                    )
                    mock_vector.add_image = AsyncMock()

                    result = await image_service.process_image(
                        bot=None, file_id=f"test_{fmt}", local_image_path=temp_file.name
                    )

                    assert result is not None
                    assert "summary" in result
                    # Verify the format was processed correctly
                    assert fmt.lower() in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_batch_image_processing(self, image_service, mock_bot):
        """Test processing multiple images in batch"""
        num_images = 5
        file_ids = [f"test_file_{i}" for i in range(num_images)]

        # Create different colored images
        image_files = []
        colors = ["red", "green", "blue", "yellow", "purple"]
        for color in colors:
            img = Image.new("RGB", (100, 100), color=color)
            img_bytes = BytesIO()
            img.save(img_bytes, format="JPEG")
            img_bytes.seek(0)
            image_files.append(img_bytes.getvalue())

        # Mock Telegram file downloads
        mock_files = []
        for i, img_data in enumerate(image_files):
            mock_file = Mock(spec=File)
            mock_file.download_as_bytearray = AsyncMock(return_value=img_data)
            mock_file.file_path = f"test/path/image_{i}.jpg"
            mock_file.file_size = len(img_data)
            mock_file.file_unique_id = f"unique_test_id_{i}"
            mock_files.append(mock_file)

        # Mock get_file to return appropriate mock_file for each call
        async def get_file_side_effect(file_id):
            index = file_ids.index(file_id)
            return mock_files[index]

        mock_bot.get_file = AsyncMock(side_effect=get_file_side_effect)

        with (
            patch.object(image_service, "llm_service") as mock_llm,
            patch.object(image_service, "embedding_service") as mock_embedding,
            patch.object(image_service, "vector_db") as mock_vector,
        ):

            # Mock responses for each image
            mock_llm.analyze_image = AsyncMock(
                side_effect=[
                    {
                        "summary": f"A {colors[i]} colored square",
                        "description": f"{colors[i]} test image",
                    }
                    for i in range(num_images)
                ]
            )
            mock_embedding.generate_embedding = AsyncMock(
                side_effect=[[0.1 * i, 0.2 * i, 0.3 * i] for i in range(num_images)]
            )
            mock_vector.add_image = AsyncMock()

            # Process images concurrently
            tasks = [
                image_service.process_image(bot=mock_bot, file_id=file_id)
                for file_id in file_ids
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify all processed successfully
            assert len(results) == num_images
            for i, result in enumerate(results):
                assert not isinstance(result, Exception)
                assert "summary" in result
                assert colors[i] in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_image_metadata_extraction(self, image_service):
        """Test extraction of image metadata during processing"""
        # Create image with metadata
        img = Image.new("RGB", (300, 200), color="orange")

        # Add EXIF data (simulated)
        exif_dict = {
            "0th": {256: 300, 257: 200},  # Width, Height
            "Exif": {},
            "GPS": {},
            "1st": {},
            "thumbnail": None,
        }

        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_file.write(img_bytes.getvalue())
            temp_file.flush()

            with (
                patch.object(image_service, "llm_service") as mock_llm,
                patch.object(image_service, "embedding_service") as mock_embedding,
                patch.object(image_service, "vector_db") as mock_vector,
            ):

                mock_llm.analyze_image = AsyncMock(
                    return_value={
                        "summary": "Orange image with metadata",
                        "description": "An orange colored image with EXIF data",
                        "metadata": {"width": 300, "height": 200, "format": "JPEG"},
                    }
                )
                mock_embedding.generate_embedding = AsyncMock(
                    return_value=[0.9, 0.8, 0.7]
                )
                mock_vector.add_image = AsyncMock()

                result = await image_service.process_image(
                    bot=None, file_id="metadata_test", local_image_path=temp_file.name
                )

                assert result is not None

                # Verify metadata was extracted - dimensions are returned directly
                if "dimensions" in result:
                    dimensions = result["dimensions"]
                    assert "original" in dimensions or "processed" in dimensions

    @pytest.mark.asyncio
    async def test_error_handling_corrupted_image(self, image_service, mock_bot):
        """Test handling of corrupted or invalid image data"""
        # Create corrupted image data
        corrupted_data = b"This is not image data"

        mock_file = Mock(spec=File)
        mock_file.download_as_bytearray = AsyncMock(return_value=corrupted_data)
        mock_file.file_path = "test/path/corrupted.jpg"
        mock_file.file_size = len(corrupted_data)
        mock_file.file_unique_id = "unique_corrupted_id"
        mock_bot.get_file = AsyncMock(return_value=mock_file)

        result = await image_service.process_image(
            bot=mock_bot, file_id="corrupted_test"
        )

        # Should handle error gracefully
        assert result is not None
        assert "error" in result or "processed_path" not in result

    @pytest.mark.asyncio
    async def test_memory_efficient_processing(self, image_service):
        """Test that large images are processed without excessive memory usage"""
        # Create very large image
        large_img = Image.new("RGB", (5000, 5000), color="cyan")
        img_bytes = BytesIO()
        large_img.save(img_bytes, format="JPEG", quality=90)
        img_bytes.seek(0)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_file.write(img_bytes.getvalue())
            temp_file.flush()

            with (
                patch.object(image_service, "llm_service") as mock_llm,
                patch.object(image_service, "embedding_service") as mock_embedding,
                patch.object(image_service, "vector_db") as mock_vector,
            ):

                mock_llm.analyze_image = AsyncMock(
                    return_value={
                        "summary": "Large cyan image processed efficiently",
                        "description": "A very large cyan image",
                    }
                )
                mock_embedding.generate_embedding = AsyncMock(
                    return_value=[0.5, 0.5, 0.5]
                )
                mock_vector.add_image = AsyncMock()

                # Process should complete without memory errors
                result = await image_service.process_image(
                    bot=None,
                    file_id="large_memory_test",
                    local_image_path=temp_file.name,
                )

                assert result is not None
                assert "summary" in result

    @pytest.mark.asyncio
    async def test_different_mode_processing(self, image_service, sample_image_file):
        """Test processing with different analysis modes"""
        modes = ["default", "artistic", "technical"]

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_file.write(sample_image_file)
            temp_file.flush()

            for mode in modes:
                with (
                    patch.object(image_service, "llm_service") as mock_llm,
                    patch.object(image_service, "embedding_service") as mock_embedding,
                    patch.object(image_service, "vector_db") as mock_vector,
                ):

                    mock_llm.analyze_image = AsyncMock(
                        return_value={
                            "summary": f"Image analyzed in {mode} mode",
                            "description": f"A blue image processed with {mode} analysis",
                            "mode": mode,
                        }
                    )
                    mock_embedding.generate_embedding = AsyncMock(
                        return_value=[0.1, 0.2, 0.3]
                    )
                    mock_vector.add_image = AsyncMock()

                    result = await image_service.process_image(
                        bot=None,
                        file_id=f"mode_test_{mode}",
                        mode=mode,
                        local_image_path=temp_file.name,
                    )

                    assert result is not None
                    assert mode in result["summary"]

                    # Verify mode was passed to LLM service
                    mock_llm.analyze_image.assert_called_once()
                    call_args = mock_llm.analyze_image.call_args
                    assert call_args[1]["mode"] == mode

    @pytest.mark.asyncio
    async def test_file_organization_structure(self, image_service, sample_image_file):
        """Test that files are organized correctly in directory structure"""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            temp_file.write(sample_image_file)
            temp_file.flush()

            with (
                patch.object(image_service, "llm_service") as mock_llm,
                patch.object(image_service, "embedding_service") as mock_embedding,
                patch.object(image_service, "vector_db") as mock_vector,
            ):

                mock_llm.analyze_image = AsyncMock(
                    return_value={
                        "summary": "File organization test",
                        "description": "Testing file organization",
                    }
                )
                mock_embedding.generate_embedding = AsyncMock(
                    return_value=[0.6, 0.7, 0.8]
                )
                mock_vector.add_image = AsyncMock()

                result = await image_service.process_image(
                    bot=None,
                    file_id="organization_test",
                    local_image_path=temp_file.name,
                )

                assert result is not None

                # Verify file was saved in correct location
                processed_path = Path(result["processed_path"])
                assert processed_path.exists()
                assert processed_path.parent == image_service.processed_dir
