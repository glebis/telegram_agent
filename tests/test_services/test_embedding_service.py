"""
Tests for EmbeddingService.

This test suite covers:
- Text embedding generation
- Image embedding generation
- Batch embedding generation
- Bytes/array conversion utilities
- Cosine similarity calculation
- Model info retrieval
- Error handling and edge cases
"""

import pytest
import struct
import asyncio
import numpy as np
from io import BytesIO
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from PIL import Image

from src.services.embedding_service import (
    EmbeddingService,
    get_embedding_service,
    _embedding_service,
)


class TestEmbeddingServiceInitialization:
    """Tests for EmbeddingService initialization and configuration"""

    def test_initialization_default_model(self):
        """Test that EmbeddingService initializes with default model name from env"""
        # Clear EMBEDDING_MODEL to test default behavior
        with patch.dict("os.environ", {"EMBEDDING_MODEL": "clip-ViT-B-32"}):
            service = EmbeddingService()
            assert service.model_name == "clip-ViT-B-32"
            assert service.model is None
            assert service.embedding_dim == 384

    def test_initialization_custom_model_from_env(self):
        """Test that EmbeddingService respects EMBEDDING_MODEL env var"""
        with patch.dict("os.environ", {"EMBEDDING_MODEL": "custom-model-v1"}):
            service = EmbeddingService()
            assert service.model_name == "custom-model-v1"

    def test_initialization_device_detection_cpu(self):
        """Test device detection defaults to CPU when CUDA unavailable"""
        with patch("src.services.embedding_service.TORCH_AVAILABLE", True):
            with patch("src.services.embedding_service.torch") as mock_torch:
                mock_torch.cuda.is_available.return_value = False
                service = EmbeddingService()
                assert service.device == "cpu"

    def test_initialization_device_detection_cuda(self):
        """Test device detection uses CUDA when available"""
        with patch("src.services.embedding_service.TORCH_AVAILABLE", True):
            with patch("src.services.embedding_service.torch") as mock_torch:
                mock_torch.cuda.is_available.return_value = True
                service = EmbeddingService()
                assert service.device == "cuda"

    def test_initialization_without_torch(self):
        """Test initialization logs warning when PyTorch unavailable"""
        with patch("src.services.embedding_service.TORCH_AVAILABLE", False):
            with patch("src.services.embedding_service.logger") as mock_logger:
                service = EmbeddingService()
                mock_logger.warning.assert_any_call(
                    "PyTorch not available - using deterministic embeddings only"
                )


