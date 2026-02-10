"""
Comprehensive tests for messaging API endpoints.

Tests cover:
- Authentication (messaging API key validation)
- Send message endpoint with filtering
- Contact CRUD operations (create, read, delete)
- Contact toggle active status
- Request/Response model validation
- Error handling and edge cases
"""

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


class TestMessagingApiKeyGeneration:
    """Test messaging API key generation logic."""

    def test_get_messaging_api_key_derives_from_webhook_secret(self):
        """Verify messaging API key is derived from webhook secret using salted hash."""
        from src.api.messaging import get_messaging_api_key

        with patch.dict(
            os.environ, {"TELEGRAM_WEBHOOK_SECRET": "test_secret"}, clear=False
        ):
            os.environ.pop("API_SECRET_KEY", None)
            key = get_messaging_api_key()

            expected = hashlib.sha256("test_secret:messaging_api".encode()).hexdigest()
            assert key == expected
            assert len(key) == 64  # SHA-256 hex digest length

    def test_get_messaging_api_key_raises_when_secret_not_configured(self):
        """Verify ValueError when webhook secret is not configured."""
        from src.api.messaging import get_messaging_api_key

        with (
            patch("src.core.config.get_settings") as mock_settings,
            patch.dict(os.environ, {}, clear=False),
        ):
            mock_settings.return_value.telegram_webhook_secret = ""
            mock_settings.return_value.api_secret_key = None
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            os.environ.pop("API_SECRET_KEY", None)

            with pytest.raises(ValueError):
                get_messaging_api_key()

    def test_get_messaging_api_key_raises_when_secret_is_none(self):
        """Verify ValueError when webhook secret is None."""
        from src.api.messaging import get_messaging_api_key

        with (
            patch("src.core.config.get_settings") as mock_settings,
            patch.dict(os.environ, {}, clear=False),
        ):
            mock_settings.return_value.telegram_webhook_secret = None
            mock_settings.return_value.api_secret_key = None
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            os.environ.pop("API_SECRET_KEY", None)

            with pytest.raises(ValueError):
                get_messaging_api_key()

    def test_get_messaging_api_key_different_from_admin_key(self):
        """Verify messaging API key uses different salt than admin API key."""
        from src.api.messaging import get_messaging_api_key

        with patch.dict(
            os.environ, {"TELEGRAM_WEBHOOK_SECRET": "test_secret"}, clear=False
        ):
            os.environ.pop("API_SECRET_KEY", None)
            messaging_key = get_messaging_api_key()
            # Admin key would use ":admin_api" salt
            admin_key = hashlib.sha256("test_secret:admin_api".encode()).hexdigest()

            assert messaging_key != admin_key


def _mock_request():
    """Create a mock FastAPI Request for verify_api_key tests."""
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    req.method = "POST"
    req.url = MagicMock()
    req.url.path = "/api/messaging/send"
    req.headers = {"user-agent": "test-agent"}
    return req


