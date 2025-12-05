#!/bin/bash
# Health check for WhatsApp Assistant

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "======================================"
echo "WhatsApp Assistant - Health Check"
echo "======================================"
echo ""

# Check if service is running
echo "1. Service Status:"
if systemctl is-active --quiet whatsapp-assistant; then
    echo "   ✅ Service is running"
    systemctl status whatsapp-assistant --no-pager | head -10
else
    echo "   ❌ Service is NOT running"
    echo "   Start with: sudo systemctl start whatsapp-assistant"
fi
echo ""

# Check configuration
echo "2. Configuration:"
CONFIG_FILE="$PROJECT_ROOT/config/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    echo "   ✅ Config file found"
    echo "   Busy mode: $(grep "^busy_mode:" "$CONFIG_FILE" | awk '{print $2}')"
    echo "   Auto-reply: $(grep "^enable_auto_reply:" "$CONFIG_FILE" | awk '{print $2}')"
    echo "   Dry run: $(grep "^dry_run:" "$CONFIG_FILE" | awk '{print $2}')"
else
    echo "   ❌ Config file not found"
    echo "   Copy config.example.yaml to config.yaml and customize"
fi
echo ""

# Check environment
echo "3. Environment:"
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    if grep -q "^ANTHROPIC_API_KEY=sk-ant-" "$ENV_FILE"; then
        echo "   ✅ ANTHROPIC_API_KEY is set"
    else
        echo "   ⚠️  ANTHROPIC_API_KEY may not be set correctly"
    fi
else
    echo "   ❌ .env file not found"
    echo "   Copy .env.example to .env and add your API key"
fi
echo ""

# Check state file
echo "4. State:"
STATE_FILE="$PROJECT_ROOT/data/state.json"
if [ -f "$STATE_FILE" ]; then
    echo "   ✅ State file exists"
    if command -v jq &> /dev/null; then
        echo "   Total replies sent: $(jq -r '.statistics.total_replies_sent // 0' "$STATE_FILE")"
        echo "   Total messages processed: $(jq -r '.statistics.total_messages_processed // 0' "$STATE_FILE")"
        echo "   Last updated: $(jq -r '.statistics.last_updated // "Never"' "$STATE_FILE")"
    else
        echo "   (Install jq for detailed stats)"
    fi
else
    echo "   ℹ️  No state file yet (will be created on first run)"
fi
echo ""

# Check WhatsApp bridge
echo "5. WhatsApp Bridge:"
if pgrep -f "whatsapp-bridge" > /dev/null; then
    echo "   ✅ WhatsApp bridge is running"
else
    echo "   ⚠️  WhatsApp bridge may not be running"
    echo "   Start your whatsapp-mcp bridge first"
fi
echo ""

# Check logs
echo "6. Recent Logs (last 10 lines):"
echo "   View full logs: journalctl -u whatsapp-assistant -f"
journalctl -u whatsapp-assistant -n 10 --no-pager 2>/dev/null || echo "   ℹ️  No logs yet or service not installed"
echo ""

echo "======================================"
echo "Useful Commands:"
echo "  Start:   sudo systemctl start whatsapp-assistant"
echo "  Stop:    sudo systemctl stop whatsapp-assistant"
echo "  Restart: sudo systemctl restart whatsapp-assistant"
echo "  Logs:    journalctl -u whatsapp-assistant -f"
echo "  Toggle:  ./scripts/toggle_busy.sh"
echo "======================================"