class TestTextEmbeddingGeneration:
    """Tests for text embedding generation"""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService instance for testing"""
        return EmbeddingService()

    @pytest.mark.asyncio
    async def test_generate_text_embedding_with_model(self, embedding_service):
        """Test text embedding generation when model is available"""
        mock_embedding = np.array([0.1, 0.2, 0.3] * 128, dtype=np.float32)

        with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
            embedding_service.model = Mock()
            embedding_service.model.encode = Mock(return_value=mock_embedding)

            result = await embedding_service.generate_text_embedding("test text")

            assert isinstance(result, list)
            assert len(result) == 384
            embedding_service.model.encode.assert_called_once_with(
                "test text", convert_to_numpy=True
            )

    @pytest.mark.asyncio
    async def test_generate_text_embedding_fallback_deterministic(self, embedding_service):
        """Test text embedding uses deterministic fallback when model unavailable"""
        with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
            # Model loaded but doesn't have encode method
            embedding_service.model = "deterministic"

            result = await embedding_service.generate_text_embedding("test text")

            assert isinstance(result, list)
            assert len(result) == embedding_service.embedding_dim
            # Verify deterministic - same input gives same output
            result2 = await embedding_service.generate_text_embedding("test text")
            assert result == result2

    @pytest.mark.asyncio
    async def test_generate_text_embedding_different_inputs(self, embedding_service):
        """Test that different text inputs produce different embeddings"""
        # Create mock model that returns deterministic but different embeddings
        mock_model = Mock()
        call_count = [0]

        def mock_encode(text, convert_to_numpy=True):
            call_count[0] += 1
            # Generate different embeddings based on text content
            import hashlib
            text_hash = hashlib.md5(text.encode()).hexdigest()
            np.random.seed(int(text_hash[:8], 16))
            return np.random.rand(384).astype(np.float32)

        mock_model.encode = mock_encode

        with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
            embedding_service.model = mock_model

            result1 = await embedding_service.generate_text_embedding("hello world")
            result2 = await embedding_service.generate_text_embedding("goodbye world")

            assert result1 != result2

    @pytest.mark.asyncio
    async def test_generate_text_embedding_error_handling(self, embedding_service):
        """Test error handling returns zero vector"""
        with patch.object(
            embedding_service, "_load_model", new_callable=AsyncMock
        ) as mock_load:
            mock_load.side_effect = Exception("Model loading failed")

            result = await embedding_service.generate_text_embedding("test")

            assert result == [0.0] * embedding_service.embedding_dim


class TestImageEmbeddingGeneration:
    """Tests for image embedding generation"""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService instance for testing"""
        return EmbeddingService()

    @pytest.fixture
    def sample_image_bytes(self):
        """Create sample image bytes for testing"""
        img = Image.new("RGB", (100, 100), color="red")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)
        return img_bytes.getvalue()

    @pytest.fixture
    def sample_rgba_image_bytes(self):
        """Create sample RGBA image bytes for testing"""
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        return img_bytes.getvalue()

    @pytest.mark.asyncio
    async def test_generate_embedding_success(self, embedding_service, sample_image_bytes):
        """Test successful image embedding generation"""
        result = await embedding_service.generate_embedding(sample_image_bytes)

        assert result is not None
        assert isinstance(result, bytes)
        # Verify structure: 4 bytes for dimension + embedding data
        dimension = struct.unpack("I", result[:4])[0]
        assert dimension == 384

    @pytest.mark.asyncio
    async def test_generate_embedding_rgba_conversion(
        self, embedding_service, sample_rgba_image_bytes
    ):
        """Test that RGBA images are converted to RGB before processing"""
        result = await embedding_service.generate_embedding(sample_rgba_image_bytes)

        assert result is not None
        assert isinstance(result, bytes)

    @pytest.mark.asyncio
    async def test_generate_embedding_deterministic(
        self, embedding_service, sample_image_bytes
    ):
        """Test that same image produces same embedding (deterministic)"""
        result1 = await embedding_service.generate_embedding(sample_image_bytes)
        result2 = await embedding_service.generate_embedding(sample_image_bytes)

        assert result1 == result2

    @pytest.mark.asyncio
    async def test_generate_embedding_different_images(self, embedding_service):
        """Test that different images produce different embeddings"""
        img1 = Image.new("RGB", (100, 100), color="red")
        img1_bytes = BytesIO()
        img1.save(img1_bytes, format="JPEG")

        img2 = Image.new("RGB", (100, 100), color="blue")
        img2_bytes = BytesIO()
        img2.save(img2_bytes, format="JPEG")

        result1 = await embedding_service.generate_embedding(img1_bytes.getvalue())
        result2 = await embedding_service.generate_embedding(img2_bytes.getvalue())

        assert result1 != result2

    @pytest.mark.asyncio
    async def test_generate_embedding_invalid_image_data(self, embedding_service):
        """Test handling of invalid image data"""
        invalid_data = b"not a valid image"

        result = await embedding_service.generate_embedding(invalid_data)

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_embedding_model_not_loaded(self, embedding_service):
        """Test handling when model fails to load"""
        with patch.object(
            embedding_service, "_load_model", new_callable=AsyncMock
        ) as mock_load:
            async def fail_load():
                embedding_service.model = None
            mock_load.side_effect = fail_load

            # Force model to stay None
            embedding_service.model = None
            with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
                embedding_service.model = None
                result = await embedding_service.generate_embedding(b"test")

                assert result is None

    @pytest.mark.asyncio
    async def test_generate_embedding_empty_bytes(self, embedding_service):
        """Test handling of empty image bytes"""
        result = await embedding_service.generate_embedding(b"")

        assert result is None


