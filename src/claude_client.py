#!/usr/bin/env python3
"""
Claude API Client for message classification and reply generation
"""
import json
import logging
import random
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import time

from anthropic import Anthropic, APIError, RateLimitError, APITimeoutError
import yaml


logger = logging.getLogger("whatsapp_assistant.claude_client")


class ClaudeClientError(Exception):
    """Base exception for Claude client errors"""
    pass


class MessageClassification:
    """Represents a message classification result"""

    def __init__(self, label: str, confidence: float, reasoning: str):
        self.label = label.upper()
        self.confidence = confidence
        self.reasoning = reasoning

    def __repr__(self):
        return f"<Classification {self.label} ({self.confidence:.2f}): {self.reasoning[:50]}...>"


class ClaudeClient:
    """
    Client for Claude API with classification and reply generation

    Features:
    - Message classification (LOGISTICAL/EMOTIONAL/CONFLICT)
    - Reply generation with persona
    - Retry logic with exponential backoff
    - Fallback templates on failure
    """

    def __init__(self, config):
        """
        Initialize Claude client

        Args:
            config: Config object with API key and model settings
        """
        self.config = config
        self.api_key = config.anthropic_api_key
        self.client = Anthropic(api_key=self.api_key)

        # Load prompts
        project_root = Path(__file__).parent.parent
        self.classify_prompt = self._load_prompt(
            project_root / "config" / "prompts" / "classify_system.txt"
        )
        self.reply_prompt = self._load_prompt(
            project_root / "config" / "prompts" / "reply_system.txt"
        )
        self.proactive_prompt = self._load_prompt(
            project_root / "config" / "prompts" / "proactive_system.txt"
        )

        # Load templates
        self.templates = {
            "emotional": self._load_templates(project_root / "config" / "templates" / "emotional.yaml"),
            "conflict": self._load_templates(project_root / "config" / "templates" / "conflict.yaml"),
            "emergency": self._load_templates(project_root / "config" / "templates" / "emergency.yaml"),
            "media": self._load_templates(project_root / "config" / "templates" / "media.yaml"),  # NEW
        }

        # Retry settings
        self.max_retries = 3
        self.base_delay = 1  # seconds

    def _load_prompt(self, path: Path) -> str:
        """Load prompt from text file"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Failed to load prompt from {path}: {e}")
            raise ClaudeClientError(f"Could not load prompt: {e}")

    def _load_templates(self, path: Path) -> Dict:
        """Load templates from YAML file"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load templates from {path}: {e}")
            return {"templates": [], "default": "I'll reply to this myself in a bit."}

    def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Retry function with exponential backoff

        Args:
            func: Function to retry
            *args, **kwargs: Arguments to pass to func

        Returns:
            Function result

        Raises:
            ClaudeClientError: If all retries fail
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except RateLimitError as e:
                if attempt == self.max_retries:
                    logger.error(f"Rate limited after {self.max_retries} attempts")
                    raise ClaudeClientError("Rate limit exceeded") from e

                # Use Retry-After header if available
                retry_after = getattr(e, 'retry_after', None)
                if retry_after:
                    delay = float(retry_after)
                else:
                    delay = self.base_delay * (2 ** (attempt - 1))

                logger.warning(f"Rate limited, retrying in {delay}s (attempt {attempt}/{self.max_retries})")
                time.sleep(delay)

            except APITimeoutError as e:
                if attempt == self.max_retries:
                    logger.error(f"API timeout after {self.max_retries} attempts")
                    raise ClaudeClientError("API timeout") from e

                delay = self.base_delay * (2 ** (attempt - 1))
                logger.warning(f"API timeout, retrying in {delay}s (attempt {attempt}/{self.max_retries})")
                time.sleep(delay)

            except APIError as e:
                # Don't retry on authentication errors
                if e.status_code == 401:
                    logger.error("Authentication failed - invalid API key")
                    raise ClaudeClientError("Invalid API key") from e

                if attempt == self.max_retries:
                    logger.error(f"API error after {self.max_retries} attempts: {e}")
                    raise ClaudeClientError(f"API error: {e}") from e

                delay = self.base_delay * (2 ** (attempt - 1))
                logger.warning(f"API error, retrying in {delay}s (attempt {attempt}/{self.max_retries}): {e}")
                time.sleep(delay)

    def classify_message(self, message: str) -> MessageClassification:
        """
        Classify message into LOGISTICAL, EMOTIONAL, or CONFLICT

        Args:
            message: Message text to classify

        Returns:
            MessageClassification object

        Raises:
            ClaudeClientError: If classification fails
        """
        logger.debug(f"Classifying message: {message[:50]}...")

        def _classify():
            response = self.client.messages.create(
                model=self.config.get("classification.model", "claude-3-5-haiku-20241022"),
                max_tokens=self.config.get("classification.max_tokens", 100),
                temperature=self.config.get("classification.temperature", 0.0),
                system=self.classify_prompt,
                messages=[
                    {"role": "user", "content": f"Classify this message:\n\n{message}"}
                ]
            )

            # Parse response
            text = response.content[0].text.strip()

            # Try to parse JSON
            try:
                data = json.loads(text)
                label = data.get("label", "LOGISTICAL").upper()
                confidence = float(data.get("confidence", 0.5))
                reasoning = data.get("reasoning", "No reasoning provided")

                return MessageClassification(label, confidence, reasoning)

            except json.JSONDecodeError as e:
                logger.warning(f"Could not parse classification JSON: {text}")
                # Default to LOGISTICAL if parsing fails
                return MessageClassification("LOGISTICAL", 0.5, "Parse error, defaulted to LOGISTICAL")

        try:
            result = self._retry_with_backoff(_classify)
            logger.info(f"Classified as {result.label} (confidence: {result.confidence:.2f})")
            return result

        except ClaudeClientError as e:
            logger.error(f"Classification failed: {e}")
            # Fallback: default to LOGISTICAL
            return MessageClassification("LOGISTICAL", 0.0, f"Classification failed: {e}")

    def generate_reply(
        self,
        message: str,
        context: List[Dict[str, str]] = None
    ) -> str:
        """
        Generate reply to message using Claude

        Args:
            message: Message to reply to
            context: List of recent messages for context (format: [{"role": "user", "content": "..."}, ...])

        Returns:
            Generated reply text

        Raises:
            ClaudeClientError: If reply generation fails
        """
        logger.debug(f"Generating reply to: {message[:50]}...")

        def _generate():
            # Build message history
            messages = []

            # Add context if provided
            if context:
                # Filter out messages with empty content
                valid_context = [
                    msg for msg in context[-self.config.get("reply_generation.context_messages", 10):]
                    if msg.get("content", "").strip()
                ]
                messages.extend(valid_context)

            # Add current message
            messages.append({"role": "user", "content": message})

            response = self.client.messages.create(
                model=self.config.get("reply_generation.model", "claude-sonnet-4-20250514"),
                max_tokens=self.config.get("reply_generation.max_tokens", 200),
                temperature=self.config.get("reply_generation.temperature", 0.7),
                system=self.reply_prompt,
                messages=messages
            )

            reply = response.content[0].text.strip()
            return reply

        try:
            result = self._retry_with_backoff(_generate)
            logger.info(f"Generated reply: {result[:50]}...")
            return result

        except ClaudeClientError as e:
            logger.error(f"Reply generation failed: {e}")
            # Fallback to safe template
            return self.get_fallback_template("logistical")

    def get_template(self, category: str) -> str:
        """
        Get random template for a category

        Args:
            category: Template category (emotional, conflict, emergency)

        Returns:
            Random template string
        """
        category = category.lower()
        templates = self.templates.get(category, {})
        options = templates.get("templates", [])

        if not options:
            return templates.get("default", "I'll reply to this myself in a bit.")

        return random.choice(options)

    def get_fallback_template(self, category: str = "logistical") -> str:
        """
        Get fallback template when AI fails

        Args:
            category: Category for fallback

        Returns:
            Safe fallback message
        """
        fallbacks = {
            "logistical": "Bas thoda time aur, text you soon",
            "emotional": "Sorry yaar, thoda busy hoon. I'll call you soon 💙",
            "conflict": "I can see this is important. Let me respond properly in a bit.",
            "emergency": "Saw your message - calling you in 2 minutes 📞"
        }

        return fallbacks.get(category.lower(), "I'll reply in a bit")

    def get_media_template(self, media_type: str) -> str:
        """
        Get random template for media type

        Args:
            media_type: Type of media (audio, image, video, sticker, document)

        Returns:
            Random template response for the media type
        """
        media_templates = self.templates.get("media", {})
        options = media_templates.get(media_type.lower(), [])

        if not options:
            return media_templates.get("default", "Media message dekha, check karunga")

        return random.choice(options)

    def generate_proactive_message(
        self,
        content_type: str,
        context: List[Dict[str, str]] = None
    ) -> str:
        """
        Generate proactive conversation starter

        Args:
            content_type: Type of content (song_suggestion, joke, discussion_topic, etc.)
            context: Recent conversation history

        Returns:
            Generated proactive message
        """
        logger.debug(f"Generating proactive message: {content_type}")

        def _generate():
            # Build context summary
            context_summary = ""
            if context and len(context) > 0:
                recent_messages = context[-5:]  # Last 5 messages
                context_summary = "\n".join([
                    f"{'Her' if msg.get('role') == 'user' else 'You'}: {msg.get('content', '')[:100]}"
                    for msg in recent_messages
                    if msg.get('content', '').strip()
                ])

            # Build prompt with content type hint
            user_prompt = f"""Content type preference: {content_type}

Recent conversation:
{context_summary if context_summary else "(No recent context)"}

Generate a natural, engaging message to initiate conversation."""

            response = self.client.messages.create(
                model=self.config.get("reply_generation.model", "claude-sonnet-4-20250514"),
                max_tokens=150,
                temperature=0.8,  # Higher temperature for more variety
                system=self.proactive_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )

            return response.content[0].text.strip()

        try:
            result = self._retry_with_backoff(_generate)
            logger.info(f"Generated proactive message ({content_type}): {result[:50]}...")
            return result

        except ClaudeClientError as e:
            logger.error(f"Proactive message generation failed: {e}")
            # Fallback to safe template
            fallbacks = {
                "song_suggestion": "Yaar, abhi ek achha gaana sun raha hoon 🎵",
                "joke": "Arrey just remembered something funny 😄",
                "discussion_topic": "Woh jo baat ho rahi thi - was thinking about it",
                "check_in": "How's your day going? Sab theek?",
                "thought_share": "Just thought of something interesting"
            }
            return fallbacks.get(content_type, "Hey, how's it going? 💙")


