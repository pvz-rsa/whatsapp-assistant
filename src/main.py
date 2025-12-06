#!/usr/bin/env python3
"""
WhatsApp Assistant - Main Orchestrator
Polls WhatsApp for new messages and automatically replies based on decision logic
"""
import asyncio
import logging
import signal
import sys
from pathlib import Path
from datetime import datetime

from config_loader import load_config, ConfigError
from utils import setup_logging
from whatsapp_client import WhatsAppClient, WhatsAppClientError
from claude_client import ClaudeClient, ClaudeClientError
from state_manager import StateManager
from rate_limiter import RateLimiter
from router import Router, Decision


logger = logging.getLogger("whatsapp_assistant")


class WhatsAppAssistant:
    """
    Main orchestrator for WhatsApp Assistant

    Responsibilities:
    - Poll WhatsApp for new messages
    - Classify and route messages
    - Send replies (or log decisions)
    - Handle errors gracefully
    - Respect rate limits and safety rules
    """

    def __init__(self, config):
        """
        Initialize assistant

        Args:
            config: Config object
        """
        self.config = config
        self.running = False
        self.shutdown_event = asyncio.Event()

        # Initialize components
        logger.info("Initializing WhatsApp Assistant...")

        self.state_manager = StateManager()
        logger.info("✓ State manager initialized")

        self.whatsapp_client = WhatsAppClient(config)
        logger.info("✓ WhatsApp client initialized")

        self.claude_client = ClaudeClient(config)
        logger.info("✓ Claude client initialized")

        self.rate_limiter = RateLimiter(self.state_manager, config)
        logger.info("✓ Rate limiter initialized")

        self.router = Router(config, self.rate_limiter, self.claude_client, self.state_manager)
        logger.info("✓ Router initialized")

        logger.info(f"✅ WhatsApp Assistant ready!")
        logger.info(f"   Target chat: {config.target_chat_id}")
        logger.info(f"   Auto-reply enabled: {config.enable_auto_reply}")
        logger.info(f"   Busy mode: {config.busy_mode}")
        logger.info(f"   Dry run: {config.dry_run}")

    async def process_message(self, message):
        """
        Process a single incoming message

        Args:
            message: WhatsAppMessage object
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"New message received:")
        logger.info(f"  Text: {message.body}")
        if message.media_type:  # NEW: Log media type
            logger.info(f"  Media: {message.media_type}")
        logger.info(f"  Time: {message.timestamp}")
        logger.info(f"{'='*60}")

        # Update statistics
        self.state_manager.increment_statistic("total_messages_processed")

        # Add to history
        try:
            msg_time = datetime.fromisoformat(message.timestamp)
            self.state_manager.add_message_to_history(
                message.body,
                from_me=False,
                timestamp=msg_time
            )
            # Track incoming message time for proactive messaging
            self.state_manager.update_last_incoming_message_time(msg_time)
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not parse timestamp: {e}")

        # Get conversation context
        history = self.state_manager.get_message_history(limit=5)
        context = []
        for msg in history:
            role = "assistant" if msg["from_me"] else "user"
            context.append({"role": role, "content": msg["message"]})

        # Make decision
        try:
            decision, reason = self.router.decide(
                message.body,
                whatsapp_message=message  # NEW: Pass full message object
            )
            logger.info(f"Decision: {decision.value}")
            logger.info(f"Reason: {reason}")

            # Execute decision
            reply_text = self.router.execute_decision(
                decision,
                message.body,
                context,
                whatsapp_message=message  # NEW: Pass full message object
            )

            if reply_text:
                # Check if dry-run mode
                if self.config.dry_run:
                    logger.info(f"[DRY RUN] Would send reply: \"{reply_text}\"")
                    logger.info("[DRY RUN] Not actually sending (dry_run=true)")
                else:
                    # Actually send the reply
                    try:
                        async with self.whatsapp_client.connect():
                            await self.whatsapp_client.send_message(
                                self.config.target_chat_id,
                                reply_text
                            )
                        logger.info(f"✅ Reply sent: \"{reply_text}\"")

                        # Record reply
                        self.rate_limiter.record_reply()

                        # Add to history
                        self.state_manager.add_message_to_history(
                            reply_text,
                            from_me=True,
                            timestamp=datetime.now()
                        )

                        # Update statistics
                        if decision == Decision.TEMPLATE_EMERGENCY:
                            self.state_manager.increment_statistic("total_skipped_emergency")

                    except WhatsAppClientError as e:
                        logger.error(f"Failed to send reply: {e}")

            else:
                logger.info("No reply sent")

                # Update skip statistics
                if "hours" in reason.lower():
                    self.state_manager.increment_statistic("total_skipped_hours")
                elif "rate limit" in reason.lower():
                    self.state_manager.increment_statistic("total_skipped_rate_limit")

            # Update last processed message
            try:
                msg_time = datetime.fromisoformat(message.timestamp)
                self.state_manager.set_last_processed(msg_time, message.id)
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not update last processed: {e}")

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

    async def check_proactive_message(self):
        """
        Check if we should send proactive message after silence

        This runs in the main polling loop to detect silence periods
        """
        try:
            # Get last incoming message time
            last_incoming_time = self.state_manager.get_last_incoming_message_time()
            current_time = datetime.now(self.config.timezone)
            unanswered_count = self.state_manager.get_unanswered_proactive_count()

            # Check if we should send proactive message
            should_send, reason = self.router.should_send_proactive_message(
                last_incoming_time,
                current_time,
                unanswered_count
            )

            if not should_send:
                logger.debug(f"Proactive check: {reason}")
                return

            logger.info(f"🌟 PROACTIVE MESSAGE TRIGGERED: {reason}")

            # Get conversation context
            context = []
            try:
                async with self.whatsapp_client.connect():
                    # Fetch recent messages for context
                    messages = await self.whatsapp_client.get_messages(
                        self.config.target_chat_id,
                        limit=10
                    )

                    # Build context
                    for msg in messages:
                        if msg.body.strip():
                            context.append({
                                "role": "assistant" if msg.from_me else "user",
                                "content": msg.body
                            })
            except Exception as e:
                logger.warning(f"Could not fetch context for proactive message: {e}")
                # Continue without context

            # Generate proactive message
            from router import Decision
            reply_text = self.router.execute_decision(
                Decision.PROACTIVE_MESSAGE,
                "",  # No incoming message
                context
            )

            if not reply_text:
                logger.warning("No proactive message generated")
                return

            # Send message (respect dry_run mode)
            if self.config.dry_run:
                logger.info(f"[DRY RUN] Would send proactive message: \"{reply_text}\"")
            else:
                async with self.whatsapp_client.connect():
                    await self.whatsapp_client.send_message(
                        self.config.target_chat_id,
                        reply_text
                    )
                logger.info(f"✅ Sent proactive message: \"{reply_text}\"")

                # Update state
                self.state_manager.increment_unanswered_proactive()
                self.rate_limiter.record_reply()  # Count toward rate limits

                # Add to history
                self.state_manager.add_message_to_history(
                    reply_text,
                    from_me=True,
                    timestamp=datetime.now()
                )

        except Exception as e:
            logger.error(f"Error in proactive message check: {e}", exc_info=True)

    async def poll_loop(self):
        """
        Main polling loop

        Continuously polls WhatsApp for new messages and processes them
        """
        polling_interval = self.config.get("polling_interval_seconds", 30)
        lookback_minutes = self.config.get("message_lookback_minutes", 5)

        logger.info(f"Starting polling loop (interval: {polling_interval}s, lookback: {lookback_minutes}min)")

        consecutive_errors = 0
        max_consecutive_errors = 5

        while self.running:
            try:
                # Connect to WhatsApp MCP server
                async with self.whatsapp_client.connect():
                    # Reset error counter on successful connection
                    consecutive_errors = 0

                    # Fetch new messages
                    new_messages = await self.whatsapp_client.get_new_messages(
                        self.config.target_chat_id,
                        since_minutes=lookback_minutes
                    )

                    # Process each new message
                    for message in new_messages:
                        await self.process_message(message)

                    # Show rate limit status
                    if new_messages:
                        usage = self.rate_limiter.get_current_usage()
                        logger.info(f"\nRate limit status:")
                        logger.info(f"  Hourly: {usage['hourly']['count']}/{usage['hourly']['limit']} "
                                   f"({usage['hourly']['remaining']} remaining)")
                        logger.info(f"  Daily: {usage['daily']['count']}/{usage['daily']['limit']} "
                                   f"({usage['daily']['remaining']} remaining)")

                # Check if we should send proactive message (runs every poll cycle)
                await self.check_proactive_message()

            except WhatsAppClientError as e:
                consecutive_errors += 1
                logger.error(f"WhatsApp client error (#{consecutive_errors}): {e}")

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"Too many consecutive errors ({consecutive_errors}). Stopping.")
                    self.running = False
                    break

                # Exponential backoff
                backoff = min(polling_interval * (2 ** (consecutive_errors - 1)), 300)
                logger.warning(f"Backing off for {backoff}s before retry...")
                await asyncio.sleep(backoff)
                continue

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Unexpected error in poll loop (#{consecutive_errors}): {e}", exc_info=True)

                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"Too many consecutive errors ({consecutive_errors}). Stopping.")
                    self.running = False
                    break

            # Wait before next poll
            try:
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=polling_interval
                )
                # If we reach here, shutdown was signaled
                logger.info("Shutdown signal received")
                break
            except asyncio.TimeoutError:
                # Normal timeout - continue polling
                pass

        logger.info("Polling loop stopped")

    async def run(self):
        """Start the assistant"""
        self.running = True

        # Display statistics on startup
        stats = self.state_manager.get_statistics()
        logger.info(f"\nSession Statistics:")
        logger.info(f"  Total messages processed: {stats.get('total_messages_processed', 0)}")
        logger.info(f"  Total replies sent: {stats.get('total_replies_sent', 0)}")
        logger.info(f"  Skipped (emergency): {stats.get('total_skipped_emergency', 0)}")
        logger.info(f"  Skipped (hours): {stats.get('total_skipped_hours', 0)}")
        logger.info(f"  Skipped (rate limit): {stats.get('total_skipped_rate_limit', 0)}")

        try:
            await self.poll_loop()
        except Exception as e:
            logger.critical(f"Fatal error in assistant: {e}", exc_info=True)
            raise
        finally:
            logger.info("WhatsApp Assistant stopped")

    def stop(self):
        """Stop the assistant gracefully"""
        logger.info("Stopping WhatsApp Assistant...")
        self.running = False
        self.shutdown_event.set()


def main():
    """Main entry point"""
    # Setup signal handlers for graceful shutdown
    assistant = None

    def signal_handler(signum, frame):
        logger.info(f"\nReceived signal {signum}")
        if assistant:
            assistant.stop()
        else:
            sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Load configuration
    try:
        config = load_config()
    except ConfigError as e:
        print(f"❌ Configuration error: {e}")
        print("Please check your config.yaml and .env files")
        return 1

    # Setup logging
    log_level = "DEBUG" if config.dry_run else "INFO"
    setup_logging(level=log_level)

    logger.info("=" * 60)
    logger.info("WhatsApp Assistant Starting")
    logger.info("=" * 60)

    # Display important warnings
    if config.dry_run:
        logger.warning("⚠️  DRY RUN MODE - No messages will actually be sent")

    if not config.enable_auto_reply:
        logger.warning("⚠️  AUTO-REPLY DISABLED - Will only log messages")

    if not config.busy_mode:
        logger.info("ℹ️  Busy mode OFF - Will not send automatic replies")
        logger.info("   Set busy_mode=true or BUSY_MODE=true to enable")

    # Create and run assistant
    try:
        assistant = WhatsAppAssistant(config)
        asyncio.run(assistant.run())

    except ClaudeClientError as e:
        logger.critical(f"Failed to initialize Claude client: {e}")
        logger.critical("Please check your ANTHROPIC_API_KEY in .env")
        return 1

    except ConfigError as e:
        logger.critical(f"Configuration error: {e}")
        return 1

    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        return 0

    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        return 1

    logger.info("WhatsApp Assistant exited normally")
    return 0


if __name__ == "__main__":
    sys.exit(main())
