"""
Tests for _retry_bot_init_background() — a background coroutine that retries
bot initialization with exponential backoff when the initial startup fails.

The function lives in src/lifecycle.py and is spawned via create_tracked_task()
when the first init attempt in lifespan() fails. It must:

1. Retry initialize_bot() every base_delay seconds (exponential backoff, max max_delay)
2. Set _bot_init_state to "initializing" before each attempt
3. On success: set state to "initialized", run _setup_webhook, set _bot_fully_initialized = True
4. On failure: set state to "failed" with the error, continue retrying
5. Be cancellable (exit cleanly on CancelledError)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.lifecycle as lifecycle_mod
from src.lifecycle import (
    BotInitState,
    _bot_init_state,
    _retry_bot_init_background,
)


@pytest.fixture(autouse=True)
def _reset_lifecycle_state():
    """Reset module-level lifecycle state before and after each test."""
    # Reset before
    lifecycle_mod._bot_init_state.__init__()
    lifecycle_mod._bot_fully_initialized = False
    yield
    # Reset after
    lifecycle_mod._bot_init_state.__init__()
    lifecycle_mod._bot_fully_initialized = False


class TestRetrySucceedsOnSecondAttempt:
    """When initialize_bot fails once then succeeds, the retry loop should
    complete with state 'initialized' and _bot_fully_initialized = True."""

    async def test_retry_succeeds_on_second_attempt(self):
        mock_plugin_manager = MagicMock()
        mock_plugin_manager.activate_plugins = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.application = MagicMock()

        with (
            patch(
                "src.lifecycle.initialize_bot",
                new_callable=AsyncMock,
                side_effect=[ConnectionError("attempt 1 failed"), None],
            ),
            patch(
                "src.lifecycle._setup_webhook",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "src.lifecycle.get_bot",
                return_value=mock_bot,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await _retry_bot_init_background(
                mock_plugin_manager, base_delay=30.0, max_delay=300.0
            )

            assert lifecycle_mod._bot_init_state.state == "initialized"
            assert lifecycle_mod._bot_fully_initialized is True


class TestRetryUpdatesStateToInitializingBeforeEachAttempt:
    """The state must transition through 'initializing' before each retry attempt."""

    async def test_retry_updates_state_to_initializing_before_each_attempt(self):
        observed_states = []

        original_set_initializing = BotInitState.set_initializing

        def tracking_set_initializing(self):
            original_set_initializing(self)
            observed_states.append("initializing")

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.activate_plugins = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.application = MagicMock()

        with (
            patch(
                "src.lifecycle.initialize_bot",
                new_callable=AsyncMock,
                side_effect=[RuntimeError("fail 1"), RuntimeError("fail 2"), None],
            ),
            patch(
                "src.lifecycle._setup_webhook",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("src.lifecycle.get_bot", return_value=mock_bot),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(
                BotInitState,
                "set_initializing",
                tracking_set_initializing,
            ),
        ):
            await _retry_bot_init_background(
                mock_plugin_manager, base_delay=30.0, max_delay=300.0
            )

            # Should have been called 3 times (once per attempt)
            assert len(observed_states) == 3
            assert all(s == "initializing" for s in observed_states)


class TestRetrySetFailedWithErrorOnEachFailure:
    """After each failed attempt, state should be 'failed' with the error message."""

    async def test_retry_sets_failed_with_error_on_each_failure(self):
        observed_errors = []

        original_set_failed = BotInitState.set_failed

        def tracking_set_failed(self, error):
            original_set_failed(self, error)
            observed_errors.append(error)

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.activate_plugins = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.application = MagicMock()

        with (
            patch(
                "src.lifecycle.initialize_bot",
                new_callable=AsyncMock,
                side_effect=[
                    ConnectionError("network down"),
                    TimeoutError("timed out"),
                    None,
                ],
            ),
            patch(
                "src.lifecycle._setup_webhook",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("src.lifecycle.get_bot", return_value=mock_bot),
            patch("asyncio.sleep", new_callable=AsyncMock),
            patch.object(
                BotInitState,
                "set_failed",
                tracking_set_failed,
            ),
        ):
            await _retry_bot_init_background(
                mock_plugin_manager, base_delay=30.0, max_delay=300.0
            )

            assert len(observed_errors) == 2
            assert "network down" in observed_errors[0]
            assert "timed out" in observed_errors[1]


class TestRetryCallsSetupWebhookOnSuccess:
    """When init finally succeeds, _setup_webhook should be called."""

    async def test_retry_calls_setup_webhook_on_success(self):
        mock_plugin_manager = MagicMock()
        mock_plugin_manager.activate_plugins = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.application = MagicMock()

        with (
            patch(
                "src.lifecycle.initialize_bot",
                new_callable=AsyncMock,
                side_effect=[RuntimeError("fail"), None],
            ),
            patch(
                "src.lifecycle._setup_webhook",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_webhook,
            patch("src.lifecycle.get_bot", return_value=mock_bot),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await _retry_bot_init_background(
                mock_plugin_manager, base_delay=30.0, max_delay=300.0
            )

            mock_webhook.assert_called_once()


class TestRetryIsCancellable:
    """The retry loop should exit cleanly when the task is cancelled."""

    async def test_retry_is_cancellable(self):
        mock_plugin_manager = MagicMock()

        call_count = 0

        async def failing_init():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("always fails")

        async def cancel_on_sleep(delay):
            """Simulate cancellation during sleep after first attempt."""
            if call_count >= 1:
                raise asyncio.CancelledError()

        with (
            patch(
                "src.lifecycle.initialize_bot",
                side_effect=failing_init,
            ),
            patch(
                "src.lifecycle._setup_webhook",
                new_callable=AsyncMock,
            ),
            patch("src.lifecycle.get_bot", return_value=MagicMock()),
            patch("asyncio.sleep", side_effect=cancel_on_sleep),
        ):
            # Should NOT raise CancelledError — should exit cleanly
            await _retry_bot_init_background(
                mock_plugin_manager, base_delay=30.0, max_delay=300.0
            )

            # Bot should NOT be initialized
            assert lifecycle_mod._bot_fully_initialized is False
            # At least one attempt was made
            assert call_count >= 1


class TestRetryExponentialBackoff:
    """The delay between retries should follow exponential backoff capped at max_delay."""

    async def test_retry_backoff_delays(self):
        sleep_delays = []
        attempt_count = 0

        async def failing_then_succeeds():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count <= 4:
                raise ConnectionError(f"fail {attempt_count}")
            # 5th attempt succeeds

        async def track_sleep(delay):
            sleep_delays.append(delay)

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.activate_plugins = AsyncMock()

        mock_bot = MagicMock()
        mock_bot.application = MagicMock()

        with (
            patch("src.lifecycle.initialize_bot", side_effect=failing_then_succeeds),
            patch(
                "src.lifecycle._setup_webhook",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("src.lifecycle.get_bot", return_value=mock_bot),
            patch("asyncio.sleep", side_effect=track_sleep),
        ):
            await _retry_bot_init_background(
                mock_plugin_manager, base_delay=30.0, max_delay=300.0
            )

            # 4 failures = 4 sleep calls
            assert len(sleep_delays) == 4
            # Exponential: 30, 60, 120, 240 (all under 300 cap)
            assert sleep_delays[0] == 30.0
            assert sleep_delays[1] == 60.0
            assert sleep_delays[2] == 120.0
            assert sleep_delays[3] == 240.0