class TestBatchEmbeddingGeneration:
    """Tests for batch embedding generation"""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService instance for testing"""
        return EmbeddingService()

    @pytest.fixture
    def sample_images(self):
        """Create multiple sample images for batch testing"""
        images = []
        for color in ["red", "green", "blue"]:
            img = Image.new("RGB", (50, 50), color=color)
            img_bytes = BytesIO()
            img.save(img_bytes, format="JPEG")
            img_bytes.seek(0)
            images.append(img_bytes.getvalue())
        return images

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_success(
        self, embedding_service, sample_images
    ):
        """Test successful batch embedding generation"""
        mock_embeddings = np.array([
            np.random.rand(384).astype(np.float32) for _ in range(3)
        ])

        with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
            embedding_service.model = Mock()
            embedding_service.model.encode = Mock(return_value=mock_embeddings)

            results = await embedding_service.generate_embeddings_batch(sample_images)

            assert len(results) == 3
            assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_partial_failure(self, embedding_service):
        """Test batch processing with some invalid images"""
        valid_img = Image.new("RGB", (50, 50), color="red")
        valid_bytes = BytesIO()
        valid_img.save(valid_bytes, format="JPEG")

        images = [
            valid_bytes.getvalue(),
            b"invalid image data",
            valid_bytes.getvalue(),
        ]

        mock_embeddings = np.array([
            np.random.rand(384).astype(np.float32) for _ in range(2)
        ])

        with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
            embedding_service.model = Mock()
            embedding_service.model.encode = Mock(return_value=mock_embeddings)

            results = await embedding_service.generate_embeddings_batch(images)

            assert len(results) == 3
            assert results[0] is not None  # First valid image
            assert results[1] is None  # Invalid image
            assert results[2] is not None  # Second valid image

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_all_invalid(self, embedding_service):
        """Test batch processing when all images are invalid"""
        invalid_images = [b"invalid1", b"invalid2", b"invalid3"]

        results = await embedding_service.generate_embeddings_batch(invalid_images)

        assert len(results) == 3
        assert all(r is None for r in results)

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_empty_list(self, embedding_service):
        """Test batch processing with empty list"""
        results = await embedding_service.generate_embeddings_batch([])

        assert results == []

    @pytest.mark.asyncio
    async def test_generate_embeddings_batch_exception_handling(
        self, embedding_service, sample_images
    ):
        """Test error handling in batch processing"""
        with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
            embedding_service.model = Mock()
            embedding_service.model.encode = Mock(side_effect=Exception("Batch error"))

            results = await embedding_service.generate_embeddings_batch(sample_images)

            assert len(results) == 3
            assert all(r is None for r in results)


class TestBytesArrayConversion:
    """Tests for bytes/array conversion utilities"""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService instance for testing"""
        return EmbeddingService()

    def test_array_to_bytes_float32(self, embedding_service):
        """Test converting float32 numpy array to bytes"""
        array = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)

        result = embedding_service._array_to_bytes(array)

        assert isinstance(result, bytes)
        # 4 bytes for dimension + 4 floats * 4 bytes each = 20 bytes
        assert len(result) == 4 + (4 * 4)

    def test_array_to_bytes_type_conversion(self, embedding_service):
        """Test that non-float32 arrays are converted"""
        array = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float64)

        result = embedding_service._array_to_bytes(array)

        assert isinstance(result, bytes)
        # Should be converted to float32
        assert len(result) == 4 + (4 * 4)

    def test_bytes_to_array_success(self, embedding_service):
        """Test converting bytes back to numpy array"""
        original_array = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        packed_bytes = embedding_service._array_to_bytes(original_array)

        result = embedding_service.bytes_to_array(packed_bytes)

        assert isinstance(result, np.ndarray)
        assert len(result) == 4
        np.testing.assert_array_almost_equal(result, original_array)

    def test_bytes_to_array_too_short(self, embedding_service):
        """Test handling of bytes that are too short"""
        short_bytes = b"\x01\x02"  # Less than 4 bytes

        result = embedding_service.bytes_to_array(short_bytes)

        assert result is None

    def test_bytes_to_array_size_mismatch(self, embedding_service):
        """Test handling of size mismatch in bytes data"""
        # Pack dimension as 10, but only provide data for 4 floats
        bad_bytes = struct.pack("I", 10) + np.array([1, 2, 3, 4], dtype=np.float32).tobytes()

        result = embedding_service.bytes_to_array(bad_bytes)

        assert result is None

    def test_bytes_to_array_dimension_mismatch_warning(self, embedding_service):
        """Test warning logged when dimension doesn't match expected"""
        # Create array with different dimension than embedding_dim (384)
        array = np.array([0.1] * 100, dtype=np.float32)
        packed_bytes = struct.pack("I", 100) + array.tobytes()

        with patch("src.services.embedding_service.logger") as mock_logger:
            result = embedding_service.bytes_to_array(packed_bytes)

            mock_logger.warning.assert_called_once()
            assert "dimension mismatch" in str(mock_logger.warning.call_args)

    def test_roundtrip_conversion(self, embedding_service):
        """Test that array -> bytes -> array produces same data"""
        original = np.random.rand(384).astype(np.float32)

        as_bytes = embedding_service._array_to_bytes(original)
        recovered = embedding_service.bytes_to_array(as_bytes)

        np.testing.assert_array_almost_equal(original, recovered)