async def main():
    """Test Claude client"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    from config_loader import load_config
    from utils import setup_logging

    # Setup
    setup_logging(level="DEBUG")

    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        logger.info("Please set ANTHROPIC_API_KEY in .env file")
        return 1

    # Create client
    try:
        client = ClaudeClient(config)
    except ClaudeClientError as e:
        logger.error(f"Failed to create Claude client: {e}")
        return 1

    # Test messages
    test_messages = [
        "Kab aoge?",
        "Can you pick up milk on the way home?",
        "Miss you so much",
        "You never have time for me anymore",
        "URGENT: Call me now!",
        "Dinner ready hai?"
    ]

    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Message Classification")
    logger.info("=" * 60)

    for msg in test_messages:
        logger.info(f"\nMessage: \"{msg}\"")
        classification = client.classify_message(msg)
        logger.info(f"→ {classification.label} ({classification.confidence:.2f})")
        logger.info(f"  Reasoning: {classification.reasoning}")

    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Reply Generation")
    logger.info("=" * 60)

    logistical_messages = [msg for msg in test_messages if "kab" in msg.lower() or "milk" in msg.lower()]

    for msg in logistical_messages:
        logger.info(f"\nHer: \"{msg}\"")
        reply = client.generate_reply(msg)
        logger.info(f"You: \"{reply}\"")

    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Templates")
    logger.info("=" * 60)

    for category in ["emotional", "conflict", "emergency"]:
        logger.info(f"\n{category.upper()} template:")
        template = client.get_template(category)
        logger.info(f"→ \"{template}\"")

    logger.info("\n✅ All tests completed successfully!")
    return 0


if __name__ == "__main__":
    import asyncio
    exit(asyncio.run(main()))
