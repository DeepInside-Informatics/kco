"""Rate limiting utilities for GraphQL polling."""

import asyncio
import time
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting."""

    capacity: int
    tokens: float
    last_refill: float
    refill_rate: float  # tokens per second

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were consumed, False otherwise
        """
        now = time.time()

        # Refill tokens based on elapsed time
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        # Check if we have enough tokens
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    def time_until_available(self, tokens: int = 1) -> float:
        """Calculate time until tokens become available.

        Args:
            tokens: Number of tokens needed

        Returns:
            Seconds until tokens become available
        """
        if self.tokens >= tokens:
            return 0.0

        needed_tokens = tokens - self.tokens
        return needed_tokens / self.refill_rate


class RateLimiter:
    """Rate limiter using token bucket algorithm."""

    def __init__(self, requests_per_minute: int = 100) -> None:
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per minute
        """
        self.requests_per_minute = requests_per_minute
        self.buckets: dict[str, RateLimitBucket] = {}
        self._lock = asyncio.Lock()

        logger.info(
            "Initialized RateLimiter",
            requests_per_minute=requests_per_minute
        )

    def _get_bucket_key(self, namespace: str, tapp_name: str) -> str:
        """Generate bucket key for TApp."""
        return f"{namespace}/{tapp_name}"

    async def _get_or_create_bucket(self, key: str) -> RateLimitBucket:
        """Get or create rate limit bucket for key."""
        async with self._lock:
            if key not in self.buckets:
                now = time.time()
                capacity = max(10, self.requests_per_minute // 6)  # Allow bursts
                refill_rate = self.requests_per_minute / 60.0  # tokens per second

                self.buckets[key] = RateLimitBucket(
                    capacity=capacity,
                    tokens=capacity,
                    last_refill=now,
                    refill_rate=refill_rate
                )

                logger.debug(
                    "Created rate limit bucket",
                    key=key,
                    capacity=capacity,
                    refill_rate=refill_rate
                )

            return self.buckets[key]

    async def acquire(
        self,
        namespace: str,
        tapp_name: str,
        tokens: int = 1,
        timeout: float | None = None
    ) -> bool:
        """Acquire tokens from rate limiter.

        Args:
            namespace: Kubernetes namespace
            tapp_name: TargetApp name
            tokens: Number of tokens to acquire
            timeout: Maximum time to wait for tokens

        Returns:
            True if tokens were acquired, False if timed out
        """
        key = self._get_bucket_key(namespace, tapp_name)
        bucket = await self._get_or_create_bucket(key)

        # Try immediate consumption
        if bucket.consume(tokens):
            logger.debug(
                "Rate limit acquired immediately",
                namespace=namespace,
                tapp=tapp_name,
                tokens=tokens,
                remaining_tokens=bucket.tokens
            )
            return True

        # If timeout is 0 or None, don't wait
        if not timeout:
            logger.debug(
                "Rate limit exceeded, not waiting",
                namespace=namespace,
                tapp=tapp_name,
                tokens=tokens,
                remaining_tokens=bucket.tokens
            )
            return False

        # Wait for tokens to become available
        wait_time = bucket.time_until_available(tokens)
        if wait_time > timeout:
            logger.debug(
                "Rate limit wait time exceeds timeout",
                namespace=namespace,
                tapp=tapp_name,
                wait_time=wait_time,
                timeout=timeout
            )
            return False

        logger.debug(
            "Waiting for rate limit tokens",
            namespace=namespace,
            tapp=tapp_name,
            wait_time=wait_time,
            tokens=tokens
        )

        await asyncio.sleep(wait_time)

        # Try again after waiting
        if bucket.consume(tokens):
            logger.debug(
                "Rate limit acquired after waiting",
                namespace=namespace,
                tapp=tapp_name,
                tokens=tokens,
                remaining_tokens=bucket.tokens
            )
            return True

        logger.warning(
            "Failed to acquire rate limit tokens after waiting",
            namespace=namespace,
            tapp=tapp_name,
            tokens=tokens
        )
        return False

    async def cleanup_expired(self, max_idle_seconds: int = 3600) -> None:
        """Clean up expired rate limit buckets.

        Args:
            max_idle_seconds: Maximum idle time before cleanup
        """
        async with self._lock:
            now = time.time()
            expired_keys = []

            for key, bucket in self.buckets.items():
                if now - bucket.last_refill > max_idle_seconds:
                    expired_keys.append(key)

            for key in expired_keys:
                del self.buckets[key]
                logger.debug("Cleaned up expired rate limit bucket", key=key)

            if expired_keys:
                logger.info(
                    "Cleaned up expired rate limit buckets",
                    count=len(expired_keys),
                    remaining=len(self.buckets)
                )

    def get_stats(self) -> dict[str, int]:
        """Get rate limiter statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "active_buckets": len(self.buckets),
            "requests_per_minute": self.requests_per_minute
        }
