#!/usr/bin/env python3
"""
Analyze WhatsApp chat export to extract texting style patterns.

Usage:
    python scripts/analyze_style.py <whatsapp_export.txt>

This script parses a WhatsApp chat export file and extracts:
- Message length distribution
- Common phrases and words
- Emoji usage patterns
- Language mix (English/Hindi/etc)
- Response patterns
"""
import re
import sys
from pathlib import Path
from collections import Counter
from dataclasses import dataclass
from typing import List, Tuple, Optional


@dataclass
class Message:
    """Represents a single WhatsApp message"""
    timestamp: str
    sender: str
    text: str
    is_from_me: bool = False


def parse_whatsapp_export(file_path: Path, your_name: str = None) -> List[Message]:
    """
    Parse WhatsApp export file.

    Format: "DD/MM/YY, HH:MM - Sender: Message text"
    or:     "MM/DD/YY, HH:MM - Sender: Message text"

    Args:
        file_path: Path to export file
        your_name: Your name as it appears in export (to identify your messages)

    Returns:
        List of Message objects
    """
    messages = []

    # WhatsApp export pattern (handles multiple date formats)
    pattern = r'^(\d{1,2}/\d{1,2}/\d{2,4},?\s*\d{1,2}:\d{2}(?:\s*[AP]M)?)\s*-\s*([^:]+):\s*(.+)$'

    with open(file_path, 'r', encoding='utf-8') as f:
        current_message = None

        for line in f:
            line = line.strip()
            if not line:
                continue

            match = re.match(pattern, line)
            if match:
                # Save previous message
                if current_message:
                    messages.append(current_message)

                timestamp, sender, text = match.groups()
                sender = sender.strip()

                # Determine if message is from you
                is_from_me = False
                if your_name and your_name.lower() in sender.lower():
                    is_from_me = True

                current_message = Message(
                    timestamp=timestamp,
                    sender=sender,
                    text=text.strip(),
                    is_from_me=is_from_me
                )
            elif current_message:
                # Continuation of previous message
                current_message.text += '\n' + line

        # Don't forget the last message
        if current_message:
            messages.append(current_message)

    return messages


def analyze_messages(messages: List[Message], sender_name: str = None) -> dict:
    """
    Analyze messages to extract style patterns.

    Args:
        messages: List of messages
        sender_name: Filter to only analyze this sender's messages

    Returns:
        Dictionary with analysis results
    """
    # Filter messages if sender specified
    if sender_name:
        msgs = [m for m in messages if sender_name.lower() in m.sender.lower()]
    else:
        msgs = [m for m in messages if m.is_from_me]

    if not msgs:
        return {"error": "No messages found for specified sender"}

    # Extract texts
    texts = [m.text for m in msgs if not m.text.startswith('<Media')]

    # Message length analysis
    word_counts = [len(t.split()) for t in texts]
    char_counts = [len(t) for t in texts]

    # Common words/phrases
    all_words = []
    for text in texts:
        words = re.findall(r'\b\w+\b', text.lower())
        all_words.extend(words)

    word_freq = Counter(all_words)

    # Common 2-word phrases
    bigrams = []
    for text in texts:
        words = re.findall(r'\b\w+\b', text.lower())
        for i in range(len(words) - 1):
            bigrams.append(f"{words[i]} {words[i+1]}")

    bigram_freq = Counter(bigrams)

    # Emoji analysis
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )

    all_emojis = []
    msgs_with_emoji = 0
    for text in texts:
        emojis = emoji_pattern.findall(text)
        if emojis:
            msgs_with_emoji += 1
            all_emojis.extend(emojis)

    emoji_freq = Counter(all_emojis)

    # Language detection (simple heuristic)
    hindi_words = {'haan', 'nahi', 'kya', 'yaar', 'arrey', 'bas', 'theek', 'hai',
                   'ho', 'kar', 'raha', 'rahi', 'karo', 'bolo', 'acha', 'accha',
                   'abhi', 'woh', 'kuch', 'nhi', 'kr', 'kya', 'aur', 'mein', 'tum'}

    hindi_count = sum(1 for w in all_words if w in hindi_words)
    hindi_ratio = hindi_count / len(all_words) if all_words else 0

    # Get example messages by length category
    short_msgs = [t for t in texts if len(t.split()) <= 3]
    medium_msgs = [t for t in texts if 4 <= len(t.split()) <= 8]
    long_msgs = [t for t in texts if len(t.split()) > 8]

    return {
        "total_messages": len(msgs),
        "text_messages": len(texts),
        "message_length": {
            "avg_words": sum(word_counts) / len(word_counts) if word_counts else 0,
            "avg_chars": sum(char_counts) / len(char_counts) if char_counts else 0,
            "min_words": min(word_counts) if word_counts else 0,
            "max_words": max(word_counts) if word_counts else 0,
            "distribution": {
                "1-3 words": len([c for c in word_counts if c <= 3]),
                "4-8 words": len([c for c in word_counts if 4 <= c <= 8]),
                "9+ words": len([c for c in word_counts if c > 8]),
            }
        },
        "common_words": dict(word_freq.most_common(30)),
        "common_phrases": dict(bigram_freq.most_common(20)),
        "emoji_usage": {
            "total_emojis": len(all_emojis),
            "unique_emojis": len(set(all_emojis)),
            "messages_with_emoji": msgs_with_emoji,
            "emoji_rate": msgs_with_emoji / len(texts) if texts else 0,
            "top_emojis": dict(emoji_freq.most_common(10)),
        },
        "language_mix": {
            "hindi_word_ratio": hindi_ratio,
            "estimated_style": "Hinglish" if 0.05 < hindi_ratio < 0.5 else
                              ("Hindi" if hindi_ratio >= 0.5 else "English")
        },
        "examples": {
            "short": short_msgs[:10],
            "medium": medium_msgs[:10],
            "long": long_msgs[:5],
        }
    }


