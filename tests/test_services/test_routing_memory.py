"""Tests for routing memory service"""

import tempfile
from pathlib import Path

import pytest

from src.services.routing_memory import RoutingMemory


class TestRoutingMemory:
    """Test routing memory operations"""

    @pytest.fixture
    def temp_vault(self):
        """Create a temporary vault directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def routing_memory(self, temp_vault):
        """Create a RoutingMemory instance with temp vault"""
        return RoutingMemory(vault_path=temp_vault)

    def test_memory_file_created(self, routing_memory, temp_vault):
        """Test that memory file is created on initialization"""
        memory_file = Path(temp_vault) / "meta" / "telegram-routing.md"
        assert memory_file.exists()

    def test_get_domain_simple(self, routing_memory):
        """Test domain extraction from simple URL"""
        assert routing_memory.get_domain("https://example.com/page") == "example.com"

    def test_get_domain_with_www(self, routing_memory):
        """Test domain extraction strips www prefix"""
        assert routing_memory.get_domain("https://www.example.com/page") == "example.com"

    def test_get_domain_with_subdomain(self, routing_memory):
        """Test domain extraction preserves subdomains"""
        assert routing_memory.get_domain("https://blog.example.com/post") == "blog.example.com"

    def test_default_destination_links(self, routing_memory):
        """Test default destination for links is inbox"""
        dest = routing_memory.get_suggested_destination(content_type="links")
        assert dest == "inbox"

    def test_default_destination_voice(self, routing_memory):
        """Test default destination for voice is daily"""
        dest = routing_memory.get_suggested_destination(content_type="voice")
        assert dest == "daily"

    def test_default_destination_images(self, routing_memory):
        """Test default destination for images is inbox"""
        dest = routing_memory.get_suggested_destination(content_type="images")
        assert dest == "inbox"

    def test_record_and_suggest_domain(self, routing_memory):
        """Test that recording a route updates domain preference"""
        url = "https://github.com/user/repo"

        # Record route to research
        routing_memory.record_route(
            destination="research",
            content_type="links",
            url=url,
            title="Test Repo"
        )

        # Should suggest research for same domain
        dest = routing_memory.get_suggested_destination(url="https://github.com/other/project")
        assert dest == "research"

    def test_record_updates_count(self, routing_memory):
        """Test that multiple records increase count"""
        url = "https://news.ycombinator.com/item?id=123"

        routing_memory.record_route(destination="inbox", url=url, title="HN Post 1")
        routing_memory.record_route(destination="inbox", url="https://news.ycombinator.com/item?id=456", title="HN Post 2")

        memory = routing_memory._parse_memory()
        assert memory["domains"]["news.ycombinator.com"]["count"] == 2

    def test_recent_routes_stored(self, routing_memory):
        """Test that recent routes are tracked"""
        routing_memory.record_route(
            destination="daily",
            content_type="links",
            url="https://test.com/page",
            title="Test Page"
        )

        memory = routing_memory._parse_memory()
        assert len(memory["recent"]) > 0
        assert "test.com" in memory["recent"][-1]
        assert "daily" in memory["recent"][-1]

    def test_recent_routes_limit(self, routing_memory):
        """Test that only last 20 routes are kept"""
        for i in range(25):
            routing_memory.record_route(
                destination="inbox",
                url=f"https://test{i}.com/page",
                title=f"Page {i}"
            )

        memory = routing_memory._parse_memory()
        assert len(memory["recent"]) <= 20

    def test_destination_override_updates_domain(self, routing_memory):
        """Test that changing destination updates the domain preference"""
        url = "https://arxiv.org/paper/123"

        # First save to inbox
        routing_memory.record_route(destination="inbox", url=url, title="Paper 1")

        # Then change to research
        routing_memory.record_route(
            destination="research",
            url="https://arxiv.org/paper/456",
            title="Paper 2"
        )

        # Should now suggest research
        dest = routing_memory.get_suggested_destination(url="https://arxiv.org/paper/789")
        assert dest == "research"

    def test_unknown_domain_falls_back_to_content_type(self, routing_memory):
        """Test fallback to content type when domain unknown"""
        # No history for this domain
        dest = routing_memory.get_suggested_destination(
            url="https://new-site.com/page",
            content_type="links"
        )
        assert dest == "inbox"