class TestCosineSimilarity:
    """Tests for cosine similarity calculation"""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService instance for testing"""
        return EmbeddingService()

    def test_calculate_cosine_similarity_identical(self, embedding_service):
        """Test similarity of identical embeddings is 1.0"""
        array = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        embedding_bytes = embedding_service._array_to_bytes(array)

        result = embedding_service.calculate_cosine_similarity(
            embedding_bytes, embedding_bytes
        )

        assert result is not None
        assert abs(result - 1.0) < 0.001

    def test_calculate_cosine_similarity_orthogonal(self, embedding_service):
        """Test similarity of orthogonal embeddings is 0.0"""
        array1 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        array2 = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)

        bytes1 = embedding_service._array_to_bytes(array1)
        bytes2 = embedding_service._array_to_bytes(array2)

        result = embedding_service.calculate_cosine_similarity(bytes1, bytes2)

        assert result is not None
        assert abs(result - 0.0) < 0.001

    def test_calculate_cosine_similarity_opposite(self, embedding_service):
        """Test similarity of opposite embeddings is -1.0"""
        array1 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        array2 = np.array([-1.0, 0.0, 0.0, 0.0], dtype=np.float32)

        bytes1 = embedding_service._array_to_bytes(array1)
        bytes2 = embedding_service._array_to_bytes(array2)

        result = embedding_service.calculate_cosine_similarity(bytes1, bytes2)

        assert result is not None
        assert abs(result - (-1.0)) < 0.001

    def test_calculate_cosine_similarity_partial(self, embedding_service):
        """Test similarity of partially similar embeddings"""
        array1 = np.array([1.0, 1.0, 0.0, 0.0], dtype=np.float32)
        array2 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

        bytes1 = embedding_service._array_to_bytes(array1)
        bytes2 = embedding_service._array_to_bytes(array2)

        result = embedding_service.calculate_cosine_similarity(bytes1, bytes2)

        assert result is not None
        # Expected: (1*1 + 1*0) / (sqrt(2) * 1) = 1/sqrt(2) ≈ 0.707
        assert 0.7 < result < 0.72

    def test_calculate_cosine_similarity_zero_vector(self, embedding_service):
        """Test similarity with zero vector returns 0.0"""
        array1 = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        array2 = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)

        bytes1 = embedding_service._array_to_bytes(array1)
        bytes2 = embedding_service._array_to_bytes(array2)

        result = embedding_service.calculate_cosine_similarity(bytes1, bytes2)

        assert result == 0.0

    def test_calculate_cosine_similarity_invalid_bytes(self, embedding_service):
        """Test handling of invalid embedding bytes"""
        valid_array = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        valid_bytes = embedding_service._array_to_bytes(valid_array)
        invalid_bytes = b"invalid"

        result = embedding_service.calculate_cosine_similarity(valid_bytes, invalid_bytes)

        assert result is None

    def test_calculate_cosine_similarity_both_invalid(self, embedding_service):
        """Test handling when both embeddings are invalid"""
        result = embedding_service.calculate_cosine_similarity(b"bad1", b"bad2")

        assert result is None


class TestModelInfo:
    """Tests for model info retrieval"""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService instance for testing"""
        return EmbeddingService()

    def test_get_model_info_not_loaded(self, embedding_service):
        """Test model info when model not yet loaded"""
        info = embedding_service.get_model_info()

        assert isinstance(info, dict)
        assert info["model_name"] == embedding_service.model_name
        assert info["embedding_dimension"] == 384
        assert info["device"] in ["cpu", "cuda"]
        assert info["loaded"] is False

    def test_get_model_info_loaded(self, embedding_service):
        """Test model info when model is loaded"""
        embedding_service.model = Mock()

        info = embedding_service.get_model_info()

        assert info["loaded"] is True


