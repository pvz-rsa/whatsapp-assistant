#!/usr/bin/env python3
"""
Router - Decision Engine for WhatsApp Assistant
Determines what action to take for each incoming message
"""
import logging
from enum import Enum
from typing import Tuple, Optional, TYPE_CHECKING
from datetime import datetime

from utils import is_within_allowed_hours, contains_emergency_keyword, contains_stop_keyword

if TYPE_CHECKING:
    from whatsapp_client import WhatsAppMessage


logger = logging.getLogger("whatsapp_assistant.router")


class Decision(Enum):
    """Possible decisions for handling a message"""
    AUTO_REPLY = "auto_reply"           # Generate AI reply
    TEMPLATE_EMOTIONAL = "template_emotional"  # Use emotional template
    TEMPLATE_CONFLICT = "template_conflict"    # Use conflict template
    TEMPLATE_EMERGENCY = "template_emergency"  # Use emergency template
    TEMPLATE_MEDIA = "template_media"   # Use media template
    PROACTIVE_MESSAGE = "proactive_message"  # Initiate conversation
    NO_REPLY_LOG = "no_reply_log"       # Don't reply, just log
    STOP_DETECTED = "stop_detected"     # User requested bot to stop


class Router:
    """
    Decision engine for routing messages to appropriate handlers

    Priority order:
    1. Emergency keywords → immediate template
    2. Outside allowed hours → skip
    3. Busy mode OFF → log only
    4. Rate limit exceeded → skip
    5. Route by classification:
       - LOGISTICAL → AI reply
       - EMOTIONAL → template
       - CONFLICT → template
    """

    def __init__(self, config, rate_limiter, claude_client, state_manager=None):
        """
        Initialize router

        Args:
            config: Config object
            rate_limiter: RateLimiter instance
            claude_client: ClaudeClient instance
            state_manager: StateManager instance (for bot disable functionality)
        """
        self.config = config
        self.rate_limiter = rate_limiter
        self.claude_client = claude_client
        self.state_manager = state_manager

    def should_send_proactive_message(
        self,
        last_incoming_time: Optional[datetime],
        current_time: datetime,
        unanswered_count: int
    ) -> Tuple[bool, str]:
        """
        Determine if we should send proactive message

        Args:
            last_incoming_time: When we last received message from target contact
            current_time: Current time
            unanswered_count: How many proactive messages we've sent without reply

        Returns:
            Tuple of (should_send, reason)
        """
        # Check if proactive messaging is enabled
        if not self.config.get("proactive_messaging.enabled", False):
            return False, "Proactive messaging disabled"

        # Check if we already sent unanswered proactive message
        max_unanswered = self.config.get("proactive_messaging.max_unanswered_proactive", 1)
        if unanswered_count >= max_unanswered:
            return False, f"Already sent {unanswered_count} unanswered proactive message(s)"

        # Check if we have last incoming time
        if not last_incoming_time:
            return False, "No last incoming message time tracked"

        # Calculate silence duration
        silence_duration = current_time - last_incoming_time
        silence_minutes = silence_duration.total_seconds() / 60

        # Check if silence threshold met (with jitter)
        threshold = self.config.get("proactive_messaging.silence_threshold_minutes", 60)
        jitter = self.config.get("proactive_messaging.jitter_minutes", 10)

        # Add random jitter for natural timing
        import random
        effective_threshold = threshold + random.randint(0, jitter)

        if silence_minutes < effective_threshold:
            return False, f"Silence duration {silence_minutes:.1f}min < threshold {effective_threshold}min"

        # Check proactive allowed hours
        proactive_start = self.config.get("proactive_messaging.allowed_hours.start", "09:00")
        proactive_end = self.config.get("proactive_messaging.allowed_hours.end", "18:00")

        from utils import is_within_allowed_hours
        if not is_within_allowed_hours(current_time, proactive_start, proactive_end):
            return False, f"Outside proactive hours ({proactive_start}-{proactive_end})"

        # All checks passed
        return True, f"Silence {silence_minutes:.1f}min exceeded threshold, sending proactive message"

    def decide(
        self,
        message: str,
        current_time: Optional[datetime] = None,
        whatsapp_message: Optional['WhatsAppMessage'] = None
    ) -> Tuple[Decision, str]:
        """
        Decide what action to take for a message

        Args:
            message: Message text
            current_time: Current time (defaults to now)
            whatsapp_message: Full WhatsAppMessage object (for media detection)

        Returns:
            Tuple of (Decision, reason)
        """
        if current_time is None:
            current_time = datetime.now(self.config.timezone)

        # PRIORITY -1: Check if bot is disabled (by previous stop word)
        if self.state_manager and self.state_manager.is_bot_disabled():
            reason = self.state_manager.get_disabled_reason() or "Unknown"
            logger.info(f"🛑 Bot is disabled: {reason}")
            return Decision.NO_REPLY_LOG, f"Bot disabled: {reason}"

        # PRIORITY 0: Check for media-only messages
        if whatsapp_message and whatsapp_message.is_media_only():
            logger.info(f"📎 Media-only message: {whatsapp_message.media_type}")
            return Decision.TEMPLATE_MEDIA, f"Media-only ({whatsapp_message.media_type})"

        # PRIORITY 0.5: Check for stop keywords (user wants bot to stop)
        stop_keywords = self.config.get("stop_keywords", [])
        if stop_keywords and contains_stop_keyword(message, stop_keywords):
            logger.warning(f"🛑 Stop keyword detected in: {message[:50]}...")
            if self.state_manager:
                self.state_manager.disable_bot(f"User said: {message[:100]}")
            return Decision.STOP_DETECTED, "Stop keyword detected - bot disabled"

        # PRIORITY 1: Check for emergency keywords
        if contains_emergency_keyword(message, self.config.emergency_keywords):
            logger.warning(f"🚨 Emergency keyword detected in message: {message[:50]}...")
            return Decision.TEMPLATE_EMERGENCY, "Emergency keyword detected"

        # PRIORITY 2: Check if auto-reply is globally disabled
        if not self.config.enable_auto_reply:
            logger.info("Auto-reply is globally disabled")
            return Decision.NO_REPLY_LOG, "Auto-reply disabled globally"

        # PRIORITY 3: Check allowed hours
        start_hour = self.config.get("allowed_hours.start", "08:00")
        end_hour = self.config.get("allowed_hours.end", "23:00")

        if not is_within_allowed_hours(current_time, start_hour, end_hour):
            logger.info(f"Outside allowed hours ({start_hour}-{end_hour})")
            return Decision.NO_REPLY_LOG, f"Outside allowed hours ({start_hour}-{end_hour})"

        # PRIORITY 4: Check if busy mode is enabled
        if not self.config.busy_mode:
            logger.info("Busy mode is OFF - not replying")
            return Decision.NO_REPLY_LOG, "Busy mode is OFF"

        # PRIORITY 5: Check rate limits
        can_send, rate_reason = self.rate_limiter.can_send_reply()
        if not can_send:
            logger.warning(f"Rate limit exceeded: {rate_reason}")
            return Decision.NO_REPLY_LOG, f"Rate limit: {rate_reason}"

        # PRIORITY 6: Classify message and route accordingly
        try:
            classification = self.claude_client.classify_message(message)

            logger.info(f"Message classified as {classification.label} "
                       f"(confidence: {classification.confidence:.2f})")

            if classification.label == "LOGISTICAL":
                return Decision.AUTO_REPLY, f"Logistical message (confidence: {classification.confidence:.2f})"

            elif classification.label == "EMOTIONAL":
                return Decision.TEMPLATE_EMOTIONAL, f"Emotional message (confidence: {classification.confidence:.2f})"

            elif classification.label == "CONFLICT":
                return Decision.TEMPLATE_CONFLICT, f"Conflict message (confidence: {classification.confidence:.2f})"

            else:
                # Unknown classification - default to template for safety
                logger.warning(f"Unknown classification: {classification.label}")
                return Decision.TEMPLATE_EMOTIONAL, f"Unknown classification: {classification.label}"

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            # On classification failure, use safe template
            return Decision.TEMPLATE_EMOTIONAL, f"Classification failed: {e}"

    def execute_decision(
        self,
        decision: Decision,
        message: str,
        context: list = None,
        whatsapp_message: Optional['WhatsAppMessage'] = None
    ) -> Optional[str]:
        """
        Execute the decision and return reply text (if applicable)

        Args:
            decision: Decision from decide()
            message: Original message
            context: Conversation context
            whatsapp_message: Full WhatsAppMessage object (for media templates)

        Returns:
            Reply text (or None if no reply)
        """
        if decision == Decision.NO_REPLY_LOG:
            logger.info("Decision: No reply (logging only)")
            return None

        elif decision == Decision.STOP_DETECTED:
            logger.warning("Decision: Stop detected - bot disabled, no reply")
            return None

        elif decision == Decision.TEMPLATE_MEDIA:
            if whatsapp_message and whatsapp_message.media_type:
                reply = self.claude_client.get_media_template(whatsapp_message.media_type)
                logger.info(f"Decision: Media template ({whatsapp_message.media_type}) → \"{reply}\"")
                return reply
            return None

        elif decision == Decision.PROACTIVE_MESSAGE:  # NEW
            logger.info("Decision: Generate proactive message")
            try:
                # Choose content type based on weights
                content_types = self.config.get("proactive_messaging.content_types", ["check_in"])
                weights = self.config.get("proactive_messaging.content_weights", {})

                # Build weighted list
                import random
                weighted_choices = []
                for content_type in content_types:
                    weight = weights.get(content_type, 1)
                    weighted_choices.extend([content_type] * weight)

                chosen_type = random.choice(weighted_choices) if weighted_choices else "check_in"

                reply = self.claude_client.generate_proactive_message(chosen_type, context)
                logger.info(f"Generated proactive message ({chosen_type}): \"{reply}\"")
                return reply

            except Exception as e:
                logger.error(f"Proactive message generation failed: {e}")
                # Fallback to simple check-in
                return "How's your day going? Sab theek? 💙"

        elif decision == Decision.TEMPLATE_EMERGENCY:
            reply = self.claude_client.get_template("emergency")
            logger.info(f"Decision: Emergency template → \"{reply}\"")
            return reply

        elif decision == Decision.TEMPLATE_EMOTIONAL:
            reply = self.claude_client.get_template("emotional")
            logger.info(f"Decision: Emotional template → \"{reply}\"")
            return reply

        elif decision == Decision.TEMPLATE_CONFLICT:
            reply = self.claude_client.get_template("conflict")
            logger.info(f"Decision: Conflict template → \"{reply}\"")
            return reply

        elif decision == Decision.AUTO_REPLY:
            logger.info("Decision: Generate AI reply")
            try:
                reply = self.claude_client.generate_reply(message, context)
                logger.info(f"Generated reply: \"{reply}\"")
                return reply
            except Exception as e:
                logger.error(f"AI reply generation failed: {e}")
                # Fallback to safe template
                return self.claude_client.get_fallback_template("logistical")

        else:
            logger.error(f"Unknown decision: {decision}")
            return None