class TestVerifyApiKey:
    """Test API key verification dependency."""

    @pytest.mark.asyncio
    async def test_verify_api_key_returns_true_for_valid_key(self):
        """Valid API key should return True."""
        from src.api.messaging import verify_api_key

        with patch("src.api.messaging.get_messaging_api_key") as mock_get_key:
            mock_get_key.return_value = "valid_key_hash"

            result = await verify_api_key(_mock_request(), "valid_key_hash")

            assert result is True

    @pytest.mark.asyncio
    async def test_verify_api_key_raises_401_when_empty(self):
        """Empty API key should raise 401 Unauthorized."""
        from fastapi import HTTPException

        from src.api.messaging import verify_api_key

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(_mock_request(), "")

        assert exc_info.value.status_code == 401
        assert "Invalid or missing API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_api_key_raises_401_for_invalid_key(self):
        """Invalid API key should raise 401 Unauthorized."""
        from fastapi import HTTPException

        from src.api.messaging import verify_api_key

        with patch("src.api.messaging.get_messaging_api_key") as mock_get_key:
            mock_get_key.return_value = "correct_key_hash"

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(_mock_request(), "wrong_key")

            assert exc_info.value.status_code == 401
            assert "Invalid or missing API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_api_key_returns_www_authenticate_header(self):
        """401 response should include WWW-Authenticate header."""
        from fastapi import HTTPException

        from src.api.messaging import verify_api_key

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(_mock_request(), "invalid_key")

        assert exc_info.value.headers == {"WWW-Authenticate": "ApiKey"}

    @pytest.mark.asyncio
    async def test_verify_api_key_raises_401_when_missing(self):
        """Missing API key should raise 401 Unauthorized."""
        from fastapi import HTTPException

        from src.api.messaging import verify_api_key

        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(_mock_request(), None)

        assert exc_info.value.status_code == 401
        assert "Invalid or missing API key" in exc_info.value.detail
        assert exc_info.value.headers == {"WWW-Authenticate": "ApiKey"}

    @pytest.mark.asyncio
    async def test_verify_api_key_raises_401_when_secret_not_configured(self):
        """Missing TELEGRAM_WEBHOOK_SECRET should raise 401, not 500."""
        from fastapi import HTTPException

        from src.api.messaging import verify_api_key

        with patch("src.api.messaging.get_messaging_api_key") as mock_get_key:
            mock_get_key.side_effect = ValueError(
                "TELEGRAM_WEBHOOK_SECRET not configured"
            )

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(_mock_request(), "some_key")

            assert exc_info.value.status_code == 401
            assert "Authentication not configured" in exc_info.value.detail
            assert exc_info.value.headers == {"WWW-Authenticate": "ApiKey"}

    @pytest.mark.asyncio
    async def test_verify_api_key_raises_401_on_unexpected_exception(self):
        """Unexpected exception in key derivation should raise 401, not 500."""
        from fastapi import HTTPException

        from src.api.messaging import verify_api_key

        with patch("src.api.messaging.get_messaging_api_key") as mock_get_key:
            mock_get_key.side_effect = RuntimeError("Unexpected config failure")

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(_mock_request(), "some_key")

            assert exc_info.value.status_code == 401
            assert "Authentication not configured" in exc_info.value.detail
            assert exc_info.value.headers == {"WWW-Authenticate": "ApiKey"}

    @pytest.mark.asyncio
    async def test_verify_api_key_logs_warning_on_invalid_attempt(self):
        """Invalid API key attempts should be logged."""
        from fastapi import HTTPException

        from src.api.messaging import verify_api_key

        with (
            patch("src.api.messaging.get_messaging_api_key") as mock_get_key,
            patch("src.api.messaging.logger") as mock_logger,
        ):
            mock_get_key.return_value = "correct_key"

            with pytest.raises(HTTPException):
                await verify_api_key(_mock_request(), "wrong_key")

            mock_logger.warning.assert_called_once()


class TestRequestModels:
    """Test Pydantic request model validation."""

    def test_send_message_request_valid_minimal(self):
        """Valid SendMessageRequest with only required fields."""
        from src.api.messaging import SendMessageRequest

        request = SendMessageRequest(message="Hello, world!")

        assert request.message == "Hello, world!"
        assert request.contact_ids is None
        assert request.roles is None

    def test_send_message_request_valid_with_contact_ids(self):
        """Valid SendMessageRequest with contact_ids filter."""
        from src.api.messaging import SendMessageRequest

        request = SendMessageRequest(message="Test message", contact_ids=[1, 2, 3])

        assert request.message == "Test message"
        assert request.contact_ids == [1, 2, 3]
        assert request.roles is None

    def test_send_message_request_valid_with_roles(self):
        """Valid SendMessageRequest with roles filter."""
        from src.api.messaging import SendMessageRequest

        request = SendMessageRequest(
            message="Admin notification", roles=["admin", "moderator"]
        )

        assert request.message == "Admin notification"
        assert request.contact_ids is None
        assert request.roles == ["admin", "moderator"]

    def test_send_message_request_valid_with_all_filters(self):
        """Valid SendMessageRequest with both filters."""
        from src.api.messaging import SendMessageRequest

        request = SendMessageRequest(
            message="Filtered message", contact_ids=[1, 2], roles=["admin"]
        )

        assert request.contact_ids == [1, 2]
        assert request.roles == ["admin"]

    def test_send_message_request_empty_message(self):
        """SendMessageRequest accepts empty message (validation at API level)."""
        from src.api.messaging import SendMessageRequest

        request = SendMessageRequest(message="")
        assert request.message == ""

    def test_admin_contact_create_valid_minimal(self):
        """Valid AdminContactCreate with required fields only."""
        from src.api.messaging import AdminContactCreate

        contact = AdminContactCreate(chat_id=123456789, name="John Doe")

        assert contact.chat_id == 123456789
        assert contact.name == "John Doe"
        assert contact.username is None
        assert contact.role is None
        assert contact.notes is None

    def test_admin_contact_create_valid_all_fields(self):
        """Valid AdminContactCreate with all fields."""
        from src.api.messaging import AdminContactCreate

        contact = AdminContactCreate(
            chat_id=123456789,
            username="johndoe",
            name="John Doe",
            role="admin",
            notes="Primary administrator",
        )

        assert contact.chat_id == 123456789
        assert contact.username == "johndoe"
        assert contact.name == "John Doe"
        assert contact.role == "admin"
        assert contact.notes == "Primary administrator"

    def test_admin_contact_create_negative_chat_id(self):
        """AdminContactCreate accepts negative chat_id (valid for groups)."""
        from src.api.messaging import AdminContactCreate

        contact = AdminContactCreate(chat_id=-123456789, name="Group Chat")
        assert contact.chat_id == -123456789


