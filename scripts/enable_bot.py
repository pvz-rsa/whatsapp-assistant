#!/usr/bin/env python3
"""
Re-enable the WhatsApp assistant bot after it was disabled by stop word detection.

Usage:
    python scripts/enable_bot.py
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from state_manager import StateManager


def main():
    state_manager = StateManager()

    if state_manager.is_bot_disabled():
        reason = state_manager.get_disabled_reason()
        print(f"Bot is currently disabled: {reason}")
        print("Re-enabling bot...")
        state_manager.enable_bot()
        print("✅ Bot re-enabled!")
    else:
        print("Bot is already enabled.")


if __name__ == "__main__":
    main()
