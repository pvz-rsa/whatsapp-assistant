#!/usr/bin/env python3
"""
WhatsApp MCP Client Wrapper
Connects to whatsapp-mcp server and provides high-level interface
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


logger = logging.getLogger("whatsapp_assistant.whatsapp_client")


class WhatsAppMessage:
    """Represents a WhatsApp message"""

    def __init__(self, data: Dict[str, Any]):
        self.raw = data
        self.id = data.get("id", "")
        self.chat_jid = data.get("chat", "")
        self.sender = data.get("sender", "")
        self.body = data.get("body", "")
        self.timestamp = data.get("timestamp", "")
        self.from_me = data.get("from_me", False)
        self.media_type = data.get("media_type", None)  # NEW: audio, image, video, sticker, document

    def is_media_only(self) -> bool:
        """Check if message is media-only (no text, only media)"""
        return bool(self.media_type and not self.body.strip())

    def __repr__(self):
        direction = "Me" if self.from_me else "Them"
        media_info = f" [{self.media_type}]" if self.media_type else ""
        return f"<WhatsAppMessage [{direction}]{media_info} {self.body[:50]}...>"


class WhatsAppClientError(Exception):
    """Base exception for WhatsApp client errors"""
    pass


class WhatsAppClient:
    """
    MCP client wrapper for whatsapp-mcp server

    Provides high-level interface for:
    - Listing chats
    - Fetching new messages
    - Sending messages
    - Tracking last processed message
    """

    def __init__(self, config):
        """
        Initialize WhatsApp client

        Args:
            config: Config object with whatsapp_mcp settings
        """
        self.config = config
        self.server_path = config.get("whatsapp_mcp.server_path")
        self.command = config.get("whatsapp_mcp.command", "uv")
        self.args = config.get("whatsapp_mcp.args", [])

        self.session: Optional[ClientSession] = None
        self.last_message_timestamp: Optional[datetime] = None

        # Reconnection settings
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 1  # Start with 1 second
        self.max_reconnect_delay = 30  # Cap at 30 seconds

    @asynccontextmanager
    async def connect(self):
        """
        Connect to MCP server (async context manager)

        Usage:
            async with client.connect():
                messages = await client.get_new_messages(chat_id)
        """
        server_params = StdioServerParameters(
            command=self.command,
            args=self.args
        )

        logger.info(f"Connecting to WhatsApp MCP server at {self.server_path}")

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self.session = session
                logger.info("✓ Connected to WhatsApp MCP server")

                try:
                    yield self
                finally:
                    self.session = None
                    logger.info("Disconnected from WhatsApp MCP server")

    async def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call MCP tool with error handling

        Args:
            tool_name: Name of MCP tool
            arguments: Tool arguments

        Returns:
            Parsed result

        Raises:
            WhatsAppClientError: If tool call fails
        """
        if not self.session:
            raise WhatsAppClientError("Not connected to MCP server. Use 'async with client.connect():'")

        try:
            result = await self.session.call_tool(tool_name, arguments)

            # Parse result
            if not result.content:
                logger.warning(f"Tool {tool_name} returned empty content")
                return None

            result_text = result.content[0].text

            # Handle empty or "No messages" responses
            if not result_text or result_text.strip() == "" or result_text == "No messages to display.":
                return None

            # Try to parse as JSON
            try:
                return json.loads(result_text)
            except json.JSONDecodeError:
                # Return raw text if not JSON
                return result_text

        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            raise WhatsAppClientError(f"Tool call failed: {e}") from e

    async def list_chats(self) -> List[Dict[str, Any]]:
        """
        List all WhatsApp chats

        Returns:
            List of chat dictionaries with jid, name, last_message, etc.
        """
        logger.debug("Listing all chats")
        chats = await self._call_tool("list_chats", {})

        if chats is None:
            return []

        if isinstance(chats, list):
            logger.info(f"Found {len(chats)} chats")
            return chats

        # Handle dict response (might be a single chat or wrapped response)
        if isinstance(chats, dict):
            # If it's a single chat dict with 'jid' key, wrap it in a list
            if 'jid' in chats:
                logger.info(f"Found 1 chat (dict format)")
                return [chats]
            # If it's a wrapper dict with 'chats' key, extract the list
            elif 'chats' in chats:
                chat_list = chats['chats']
                if isinstance(chat_list, list):
                    logger.info(f"Found {len(chat_list)} chats (wrapped format)")
                    return chat_list

        logger.warning(f"Unexpected chats format: {type(chats)}")
        return []

    async def get_messages(
        self,
        chat_jid: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[WhatsAppMessage]:
        """
        Get messages from a specific chat

        Args:
            chat_jid: Chat JID (e.g., "1234567890@s.whatsapp.net")
            limit: Maximum number of messages to fetch
            offset: Number of messages to skip

        Returns:
            List of WhatsAppMessage objects
        """
        logger.debug(f"Fetching messages from {chat_jid} (limit={limit}, offset={offset})")

        messages_data = await self._call_tool("list_messages", {
            "chat_jid": chat_jid,
            "limit": limit,
            "offset": offset,
            "include_context": False  # Don't include context to get simple list
        })

        if messages_data is None:
            return []

        # Debug: log what we got
        logger.debug(f"Messages data type: {type(messages_data)}, value: {str(messages_data)[:200]}")

        # Handle dict response - wrap single message in list
        if isinstance(messages_data, dict):
            if 'id' in messages_data and 'body' in messages_data:
                logger.info("Got single message as dict, wrapping in list")
                messages_data = [messages_data]
            else:
                logger.warning(f"Unexpected dict format: {str(messages_data)[:500]}")
                return []

        if not isinstance(messages_data, list):
            logger.warning(f"Unexpected messages format: {type(messages_data)}, data: {str(messages_data)[:500]}")
            return []

        messages = [WhatsAppMessage(msg) for msg in messages_data]
        logger.info(f"Retrieved {len(messages)} messages from {chat_jid}")

        return messages

    async def get_new_messages(
        self,
        chat_jid: str,
        since_minutes: int = 5
    ) -> List[WhatsAppMessage]:
        """
        Get new messages from a chat since last check

        Args:
            chat_jid: Chat JID
            since_minutes: Look back this many minutes (default: 5)

        Returns:
            List of new WhatsAppMessage objects (not from me)
        """
        # Fetch recent messages
        messages = await self.get_messages(chat_jid, limit=20)

        if not messages:
            return []

        # Filter messages
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(minutes=since_minutes)

        new_messages = []
        for msg in messages:
            # Skip messages from me
            if msg.from_me:
                continue

            # Parse timestamp (format: "2025-12-04T15:39:32+04:00")
            try:
                msg_time = datetime.fromisoformat(msg.timestamp)

                # Skip old messages
                if msg_time < cutoff_time:
                    continue

                # Skip already processed messages
                if self.last_message_timestamp and msg_time <= self.last_message_timestamp:
                    continue

                new_messages.append(msg)

            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse timestamp '{msg.timestamp}': {e}")
                continue

        if new_messages:
            logger.info(f"Found {len(new_messages)} new message(s) from {chat_jid}")
            # Update last processed timestamp
            self.last_message_timestamp = max(
                datetime.fromisoformat(msg.timestamp) for msg in new_messages
            )
        else:
            logger.debug(f"No new messages from {chat_jid}")

        return new_messages

    async def send_message(self, recipient: str, message: str) -> bool:
        """
        Send a message to a recipient

        Args:
            recipient: Recipient JID (e.g., "1234567890@s.whatsapp.net")
            message: Message text to send

        Returns:
            True if sent successfully

        Raises:
            WhatsAppClientError: If sending fails
        """
        logger.info(f"Sending message to {recipient}: {message[:50]}...")

        try:
            result = await self._call_tool("send_message", {
                "recipient": recipient,
                "message": message
            })

            logger.info(f"✓ Message sent successfully to {recipient}")
            return True

        except WhatsAppClientError as e:
            logger.error(f"Failed to send message: {e}")
            raise

    async def reconnect_with_backoff(self, attempt: int = 1) -> bool:
        """
        Reconnect to MCP server with exponential backoff

        Args:
            attempt: Current reconnection attempt number

        Returns:
            True if reconnection succeeded
        """
        if attempt > self.max_reconnect_attempts:
            logger.error(f"Failed to reconnect after {self.max_reconnect_attempts} attempts")
            return False

        delay = min(self.reconnect_delay * (2 ** (attempt - 1)), self.max_reconnect_delay)
        logger.warning(f"Reconnection attempt {attempt}/{self.max_reconnect_attempts} in {delay}s...")

        await asyncio.sleep(delay)

        try:
            async with self.connect():
                logger.info("✓ Reconnected successfully")
                return True
        except Exception as e:
            logger.error(f"Reconnection attempt {attempt} failed: {e}")
            return await self.reconnect_with_backoff(attempt + 1)


async def main():
    """Test WhatsApp client"""
    import sys
    sys.path.insert(0, str(__file__).replace("whatsapp_client.py", ""))

    from config_loader import load_config
    from utils import setup_logging

    # Setup
    setup_logging(level="DEBUG")
    config = load_config()

    # Create client
    client = WhatsAppClient(config)

    try:
        async with client.connect():
            # Test 1: List chats
            logger.info("\n" + "=" * 60)
            logger.info("TEST 1: List all chats")
            logger.info("=" * 60)
            chats = await client.list_chats()
            for chat in chats[:3]:
                logger.info(f"Chat: {chat.get('name', 'Unknown')} ({chat.get('jid', 'N/A')})")

            # Test 2: Get messages from wife's chat
            wife_chat_id = config.wife_chat_id
            logger.info("\n" + "=" * 60)
            logger.info(f"TEST 2: Get messages from {wife_chat_id}")
            logger.info("=" * 60)
            messages = await client.get_messages(wife_chat_id, limit=5)
            for msg in messages:
                direction = "→" if msg.from_me else "←"
                logger.info(f"{direction} {msg.body[:60]}")

            # Test 3: Get new messages
            logger.info("\n" + "=" * 60)
            logger.info(f"TEST 3: Get new messages (last 5 minutes)")
            logger.info("=" * 60)
            new_messages = await client.get_new_messages(wife_chat_id, since_minutes=60)
            logger.info(f"Found {len(new_messages)} new message(s)")
            for msg in new_messages:
                logger.info(f"← {msg.body}")

            logger.info("\n✅ All tests completed successfully!")

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))
