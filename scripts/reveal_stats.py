#!/usr/bin/env python3
"""
Generate statistics dashboard for reveal conversation
Shows what the assistant did and how it behaved
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from state_manager import StateManager
from rate_limiter import RateLimiter
from config_loader import load_config


def generate_stats():
    """Generate reveal statistics"""

    project_root = Path(__file__).parent.parent
    state_manager = StateManager()
    config = load_config()
    rate_limiter = RateLimiter(state_manager, config)

    # Get data
    stats = state_manager.get_statistics()
    history = state_manager.get_message_history(limit=100)
    usage = rate_limiter.get_current_usage()

    # Calculate metrics
    total_messages = stats.get('total_messages_processed', 0)
    total_replies = stats.get('total_replies_sent', 0)
    reply_rate = (total_replies / total_messages * 100) if total_messages > 0 else 0

    # Count message types
    messages_from_contact = sum(1 for msg in history if not msg.get("from_me", False))
    messages_from_me = sum(1 for msg in history if msg.get("from_me", False))

    # Display
    print("=" * 80)
    print("WhatsApp Assistant - Reveal Statistics Dashboard")
    print("=" * 80)
    print()

    print("📊 OVERALL STATISTICS")
    print("-" * 80)
    print(f"  Total messages from contact: {total_messages}")
    print(f"  Total replies sent:          {total_replies}")
    print(f"  Reply rate:                  {reply_rate:.1f}%")
    print()

    print("🛡️ SAFETY FEATURES ACTIVATED")
    print("-" * 80)
    print(f"  Emergency responses:         {stats.get('total_skipped_emergency', 0)}")
    print(f"  Skipped (outside hours):     {stats.get('total_skipped_hours', 0)}")
    print(f"  Skipped (rate limit):        {stats.get('total_skipped_rate_limit', 0)}")
    print()

    print("📈 CONVERSATION BREAKDOWN")
    print("-" * 80)
    print(f"  Messages in history:         {len(history)}")
    print(f"  - From contact:              {messages_from_contact}")
    print(f"  - From assistant:            {messages_from_me}")
    print()

    print("⚖️ RATE LIMIT STATUS")
    print("-" * 80)
    print(f"  Hourly limit:                {usage['hourly']['count']}/{usage['hourly']['limit']} "
          f"({usage['hourly']['remaining']} remaining)")
    print(f"  Daily limit:                 {usage['daily']['count']}/{usage['daily']['limit']} "
          f"({usage['daily']['remaining']} remaining)")
    print()

    print("⚙️ CONFIGURATION")
    print("-" * 80)
    print(f"  Auto-reply enabled:          {config.enable_auto_reply}")
    print(f"  Busy mode:                   {config.busy_mode}")
    print(f"  Dry run:                     {config.dry_run}")
    print(f"  Allowed hours:               {config.get('allowed_hours.start')} - "
          f"{config.get('allowed_hours.end')}")
    print()

    print("🕐 TIMELINE")
    print("-" * 80)
    last_processed = state_manager.get_last_processed_timestamp()
    if last_processed:
        print(f"  Last message processed:      {last_processed.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print(f"  Last message processed:      Never")

    last_updated = stats.get('last_updated')
    if last_updated:
        print(f"  Last activity:               {last_updated}")
    else:
        print(f"  Last activity:               Never")
    print()

    print("=" * 80)
    print()

    # Interpretation
    print("💡 WHAT THIS MEANS")
    print("-" * 80)
    if total_replies == 0:
        print("  The assistant hasn't sent any replies yet.")
        print("  This could be because:")
        print("    - Busy mode was OFF")
        print("    - No messages were received")
        print("    - All messages were outside allowed hours")
    elif reply_rate < 50:
        print(f"  The assistant replied to {reply_rate:.0f}% of messages.")
        print("  This shows it's being conservative and respecting safety rules.")
    else:
        print(f"  The assistant replied to {reply_rate:.0f}% of messages.")
        print("  It was actively helping while you were busy.")
    print()

    emergency_count = stats.get('total_skipped_emergency', 0)
    if emergency_count > 0:
        print(f"  ⚠️  {emergency_count} emergency keyword(s) were detected.")
        print("  The assistant sent safe template responses and flagged them for your attention.")
    print()

    print("Use these statistics when having the reveal conversation.")
    print("Run `python scripts/export_conversation.py` for the full message log.")
    print("=" * 80)


if __name__ == "__main__":
    generate_stats()
