#!/usr/bin/env python3
"""
Export conversation log for reveal conversation
Creates a human-readable report of all interactions
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from state_manager import StateManager


def export_conversation():
    """Export conversation history to readable format"""

    project_root = Path(__file__).parent.parent
    state_manager = StateManager()

    # Load state
    history = state_manager.get_message_history(limit=100)
    stats = state_manager.get_statistics()

    # Create output file
    output_file = project_root / "data" / "conversation_export.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("WhatsApp Assistant - Conversation Export for Reveal\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Statistics
        f.write("STATISTICS\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total Messages Processed: {stats.get('total_messages_processed', 0)}\n")
        f.write(f"Total Replies Sent: {stats.get('total_replies_sent', 0)}\n")
        f.write(f"Emergency Responses: {stats.get('total_skipped_emergency', 0)}\n")
        f.write(f"Skipped (Outside Hours): {stats.get('total_skipped_hours', 0)}\n")
        f.write(f"Skipped (Rate Limit): {stats.get('total_skipped_rate_limit', 0)}\n")
        f.write(f"Last Updated: {stats.get('last_updated', 'Never')}\n")
        f.write("\n\n")

        # Conversation History
        f.write("CONVERSATION HISTORY\n")
        f.write("-" * 80 + "\n\n")

        if not history:
            f.write("No conversation history yet.\n")
        else:
            for msg in history:
                timestamp = msg.get("timestamp", "Unknown")
                from_me = msg.get("from_me", False)
                text = msg.get("message", "")

                if from_me:
                    f.write(f"[{timestamp}] You (Assistant): {text}\n")
                else:
                    f.write(f"[{timestamp}] Contact: {text}\n")
                f.write("\n")

        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write("END OF EXPORT\n")
        f.write("=" * 80 + "\n")

    print(f"✅ Conversation exported to: {output_file}")
    print(f"\nStatistics:")
    print(f"  Messages processed: {stats.get('total_messages_processed', 0)}")
    print(f"  Replies sent: {stats.get('total_replies_sent', 0)}")
    print(f"  Conversation entries: {len(history)}")
    print(f"\nUse this export when reviewing conversation history.")


if __name__ == "__main__":
    export_conversation()
