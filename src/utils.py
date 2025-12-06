#!/usr/bin/env python3
"""
Utility functions for WhatsApp Assistant
"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import pytz
from logging.handlers import RotatingFileHandler


def setup_logging(
    log_file: Optional[Path] = None,
    level: str = "INFO",
    console: bool = True
) -> logging.Logger:
    """
    Configure logging with both file and console handlers

    Args:
        log_file: Path to log file (defaults to data/logs/assistant.log)
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        console: Whether to also log to console

    Returns:
        Configured logger
    """
    # Create logger
    logger = logging.getLogger("whatsapp_assistant")
    logger.setLevel(getattr(logging, level.upper()))

    # Clear existing handlers
    logger.handlers.clear()

    # Log format
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler with rotation
    if log_file is None:
        project_root = Path(__file__).parent.parent
        log_file = project_root / "data" / "logs" / "assistant.log"

    log_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def get_current_time(timezone: pytz.tzinfo.BaseTzInfo) -> datetime:
    """
    Get current time in specified timezone

    Args:
        timezone: Timezone object from pytz

    Returns:
        Timezone-aware datetime
    """
    return datetime.now(timezone)


def is_within_allowed_hours(
    current_time: datetime,
    start_hour: str,
    end_hour: str
) -> bool:
    """
    Check if current time is within allowed hours

    Args:
        current_time: Timezone-aware datetime
        start_hour: Start time in HH:MM format (e.g., "08:00")
        end_hour: End time in HH:MM format (e.g., "23:00")

    Returns:
        True if current time is within allowed hours
    """
    # Parse start and end times
    start_h, start_m = map(int, start_hour.split(":"))
    end_h, end_m = map(int, end_hour.split(":"))

    # Create time objects in the same timezone
    start_time = current_time.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end_time = current_time.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

    # Handle overnight range (e.g., 23:00 to 02:00)
    if end_time < start_time:
        return current_time >= start_time or current_time <= end_time

    return start_time <= current_time <= end_time


def contains_emergency_keyword(text: str, keywords: list[str]) -> bool:
    """
    Check if text contains any emergency keywords (case-insensitive)

    Args:
        text: Message text to check
        keywords: List of emergency keywords (should be lowercase)

    Returns:
        True if any keyword is found
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)


def contains_stop_keyword(text: str, keywords: list[str]) -> bool:
    """
    Check if text contains any stop keywords (case-insensitive)
    These indicate user wants the bot to stop messaging them.

    Args:
        text: Message text to check
        keywords: List of stop keywords

    Returns:
        True if any stop keyword is found
    """
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in keywords)


def format_timestamp(dt: datetime) -> str:
    """
    Format datetime for display

    Args:
        dt: Datetime object

    Returns:
        Formatted string (e.g., "2025-12-04 15:30:45")
    """
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def truncate_text(text: str, max_length: int = 100) -> str:
    """
    Truncate text for logging

    Args:
        text: Text to truncate
        max_length: Maximum length

    Returns:
        Truncated text with ellipsis if needed
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def sanitize_for_log(text: str) -> str:
    """
    Sanitize text for safe logging (remove sensitive info)

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text
    """
    # Remove phone numbers (simple pattern)
    import re
    text = re.sub(r'\+?\d{10,13}', '[PHONE]', text)

    # Remove email addresses
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]', text)

    return text


if __name__ == "__main__":
    # Test logging setup
    logger = setup_logging(level="DEBUG")
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

    # Test timezone utilities
    from config_loader import load_config

    try:
        config = load_config()
        tz = config.timezone
        current = get_current_time(tz)

        logger.info(f"Current time: {format_timestamp(current)}")
        logger.info(f"Timezone: {tz}")

        start = config.get("allowed_hours.start")
        end = config.get("allowed_hours.end")
        within_hours = is_within_allowed_hours(current, start, end)
        logger.info(f"Within allowed hours ({start}-{end}): {within_hours}")

        # Test emergency keyword detection
        test_messages = [
            "Hey, when are you coming home?",
            "URGENT: Need to talk",
            "कॉल करो please"
        ]

        for msg in test_messages:
            has_emergency = contains_emergency_keyword(msg, config.emergency_keywords)
            logger.info(f"Message: '{msg}' - Emergency: {has_emergency}")

    except Exception as e:
        logger.error(f"Error during testing: {e}")
