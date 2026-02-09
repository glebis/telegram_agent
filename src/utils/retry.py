"""
Retry utilities for resilient service calls.

Provides decorators and context managers for automatic retry with
exponential backoff, configurable exceptions, and logging.
"""

import asyncio
import functools
import logging
import random
import time
from typing import Any, Callable, Optional, Sequence, Type, TypeVar

logger = logging.getLogger(__name__)

# Type variable for generic return types
T = TypeVar("T")

# Default exceptions to retry on
DEFAULT_RETRY_EXCEPTIONS: tuple = (
    ConnectionError,
    TimeoutError,
    OSError,
)


class RetryableError(Exception):
    """Signal a transient failure that should be retried."""

    pass


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        jitter_max: float = 0.5,
        exceptions: Sequence[Type[Exception]] = DEFAULT_RETRY_EXCEPTIONS,
        on_retry: Optional[Callable[[Exception, int], None]] = None,
    ):
        """
        Initialize retry configuration.

        Args:
            max_attempts: Maximum number of attempts (including first try)
            base_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            exponential_base: Base for exponential backoff (delay * base^attempt)
            jitter: Whether to add random jitter to delays
            jitter_max: Maximum jitter as fraction of delay (0.0 to 1.0)
            exceptions: Tuple of exception types to retry on
            on_retry: Optional callback called on each retry with (exception, attempt)
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.jitter_max = jitter_max
        self.exceptions = tuple(exceptions)
        self.on_retry = on_retry

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given attempt number.

        Args:
            attempt: The attempt number (0-indexed)

        Returns:
            Delay in seconds with optional jitter
        """
        delay = self.base_delay * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            jitter_amount = delay * random.uniform(0, self.jitter_max)
            delay += jitter_amount

        return delay


# Default configuration
DEFAULT_CONFIG = RetryConfig()


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Sequence[Type[Exception]] = DEFAULT_RETRY_EXCEPTIONS,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    """
    Decorator for retrying synchronous functions with exponential backoff.

    Usage:
        @retry(max_attempts=3, base_delay=1.0)
        def fetch_data():
            return requests.get(url).json()

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter
        exceptions: Exception types to retry on
        on_retry: Callback on each retry

    Returns:
        Decorated function with retry logic
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        exceptions=exceptions,
        on_retry=on_retry,
    )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except config.exceptions as e:
                    last_exception = e

                    if attempt < config.max_attempts - 1:
                        delay = config.calculate_delay(attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{config.max_attempts} for {func.__name__}: "
                            f"{type(e).__name__}: {e}. Waiting {delay:.2f}s"
                        )

                        if config.on_retry:
                            config.on_retry(e, attempt + 1)

                        time.sleep(delay)
                    else:
                        logger.error(
                            f"All {config.max_attempts} attempts failed for {func.__name__}: "
                            f"{type(e).__name__}: {e}"
                        )

            # All retries exhausted
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Retry failed for {func.__name__}")

        return wrapper

    return decorator


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Sequence[Type[Exception]] = DEFAULT_RETRY_EXCEPTIONS,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable:
    """
    Decorator for retrying async functions with exponential backoff.

    Usage:
        @async_retry(max_attempts=3, base_delay=1.0)
        async def fetch_data():
            async with httpx.AsyncClient() as client:
                return await client.get(url)

    Args:
        max_attempts: Maximum number of attempts
        base_delay: Initial delay between retries
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff
        jitter: Whether to add random jitter
        exceptions: Exception types to retry on
        on_retry: Callback on each retry

    Returns:
        Decorated async function with retry logic
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        exceptions=exceptions,
        on_retry=on_retry,
    )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except config.exceptions as e:
                    last_exception = e

                    if attempt < config.max_attempts - 1:
                        delay = config.calculate_delay(attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{config.max_attempts} for {func.__name__}: "
                            f"{type(e).__name__}: {e}. Waiting {delay:.2f}s"
                        )

                        if config.on_retry:
                            config.on_retry(e, attempt + 1)

                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"All {config.max_attempts} attempts failed for {func.__name__}: "
                            f"{type(e).__name__}: {e}"
                        )

            # All retries exhausted
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Retry failed for {func.__name__}")

        return wrapper

    return decorator


class RetryContext:
    """
    Context manager for retry logic around code blocks.

    Usage:
        async with RetryContext(max_attempts=3) as ctx:
            result = await risky_operation()

    The context will automatically retry the block on configured exceptions.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exceptions: Sequence[Type[Exception]] = DEFAULT_RETRY_EXCEPTIONS,
    ):
        self.config = RetryConfig(
            max_attempts=max_attempts,
            base_delay=base_delay,
            max_delay=max_delay,
            exceptions=exceptions,
        )
        self.attempt = 0
        self.last_exception: Optional[Exception] = None

    @property
    def should_retry(self) -> bool:
        """Check if another retry attempt should be made."""
        return self.attempt < self.config.max_attempts

    def record_attempt(self, exception: Exception) -> bool:
        """
        Record a failed attempt.

        Args:
            exception: The exception that occurred

        Returns:
            True if should retry, False if max attempts reached
        """
        self.last_exception = exception
        self.attempt += 1
        return self.should_retry

    def get_delay(self) -> float:
        """Get the delay before the next retry."""
        return self.config.calculate_delay(self.attempt - 1)


async def with_retry(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    exceptions: Sequence[Type[Exception]] = DEFAULT_RETRY_EXCEPTIONS,
    **kwargs: Any,
) -> T:
    """
    Execute an async function with retry logic.

    Usage:
        result = await with_retry(
            fetch_data,
            url="https://api.example.com",
            max_attempts=3,
        )

    Args:
        func: Async function to call
        *args: Positional arguments for func
        max_attempts: Maximum retry attempts
        base_delay: Base delay between retries
        exceptions: Exception types to retry on
        **kwargs: Keyword arguments for func

    Returns:
        Result of the function call
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        exceptions=exceptions,
    )

    last_exception: Optional[Exception] = None

    for attempt in range(config.max_attempts):
        try:
            return await func(*args, **kwargs)
        except config.exceptions as e:
            last_exception = e
            if attempt < config.max_attempts - 1:
                delay = config.calculate_delay(attempt)
                logger.warning(
                    f"Retry {attempt + 1}/{config.max_attempts}: "
                    f"{type(e).__name__}: {e}. Waiting {delay:.2f}s"
                )
                await asyncio.sleep(delay)

    if last_exception:
        raise last_exception
    raise RuntimeError("Retry failed unexpectedly")


# Convenience aliases
retry_on_network_error = functools.partial(
    async_retry,
    exceptions=(ConnectionError, TimeoutError, OSError),
)

retry_on_timeout = functools.partial(
    async_retry,
    exceptions=(TimeoutError, asyncio.TimeoutError),
)
