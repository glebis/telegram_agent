"""
Tests for retry utilities.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from src.utils.retry import (
    RetryableError,
    RetryConfig,
    async_retry,
    retry,
    with_retry,
)


class TestRetryConfig:
    """Tests for RetryConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RetryConfig()

        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.jitter is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=0.5,
            max_delay=10.0,
            jitter=False,
        )

        assert config.max_attempts == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 10.0
        assert config.jitter is False

    def test_calculate_delay_exponential(self):
        """Test exponential backoff calculation."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)

        assert config.calculate_delay(0) == 1.0  # 1 * 2^0
        assert config.calculate_delay(1) == 2.0  # 1 * 2^1
        assert config.calculate_delay(2) == 4.0  # 1 * 2^2
        assert config.calculate_delay(3) == 8.0  # 1 * 2^3

    def test_calculate_delay_respects_max(self):
        """Test that delay respects max_delay."""
        config = RetryConfig(
            base_delay=1.0,
            max_delay=5.0,
            exponential_base=2.0,
            jitter=False,
        )

        # 1 * 2^4 = 16, but should cap at 5
        assert config.calculate_delay(4) == 5.0

    def test_calculate_delay_with_jitter(self):
        """Test that jitter adds randomness."""
        config = RetryConfig(base_delay=1.0, jitter=True, jitter_max=0.5)

        # Run multiple times to check jitter adds variation
        delays = [config.calculate_delay(0) for _ in range(10)]

        # All delays should be >= base_delay (1.0)
        assert all(d >= 1.0 for d in delays)
        # At least some should be different (jitter adds variation)
        assert len(set(delays)) > 1


class TestSyncRetry:
    """Tests for synchronous retry decorator."""

    def test_retry_success_first_attempt(self):
        """Test successful call on first attempt."""
        mock = MagicMock(return_value="success")

        @retry(max_attempts=3)
        def test_func():
            return mock()

        result = test_func()

        assert result == "success"
        assert mock.call_count == 1

    def test_retry_success_after_failures(self):
        """Test success after some failures."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Failed")
            return "success"

        result = test_func()

        assert result == "success"
        assert call_count == 3

    def test_retry_exhausts_attempts(self):
        """Test that all attempts are exhausted on persistent failure."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Always fails")

        with pytest.raises(ConnectionError):
            test_func()

        assert call_count == 3

    def test_retry_only_on_specified_exceptions(self):
        """Test that only specified exceptions trigger retry."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01, exceptions=(ConnectionError,))
        def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a connection error")

        with pytest.raises(ValueError):
            test_func()

        # Should not retry on ValueError
        assert call_count == 1

    def test_retry_callback(self):
        """Test that on_retry callback is called."""
        callback_calls = []

        def on_retry(exc, attempt):
            callback_calls.append((type(exc).__name__, attempt))

        call_count = 0

        @retry(max_attempts=3, base_delay=0.01, on_retry=on_retry)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Failed")
            return "success"

        test_func()

        assert len(callback_calls) == 2
        assert callback_calls[0] == ("ConnectionError", 1)
        assert callback_calls[1] == ("ConnectionError", 2)


class TestAsyncRetry:
    """Tests for async retry decorator."""

    @pytest.mark.asyncio
    async def test_async_retry_success_first_attempt(self):
        """Test successful async call on first attempt."""
        mock = MagicMock(return_value="success")

        @async_retry(max_attempts=3)
        async def test_func():
            return mock()

        result = await test_func()

        assert result == "success"
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_async_retry_success_after_failures(self):
        """Test async success after some failures."""
        call_count = 0

        @async_retry(max_attempts=3, base_delay=0.01)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Failed")
            return "success"

        result = await test_func()

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_retry_exhausts_attempts(self):
        """Test async exhausts all attempts on persistent failure."""
        call_count = 0

        @async_retry(max_attempts=3, base_delay=0.01)
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("Always times out")

        with pytest.raises(TimeoutError):
            await test_func()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_async_retry_preserves_async_behavior(self):
        """Test that async behavior is preserved."""

        @async_retry(max_attempts=2, base_delay=0.01)
        async def test_func():
            await asyncio.sleep(0.01)
            return "async result"

        result = await test_func()
        assert result == "async result"


