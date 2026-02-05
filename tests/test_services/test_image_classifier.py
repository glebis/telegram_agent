"""Tests for image classifier service"""

from unittest.mock import AsyncMock, patch

import pytest

from src.services.image_classifier import (
    CLASSIFICATION_PROMPT,
    IMAGE_CATEGORIES,
    ImageClassifier,
    get_image_classifier,
)


class TestImageClassifier:
    """Test suite for ImageClassifier"""

    def test_image_categories_defined(self):
        """Test that all expected categories are defined"""
        expected_categories = [
            "screenshot",
            "receipt",
            "document",
            "photo",
            "diagram",
            "other",
        ]
        assert set(IMAGE_CATEGORIES.keys()) == set(expected_categories)

    def test_category_destinations(self):
        """Test that each category has a valid destination"""
        valid_destinations = ["inbox", "expenses", "media", "research"]
        for category, info in IMAGE_CATEGORIES.items():
            assert "destination" in info
            assert info["destination"] in valid_destinations

    def test_classification_prompt_contains_categories(self):
        """Test that classification prompt includes all categories"""
        for category in IMAGE_CATEGORIES.keys():
            assert category in CLASSIFICATION_PROMPT.lower()

    def test_get_image_classifier_singleton(self):
        """Test that get_image_classifier returns singleton"""
        classifier1 = get_image_classifier()
        classifier2 = get_image_classifier()
        assert classifier1 is classifier2

    def test_classifier_has_models_configured(self):
        """Test that classifier has model names configured"""
        classifier = ImageClassifier()
        assert classifier.groq_model == "meta-llama/llama-4-scout-17b-16e-instruct"
        assert classifier.openai_model == "gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_classify_normalizes_category(self):
        """Test that classify normalizes category names"""
        classifier = ImageClassifier()

        # Mock both API calls to return uppercase category
        with patch.object(
            classifier, "_classify_with_groq", new_callable=AsyncMock
        ) as mock_groq:
            mock_groq.return_value = "SCREENSHOT"

            result = await classifier.classify("/fake/path.jpg")

            assert result["category"] == "screenshot"
            assert result["destination"] == "inbox"

    @pytest.mark.asyncio
    async def test_classify_fallback_to_openai(self):
        """Test that classify falls back to OpenAI when Groq fails"""
        classifier = ImageClassifier()

        with patch.object(
            classifier, "_classify_with_groq", new_callable=AsyncMock
        ) as mock_groq:
            with patch.object(
                classifier, "_classify_with_openai", new_callable=AsyncMock
            ) as mock_openai:
                mock_groq.return_value = None
                mock_openai.return_value = "receipt"

                result = await classifier.classify("/fake/path.jpg")

                assert result["category"] == "receipt"
                assert result["destination"] == "expenses"
                assert result["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_classify_fallback_to_default(self):
        """Test that classify falls back to default when all APIs fail"""
        classifier = ImageClassifier()

        with patch.object(
            classifier, "_classify_with_groq", new_callable=AsyncMock
        ) as mock_groq:
            with patch.object(
                classifier, "_classify_with_openai", new_callable=AsyncMock
            ) as mock_openai:
                mock_groq.return_value = None
                mock_openai.return_value = None

                result = await classifier.classify("/fake/path.jpg")

                assert result["category"] == "other"
                assert result["destination"] == "inbox"
                assert result["provider"] == "default"

    @pytest.mark.asyncio
    async def test_classify_handles_partial_match(self):
        """Test that classify handles partial category matches"""
        classifier = ImageClassifier()

        with patch.object(
            classifier, "_classify_with_groq", new_callable=AsyncMock
        ) as mock_groq:
            # API returns something like "It's a screenshot of a website"
            mock_groq.return_value = "screenshot of website"

            result = await classifier.classify("/fake/path.jpg")

            # Should match "screenshot" category
            assert result["category"] == "screenshot"

    @pytest.mark.asyncio
    async def test_classify_unknown_category_maps_to_other(self):
        """Test that unknown categories map to 'other'"""
        classifier = ImageClassifier()

        with patch.object(
            classifier, "_classify_with_groq", new_callable=AsyncMock
        ) as mock_groq:
            mock_groq.return_value = "completely_unknown_category"

            result = await classifier.classify("/fake/path.jpg")

            assert result["category"] == "other"
            assert result["destination"] == "inbox"

    def test_encode_image_mime_types(self):
        """Test that _encode_image detects correct mime types"""
        classifier = ImageClassifier()

        # Test with a real temp file
        import os
        import tempfile

        test_cases = [
            (".jpg", "image/jpeg"),
            (".jpeg", "image/jpeg"),
            (".png", "image/png"),
            (".gif", "image/gif"),
            (".webp", "image/webp"),
        ]

        for ext, expected_mime in test_cases:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(b"fake image data")
                temp_path = f.name

            try:
                _, mime_type = classifier._encode_image(temp_path)
                assert (
                    mime_type == expected_mime
                ), f"Expected {expected_mime} for {ext}, got {mime_type}"
            finally:
                os.unlink(temp_path)