def generate_prompt_suggestions(analysis: dict) -> str:
    """Generate suggestions for the personality prompt based on analysis."""

    suggestions = []

    # Length suggestion
    avg_words = analysis["message_length"]["avg_words"]
    dist = analysis["message_length"]["distribution"]

    suggestions.append("## Message Length")
    if dist["1-3 words"] > dist["4-8 words"]:
        suggestions.append(f"- Your messages are typically VERY short (1-3 words)")
        suggestions.append(f"- Average: {avg_words:.1f} words per message")
        suggestions.append(f"- Suggest prompt: 'Keep messages 1-5 words, MAX 8 words'")
    else:
        suggestions.append(f"- Average message length: {avg_words:.1f} words")
        suggestions.append(f"- Suggest prompt: 'Keep messages under 10 words typically'")

    # Language suggestion
    suggestions.append("\n## Language Style")
    lang = analysis["language_mix"]["estimated_style"]
    ratio = analysis["language_mix"]["hindi_word_ratio"]
    suggestions.append(f"- Detected style: {lang} (Hindi ratio: {ratio:.1%})")

    # Emoji suggestion
    suggestions.append("\n## Emoji Usage")
    emoji_rate = analysis["emoji_usage"]["emoji_rate"]
    top_emojis = list(analysis["emoji_usage"]["top_emojis"].keys())[:5]
    suggestions.append(f"- Emoji rate: {emoji_rate:.1%} of messages have emojis")
    if top_emojis:
        suggestions.append(f"- Most used: {' '.join(top_emojis)}")
    if emoji_rate < 0.1:
        suggestions.append(f"- Suggest prompt: 'RARELY use emojis (< 10% of messages)'")

    # Common phrases
    suggestions.append("\n## Common Phrases")
    for phrase, count in list(analysis["common_phrases"].items())[:10]:
        suggestions.append(f"- '{phrase}' ({count} times)")

    # Example messages
    suggestions.append("\n## Real Message Examples (for prompt)")
    suggestions.append("\n### Short responses:")
    for msg in analysis["examples"]["short"][:5]:
        suggestions.append(f'- "{msg}"')

    suggestions.append("\n### Medium responses:")
    for msg in analysis["examples"]["medium"][:5]:
        suggestions.append(f'- "{msg}"')

    return "\n".join(suggestions)


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_style.py <whatsapp_export.txt> [your_name]")
        print("\nTo export WhatsApp chat:")
        print("1. Open chat in WhatsApp")
        print("2. Tap menu (⋮) > More > Export chat")
        print("3. Choose 'Without Media'")
        print("4. Save the .txt file")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    your_name = sys.argv[2] if len(sys.argv) > 2 else None

    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    print(f"Parsing {file_path}...")
    messages = parse_whatsapp_export(file_path, your_name)
    print(f"Found {len(messages)} total messages")

    # Show unique senders
    senders = set(m.sender for m in messages)
    print(f"\nSenders found:")
    for sender in senders:
        count = len([m for m in messages if m.sender == sender])
        print(f"  - {sender}: {count} messages")

    if not your_name:
        print("\nTip: Run with your name to filter: python analyze_style.py export.txt 'Your Name'")
        your_name = input("\nEnter your name (as shown above): ").strip()

    print(f"\nAnalyzing messages from: {your_name}")
    analysis = analyze_messages(messages, your_name)

    if "error" in analysis:
        print(f"Error: {analysis['error']}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("STYLE ANALYSIS RESULTS")
    print("=" * 60)

    print(f"\nTotal messages analyzed: {analysis['text_messages']}")
    print(f"Average message length: {analysis['message_length']['avg_words']:.1f} words")
    print(f"Length distribution:")
    for bucket, count in analysis['message_length']['distribution'].items():
        pct = count / analysis['text_messages'] * 100 if analysis['text_messages'] else 0
        print(f"  {bucket}: {count} ({pct:.1f}%)")

    print(f"\nLanguage: {analysis['language_mix']['estimated_style']}")
    print(f"Hindi word ratio: {analysis['language_mix']['hindi_word_ratio']:.1%}")

    print(f"\nEmoji usage: {analysis['emoji_usage']['emoji_rate']:.1%} of messages")
    if analysis['emoji_usage']['top_emojis']:
        print(f"Top emojis: {' '.join(analysis['emoji_usage']['top_emojis'].keys())}")

    print("\n" + "=" * 60)
    print("PROMPT SUGGESTIONS")
    print("=" * 60)
    print(generate_prompt_suggestions(analysis))

    # Save analysis
    output_path = Path("data/style_analysis.txt")
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(generate_prompt_suggestions(analysis))
    print(f"\n✅ Analysis saved to: {output_path}")


if __name__ == "__main__":
    main()
