from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.embedding_service import EmbeddingService
from src.services.similarity_service import SimilarityService


class TestSimilarityService:
    """Test suite for vector similarity search functionality"""

    @pytest.fixture
    def similarity_service(self):
        """Create SimilarityService instance for testing"""
        return SimilarityService()

    @pytest.fixture
    def sample_embeddings(self):
        """Create sample embeddings for testing"""
        return {
            "image1": [0.1, 0.2, 0.3, 0.4, 0.5],
            "image2": [0.2, 0.3, 0.4, 0.5, 0.6],
            "image3": [0.9, 0.8, 0.7, 0.6, 0.5],
            "image4": [0.1, 0.15, 0.25, 0.35, 0.45],  # Similar to image1
            "image5": [0.85, 0.75, 0.65, 0.55, 0.45],  # Similar to image3
        }

    @pytest.fixture
    def mock_vector_db(self):
        """Create mock vector database"""
        mock_db = Mock()
        return mock_db

    @pytest.mark.asyncio
    async def test_find_similar_images_basic(
        self, similarity_service, sample_embeddings, mock_vector_db
    ):
        """Test basic similarity search functionality"""
        query_embedding = [0.15, 0.25, 0.35, 0.45, 0.55]  # Similar to image1 and image4

        # Mock database response
        similar_results = [
            {"image_id": "image1", "similarity": 0.95, "file_path": "/test/image1.jpg"},
            {"image_id": "image4", "similarity": 0.92, "file_path": "/test/image4.jpg"},
            {"image_id": "image2", "similarity": 0.78, "file_path": "/test/image2.jpg"},
        ]

        with patch.object(similarity_service, "vector_db", mock_vector_db):
            mock_vector_db.search_similar = AsyncMock(return_value=similar_results)

            results = await similarity_service.find_similar_images(
                query_embedding=query_embedding, limit=3, threshold=0.7
            )

            assert len(results) == 3
            assert (
                results[0]["similarity"] >= results[1]["similarity"]
            )  # Results should be sorted
            assert all(
                result["similarity"] >= 0.7 for result in results
            )  # Above threshold
            mock_vector_db.search_similar.assert_called_once()

    @pytest.mark.asyncio
    async def test_similarity_threshold_filtering(
        self, similarity_service, mock_vector_db
    ):
        """Test that similarity threshold filtering works correctly"""
        query_embedding = [0.5, 0.5, 0.5, 0.5, 0.5]

        # Mock results with varying similarity scores
        all_results = [
            {"image_id": "high_sim", "similarity": 0.95, "file_path": "/test/high.jpg"},
            {"image_id": "med_sim", "similarity": 0.75, "file_path": "/test/med.jpg"},
            {"image_id": "low_sim", "similarity": 0.45, "file_path": "/test/low.jpg"},
        ]

        with patch.object(similarity_service, "vector_db", mock_vector_db):
            mock_vector_db.search_similar = AsyncMock(return_value=all_results)

            # Test with threshold 0.7
            results = await similarity_service.find_similar_images(
                query_embedding=query_embedding, threshold=0.7
            )

            # Should only return images above threshold
            assert len(results) == 2
            assert all(result["similarity"] >= 0.7 for result in results)
            assert results[0]["image_id"] == "high_sim"
            assert results[1]["image_id"] == "med_sim"

    @pytest.mark.asyncio
    async def test_limit_parameter_enforcement(
        self, similarity_service, mock_vector_db
    ):
        """Test that limit parameter properly restricts result count"""
        query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        # Mock more results than limit
        many_results = [
            {
                "image_id": f"image_{i}",
                "similarity": 0.9 - (i * 0.1),
                "file_path": f"/test/image_{i}.jpg",
            }
            for i in range(10)
        ]

        with patch.object(similarity_service, "vector_db", mock_vector_db):
            mock_vector_db.search_similar = AsyncMock(return_value=many_results)

            # Test with limit of 3
            results = await similarity_service.find_similar_images(
                query_embedding=query_embedding, limit=3
            )

            assert len(results) == 3
            # Should return top 3 most similar
            assert (
                results[0]["similarity"]
                >= results[1]["similarity"]
                >= results[2]["similarity"]
            )

    @pytest.mark.asyncio
    async def test_calculate_embedding_similarity(self, similarity_service):
        """Test direct embedding similarity calculation"""
        embedding1 = [1.0, 0.0, 0.0, 0.0]
        embedding2 = [0.0, 1.0, 0.0, 0.0]
        embedding3 = [1.0, 0.0, 0.0, 0.0]  # Identical to embedding1

        # Calculate similarities
        sim_different = similarity_service.calculate_similarity(embedding1, embedding2)
        sim_identical = similarity_service.calculate_similarity(embedding1, embedding3)

        # Identical embeddings should have similarity 1.0
        assert abs(sim_identical - 1.0) < 0.001

        # Orthogonal embeddings should have similarity 0.0
        assert abs(sim_different - 0.0) < 0.001

    @pytest.mark.asyncio
    async def test_batch_similarity_search(self, similarity_service, mock_vector_db):
        """Test searching for similar images to multiple queries"""
        query_embeddings = [
            [0.1, 0.2, 0.3, 0.4, 0.5],
            [0.9, 0.8, 0.7, 0.6, 0.5],
            [0.5, 0.5, 0.5, 0.5, 0.5],
        ]

        # Mock different results for each query
        mock_results = [
            [
                {
                    "image_id": "result_1_1",
                    "similarity": 0.9,
                    "file_path": "/test/1_1.jpg",
                }
            ],
            [
                {
                    "image_id": "result_2_1",
                    "similarity": 0.85,
                    "file_path": "/test/2_1.jpg",
                }
            ],
            [
                {
                    "image_id": "result_3_1",
                    "similarity": 0.8,
                    "file_path": "/test/3_1.jpg",
                }
            ],
        ]

        with patch.object(similarity_service, "vector_db", mock_vector_db):
            mock_vector_db.search_similar = AsyncMock(side_effect=mock_results)

            results = await similarity_service.batch_find_similar(
                query_embeddings=query_embeddings, limit=1
            )

            assert len(results) == 3
            assert mock_vector_db.search_similar.call_count == 3

            # Verify each query got appropriate results
            for i, result_set in enumerate(results):
                assert len(result_set) == 1
                assert f"result_{i+1}_1" in result_set[0]["image_id"]

    @pytest.mark.asyncio
    async def test_similarity_clustering(self, similarity_service, sample_embeddings):
        """Test clustering similar images together"""
        embeddings_list = list(sample_embeddings.values())
        image_ids = list(sample_embeddings.keys())

        clusters = similarity_service.cluster_by_similarity(
            embeddings=embeddings_list, image_ids=image_ids, similarity_threshold=0.8
        )

        assert isinstance(clusters, list)
        assert len(clusters) > 0

        # Each cluster should contain similar images
        for cluster in clusters:
            assert len(cluster) >= 1
            assert all(isinstance(img_id, str) for img_id in cluster)

    @pytest.mark.asyncio
    async def test_duplicate_detection(self, similarity_service, mock_vector_db):
        """Test detection of near-duplicate images"""
        query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        # Mock results with very high similarity (potential duplicates)
        duplicate_results = [
            {
                "image_id": "original",
                "similarity": 1.0,
                "file_path": "/test/original.jpg",
            },
            {
                "image_id": "duplicate1",
                "similarity": 0.99,
                "file_path": "/test/dup1.jpg",
            },
            {
                "image_id": "duplicate2",
                "similarity": 0.98,
                "file_path": "/test/dup2.jpg",
            },
            {
                "image_id": "similar",
                "similarity": 0.85,
                "file_path": "/test/similar.jpg",
            },
        ]

        with patch.object(similarity_service, "vector_db", mock_vector_db):
            mock_vector_db.search_similar = AsyncMock(return_value=duplicate_results)

            duplicates = await similarity_service.find_duplicates(
                query_embedding=query_embedding, duplicate_threshold=0.97
            )

            # Should identify images with similarity >= 0.97 as duplicates
            assert len(duplicates) == 3  # original, duplicate1, duplicate2
            assert all(dup["similarity"] >= 0.97 for dup in duplicates)

    @pytest.mark.asyncio
    async def test_semantic_similarity_search(self, similarity_service, mock_vector_db):
        """Test semantic similarity search with text descriptions"""
        text_query = "red car on a road"

        # Mock embedding service to convert text to embedding
        mock_embedding_service = Mock(spec=EmbeddingService)
        text_embedding = [0.2, 0.4, 0.6, 0.8, 1.0]
        mock_embedding_service.generate_text_embedding = AsyncMock(
            return_value=text_embedding
        )

        # Mock similar image results
        semantic_results = [
            {
                "image_id": "red_car_1",
                "similarity": 0.88,
                "file_path": "/test/red_car.jpg",
                "description": "A red sports car driving on highway",
            },
            {
                "image_id": "car_road_2",
                "similarity": 0.82,
                "file_path": "/test/car_road.jpg",
                "description": "Blue car on country road",
            },
        ]

        with (
            patch.object(
                similarity_service, "embedding_service", mock_embedding_service
            ),
            patch.object(similarity_service, "vector_db", mock_vector_db),
        ):

            mock_vector_db.search_similar = AsyncMock(return_value=semantic_results)

            results = await similarity_service.search_by_text(
                text_query=text_query, limit=2
            )

            assert len(results) == 2
            assert results[0]["similarity"] >= results[1]["similarity"]
            mock_embedding_service.generate_text_embedding.assert_called_once_with(
                text_query
            )

    @pytest.mark.asyncio
    async def test_cross_modal_similarity(self, similarity_service, mock_vector_db):
        """Test similarity search across different types of content"""
        # Test finding images similar to both visual and textual content
        image_embedding = [0.1, 0.3, 0.5, 0.7, 0.9]
        text_embedding = [0.2, 0.4, 0.6, 0.8, 0.8]

        # Mock results for cross-modal search
        cross_modal_results = [
            {
                "image_id": "visual_match",
                "similarity": 0.85,
                "file_path": "/test/visual.jpg",
            },
            {
                "image_id": "textual_match",
                "similarity": 0.78,
                "file_path": "/test/textual.jpg",
            },
            {
                "image_id": "combined_match",
                "similarity": 0.92,
                "file_path": "/test/combined.jpg",
            },
        ]

        with patch.object(similarity_service, "vector_db", mock_vector_db):
            mock_vector_db.search_similar = AsyncMock(return_value=cross_modal_results)

            # Combine embeddings (weighted average)
            combined_embedding = [
                (img_val + txt_val) / 2
                for img_val, txt_val in zip(image_embedding, text_embedding)
            ]

            results = await similarity_service.find_similar_images(
                query_embedding=combined_embedding, limit=3
            )

            assert len(results) == 3
            # Combined match should score highest
            assert results[0]["image_id"] == "combined_match"

    @pytest.mark.asyncio
    async def test_similarity_ranking_accuracy(self, similarity_service):
        """Test that similarity ranking produces accurate ordering"""
        reference_embedding = [1.0, 0.0, 0.0, 0.0, 0.0]

        test_embeddings = {
            "identical": [1.0, 0.0, 0.0, 0.0, 0.0],  # Should rank 1st
            "very_similar": [0.9, 0.1, 0.0, 0.0, 0.0],  # Should rank 2nd
            "somewhat_similar": [0.7, 0.3, 0.0, 0.0, 0.0],  # Should rank 3rd
            "different": [0.0, 1.0, 0.0, 0.0, 0.0],  # Should rank 4th
            "opposite": [-1.0, 0.0, 0.0, 0.0, 0.0],  # Should rank 5th
        }

        similarities = {}
        for name, embedding in test_embeddings.items():
            sim = similarity_service.calculate_similarity(
                reference_embedding, embedding
            )
            similarities[name] = sim

        # Sort by similarity score
        ranked = sorted(similarities.items(), key=lambda x: x[1], reverse=True)

        # Verify correct ranking
        assert ranked[0][0] == "identical"
        assert ranked[1][0] == "very_similar"
        assert ranked[2][0] == "somewhat_similar"
        assert ranked[3][0] == "different"
        assert ranked[4][0] == "opposite"

    @pytest.mark.asyncio
    async def test_empty_database_handling(self, similarity_service, mock_vector_db):
        """Test handling of empty vector database"""
        query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        with patch.object(similarity_service, "vector_db", mock_vector_db):
            mock_vector_db.search_similar = AsyncMock(return_value=[])

            results = await similarity_service.find_similar_images(
                query_embedding=query_embedding
            )

            assert results == []
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_performance_with_large_dataset(
        self, similarity_service, mock_vector_db
    ):
        """Test performance with large number of vectors"""
        query_embedding = [0.5] * 512  # High-dimensional embedding

        # Mock large dataset results
        large_results = [
            {
                "image_id": f"image_{i}",
                "similarity": 0.9 - (i * 0.001),
                "file_path": f"/test/image_{i}.jpg",
            }
            for i in range(1000)
        ]

        with patch.object(similarity_service, "vector_db", mock_vector_db):
            mock_vector_db.search_similar = AsyncMock(
                return_value=large_results[:10]
            )  # Top 10

            import time

            start_time = time.time()

            results = await similarity_service.find_similar_images(
                query_embedding=query_embedding, limit=10
            )

            end_time = time.time()
            search_time = end_time - start_time

            # Should complete within reasonable time (under 1 second for mocked data)
            assert search_time < 1.0
            assert len(results) == 10
            # Results should be in descending order of similarity
            for i in range(1, len(results)):
                assert results[i - 1]["similarity"] >= results[i]["similarity"]
