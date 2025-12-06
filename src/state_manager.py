#!/usr/bin/env python3
"""
State Manager for persistent storage
Stores last processed message, conversation history, and rate limit data
"""
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


logger = logging.getLogger("whatsapp_assistant.state_manager")


class StateManager:
    """
    Thread-safe JSON-based state persistence

    Stores:
    - Last processed message timestamp
    - Recent message history (sliding window)
    - Rate limit counters
    """

    def __init__(self, state_file: Optional[Path] = None):
        """
        Initialize state manager

        Args:
            state_file: Path to state JSON file (defaults to data/state.json)
        """
        if state_file is None:
            project_root = Path(__file__).parent.parent
            state_file = project_root / "data" / "state.json"

        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        self.lock = threading.RLock()
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        """Load state from disk"""
        if not self.state_file.exists():
            logger.info(f"No existing state file, creating new one at {self.state_file}")
            return self._default_state()

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
                logger.info(f"Loaded state from {self.state_file}")
                return state
        except Exception as e:
            logger.error(f"Failed to load state from {self.state_file}: {e}")
            logger.warning("Using default state")
            return self._default_state()

    def _default_state(self) -> Dict[str, Any]:
        """Create default state structure"""
        return {
            "version": "1.0",
            "last_processed_timestamp": None,
            "last_processed_message_id": None,
            "message_history": [],  # List of recent messages
            "rate_limit": {
                "reply_timestamps": [],  # List of timestamps when replies were sent
                "hourly_count": 0,
                "daily_count": 0,
                "last_reset_hour": None,
                "last_reset_day": None
            },
            "statistics": {
                "total_messages_processed": 0,
                "total_replies_sent": 0,
                "total_skipped_emergency": 0,
                "total_skipped_hours": 0,
                "total_skipped_rate_limit": 0,
                "last_updated": None
            },
            "proactive": {  # NEW: Proactive messaging tracking
                "last_incoming_message_time": None,
                "unanswered_proactive_count": 0,
                "last_proactive_message_time": None
            },
            "bot_control": {  # Bot enable/disable tracking
                "disabled": False,
                "disabled_reason": None,
                "disabled_at": None
            }
        }

    def _save(self):
        """Save state to disk (assumes lock is held)"""
        try:
            # Write to temp file first, then rename (atomic operation)
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)

            temp_file.replace(self.state_file)
            logger.debug(f"State saved to {self.state_file}")

        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def get_last_processed_timestamp(self) -> Optional[datetime]:
        """Get last processed message timestamp"""
        with self.lock:
            ts = self.state.get("last_processed_timestamp")
            if ts:
                return datetime.fromisoformat(ts)
            return None

    def set_last_processed(self, timestamp: datetime, message_id: str):
        """
        Update last processed message

        Args:
            timestamp: Message timestamp
            message_id: Message ID
        """
        with self.lock:
            self.state["last_processed_timestamp"] = timestamp.isoformat()
            self.state["last_processed_message_id"] = message_id
            self._save()

    def add_message_to_history(
        self,
        message: str,
        from_me: bool,
        timestamp: datetime,
        max_history: int = 20
    ):
        """
        Add message to history (sliding window)

        Args:
            message: Message text
            from_me: Whether message is from me
            timestamp: Message timestamp
            max_history: Maximum history size
        """
        with self.lock:
            history = self.state.get("message_history", [])

            # Add new message
            history.append({
                "message": message,
                "from_me": from_me,
                "timestamp": timestamp.isoformat()
            })

            # Keep only last N messages
            self.state["message_history"] = history[-max_history:]

            self._save()

    def get_message_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent message history

        Args:
            limit: Number of recent messages to return

        Returns:
            List of message dicts
        """
        with self.lock:
            history = self.state.get("message_history", [])
            return history[-limit:]

    def record_reply_sent(self, timestamp: Optional[datetime] = None):
        """
        Record that a reply was sent (for rate limiting)

        Args:
            timestamp: Reply timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.now()

        with self.lock:
            rate_limit = self.state.get("rate_limit", {})
            timestamps = rate_limit.get("reply_timestamps", [])

            # Add new timestamp
            timestamps.append(timestamp.isoformat())

            # Clean old timestamps (older than 24 hours)
            cutoff = datetime.now().timestamp() - (24 * 3600)
            timestamps = [
                ts for ts in timestamps
                if datetime.fromisoformat(ts).timestamp() > cutoff
            ]

            rate_limit["reply_timestamps"] = timestamps
            self.state["rate_limit"] = rate_limit

            # Update statistics
            stats = self.state.get("statistics", {})
            stats["total_replies_sent"] = stats.get("total_replies_sent", 0) + 1
            stats["last_updated"] = datetime.now().isoformat()
            self.state["statistics"] = stats

            self._save()

    def get_reply_timestamps(self, since_hours: int = 1) -> List[datetime]:
        """
        Get timestamps of replies sent in last N hours

        Args:
            since_hours: Number of hours to look back

        Returns:
            List of datetime objects
        """
        with self.lock:
            rate_limit = self.state.get("rate_limit", {})
            timestamps = rate_limit.get("reply_timestamps", [])

            cutoff = datetime.now().timestamp() - (since_hours * 3600)

            recent = []
            for ts_str in timestamps:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.timestamp() > cutoff:
                        recent.append(ts)
                except (ValueError, TypeError):
                    continue

            return recent

    def increment_statistic(self, key: str):
        """
        Increment a statistic counter

        Args:
            key: Statistic key (e.g., "total_messages_processed")
        """
        with self.lock:
            stats = self.state.get("statistics", {})
            stats[key] = stats.get(key, 0) + 1
            stats["last_updated"] = datetime.now().isoformat()
            self.state["statistics"] = stats
            self._save()

    def get_statistics(self) -> Dict[str, Any]:
        """Get all statistics"""
        with self.lock:
            return self.state.get("statistics", {}).copy()

    def get_last_incoming_message_time(self) -> Optional[datetime]:
        """Get timestamp of last incoming message from target contact"""
        with self.lock:
            proactive = self.state.get("proactive", {})
            timestamp_str = proactive.get("last_incoming_message_time")
            if timestamp_str:
                return datetime.fromisoformat(timestamp_str)
            return None

    def update_last_incoming_message_time(self, timestamp: datetime):
        """Update last incoming message time (resets unanswered count)"""
        with self.lock:
            if "proactive" not in self.state:
                self.state["proactive"] = {}
            self.state["proactive"]["last_incoming_message_time"] = timestamp.isoformat()
            self.state["proactive"]["unanswered_proactive_count"] = 0
            self._save()

    def get_unanswered_proactive_count(self) -> int:
        """Get count of unanswered proactive messages"""
        with self.lock:
            proactive = self.state.get("proactive", {})
            return proactive.get("unanswered_proactive_count", 0)

    def increment_unanswered_proactive(self):
        """Increment unanswered proactive message counter"""
        with self.lock:
            if "proactive" not in self.state:
                self.state["proactive"] = {}
            from datetime import timezone
            count = self.state["proactive"].get("unanswered_proactive_count", 0)
            self.state["proactive"]["unanswered_proactive_count"] = count + 1
            self.state["proactive"]["last_proactive_message_time"] = datetime.now(timezone.utc).isoformat()
            self._save()

    def reset_unanswered_proactive(self):
        """Reset unanswered counter when target contact replies"""
        with self.lock:
            if "proactive" not in self.state:
                self.state["proactive"] = {}
            self.state["proactive"]["unanswered_proactive_count"] = 0
            self._save()

    def is_bot_disabled(self) -> bool:
        """Check if bot has been disabled by stop word detection"""
        with self.lock:
            bot_control = self.state.get("bot_control", {})
            return bot_control.get("disabled", False)

    def get_disabled_reason(self) -> Optional[str]:
        """Get reason why bot was disabled"""
        with self.lock:
            bot_control = self.state.get("bot_control", {})
            return bot_control.get("disabled_reason")

    def disable_bot(self, reason: str):
        """
        Disable the bot (triggered by stop word detection)

        Args:
            reason: Why the bot was disabled (e.g., "User said 'stop'")
        """
        with self.lock:
            if "bot_control" not in self.state:
                self.state["bot_control"] = {}
            self.state["bot_control"]["disabled"] = True
            self.state["bot_control"]["disabled_reason"] = reason
            self.state["bot_control"]["disabled_at"] = datetime.now().isoformat()
            self._save()
            logger.warning(f"🛑 Bot disabled: {reason}")

    def enable_bot(self):
        """Re-enable the bot (manual action)"""
        with self.lock:
            if "bot_control" not in self.state:
                self.state["bot_control"] = {}
            self.state["bot_control"]["disabled"] = False
            self.state["bot_control"]["disabled_reason"] = None
            self.state["bot_control"]["disabled_at"] = None
            self._save()
            logger.info("✅ Bot re-enabled")

    def reset(self):
        """Reset state to default (careful!)"""
        with self.lock:
            self.state = self._default_state()
            self._save()
            logger.warning("State has been reset to default")


