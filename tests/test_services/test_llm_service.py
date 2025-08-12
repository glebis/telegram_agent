import pytest
import asyncio
import base64
from unittest.mock import Mock, patch, AsyncMock
from io import BytesIO
from PIL import Image

from src.services.llm_service import LLMService


class TestLLMService:
    """Test suite for LLM service focusing on summary generation capabilities"""

    @pytest.fixture
    def llm_service(self):
        """Create LLM service instance for testing"""
        with patch("src.services.llm_service.ModeManager") as mock_mode_manager:
            mock_mode_manager.return_value.get_mode_prompt.return_value = (
                "Analyze this image and provide a summary."
            )
            return LLMService()

    @pytest.fixture
    def sample_image_data(self):
        """Create sample image data for testing"""
        img = Image.new("RGB", (100, 100), color="red")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        return img_bytes.getvalue()

    @pytest.fixture
    def mock_llm_response(self):
        """Mock LLM analysis response with summary"""
        return {
            "summary": "A red square image with minimal visual content",
            "description": "This is a simple red-colored square image with uniform coloring",
            "text_content": "",
            "objects": ["geometric shape", "color block"],
            "emotions": ["neutral"],
            "style": "minimalist",
            "quality_score": 0.3,
            "confidence": 0.95,
        }

    def _create_mock_response(self, content_dict):
        """Helper to create a properly structured mock response"""
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = str(content_dict)
        return mock_response

    @pytest.mark.asyncio
    async def test_analyze_image_generates_summary(
        self, llm_service, sample_image_data, mock_llm_response
    ):
        """Test that image analysis generates proper summary"""
        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch.object(llm_service, "_structure_response") as mock_structure,
        ):

            mock_to_thread.return_value = self._create_mock_response(mock_llm_response)
            mock_structure.return_value = mock_llm_response

            result = await llm_service.analyze_image(
                image_data=sample_image_data, mode="default"
            )

            assert result is not None
            assert "summary" in result
            assert "description" in result
            assert len(result["summary"]) > 0
            assert isinstance(result["summary"], str)
            mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_image_with_artistic_mode(
        self, llm_service, sample_image_data
    ):
        """Test summary generation with artistic mode preset"""
        artistic_response = {
            "summary": "A bold geometric composition featuring pure red pigmentation",
            "artistic_elements": [
                "color theory",
                "minimalism",
                "geometric abstraction",
            ],
            "mood": "bold and confident",
            "composition": "centered square format",
        }

        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch.object(llm_service, "_structure_response") as mock_structure,
        ):

            mock_to_thread.return_value = self._create_mock_response(artistic_response)
            mock_structure.return_value = artistic_response

            result = await llm_service.analyze_image(
                image_data=sample_image_data,
                mode="artistic",
                preset="detailed_artistic",
            )

            assert "summary" in result
            assert (
                "artistic" in result["summary"].lower()
                or "bold" in result["summary"].lower()
            )

    @pytest.mark.asyncio
    async def test_batch_image_analysis_summaries(self, llm_service):
        """Test batch processing of multiple images for summary generation"""
        images = []
        for color in ["red", "blue", "green"]:
            img = Image.new("RGB", (50, 50), color=color)
            img_bytes = BytesIO()
            img.save(img_bytes, format="JPEG")
            images.append(img_bytes.getvalue())

        mock_responses = [
            {"summary": f"A {color} colored square image"}
            for color in ["red", "blue", "green"]
        ]

        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch.object(llm_service, "_structure_response") as mock_structure,
        ):

            mock_to_thread.side_effect = [
                self._create_mock_response(resp) for resp in mock_responses
            ]
            mock_structure.side_effect = mock_responses

            results = []
            for image_data in images:
                result = await llm_service.analyze_image(image_data)
                results.append(result)

            assert len(results) == 3
            for result in results:
                assert "summary" in result
                assert len(result["summary"]) > 0

    @pytest.mark.asyncio
    async def test_summary_quality_validation(self, llm_service, sample_image_data):
        """Test that generated summaries meet quality standards"""
        quality_response = {
            "summary": "A well-composed geometric image featuring solid red coloration with clean edges and uniform saturation.",
            "confidence": 0.92,
            "quality_indicators": [
                "clear_composition",
                "good_lighting",
                "minimal_noise",
            ],
        }

        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch.object(llm_service, "_structure_response") as mock_structure,
        ):

            mock_to_thread.return_value = self._create_mock_response(quality_response)
            mock_structure.return_value = quality_response

            result = await llm_service.analyze_image(sample_image_data)

            # Validate summary quality
            summary = result.get("summary", "")
            assert len(summary.split()) >= 5  # Minimum word count
            assert summary[0].isupper()  # Starts with capital letter
            assert summary.endswith(".")  # Proper punctuation

    @pytest.mark.asyncio
    async def test_error_handling_in_summary_generation(
        self, llm_service, sample_image_data
    ):
        """Test error handling during summary generation"""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = Exception("API Error")

            with pytest.raises(Exception):
                await llm_service.analyze_image(sample_image_data)

    @pytest.mark.asyncio
    async def test_text_extraction_integration_with_summary(self, llm_service):
        """Test that text extraction is properly integrated with summary generation"""
        # Create image with text (simulated)
        img = Image.new("RGB", (200, 100), color="white")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")

        text_response = {
            "summary": "An image containing the text 'Hello World' on a white background",
            "text_content": "Hello World",
            "has_text": True,
        }

        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch.object(llm_service, "_structure_response") as mock_structure,
        ):

            mock_to_thread.return_value = self._create_mock_response(text_response)
            mock_structure.return_value = text_response

            result = await llm_service.analyze_image(
                img_bytes.getvalue(), extract_text=True
            )

            assert "text_content" in result
            assert "summary" in result
            # Summary should reference text content when present
            if result.get("text_content"):
                assert "text" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_mode_based_summary_customization(
        self, llm_service, sample_image_data
    ):
        """Test that different modes produce appropriately customized summaries"""
        modes_and_responses = {
            "default": {"summary": "A red square image with uniform coloring"},
            "artistic": {"summary": "A bold geometric composition in pure red"},
            "technical": {
                "summary": "RGB image, 100x100 pixels, solid red color channel"
            },
        }

        for mode, expected_response in modes_and_responses.items():
            with (
                patch("asyncio.to_thread") as mock_to_thread,
                patch.object(llm_service, "_structure_response") as mock_structure,
            ):

                mock_to_thread.return_value = self._create_mock_response(
                    expected_response
                )
                mock_structure.return_value = expected_response

                result = await llm_service.analyze_image(sample_image_data, mode=mode)

                assert "summary" in result
                summary = result["summary"].lower()

                # Verify mode-appropriate language
                if mode == "artistic":
                    assert any(
                        word in summary for word in ["bold", "composition", "geometric"]
                    )
                elif mode == "technical":
                    assert any(word in summary for word in ["pixels", "rgb", "channel"])

    @pytest.mark.asyncio
    async def test_concurrent_summary_generation(self, llm_service, sample_image_data):
        """Test concurrent summary generation for multiple images"""
        num_concurrent = 3

        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch.object(llm_service, "_structure_response") as mock_structure,
        ):

            mock_response = {"summary": "Concurrent test image"}
            mock_to_thread.return_value = self._create_mock_response(mock_response)
            mock_structure.return_value = mock_response

            # Create concurrent tasks
            tasks = [
                llm_service.analyze_image(sample_image_data)
                for _ in range(num_concurrent)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Verify all completed successfully
            assert len(results) == num_concurrent
            for result in results:
                assert not isinstance(result, Exception)
                assert "summary" in result

    @pytest.mark.asyncio
    async def test_summary_consistency_across_retries(
        self, llm_service, sample_image_data
    ):
        """Test that summary generation is consistent across multiple attempts"""
        consistent_response = {
            "summary": "A consistent red square image for testing",
            "confidence": 0.95,
        }

        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch.object(llm_service, "_structure_response") as mock_structure,
        ):

            mock_to_thread.return_value = self._create_mock_response(
                consistent_response
            )
            mock_structure.return_value = consistent_response

            # Generate summaries multiple times
            results = []
            for _ in range(3):
                result = await llm_service.analyze_image(sample_image_data)
                results.append(result.get("summary", ""))

            # Check consistency (all should be identical with mocked response)
            assert len(set(results)) == 1  # All summaries should be the same
            assert all(len(summary) > 0 for summary in results)