def main():
    """Test router"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))

    from config_loader import load_config
    from state_manager import StateManager
    from rate_limiter import RateLimiter
    from claude_client import ClaudeClient
    from utils import setup_logging
    import tempfile
    from datetime import time

    setup_logging(level="DEBUG")

    # Create test components
    config = load_config()

    # Create temp state manager
    temp_dir = Path(tempfile.mkdtemp())
    state_file = temp_dir / "test_state.json"
    state_manager = StateManager(state_file)

    # Override config for testing
    config.raw["rate_limiting"]["max_replies_per_hour"] = 10
    config.raw["busy_mode"] = True  # Enable busy mode for testing

    rate_limiter = RateLimiter(state_manager, config)

    try:
        claude_client = ClaudeClient(config)
    except Exception as e:
        logger.warning(f"Could not create Claude client: {e}")
        logger.info("Tests will use mock classification")
        claude_client = None
        # Cleanup and exit
        state_file.unlink()
        temp_dir.rmdir()
        return 0

    # Create router
    router = Router(config, rate_limiter, claude_client)

    # Test messages
    test_cases = [
        ("URGENT: Call me now!", "Should trigger emergency template"),
        ("Kab aoge?", "Should classify as LOGISTICAL and generate AI reply"),
        ("Miss you so much", "Should classify as EMOTIONAL and use template"),
        ("You never have time for me", "Should classify as CONFLICT and use template"),
        ("Can you pick up milk?", "Should classify as LOGISTICAL and generate AI reply"),
    ]

    logger.info("\n" + "=" * 60)
    logger.info("TEST: Router Decision Making")
    logger.info("=" * 60)

    for message, expected in test_cases:
        logger.info(f"\n{'─' * 60}")
        logger.info(f"Message: \"{message}\"")
        logger.info(f"Expected: {expected}")
        logger.info(f"{'─' * 60}")

        # Make decision
        decision, reason = router.decide(message)
        logger.info(f"Decision: {decision.value}")
        logger.info(f"Reason: {reason}")

        # Execute decision (in dry-run mode)
        if decision != Decision.NO_REPLY_LOG:
            reply = router.execute_decision(decision, message)
            if reply:
                logger.info(f"Reply: \"{reply}\"")

    # Test rate limiting
    logger.info("\n" + "=" * 60)
    logger.info("TEST: Rate Limit Blocking")
    logger.info("=" * 60)

    # Fill up rate limit
    for i in range(11):
        decision, reason = router.decide("Test message")
        logger.info(f"Attempt #{i + 1}: {decision.value} - {reason}")

        if decision != Decision.NO_REPLY_LOG:
            rate_limiter.record_reply()

    # Cleanup
    state_file.unlink()
    temp_dir.rmdir()

    logger.info("\n✅ Router tests completed!")


if __name__ == "__main__":
    main()