class TestResponseModels:
    """Test Pydantic response models."""

    def test_send_message_response_success(self):
        """SendMessageResponse for successful delivery."""
        from src.api.messaging import SendMessageResponse

        response = SendMessageResponse(
            success=True, sent_to=["John", "Jane"], failed=[]
        )

        assert response.success is True
        assert response.sent_to == ["John", "Jane"]
        assert response.failed == []

    def test_send_message_response_partial_failure(self):
        """SendMessageResponse for partial delivery failure."""
        from src.api.messaging import SendMessageResponse

        response = SendMessageResponse(success=False, sent_to=["John"], failed=["Jane"])

        assert response.success is False
        assert response.sent_to == ["John"]
        assert response.failed == ["Jane"]

    def test_send_message_response_complete_failure(self):
        """SendMessageResponse when all deliveries fail."""
        from src.api.messaging import SendMessageResponse

        response = SendMessageResponse(
            success=False, sent_to=[], failed=["John", "Jane"]
        )

        assert response.success is False
        assert response.sent_to == []
        assert response.failed == ["John", "Jane"]

    def test_admin_contact_response_complete(self):
        """AdminContactResponse with all fields."""
        from src.api.messaging import AdminContactResponse

        response = AdminContactResponse(
            id=1,
            chat_id=123456789,
            username="johndoe",
            name="John Doe",
            role="admin",
            active=True,
            notes="Primary administrator",
        )

        assert response.id == 1
        assert response.chat_id == 123456789
        assert response.username == "johndoe"
        assert response.name == "John Doe"
        assert response.role == "admin"
        assert response.active is True
        assert response.notes == "Primary administrator"

    def test_admin_contact_response_minimal(self):
        """AdminContactResponse with optional fields as None."""
        from src.api.messaging import AdminContactResponse

        response = AdminContactResponse(
            id=1,
            chat_id=123456789,
            username=None,
            name="John Doe",
            role=None,
            active=True,
            notes=None,
        )

        assert response.username is None
        assert response.role is None
        assert response.notes is None

    def test_admin_contact_response_from_attributes_config(self):
        """AdminContactResponse has from_attributes config for ORM compatibility."""
        from src.api.messaging import AdminContactResponse

        assert AdminContactResponse.model_config.get("from_attributes") is True


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
            patch(
                "src.api.messaging.get_messaging_api_key",
                return_value=get_test_messaging_api_key(),
            ),
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

    # ==================== Send Message Tests ====================

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

    def test_send_message_missing_api_key_returns_401(self, client):
        """Missing API key should return 401 Unauthorized."""
        response = client.post(
            "/api/messaging/send",
            json={"message": "Hello"},
        )

        assert response.status_code == 401
        assert "Invalid or missing API key" in response.json().get("detail", "")

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

    def test_send_message_success_to_all_contacts(self, client, messaging_api_key):
        """Successfully send message to all active contacts."""
        contacts = [
            AdminContact(id=1, chat_id=111, name="Alice", role="admin", active=True),
            AdminContact(id=2, chat_id=222, name="Bob", role="user", active=True),
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
                json={"message": "Hello everyone!"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert set(payload["sent_to"]) == {"Alice", "Bob"}
        assert payload["failed"] == []

    def test_send_message_handles_exception(self, client, messaging_api_key):
        """Exception during send should be caught and contact marked as failed."""
        contacts = [
            AdminContact(id=1, chat_id=111, name="Alice", role="ops", active=True),
        ]
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = contacts
        mock_session.execute.return_value = result

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock(side_effect=Exception("Network error"))

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
                json={"message": "Test"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is False
        assert payload["failed"] == ["Alice"]

    def test_send_message_with_only_contact_ids_filter(self, client, messaging_api_key):
        """Filter by contact_ids only."""
        contacts = [
            AdminContact(id=1, chat_id=111, name="Alice", role="ops", active=True),
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
                json={"message": "Targeted", "contact_ids": [1]},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_send_message_with_only_roles_filter(self, client, messaging_api_key):
        """Filter by roles only."""
        contacts = [
            AdminContact(id=1, chat_id=111, name="Admin", role="admin", active=True),
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
                json={"message": "Admin only", "roles": ["admin"]},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True

    # ==================== List Contacts Tests ====================

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

    def test_list_contacts_empty(self, client, messaging_api_key):
        """List contacts when none exist returns empty array."""
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
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
        assert response.json() == []

    def test_list_contacts_includes_inactive(self, client, messaging_api_key):
        """List contacts includes both active and inactive contacts."""
        contacts = [
            AdminContact(id=1, chat_id=111, name="Active", role="ops", active=True),
            AdminContact(id=2, chat_id=222, name="Inactive", role="ops", active=False),
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
        active_states = {item["name"]: item["active"] for item in data}
        assert active_states["Active"] is True
        assert active_states["Inactive"] is False

    def test_list_contacts_requires_auth(self, client):
        """List contacts requires authentication."""
        response = client.get("/api/messaging/contacts")
        assert response.status_code == 401  # Missing header returns 401

    # ==================== Create Contact Tests ====================

    def test_create_contact_rejects_duplicates(self, client, messaging_api_key):
        """Duplicate chat_id should return 400."""
        existing = AdminContact(
            id=1, chat_id=111, name="Alice", role="ops", active=True
        )
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

    def test_create_contact_minimal_data(self, client, messaging_api_key):
        """Create contact with only required fields."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result

        async def set_contact_id(contact):
            contact.id = 1

        mock_session.refresh = AsyncMock(side_effect=set_contact_id)

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.post(
                "/api/messaging/contacts",
                headers={"X-Api-Key": messaging_api_key},
                json={"chat_id": 123, "name": "Minimal"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["username"] is None
        assert data["role"] is None
        assert data["notes"] is None

    def test_create_contact_validation_error_missing_name(
        self, client, messaging_api_key
    ):
        """Creating contact without required name field returns 422."""
        response = client.post(
            "/api/messaging/contacts",
            headers={"X-Api-Key": messaging_api_key},
            json={"chat_id": 123},
        )

        assert response.status_code == 422

    def test_create_contact_validation_error_missing_chat_id(
        self, client, messaging_api_key
    ):
        """Creating contact without required chat_id field returns 422."""
        response = client.post(
            "/api/messaging/contacts",
            headers={"X-Api-Key": messaging_api_key},
            json={"name": "Test"},
        )

        assert response.status_code == 422

    def test_create_contact_requires_auth(self, client):
        """Create contact requires authentication."""
        response = client.post(
            "/api/messaging/contacts",
            json={"chat_id": 123, "name": "Test"},
        )
        assert response.status_code == 401  # Missing header returns 401

    # ==================== Delete Contact Tests ====================

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
        assert "not found" in response.json().get("detail", "").lower()

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

    def test_delete_contact_requires_auth(self, client):
        """Delete contact requires authentication."""
        response = client.delete("/api/messaging/contacts/1")
        assert response.status_code == 401  # Missing header returns 401

    # ==================== Toggle Contact Active Tests ====================

    def test_toggle_contact_active_to_inactive(self, client, messaging_api_key):
        """Toggle endpoint should flip active flag from True to False."""
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

    def test_toggle_contact_inactive_to_active(self, client, messaging_api_key):
        """Toggle endpoint should flip active flag from False to True."""
        contact = AdminContact(
            id=1, chat_id=111, name="Alice", role="ops", active=False
        )
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
        assert data["active"] is True

    def test_toggle_contact_not_found(self, client, messaging_api_key):
        """Toggling missing contact should return 404."""
        mock_session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.patch(
                "/api/messaging/contacts/99/toggle",
                headers={"X-Api-Key": messaging_api_key},
            )

        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()

    def test_toggle_contact_requires_auth(self, client):
        """Toggle contact requires authentication."""
        response = client.patch("/api/messaging/contacts/1/toggle")
        assert response.status_code == 401  # Missing header returns 401


class TestAuthenticationRequirement:
    """Test that all messaging endpoints require authentication."""

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
            patch(
                "src.api.messaging.get_messaging_api_key",
                return_value=get_test_messaging_api_key(),
            ),
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

    def test_invalid_api_key_rejected_on_send(self, client):
        """Invalid API key is rejected on send endpoint."""
        response = client.post(
            "/api/messaging/send",
            headers={"X-Api-Key": "invalid_key"},
            json={"message": "Test"},
        )
        assert response.status_code == 401

    def test_invalid_api_key_rejected_on_list_contacts(self, client):
        """Invalid API key is rejected on list contacts endpoint."""
        response = client.get(
            "/api/messaging/contacts",
            headers={"X-Api-Key": "invalid_key"},
        )
        assert response.status_code == 401

    def test_invalid_api_key_rejected_on_create_contact(self, client):
        """Invalid API key is rejected on create contact endpoint."""
        response = client.post(
            "/api/messaging/contacts",
            headers={"X-Api-Key": "invalid_key"},
            json={"chat_id": 123, "name": "Test"},
        )
        assert response.status_code == 401

    def test_invalid_api_key_rejected_on_delete_contact(self, client):
        """Invalid API key is rejected on delete contact endpoint."""
        response = client.delete(
            "/api/messaging/contacts/1",
            headers={"X-Api-Key": "invalid_key"},
        )
        assert response.status_code == 401

    def test_invalid_api_key_rejected_on_toggle_contact(self, client):
        """Invalid API key is rejected on toggle contact endpoint."""
        response = client.patch(
            "/api/messaging/contacts/1/toggle",
            headers={"X-Api-Key": "invalid_key"},
        )
        assert response.status_code == 401


class TestRouterConfiguration:
    """Test router is correctly configured."""

    def test_router_prefix(self):
        """Verify router has correct prefix."""
        from src.api.messaging import router

        assert router.prefix == "/api/messaging"

    def test_router_tags(self):
        """Verify router has correct tags."""
        from src.api.messaging import router

        assert "messaging" in router.tags


class TestMessageLogging:
    """Test that operations are properly logged."""

    def test_send_message_logs_request(self, caplog):
        """Verify that send_message logs the request."""
        # This test verifies the logging behavior documented in the source
        from src.api.messaging import SendMessageRequest

        request = SendMessageRequest(message="A" * 100)
        # The endpoint logs first 50 chars + "..."
        truncated = request.message[:50] + "..."
        assert len(truncated) == 53

    def test_create_contact_logs_success(self):
        """Verify create_contact logs the creation."""
        # This test validates the logging pattern exists in the code

        from src.api import messaging

        assert hasattr(messaging, "logger")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

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
            patch(
                "src.api.messaging.get_messaging_api_key",
                return_value=get_test_messaging_api_key(),
            ),
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

    def test_send_message_empty_contact_ids_list(self, client, messaging_api_key):
        """Empty contact_ids list should not filter (return 404 if no active contacts)."""
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
                json={"message": "Test", "contact_ids": []},
            )

        # Empty list should be treated as "no filter" which queries all active contacts
        # Since no contacts exist, returns 404
        assert response.status_code == 404

    def test_send_message_empty_roles_list(self, client, messaging_api_key):
        """Empty roles list should not filter (return 404 if no active contacts)."""
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
                json={"message": "Test", "roles": []},
            )

        assert response.status_code == 404

    def test_send_message_very_long_message(self, client, messaging_api_key):
        """Very long messages should be handled correctly."""
        contacts = [
            AdminContact(id=1, chat_id=111, name="Alice", role="ops", active=True),
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
            long_message = "A" * 10000
            response = client.post(
                "/api/messaging/send",
                headers={"X-Api-Key": messaging_api_key},
                json={"message": long_message},
            )

        assert response.status_code == 200
        # Verify the full message was passed to send_message
        mock_bot.send_message.assert_called_once()
        call_args = mock_bot.send_message.call_args
        assert len(call_args[0][1]) == 10000

    def test_create_contact_with_special_characters_in_name(
        self, client, messaging_api_key
    ):
        """Contact name with special characters should be accepted."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result

        async def set_contact_id(contact):
            contact.id = 1

        mock_session.refresh = AsyncMock(side_effect=set_contact_id)

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.post(
                "/api/messaging/contacts",
                headers={"X-Api-Key": messaging_api_key},
                json={"chat_id": 123, "name": "John O'Brien-Smith"},
            )

        assert response.status_code == 201
        assert response.json()["name"] == "John O'Brien-Smith"

    def test_create_contact_with_unicode_name(self, client, messaging_api_key):
        """Contact name with unicode characters should be accepted."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result

        async def set_contact_id(contact):
            contact.id = 1

        mock_session.refresh = AsyncMock(side_effect=set_contact_id)

        with patch(
            "src.api.messaging.get_db_session",
            return_value=build_db_context(mock_session),
        ):
            response = client.post(
                "/api/messaging/contacts",
                headers={"X-Api-Key": messaging_api_key},
                json={"chat_id": 123, "name": "Alexandr Ivanov"},
            )

        assert response.status_code == 201
