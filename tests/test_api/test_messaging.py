"""Tests for messaging API endpoints and auth behavior."""

import hashlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.admin_contact import AdminContact


os.environ["TELEGRAM_WEBHOOK_SECRET"] = "test_webhook_secret_12345"
os.environ["TELEGRAM_BOT_TOKEN"] = "test:bot_token"
os.environ["ENVIRONMENT"] = "test"


def get_test_messaging_api_key() -> str:
    """Generate the expected messaging API key for tests."""
    secret = os.environ["TELEGRAM_WEBHOOK_SECRET"]
    return hashlib.sha256(f"{secret}:messaging_api".encode()).hexdigest()


def build_db_context(session: AsyncMock) -> AsyncMock:
    """Build an async context manager for mocked DB sessions."""
    context_manager = AsyncMock()
    context_manager.__aenter__.return_value = session
    context_manager.__aexit__.return_value = None
    return context_manager


class TestMessagingApiKey:
    """Tests for messaging API key derivation."""

    def test_get_messaging_api_key_derives_from_secret(self):
        """Verify messaging API key is derived from webhook secret using salted hash."""
        from src.api.messaging import get_messaging_api_key

        with patch("src.api.messaging.get_settings") as mock_settings:
            mock_settings.return_value.telegram_webhook_secret = "test_secret"

            key = get_messaging_api_key()

            expected = hashlib.sha256("test_secret:messaging_api".encode()).hexdigest()
            assert key == expected
            assert len(key) == 64