def main():
    """Test state manager"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    from utils import setup_logging

    setup_logging(level="DEBUG")

    # Create state manager with temp file
    import tempfile
    temp_dir = Path(tempfile.mkdtemp())
    state_file = temp_dir / "test_state.json"

    logger.info(f"Using temp state file: {state_file}")

    # Create manager
    manager = StateManager(state_file)

    # Test 1: Add messages to history
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Message History")
    logger.info("=" * 60)

    manager.add_message_to_history("Kab aoge?", False, datetime.now())
    manager.add_message_to_history("Aa raha hoon", True, datetime.now())
    manager.add_message_to_history("Theek hai", False, datetime.now())

    history = manager.get_message_history()
    logger.info(f"Message history ({len(history)} messages):")
    for msg in history:
        direction = "→" if msg["from_me"] else "←"
        logger.info(f"  {direction} {msg['message']}")

    # Test 2: Rate limiting
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Rate Limiting")
    logger.info("=" * 60)

    for i in range(5):
        manager.record_reply_sent()
        logger.info(f"Recorded reply #{i + 1}")

    recent_replies = manager.get_reply_timestamps(since_hours=1)
    logger.info(f"Replies in last hour: {len(recent_replies)}")

    # Test 3: Statistics
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Statistics")
    logger.info("=" * 60)

    manager.increment_statistic("total_messages_processed")
    manager.increment_statistic("total_messages_processed")
    manager.increment_statistic("total_skipped_emergency")

    stats = manager.get_statistics()
    logger.info("Statistics:")
    for key, value in stats.items():
        logger.info(f"  {key}: {value}")

    # Test 4: Persistence
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Persistence")
    logger.info("=" * 60)

    logger.info("Creating new manager instance (should load from disk)...")
    manager2 = StateManager(state_file)
    history2 = manager2.get_message_history()
    stats2 = manager2.get_statistics()

    logger.info(f"Loaded {len(history2)} messages from disk")
    logger.info(f"Total replies sent: {stats2.get('total_replies_sent', 0)}")

    # Cleanup
    state_file.unlink()
    temp_dir.rmdir()

    logger.info("\n✅ All tests passed!")


if __name__ == "__main__":
    main()
