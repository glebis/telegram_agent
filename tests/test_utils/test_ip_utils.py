"""
Tests for IP address detection and management utilities.

Tests cover:
- External IP address retrieval
- Railway environment variable detection
- Webhook base URL construction
- Fallback behavior when services fail
- Error handling and edge cases
"""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.utils.ip_utils import (
    IP_SERVICES,
    get_external_ip,
    get_webhook_base_url,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def clean_environment():
    """Clean up environment variables before and after each test."""
    # Store original values
    env_vars_to_clean = [
        "WEBHOOK_BASE_URL",
        "RAILWAY_PUBLIC_DOMAIN",
        "RAILWAY_SERVICE_URL",
        "RAILWAY_STATIC_URL",
        "RAILWAY_APP_URL",
        "HOSTNAME",
        "WEBHOOK_USE_HTTPS",
    ]
    original_values = {key: os.environ.get(key) for key in env_vars_to_clean}

    # Clear for test
    for key in env_vars_to_clean:
        if key in os.environ:
            del os.environ[key]

    yield

    # Restore original values
    for key, value in original_values.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]


@pytest.fixture
def mock_requests_success():
    """Mock requests.get to return a successful IP response."""
    with patch("src.utils.ip_utils.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "  203.0.113.42  \n"  # With whitespace to test strip()
        mock_get.return_value = mock_response
        yield mock_get


@pytest.fixture
def mock_requests_failure():
    """Mock requests.get to always fail."""
    with patch("src.utils.ip_utils.requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("Connection failed")
        yield mock_get


# =============================================================================
# IP_SERVICES Tests
# =============================================================================


class TestIPServices:
    """Tests for IP_SERVICES constant."""

    def test_ip_services_is_list(self):
        """Test that IP_SERVICES is a list."""
        assert isinstance(IP_SERVICES, list)

    def test_ip_services_not_empty(self):
        """Test that IP_SERVICES contains at least one service."""
        assert len(IP_SERVICES) > 0

    def test_ip_services_contains_valid_urls(self):
        """Test that all IP services are valid HTTPS URLs."""
        for service in IP_SERVICES:
            assert service.startswith("https://"), f"Service {service} should use HTTPS"

    def test_ip_services_contains_expected_services(self):
        """Test that known IP services are included."""
        expected_services = [
            "https://api.ipify.org",
            "https://ipinfo.io/ip",
            "https://ifconfig.me/ip",
        ]
        for expected in expected_services:
            assert expected in IP_SERVICES, f"Expected {expected} in IP_SERVICES"


# =============================================================================
# get_external_ip Tests
# =============================================================================


class TestGetExternalIP:
    """Tests for get_external_ip function."""

    def test_returns_ip_on_success(self, mock_requests_success):
        """Test successful IP retrieval."""
        ip = get_external_ip()

        assert ip == "203.0.113.42"  # Whitespace should be stripped
        mock_requests_success.assert_called()

    def test_strips_whitespace_from_response(self, mock_requests_success):
        """Test that whitespace is properly stripped from response."""
        mock_requests_success.return_value.text = "\n  192.168.1.1  \n"

        ip = get_external_ip()

        assert ip == "192.168.1.1"
        assert not ip.startswith(" ")
        assert not ip.endswith(" ")

    def test_returns_none_when_all_services_fail(self, mock_requests_failure):
        """Test that None is returned when all services fail."""
        ip = get_external_ip()

        assert ip is None
        # Should have tried all services
        assert mock_requests_failure.call_count == len(IP_SERVICES)

    def test_tries_next_service_on_failure(self):
        """Test that next service is tried when one fails."""
        with patch("src.utils.ip_utils.requests.get") as mock_get:
            # First service fails, second succeeds
            mock_response_success = MagicMock()
            mock_response_success.status_code = 200
            mock_response_success.text = "10.0.0.1"

            mock_get.side_effect = [
                requests.RequestException("First failed"),
                mock_response_success,
            ]

            ip = get_external_ip()

            assert ip == "10.0.0.1"
            assert mock_get.call_count == 2

    def test_tries_next_on_non_200_status(self):
        """Test that next service is tried on non-200 status code."""
        with patch("src.utils.ip_utils.requests.get") as mock_get:
            mock_response_500 = MagicMock()
            mock_response_500.status_code = 500

            mock_response_200 = MagicMock()
            mock_response_200.status_code = 200
            mock_response_200.text = "172.16.0.1"

            mock_get.side_effect = [mock_response_500, mock_response_200]

            ip = get_external_ip()

            assert ip == "172.16.0.1"
            assert mock_get.call_count == 2

    def test_uses_timeout(self, mock_requests_success):
        """Test that requests are made with a timeout."""
        get_external_ip()

        # Check that timeout=5 was passed
        call_kwargs = mock_requests_success.call_args[1]
        assert call_kwargs.get("timeout") == 5

    def test_handles_timeout_exception(self):
        """Test handling of timeout exceptions."""
        with patch("src.utils.ip_utils.requests.get") as mock_get:
            mock_get.side_effect = requests.Timeout("Request timed out")

            ip = get_external_ip()

            assert ip is None

    def test_handles_connection_error(self):
        """Test handling of connection errors."""
        with patch("src.utils.ip_utils.requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("No network")

            ip = get_external_ip()

            assert ip is None

    def test_stops_on_first_success(self, mock_requests_success):
        """Test that iteration stops on first successful response."""
        get_external_ip()

        # Should only call first service
        assert mock_requests_success.call_count == 1


# =============================================================================
# get_webhook_base_url Tests - Explicit URL
# =============================================================================


class TestGetWebhookBaseURLExplicit:
    """Tests for get_webhook_base_url with explicitly set URL."""

    def test_uses_webhook_base_url_env_var(self):
        """Test that WEBHOOK_BASE_URL environment variable is used."""
        os.environ["WEBHOOK_BASE_URL"] = "https://my-custom-domain.com"

        url, is_auto = get_webhook_base_url()

        assert url == "https://my-custom-domain.com"
        assert is_auto is False

    def test_explicit_url_takes_precedence(self):
        """Test that explicit URL takes precedence over auto-detection."""
        os.environ["WEBHOOK_BASE_URL"] = "https://explicit.com"
        os.environ["RAILWAY_PUBLIC_DOMAIN"] = "railway.app"

        url, is_auto = get_webhook_base_url()

        assert url == "https://explicit.com"
        assert is_auto is False


# =============================================================================
# get_webhook_base_url Tests - Railway Detection
# =============================================================================


class TestGetWebhookBaseURLRailway:
    """Tests for get_webhook_base_url with Railway environment."""

    def test_uses_railway_public_domain(self):
        """Test using RAILWAY_PUBLIC_DOMAIN."""
        os.environ["RAILWAY_PUBLIC_DOMAIN"] = "myapp.railway.app"

        url, is_auto = get_webhook_base_url()

        assert url == "https://myapp.railway.app"
        assert is_auto is True

    def test_uses_railway_app_url_without_scheme(self):
        """Test using RAILWAY_APP_URL without https scheme."""
        os.environ["RAILWAY_APP_URL"] = "myapp.up.railway.app"

        url, is_auto = get_webhook_base_url()

        assert url == "https://myapp.up.railway.app"
        assert is_auto is True

    def test_uses_railway_app_url_with_scheme(self):
        """Test using RAILWAY_APP_URL with https scheme."""
        os.environ["RAILWAY_APP_URL"] = "https://myapp.up.railway.app"

        url, is_auto = get_webhook_base_url()

        assert url == "https://myapp.up.railway.app"
        assert is_auto is True

    def test_uses_railway_service_url_without_scheme(self):
        """Test using RAILWAY_SERVICE_URL without https scheme."""
        os.environ["RAILWAY_SERVICE_URL"] = "service.railway.internal"

        url, is_auto = get_webhook_base_url()

        assert url == "https://service.railway.internal"
        assert is_auto is True

    def test_uses_railway_service_url_with_scheme(self):
        """Test using RAILWAY_SERVICE_URL with https scheme."""
        os.environ["RAILWAY_SERVICE_URL"] = "https://service.railway.internal"

        url, is_auto = get_webhook_base_url()

        assert url == "https://service.railway.internal"
        assert is_auto is True

    def test_uses_railway_static_url_without_scheme(self):
        """Test using RAILWAY_STATIC_URL without https scheme."""
        os.environ["RAILWAY_STATIC_URL"] = "static.railway.app"

        url, is_auto = get_webhook_base_url()

        assert url == "https://static.railway.app"
        assert is_auto is True

    def test_uses_railway_static_url_with_scheme(self):
        """Test using RAILWAY_STATIC_URL with https scheme."""
        os.environ["RAILWAY_STATIC_URL"] = "https://static.railway.app"

        url, is_auto = get_webhook_base_url()

        assert url == "https://static.railway.app"
        assert is_auto is True

    def test_railway_priority_order(self):
        """Test Railway variable priority: public_domain > app_url > service_url > static_url."""
        # Set all Railway variables
        os.environ["RAILWAY_PUBLIC_DOMAIN"] = "public.domain"
        os.environ["RAILWAY_APP_URL"] = "app.url"
        os.environ["RAILWAY_SERVICE_URL"] = "service.url"
        os.environ["RAILWAY_STATIC_URL"] = "static.url"

        url, is_auto = get_webhook_base_url()

        assert url == "https://public.domain"
        assert is_auto is True

    def test_railway_app_url_priority_over_service(self):
        """Test RAILWAY_APP_URL takes priority over RAILWAY_SERVICE_URL."""
        os.environ["RAILWAY_APP_URL"] = "app.railway.app"
        os.environ["RAILWAY_SERVICE_URL"] = "service.railway.app"

        url, is_auto = get_webhook_base_url()

        assert url == "https://app.railway.app"

    def test_railway_service_url_priority_over_static(self):
        """Test RAILWAY_SERVICE_URL takes priority over RAILWAY_STATIC_URL."""
        os.environ["RAILWAY_SERVICE_URL"] = "service.railway.app"
        os.environ["RAILWAY_STATIC_URL"] = "static.railway.app"

        url, is_auto = get_webhook_base_url()

        assert url == "https://service.railway.app"

    def test_railway_hostname_fallback(self):
        """Test using HOSTNAME when it contains 'railway'."""
        os.environ["HOSTNAME"] = "myapp-railway-container.internal"

        url, is_auto = get_webhook_base_url()

        assert url == "https://myapp-railway-container.internal"
        assert is_auto is True

    def test_railway_hostname_case_insensitive(self):
        """Test HOSTNAME railway detection is case-insensitive."""
        os.environ["HOSTNAME"] = "MyApp-RAILWAY-Container"

        url, is_auto = get_webhook_base_url()

        assert "MyApp-RAILWAY-Container" in url
        assert is_auto is True

    def test_non_railway_hostname_ignored(self):
        """Test that non-Railway HOSTNAME is ignored."""
        os.environ["HOSTNAME"] = "my-docker-container"

        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = None

            url, is_auto = get_webhook_base_url()

            assert url == ""
            assert is_auto is False


# =============================================================================
# get_webhook_base_url Tests - External IP Fallback
# =============================================================================


class TestGetWebhookBaseURLExternalIP:
    """Tests for get_webhook_base_url with external IP fallback."""

    def test_uses_external_ip_as_fallback(self):
        """Test falling back to external IP when no Railway vars."""
        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "203.0.113.50"

            url, is_auto = get_webhook_base_url()

            assert url == "https://203.0.113.50"
            assert is_auto is True

    def test_uses_https_by_default(self):
        """Test that HTTPS is used by default."""
        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "10.0.0.1"

            url, is_auto = get_webhook_base_url()

            assert url.startswith("https://")

    def test_uses_http_when_https_disabled(self):
        """Test using HTTP when WEBHOOK_USE_HTTPS is false."""
        os.environ["WEBHOOK_USE_HTTPS"] = "false"

        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "10.0.0.1"

            url, is_auto = get_webhook_base_url()

            assert url == "http://10.0.0.1:80"

    def test_uses_http_with_port_80(self):
        """Test that HTTP includes port 80."""
        os.environ["WEBHOOK_USE_HTTPS"] = "false"

        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "192.168.1.1"

            url, is_auto = get_webhook_base_url()

            assert ":80" in url

    def test_https_omits_port(self):
        """Test that HTTPS doesn't include port (uses default 443)."""
        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "192.168.1.1"

            url, is_auto = get_webhook_base_url()

            assert ":443" not in url
            assert url == "https://192.168.1.1"

    def test_webhook_use_https_true(self):
        """Test WEBHOOK_USE_HTTPS=true explicitly."""
        os.environ["WEBHOOK_USE_HTTPS"] = "true"

        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "10.0.0.1"

            url, is_auto = get_webhook_base_url()

            assert url.startswith("https://")

    def test_webhook_use_https_case_insensitive(self):
        """Test WEBHOOK_USE_HTTPS is case-insensitive for false."""
        os.environ["WEBHOOK_USE_HTTPS"] = "FALSE"

        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "10.0.0.1"

            url, is_auto = get_webhook_base_url()

            assert url.startswith("http://")
            assert ":80" in url


# =============================================================================
# get_webhook_base_url Tests - Error Cases
# =============================================================================


class TestGetWebhookBaseURLErrors:
    """Tests for get_webhook_base_url error handling."""

    def test_returns_empty_when_no_url_available(self):
        """Test returning empty string when no URL can be determined."""
        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = None

            url, is_auto = get_webhook_base_url()

            assert url == ""
            assert is_auto is False

    def test_returns_is_auto_false_when_failed(self):
        """Test is_auto is False when auto-detection fails."""
        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = None

            url, is_auto = get_webhook_base_url()

            assert is_auto is False


# =============================================================================
# get_webhook_base_url Tests - Edge Cases
# =============================================================================


class TestGetWebhookBaseURLEdgeCases:
    """Tests for edge cases in get_webhook_base_url."""

    def test_handles_empty_webhook_base_url(self):
        """Test that empty WEBHOOK_BASE_URL is treated as not set."""
        os.environ["WEBHOOK_BASE_URL"] = ""

        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "1.2.3.4"

            url, is_auto = get_webhook_base_url()

            # Empty string is falsy, should fall through to auto-detection
            assert url == "https://1.2.3.4"
            assert is_auto is True

    def test_handles_empty_railway_vars(self):
        """Test that empty Railway vars are treated as not set."""
        os.environ["RAILWAY_PUBLIC_DOMAIN"] = ""
        os.environ["RAILWAY_APP_URL"] = ""

        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "5.6.7.8"

            url, is_auto = get_webhook_base_url()

            assert url == "https://5.6.7.8"

    def test_ipv4_address_format(self):
        """Test correct handling of IPv4 addresses."""
        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "192.168.100.200"

            url, is_auto = get_webhook_base_url()

            assert url == "https://192.168.100.200"

    def test_handles_http_prefix_in_railway_app_url(self):
        """Test handling of http:// prefix in RAILWAY_APP_URL."""
        os.environ["RAILWAY_APP_URL"] = "http://legacy.railway.app"

        url, is_auto = get_webhook_base_url()

        # Should keep the http prefix as-is (starts with http)
        assert url == "http://legacy.railway.app"


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for ip_utils module."""

    def test_full_fallback_chain(self):
        """Test complete fallback chain from explicit URL to external IP."""
        # No explicit URL, no Railway vars
        with patch("src.utils.ip_utils.get_external_ip") as mock_ip:
            mock_ip.return_value = "100.100.100.100"

            url, is_auto = get_webhook_base_url()

            assert url == "https://100.100.100.100"
            assert is_auto is True

    def test_external_ip_service_integration(self):
        """Test that get_webhook_base_url properly integrates with get_external_ip."""
        with patch("src.utils.ip_utils.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "50.60.70.80"
            mock_get.return_value = mock_response

            url, is_auto = get_webhook_base_url()

            assert url == "https://50.60.70.80"
            assert is_auto is True
            mock_get.assert_called()


# =============================================================================
# Logging Tests
# =============================================================================


class TestLogging:
    """Tests for logging behavior."""

    def test_logs_explicit_url_usage(self):
        """Test that using explicit URL is logged."""
        os.environ["WEBHOOK_BASE_URL"] = "https://logged.example.com"

        with patch("src.utils.ip_utils.logger") as mock_logger:
            get_webhook_base_url()

            # Should log info about using provided URL
            mock_logger.info.assert_called()
            calls = [str(c) for c in mock_logger.info.call_args_list]
            assert any("WEBHOOK_BASE_URL" in str(c) for c in calls)

    def test_logs_railway_detection(self):
        """Test that Railway variable detection is logged."""
        os.environ["RAILWAY_PUBLIC_DOMAIN"] = "logged.railway.app"

        with patch("src.utils.ip_utils.logger") as mock_logger:
            get_webhook_base_url()

            mock_logger.info.assert_called()

    def test_logs_external_ip_retrieval(self, mock_requests_success):
        """Test that external IP retrieval is logged."""
        with patch("src.utils.ip_utils.logger") as mock_logger:
            get_external_ip()

            mock_logger.info.assert_called()

    def test_logs_service_failures(self, mock_requests_failure):
        """Test that service failures are logged as warnings."""
        with patch("src.utils.ip_utils.logger") as mock_logger:
            get_external_ip()

            mock_logger.warning.assert_called()

    def test_logs_complete_failure(self, mock_requests_failure):
        """Test that complete failure to get IP is logged as error."""
        with patch("src.utils.ip_utils.logger") as mock_logger:
            get_external_ip()

            mock_logger.error.assert_called()