class TestMessagingEndpoints:
    """Integration-style tests for messaging endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        with (
            patch("src.main.initialize_bot", new_callable=AsyncMock),
            patch("src.main.shutdown_bot", new_callable=AsyncMock),
            patch("src.main.init_database", new_callable=AsyncMock),
            patch("src.main.close_database", new_callable=AsyncMock),
            patch("src.main.setup_services"),
            patch("src.main.get_plugin_manager") as mock_pm,
            patch("src.main.get_bot") as mock_get_bot,
        ):
            mock_pm_instance = MagicMock()
            mock_pm_instance.load_plugins = AsyncMock(return_value={})
            mock_pm_instance.activate_plugins = AsyncMock()
            mock_pm_instance.shutdown = AsyncMock()
            mock_pm.return_value = mock_pm_instance

            mock_bot = MagicMock()
            mock_bot.application = MagicMock()
            mock_get_bot.return_value = mock_bot

            from fastapi.testclient import TestClient
            from src.main import app

            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    @pytest.fixture
    def messaging_api_key(self):
        """Get valid messaging API key for tests."""
        return get_test_messaging_api_key()

    def test_send_message_returns_404_when_no_contacts(self, client, messaging_api_key):
        """No contacts should return 404 to avoid silent success."""
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.post(
                "/api/messaging/send",
                headers={"X-Api-Key": messaging_api_key},
                json={"message": "Hello"},
            )

        assert response.status_code == 404
        assert "No matching admin contacts found" in response.json().get("detail", "")

    def test_send_message_missing_api_key_returns_422(self, client):
        """Missing API key should fail request validation."""
        response = client.post(
            "/api/messaging/send",
            json={"message": "Hello"},
        )

        assert response.status_code == 422

    def test_send_message_invalid_api_key_returns_401(self, client):
        """Invalid API key should be rejected."""
        response = client.post(
            "/api/messaging/send",
            headers={"X-Api-Key": "invalid"},
            json={"message": "Hello"},
        )

        assert response.status_code == 401

    def test_send_message_tracks_failures(self, client, messaging_api_key):
        """Failed sends should be reported and set success=false."""
        contacts = [
            AdminContact(id=1, chat_id=111, name="Alice", role="ops", active=True),
            AdminContact(id=2, chat_id=222, name="Bob", role="ops", active=True),
        ]
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = contacts
        mock_session.execute.return_value = result

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(side_effect=[True, False])

        with (
            patch(
                "src.api.messaging.get_db_session",
                return_value=build_db_context(mock_session),
            ),
            patch("src.api.messaging.get_bot", return_value=mock_bot),
        ):
            response = client.post(
                "/api/messaging/send",
                headers={"X-Api-Key": messaging_api_key},
                json={"message": "Status check"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is False
        assert payload["sent_to"] == ["Alice"]
        assert payload["failed"] == ["Bob"]
        assert mock_bot.send_message.call_count == 2

    def test_send_message_filters_contacts(self, client, messaging_api_key):
        """Filters should only target matching contacts."""
        contacts = [
            AdminContact(id=2, chat_id=222, name="Bob", role="ops", active=True),
        ]
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = contacts
        mock_session.execute.return_value = result

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(return_value=True)

        with (
            patch(
                "src.api.messaging.get_db_session",
                return_value=build_db_context(mock_session),
            ),
            patch("src.api.messaging.get_bot", return_value=mock_bot),
        ):
            response = client.post(
                "/api/messaging/send",
                headers={"X-Api-Key": messaging_api_key},
                json={"message": "Status", "contact_ids": [2], "roles": ["ops"]},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["sent_to"] == ["Bob"]
        assert mock_bot.send_message.call_count == 1

    def test_list_contacts_returns_all(self, client, messaging_api_key):
        """List endpoint should return all contacts."""
        contacts = [
            AdminContact(id=1, chat_id=111, name="Alice", role="ops", active=True),
            AdminContact(id=2, chat_id=222, name="Bob", role="ops", active=False),
        ]
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = contacts
        mock_session.execute.return_value = result

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.get(
                "/api/messaging/contacts",
                headers={"X-Api-Key": messaging_api_key},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert {item["name"] for item in data} == {"Alice", "Bob"}

    def test_create_contact_rejects_duplicates(self, client, messaging_api_key):
        """Duplicate chat_id should return 400."""
        existing = AdminContact(id=1, chat_id=111, name="Alice", role="ops", active=True)
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = result

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.post(
                "/api/messaging/contacts",
                headers={"X-Api-Key": messaging_api_key},
                json={"chat_id": 111, "name": "Alice"},
            )

        assert response.status_code == 400
        assert "already exists" in response.json().get("detail", "")

    def test_create_contact_success(self, client, messaging_api_key):
        """New contact should be created and returned."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result

        async def set_contact_id(contact):
            contact.id = 7

        mock_session.refresh = AsyncMock(side_effect=set_contact_id)

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.post(
                "/api/messaging/contacts",
                headers={"X-Api-Key": messaging_api_key},
                json={
                    "chat_id": 777,
                    "name": "New Admin",
                    "username": "new_admin",
                    "role": "ops",
                    "notes": "Primary contact",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 7
        assert data["chat_id"] == 777
        assert data["name"] == "New Admin"
        assert data["active"] is True

    def test_delete_contact_not_found(self, client, messaging_api_key):
        """Deleting missing contact should return 404."""
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.delete(
                "/api/messaging/contacts/99",
                headers={"X-Api-Key": messaging_api_key},
            )

        assert response.status_code == 404

    def test_delete_contact_success(self, client, messaging_api_key):
        """Deleting an existing contact should return 204."""
        contact = AdminContact(id=1, chat_id=111, name="Alice", role="ops", active=True)
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = contact
        mock_session.execute.return_value = result

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.delete(
                "/api/messaging/contacts/1",
                headers={"X-Api-Key": messaging_api_key},
            )

        assert response.status_code == 204
        mock_session.delete.assert_awaited_once_with(contact)

    def test_toggle_contact_active(self, client, messaging_api_key):
        """Toggle endpoint should flip active flag."""
        contact = AdminContact(id=1, chat_id=111, name="Alice", role="ops", active=True)
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = contact
        mock_session.execute.return_value = result

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.patch(
                "/api/messaging/contacts/1/toggle",
                headers={"X-Api-Key": messaging_api_key},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["active"] is False
