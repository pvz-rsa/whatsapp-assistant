# WhatsApp Auto-Reply Assistant

AI-powered WhatsApp auto-reply bot that responds in your texting style when you're busy. Uses Claude for intelligent message classification and response generation.

**All-in-one repo** - includes the WhatsApp bridge, no external dependencies to set up.

## Features

- **AI-Powered Replies**: Uses Claude (Sonnet/Haiku) for intelligent, contextual responses
- **Message Classification**: Routes messages to AI or safe templates based on type
- **Safety First**: Emergency detection, rate limiting, conflict avoidance
- **Multilingual**: Supports code-switching (e.g., Hinglish)
- **Time-Aware**: Only operates during configured hours
- **Transparent**: Full logging and conversation export tools

## Architecture

```
WhatsApp App ←→ Go Bridge (localhost:8080) ←→ MCP Server ←→ Assistant ←→ Claude API
                     ↓
              Local SQLite DB
```

Everything runs locally. Your messages never leave your machine (except to WhatsApp/Claude).

## Prerequisites

- **Go 1.21+** - for the WhatsApp bridge
- **Python 3.10+** - for the assistant
- **uv** - Python package manager ([install](https://github.com/astral-sh/uv))
- **Anthropic API key** - for Claude

## Quick Start

### 1. Clone & Configure

```bash
git clone https://github.com/pvz-rsa/whatsapp-assistant.git
cd whatsapp-assistant

# Copy example configs
cp .env.example .env
cp config/config.example.yaml config/config.yaml
cp config/prompts/reply_system.example.txt config/prompts/reply_system.txt
cp config/prompts/proactive_system.example.txt config/prompts/proactive_system.txt

# Add your API key
nano .env
# Set: ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 2. Start the WhatsApp Bridge

```bash
cd whatsapp-mcp/whatsapp-bridge
go run main.go
```

**First time**: A QR code will appear. Scan it with WhatsApp on your phone (Settings → Linked Devices → Link a Device).

Keep this terminal running.

### 3. Find Your Chat ID

Once connected, your chats sync to the local database. Find the target chat JID:

```bash
# In a new terminal, from project root
cd whatsapp-mcp/whatsapp-mcp-server
uv run python -c "
from whatsapp import list_chats
for chat in list_chats(limit=10):
    print(f'{chat.name}: {chat.jid}')
"
```

Copy the JID (e.g., `919876543210@s.whatsapp.net`) to your config.

### 4. Configure the Assistant

```bash
nano config/config.yaml
# Set: wife_chat_id: "919876543210@s.whatsapp.net"
# Set: timezone: "Your/Timezone"
```

### 5. Customize Your Persona

Edit `config/prompts/reply_system.txt` with:
- Your common phrases
- Language style (formal/casual, code-switching patterns)
- Emoji preferences
- Real examples from your chats

### 6. Test (Dry Run)

```bash
# From project root
DRY_RUN=true uv run --with anthropic --with mcp --with pyyaml --with python-dotenv --with pytz python3 src/main.py
```

Watch the logs - it will show what it *would* send without actually sending.

### 7. Go Live

```bash
# Edit config
nano config/config.yaml
# Set: busy_mode: true
# Set: dry_run: false

# Run
uv run --with anthropic --with mcp --with pyyaml --with python-dotenv --with pytz python3 src/main.py
```

## How It Works

### Message Classification

| Type | Example | Action |
|------|---------|--------|
| **LOGISTICAL** | "When are you coming?" | AI generates reply |
| **EMOTIONAL** | "Miss you" | Safe template |
| **CONFLICT** | "You never have time" | Safe template |
| **EMERGENCY** | "CALL ME NOW" | Template + flag |

### Decision Flow

```
Message → Emergency? → Outside hours? → Busy mode off? → Rate limited? → Classify → Route
              ↓              ↓                ↓                ↓            ↓
           Template        Skip             Skip             Skip      AI/Template
```

## File Structure

```
whatsapp-assistant/
├── src/                       # Assistant code
│   ├── main.py               # Orchestrator
│   ├── router.py             # Decision engine
│   ├── claude_client.py      # AI integration
│   └── ...
├── config/
│   ├── config.yaml           # Your config (gitignored)
│   ├── prompts/              # AI prompts
│   └── templates/            # Response templates
├── whatsapp-mcp/             # Bundled WhatsApp bridge
│   ├── whatsapp-bridge/      # Go bridge (connects to WhatsApp)
│   └── whatsapp-mcp-server/  # Python MCP server
├── data/                     # Runtime data (gitignored)
└── scripts/                  # Utility scripts
```

## Configuration

Key settings in `config/config.yaml`:

```yaml
wife_chat_id: "919876543210@s.whatsapp.net"  # Target chat
busy_mode: true              # Enable auto-replies
dry_run: false               # Actually send messages

allowed_hours:
  start: "08:00"
  end: "23:00"
  timezone: "Asia/Kolkata"

rate_limiting:
  max_replies_per_hour: 10
  max_replies_per_day: 50
```

## Running as a Service

```bash
# Edit service file with your paths
nano whatsapp-assistant.service

# Install
sudo cp whatsapp-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable whatsapp-assistant
sudo systemctl start whatsapp-assistant

# Check logs
journalctl -u whatsapp-assistant -f
```

## Utility Scripts

```bash
# Toggle busy mode
./scripts/toggle_busy.sh

# Health check
./scripts/check_health.sh

# Export conversation log
python3 scripts/export_conversation.py

# View statistics
python3 scripts/reveal_stats.py
```

## Safety Features

- **Emergency Detection**: Flags URGENT/CALL/EMERGENCY keywords
- **Time Restrictions**: Only operates during allowed hours
- **Rate Limiting**: Configurable hourly/daily limits
- **Conflict Avoidance**: Uses safe templates for emotional/conflict messages
- **Full Logging**: Every decision recorded locally

## Cost Estimate

~$1/month for typical usage (10-20 messages/day):
- Classification (Haiku): ~$0.001/message
- Reply generation (Sonnet): ~$0.003/message

## Troubleshooting

### QR code not appearing
```bash
# Delete old session and restart
rm -rf whatsapp-mcp/whatsapp-bridge/store/
cd whatsapp-mcp/whatsapp-bridge && go run main.go
```

### Bridge not connecting
- Make sure WhatsApp is open on your phone
- Check your phone has internet
- Try unlinking and re-linking the device

### Assistant not sending
```bash
# Check:
# 1. Bridge is running (terminal 1)
# 2. busy_mode: true in config
# 3. Within allowed_hours
# 4. dry_run: false
./scripts/check_health.sh
```

## Credits

WhatsApp bridge based on [whatsapp-mcp](https://github.com/lharries/whatsapp-mcp) by Luke Harries (MIT License).

## License

MIT License - Use responsibly and transparently.

---

**Remember**: This is a tool for when you're genuinely busy, not a replacement for real communication. Be transparent with your loved ones.