class TestWithRetry:
    """Tests for with_retry helper function."""

    @pytest.mark.asyncio
    async def test_with_retry_success(self):
        """Test with_retry on successful call."""

        async def my_func(value):
            return value * 2

        result = await with_retry(my_func, 5, max_attempts=3)

        assert result == 10

    @pytest.mark.asyncio
    async def test_with_retry_with_kwargs(self):
        """Test with_retry with keyword arguments."""

        async def my_func(a, b=10):
            return a + b

        result = await with_retry(my_func, 5, b=20, max_attempts=3)

        assert result == 25

    @pytest.mark.asyncio
    async def test_with_retry_retries_on_failure(self):
        """Test with_retry retries on failure."""
        call_count = 0

        async def my_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("First call fails")
            return "success"

        result = await with_retry(my_func, max_attempts=3, base_delay=0.01)

        assert result == "success"
        assert call_count == 2


class TestRetryIntegration:
    """Integration tests for retry utilities."""

    @pytest.mark.asyncio
    async def test_retry_with_various_exceptions(self):
        """Test retry with multiple exception types."""
        call_count = 0
        exceptions = [ConnectionError, TimeoutError, OSError]

        @async_retry(
            max_attempts=5,
            base_delay=0.01,
            exceptions=(ConnectionError, TimeoutError, OSError),
        )
        async def test_func():
            nonlocal call_count
            if call_count < len(exceptions):
                exc = exceptions[call_count]
                call_count += 1
                raise exc("Error")
            call_count += 1
            return "success"

        result = await test_func()

        assert result == "success"
        assert call_count == 4  # 3 failures + 1 success

    def test_retry_preserves_function_metadata(self):
        """Test that decorator preserves function metadata."""

        @retry(max_attempts=3)
        def documented_function():
            """This is a docstring."""

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a docstring."

    @pytest.mark.asyncio
    async def test_async_retry_preserves_function_metadata(self):
        """Test that async decorator preserves function metadata."""

        @async_retry(max_attempts=3)
        async def async_documented():
            """Async docstring."""

        assert async_documented.__name__ == "async_documented"
        assert async_documented.__doc__ == "Async docstring."


class TestRetryableError:
    """Tests for RetryableError integration."""

    def test_retryable_error_is_retried(self):
        """Test that RetryableError triggers retries when in exceptions list."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01, exceptions=(RetryableError,))
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("transient failure")
            return "success"

        result = test_func()

        assert result == "success"
        assert call_count == 3

    def test_retryable_error_exhausts_attempts(self):
        """Test that RetryableError is re-raised after all attempts."""
        call_count = 0

        @retry(max_attempts=2, base_delay=0.01, exceptions=(RetryableError,))
        def test_func():
            nonlocal call_count
            call_count += 1
            raise RetryableError("always fails")

        with pytest.raises(RetryableError, match="always fails"):
            test_func()

        assert call_count == 2


class TestTelegramSendRetry:
    """Tests for Telegram API retry on rate limit."""

    def test_telegram_send_retries_on_rate_limit(self):
        """Mock _run_telegram_api_sync to return 429, then success."""
        import json
        from unittest.mock import patch

        from src.utils.subprocess_helper import SubprocessResult

        call_count = 0

        def mock_run_python_script(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: simulate 429 rate limit
                return SubprocessResult(
                    success=True,
                    stdout=json.dumps(
                        {
                            "success": False,
                            "error": {
                                "error_code": 429,
                                "description": "Too Many Requests",
                            },
                        }
                    ),
                    stderr="",
                    return_code=0,
                )
            else:
                # Second call: success
                return SubprocessResult(
                    success=True,
                    stdout=json.dumps(
                        {
                            "success": True,
                            "result": {"message_id": 123},
                        }
                    ),
                    stderr="",
                    return_code=0,
                )

        with patch(
            "src.utils.telegram_api.run_python_script",
            side_effect=mock_run_python_script,
        ):
            with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token"}):
                from src.utils.telegram_api import _run_telegram_api_sync

                result = _run_telegram_api_sync(
                    "sendMessage", {"chat_id": 1, "text": "hi"}
                )

        assert result is not None
        assert result["message_id"] == 123
        assert call_count == 2


class TestLLMRetry:
    """Tests for LLM call retry on transient errors."""

    @pytest.mark.asyncio
    async def test_llm_retries_on_transient_error(self):
        """Mock litellm.completion to raise on first call, succeed on second."""
        from unittest.mock import MagicMock, patch

        from src.services.llm_service import LLMService

        service = LLMService()

        call_count = 0
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test response"

        async def mock_to_thread(func, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("transient LLM error")
            return mock_response

        with patch(
            "src.services.llm_service.asyncio.to_thread", side_effect=mock_to_thread
        ):
            result = await service._call_llm(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "test"}],
                max_tokens=100,
            )

        assert result == mock_response
        assert call_count == 2
