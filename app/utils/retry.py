"""
Retry & Rate-Limiting Utilities

Provides:
- RateLimiter: Token-bucket-style rate limiter for sync code
- AsyncRateLimiter: Async-compatible rate limiter
- retry_sync: Decorator for sync functions with exponential backoff
- retry_async: Decorator for async functions with exponential backoff
"""

import asyncio
import functools
import logging
import time
from typing import Any, Callable, Optional, Type

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    RetryError,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Sync Rate Limiter (used by Instagram / YouTube scrapers)
# ──────────────────────────────────────────────────────────────

class RateLimiter:
    """
    Simple token-bucket rate limiter for synchronous code.

    Usage:
        limiter = RateLimiter(calls_per_minute=6)
        for item in items:
            limiter.wait()
            process(item)
    """

    def __init__(self, calls_per_minute: int = 10):
        self.min_interval = 60.0 / calls_per_minute
        self._last_call: float = 0.0
        self._call_count: int = 0

    def wait(self) -> None:
        """Block until enough time has passed since the last call."""
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            logger.debug(f"RateLimiter: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self._last_call = time.monotonic()
        self._call_count += 1

    @property
    def total_calls(self) -> int:
        return self._call_count


# ──────────────────────────────────────────────────────────────
# Async Rate Limiter (used by Playwright scrapers)
# ──────────────────────────────────────────────────────────────

class AsyncRateLimiter:
    """
    Async-compatible rate limiter.

    Usage:
        limiter = AsyncRateLimiter(calls_per_minute=10)
        for item in items:
            await limiter.wait()
            await process(item)
    """

    def __init__(self, calls_per_minute: int = 10):
        self.min_interval = 60.0 / calls_per_minute
        self._last_call: float = 0.0

    async def wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()


# ──────────────────────────────────────────────────────────────
# Retry Decorators (using tenacity)
# ──────────────────────────────────────────────────────────────

def retry_sync(
    max_attempts: int = 3,
    min_wait: float = 2.0,
    max_wait: float = 30.0,
    retry_on: Optional[tuple[Type[Exception], ...]] = None,
) -> Callable:
    """
    Decorator: retry a sync function with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts.
        min_wait: Minimum wait between retries (seconds).
        max_wait: Maximum wait between retries (seconds).
        retry_on: Tuple of exception types to retry on. None = retry on all.
    """
    def decorator(fn: Callable) -> Callable:
        retry_kwargs = {
            "stop": stop_after_attempt(max_attempts),
            "wait": wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            "before_sleep": before_sleep_log(logger, logging.WARNING),
            "reraise": True,
        }
        if retry_on:
            retry_kwargs["retry"] = retry_if_exception_type(retry_on)

        @retry(**retry_kwargs)
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        return wrapper
    return decorator


def retry_async(
    max_attempts: int = 3,
    min_wait: float = 2.0,
    max_wait: float = 30.0,
    retry_on: Optional[tuple[Type[Exception], ...]] = None,
) -> Callable:
    """
    Decorator: retry an async function with exponential backoff.
    """
    def decorator(fn: Callable) -> Callable:
        retry_kwargs = {
            "stop": stop_after_attempt(max_attempts),
            "wait": wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            "before_sleep": before_sleep_log(logger, logging.WARNING),
            "reraise": True,
        }
        if retry_on:
            retry_kwargs["retry"] = retry_if_exception_type(retry_on)

        @retry(**retry_kwargs)
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await fn(*args, **kwargs)

        return wrapper
    return decorator
