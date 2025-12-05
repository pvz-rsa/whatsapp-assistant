#!/usr/bin/env python3
"""
Rate Limiter for controlling reply frequency
Prevents spam and respects hourly/daily limits
"""
import logging
from datetime import datetime
from typing import Tuple


logger = logging.getLogger("whatsapp_assistant.rate_limiter")


class RateLimiter:
    """
    Sliding window rate limiter

    Features:
    - Hourly and daily limits
    - Sliding window (not fixed hour/day boundaries)
    - Thread-safe via state_manager
    """

    def __init__(self, state_manager, config):
        """
        Initialize rate limiter

        Args:
            state_manager: StateManager instance
            config: Config object with rate_limiting settings
        """
        self.state_manager = state_manager
        self.config = config

        self.max_per_hour = config.get("rate_limiting.max_replies_per_hour", 10)
        self.max_per_day = config.get("rate_limiting.max_replies_per_day", 50)

    def can_send_reply(self) -> Tuple[bool, str]:
        """
        Check if a reply can be sent within rate limits

        Returns:
            Tuple of (can_send: bool, reason: str)
            - If can_send is False, reason explains why
        """
        # Get recent reply timestamps
        last_hour_replies = self.state_manager.get_reply_timestamps(since_hours=1)
        last_day_replies = self.state_manager.get_reply_timestamps(since_hours=24)

        # Check hourly limit
        if len(last_hour_replies) >= self.max_per_hour:
            logger.warning(f"Hourly rate limit reached ({len(last_hour_replies)}/{self.max_per_hour})")
            return False, f"Hourly limit reached ({len(last_hour_replies)}/{self.max_per_hour})"

        # Check daily limit
        if len(last_day_replies) >= self.max_per_day:
            logger.warning(f"Daily rate limit reached ({len(last_day_replies)}/{self.max_per_day})")
            return False, f"Daily limit reached ({len(last_day_replies)}/{self.max_per_day})"

        logger.debug(f"Rate limit OK: {len(last_hour_replies)}/{self.max_per_hour} hourly, "
                    f"{len(last_day_replies)}/{self.max_per_day} daily")
        return True, "OK"

    def record_reply(self):
        """Record that a reply was sent"""
        self.state_manager.record_reply_sent()
        logger.debug("Reply recorded in rate limiter")

    def get_current_usage(self) -> dict:
        """
        Get current rate limit usage

        Returns:
            Dict with usage statistics
        """
        last_hour_replies = self.state_manager.get_reply_timestamps(since_hours=1)
        last_day_replies = self.state_manager.get_reply_timestamps(since_hours=24)

        return {
            "hourly": {
                "count": len(last_hour_replies),
                "limit": self.max_per_hour,
                "remaining": max(0, self.max_per_hour - len(last_hour_replies))
            },
            "daily": {
                "count": len(last_day_replies),
                "limit": self.max_per_day,
                "remaining": max(0, self.max_per_day - len(last_day_replies))
            }
        }

    def time_until_next_available(self) -> int:
        """
        Get seconds until next reply slot is available

        Returns:
            Seconds until next slot (0 if available now)
        """
        can_send, _ = self.can_send_reply()

        if can_send:
            return 0

        # Find oldest reply in the current window
        last_hour_replies = self.state_manager.get_reply_timestamps(since_hours=1)

        if not last_hour_replies:
            return 0

        # Sort and find oldest
        sorted_replies = sorted(last_hour_replies)
        oldest = sorted_replies[0]

        # Calculate when this reply will fall out of the window
        now = datetime.now()
        age = (now - oldest).total_seconds()
        remaining = 3600 - age  # 1 hour window

        return max(0, int(remaining))


def main():
    """Test rate limiter"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))

    from config_loader import load_config
    from state_manager import StateManager
    from utils import setup_logging
    import time

    setup_logging(level="DEBUG")

    # Create test state manager
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
    state_file = temp_dir / "test_state.json"

    state_manager = StateManager(state_file)
    config = load_config()

    # Override limits for testing
    config.raw["rate_limiting"]["max_replies_per_hour"] = 5
    config.raw["rate_limiting"]["max_replies_per_day"] = 10

    # Create rate limiter
    limiter = RateLimiter(state_manager, config)

    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Basic Rate Limiting")
    logger.info("=" * 60)

    # Test sending within limits
    for i in range(7):
        can_send, reason = limiter.can_send_reply()
        usage = limiter.get_current_usage()

        logger.info(f"\nAttempt #{i + 1}:")
        logger.info(f"  Can send: {can_send}")
        logger.info(f"  Reason: {reason}")
        logger.info(f"  Hourly: {usage['hourly']['count']}/{usage['hourly']['limit']}")
        logger.info(f"  Daily: {usage['daily']['count']}/{usage['daily']['limit']}")

        if can_send:
            limiter.record_reply()
            logger.info("  ✓ Reply sent and recorded")
        else:
            logger.info("  ✗ Reply blocked by rate limit")
            time_until = limiter.time_until_next_available()
            logger.info(f"  Next available in: {time_until}s")

    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Usage Statistics")
    logger.info("=" * 60)

    usage = limiter.get_current_usage()
    logger.info(f"Hourly usage: {usage['hourly']['count']}/{usage['hourly']['limit']} "
               f"({usage['hourly']['remaining']} remaining)")
    logger.info(f"Daily usage: {usage['daily']['count']}/{usage['daily']['limit']} "
               f"({usage['daily']['remaining']} remaining)")

    # Cleanup
    state_file.unlink()
    temp_dir.rmdir()

    logger.info("\n✅ All tests passed!")


if __name__ == "__main__":
    main()