class TestModelLoading:
    """Tests for model loading functionality"""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService instance for testing"""
        return EmbeddingService()

    @pytest.mark.asyncio
    async def test_load_model_lazy(self, embedding_service):
        """Test that model loads lazily on first use"""
        assert embedding_service.model is None

        await embedding_service._load_model()

        # Model should be set to "deterministic" placeholder
        assert embedding_service.model is not None

    @pytest.mark.asyncio
    async def test_load_model_only_once(self, embedding_service):
        """Test that model only loads once (caching)"""
        await embedding_service._load_model()
        first_model = embedding_service.model

        await embedding_service._load_model()

        assert embedding_service.model is first_model


class TestGlobalServiceInstance:
    """Tests for global service instance management"""

    def test_get_embedding_service_singleton(self):
        """Test that get_embedding_service returns singleton"""
        # Reset global instance
        import src.services.embedding_service as module
        module._embedding_service = None

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2

    def test_get_embedding_service_creates_instance(self):
        """Test that get_embedding_service creates instance if none exists"""
        import src.services.embedding_service as module
        module._embedding_service = None

        service = get_embedding_service()

        assert isinstance(service, EmbeddingService)


class TestEdgeCases:
    """Tests for edge cases and special scenarios"""

    @pytest.fixture
    def embedding_service(self):
        """Create EmbeddingService instance for testing"""
        return EmbeddingService()

    @pytest.mark.asyncio
    async def test_unicode_text_embedding(self, embedding_service):
        """Test text embedding with unicode characters"""
        with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
            embedding_service.model = "deterministic"

            result = await embedding_service.generate_text_embedding("日本語テスト 🎉")

            assert isinstance(result, list)
            assert len(result) == embedding_service.embedding_dim

    @pytest.mark.asyncio
    async def test_empty_text_embedding(self, embedding_service):
        """Test text embedding with empty string"""
        with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
            embedding_service.model = "deterministic"

            result = await embedding_service.generate_text_embedding("")

            assert isinstance(result, list)
            assert len(result) == embedding_service.embedding_dim

    @pytest.mark.asyncio
    async def test_very_long_text_embedding(self, embedding_service):
        """Test text embedding with very long text"""
        long_text = "a" * 10000

        with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
            embedding_service.model = "deterministic"

            result = await embedding_service.generate_text_embedding(long_text)

            assert isinstance(result, list)
            assert len(result) == embedding_service.embedding_dim

    @pytest.mark.asyncio
    async def test_grayscale_image_conversion(self, embedding_service):
        """Test handling of grayscale images (converted to RGB)"""
        img = Image.new("L", (50, 50), color=128)
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        result = await embedding_service.generate_embedding(img_bytes.getvalue())

        assert result is not None

    @pytest.mark.asyncio
    async def test_very_small_image(self, embedding_service):
        """Test handling of very small images"""
        img = Image.new("RGB", (1, 1), color="red")
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)

        result = await embedding_service.generate_embedding(img_bytes.getvalue())

        assert result is not None

    @pytest.mark.asyncio
    async def test_large_image(self, embedding_service):
        """Test handling of larger images"""
        img = Image.new("RGB", (1000, 1000), color="red")
        img_bytes = BytesIO()
        img.save(img_bytes, format="JPEG")
        img_bytes.seek(0)

        result = await embedding_service.generate_embedding(img_bytes.getvalue())

        assert result is not None

    def test_array_to_bytes_empty_array(self, embedding_service):
        """Test handling of empty array"""
        array = np.array([], dtype=np.float32)

        result = embedding_service._array_to_bytes(array)

        assert isinstance(result, bytes)
        # 4 bytes for dimension (0) + 0 data bytes
        assert len(result) == 4

    @pytest.mark.asyncio
    async def test_concurrent_embedding_generation(self, embedding_service):
        """Test concurrent embedding generation doesn't cause issues"""
        texts = ["text1", "text2", "text3", "text4", "text5"]

        with patch.object(embedding_service, "_load_model", new_callable=AsyncMock):
            embedding_service.model = "deterministic"

            tasks = [
                embedding_service.generate_text_embedding(text) for text in texts
            ]
            results = await asyncio.gather(*tasks)

            assert len(results) == 5
            assert all(isinstance(r, list) for r in results)
            assert all(len(r) == embedding_service.embedding_dim for r in results)
