#!/bin/bash
# Toggle busy mode on/off for WhatsApp Assistant

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_ROOT/config/config.yaml"

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Config file not found: $CONFIG_FILE"
    exit 1
fi

# Get current busy mode status
current_status=$(grep "^busy_mode:" "$CONFIG_FILE" | awk '{print $2}')

# Toggle
if [ "$current_status" == "true" ]; then
    new_status="false"
    echo "📴 Turning busy mode OFF"
else
    new_status="true"
    echo "📲 Turning busy mode ON"
fi

# Update config
sed -i "s/^busy_mode: .*/busy_mode: $new_status/" "$CONFIG_FILE"

echo "✅ Busy mode is now: $new_status"
echo ""
echo "Restart the service for changes to take effect:"
echo "  sudo systemctl restart whatsapp-assistant"
