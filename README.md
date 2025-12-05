# WhatsApp Auto-Reply Assistant

Personal WhatsApp auto-reply agent that responds in your texting style when you're busy.

## Features

- **AI-Powered Replies**: Uses Claude (Sonnet/Haiku) for intelligent, contextual responses
- **Safety First**: Emergency detection, rate limiting, and conflict avoidance
- **Multilingual Support**: Naturally mixes languages (code-switching)
- **Smart Routing**: Classifies messages and routes to AI or templates
- **Time-Aware**: Respects allowed hours
- **Rate Limited**: Configurable hourly/daily limits
- **Transparent**: Logs all decisions for review

## Architecture

```
WhatsApp App → Go Bridge → MCP Server → Python Orchestrator → Claude API
```

## Prerequisites

- Python 3.10+
- [whatsapp-mcp](https://github.com/lharries/whatsapp-mcp) (WhatsApp bridge)
- [uv](https://github.com/astral-sh/uv) package manager
- Anthropic API key

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/yourusername/whatsapp-assistant.git
cd whatsapp-assistant

# Copy example configs
cp .env.example .env
cp config/config.example.yaml config/config.yaml
```

### 2. Configure

**Add your API key:**
```bash
nano .env
# Set: ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**Configure the assistant:**
```bash
nano config/config.yaml
# Set your target chat_id, timezone, etc.
```

**Customize the persona:**
```bash
nano config/prompts/reply_system.txt
# Update to match your texting style
```

### 3. Start WhatsApp Bridge

The WhatsApp MCP bridge must be running first. Follow the [whatsapp-mcp setup guide](https://github.com/lharries/whatsapp-mcp).

### 4. Test in Dry-Run Mode

```bash
# Test with dry-run (no actual messages sent)
DRY_RUN=true uv run --with anthropic --with mcp --with pyyaml --with python-dotenv --with pytz python3 src/main.py
```

### 5. Enable Auto-Reply

When ready to start auto-replying:

```bash
# Edit config
nano config/config.yaml
# Set: busy_mode: true
# Set: dry_run: false

# Or use toggle script
./scripts/toggle_busy.sh
```

### 6. Run as Service (Optional)

```bash
# Edit service file with your paths
nano whatsapp-assistant.service

# Install service
sudo cp whatsapp-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable whatsapp-assistant
sudo systemctl start whatsapp-assistant

# Check status
sudo systemctl status whatsapp-assistant
journalctl -u whatsapp-assistant -f
```

## Configuration

Edit `config/config.yaml`:

```yaml
# Core
wife_chat_id: "1234567890@s.whatsapp.net"  # Target chat JID
busy_mode: false       # Toggle to enable/disable
dry_run: true          # Test mode (no actual sends)
enable_auto_reply: true  # Master kill switch

# Hours
allowed_hours:
  start: "08:00"
  end: "23:00"
  timezone: "Asia/Kolkata"

# Rate Limits
rate_limiting:
  max_replies_per_hour: 10
  max_replies_per_day: 50

# Emergency Keywords
emergency_keywords:
  - "URGENT"
  - "EMERGENCY"
  - "CALL ME"
```

## How It Works

### Message Classification

1. **LOGISTICAL**: "When are you coming?", "Can you pick up milk?" → AI generates reply
2. **EMOTIONAL**: "Miss you", "Tired" → Uses safe template
3. **CONFLICT**: "You never have time" → Uses safe template

### Decision Priority

1. **Emergency keywords** → Immediate template + flag
2. **Outside hours** → Skip
3. **Busy mode OFF** → Log only
4. **Rate limit exceeded** → Skip
5. **Classify** → Route to AI or template

### Safety Rules

- ✅ **Auto-reply**: Logistics, schedules, simple requests
- ⚠️ **Template**: Emotional check-ins, feelings
- 🚫 **Template**: URGENT, CALL, EMERGENCY keywords
- 🚫 **Template**: Conflict, complaints

## Personalization

### Update Persona

Edit `config/prompts/reply_system.txt` to match your style:

- Add your common phrases
- Adjust language mixing ratio
- Update emoji preferences
- Add personal examples

### Update Templates

Edit `config/templates/*.yaml` to customize responses:

- `emotional.yaml` - For feelings/connection messages
- `conflict.yaml` - For disagreements/complaints
- `emergency.yaml` - For urgent keywords
- `media.yaml` - For voice notes, images, etc.

## File Structure

```
whatsapp-assistant/
├── src/
│   ├── main.py              # Orchestrator
│   ├── whatsapp_client.py   # MCP wrapper
│   ├── claude_client.py     # AI client
│   ├── router.py            # Decision engine
│   ├── rate_limiter.py      # Rate limiting
│   ├── state_manager.py     # Persistence
│   ├── config_loader.py     # Config validation
│   └── utils.py             # Helpers
├── config/
│   ├── config.yaml          # Main config (gitignored)
│   ├── config.example.yaml  # Template config
│   ├── prompts/             # AI prompts
│   └── templates/           # Response templates
├── data/                    # Runtime data (gitignored)
├── scripts/
│   ├── toggle_busy.sh       # Toggle busy mode
│   ├── check_health.sh      # Health check
│   ├── export_conversation.py  # Export for review
│   └── reveal_stats.py      # Generate statistics
└── whatsapp-assistant.service  # Systemd service template
```

## Commands Reference

```bash
# Manual run
uv run --with anthropic --with mcp --with pyyaml --with python-dotenv --with pytz python3 src/main.py

# Service management
sudo systemctl start whatsapp-assistant
sudo systemctl stop whatsapp-assistant
sudo systemctl restart whatsapp-assistant
sudo systemctl status whatsapp-assistant

# Logs
journalctl -u whatsapp-assistant -f

# Health check
./scripts/check_health.sh

# Toggle busy mode
./scripts/toggle_busy.sh
```

## Cost Estimate

**Anthropic API** (10 messages/day):
- Classification (Haiku): ~$0.0005/day
- Reply generation (Sonnet): ~$0.03/day
- **Total: ~$1/month**

## Safety Features

- **Emergency Detection**: Flags URGENT/CALL/EMERGENCY
- **Time Restrictions**: Only operates during allowed hours
- **Rate Limiting**: Configurable hourly/daily limits
- **Conflict Avoidance**: Uses safe templates for sensitive topics
- **Full Logging**: Every decision recorded
- **Local Storage**: All data stays on your machine

## Transparency

This tool is designed to be used **transparently**. Built-in tools help you review and share what was sent:

```bash
# Generate statistics
python3 scripts/reveal_stats.py

# Export conversation log
python3 scripts/export_conversation.py
```

## Troubleshooting

### Service won't start

```bash
journalctl -u whatsapp-assistant -n 50

# Common issues:
# 1. API key not set → Check .env file
# 2. WhatsApp bridge not running → Start the bridge first
# 3. Config error → Run: python3 src/config_loader.py
```

### Not sending replies

```bash
# Check:
# 1. Busy mode is ON
# 2. Within allowed hours
# 3. Rate limit not exceeded
# 4. Auto-reply enabled
./scripts/check_health.sh
```

## License

MIT License - Use responsibly and transparently.

---

**Remember**: This is a tool to help when you're genuinely busy, not a replacement for real communication. Use responsibly and with full transparency.
