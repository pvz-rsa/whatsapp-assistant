#!/usr/bin/env python3
"""
Configuration loader and validator for WhatsApp Assistant
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import pytz


class ConfigError(Exception):
    """Raised when configuration is invalid"""
    pass


class Config:
    """Configuration container with validation"""

    def __init__(self, config_dict: Dict[str, Any]):
        self.raw = config_dict
        self._validate()

    def _validate(self):
        """Validate configuration structure and values"""

        # Required fields
        required = ["wife_chat_id", "anthropic_api_key_env"]
        for field in required:
            if field not in self.raw:
                raise ConfigError(f"Missing required field: {field}")

        # Validate chat_id format
        chat_id = self.raw["wife_chat_id"]
        if not chat_id.endswith("@s.whatsapp.net"):
            raise ConfigError(f"Invalid chat_id format: {chat_id}")

        # Validate timezone
        tz_name = self.raw.get("allowed_hours", {}).get("timezone", "Asia/Kolkata")
        try:
            pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            raise ConfigError(f"Invalid timezone: {tz_name}")

        # Validate rate limits
        rate_limits = self.raw.get("rate_limiting", {})
        if rate_limits.get("max_replies_per_hour", 0) <= 0:
            raise ConfigError("max_replies_per_hour must be positive")
        if rate_limits.get("max_replies_per_day", 0) <= 0:
            raise ConfigError("max_replies_per_day must be positive")

        # Validate polling interval
        if self.raw.get("polling_interval_seconds", 0) < 10:
            raise ConfigError("polling_interval_seconds must be >= 10")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot notation support"""
        keys = key.split(".")
        value = self.raw
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value

    @property
    def wife_chat_id(self) -> str:
        return self.raw["wife_chat_id"]

    @property
    def enable_auto_reply(self) -> bool:
        return self.raw.get("enable_auto_reply", True)

    @property
    def busy_mode(self) -> bool:
        """Can be overridden by BUSY_MODE env var"""
        env_override = os.getenv("BUSY_MODE")
        if env_override is not None:
            return env_override.lower() in ("true", "1", "yes")
        return self.raw.get("busy_mode", False)

    @property
    def dry_run(self) -> bool:
        """Can be overridden by DRY_RUN env var"""
        env_override = os.getenv("DRY_RUN")
        if env_override is not None:
            return env_override.lower() in ("true", "1", "yes")
        return self.raw.get("dry_run", False)

    @property
    def anthropic_api_key(self) -> str:
        """Get API key from environment"""
        key_env_name = self.raw.get("anthropic_api_key_env", "ANTHROPIC_API_KEY")
        key = os.getenv(key_env_name)
        if not key:
            raise ConfigError(f"Environment variable {key_env_name} not set")
        if key == "sk-ant-your-key-here":
            raise ConfigError("Please set a valid ANTHROPIC_API_KEY in .env")
        return key

    @property
    def emergency_keywords(self) -> list[str]:
        """Get emergency keywords (case-insensitive)"""
        keywords = self.raw.get("emergency_keywords", [])
        return [k.lower() for k in keywords]

    @property
    def timezone(self) -> pytz.tzinfo.BaseTzInfo:
        """Get timezone object"""
        tz_name = self.get("allowed_hours.timezone", "Asia/Kolkata")
        return pytz.timezone(tz_name)


def load_config(config_path: Optional[Path] = None) -> Config:
    """
    Load and validate configuration from YAML file

    Args:
        config_path: Path to config.yaml (defaults to ../config/config.yaml relative to this file)

    Returns:
        Config object

    Raises:
        ConfigError: If configuration is invalid
    """
    # Load environment variables from .env
    project_root = Path(__file__).parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Default config path
    if config_path is None:
        config_path = project_root / "config" / "config.yaml"

    # Load YAML
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}")

    if not isinstance(config_dict, dict):
        raise ConfigError("Config file must contain a YAML dictionary")

    return Config(config_dict)


def main():
    """Test configuration loading"""
    try:
        config = load_config()
        print("✅ Configuration loaded successfully!")
        print(f"\nWife's chat ID: {config.wife_chat_id}")
        print(f"Auto-reply enabled: {config.enable_auto_reply}")
        print(f"Busy mode: {config.busy_mode}")
        print(f"Dry run: {config.dry_run}")
        print(f"Timezone: {config.timezone}")
        print(f"Polling interval: {config.get('polling_interval_seconds')}s")
        print(f"Rate limits: {config.get('rate_limiting.max_replies_per_hour')}/hour, {config.get('rate_limiting.max_replies_per_day')}/day")
        print(f"Emergency keywords: {', '.join(config.emergency_keywords[:3])}...")

        # Test API key (without printing it)
        try:
            key = config.anthropic_api_key
            print(f"API key: {'*' * 20}{key[-8:]}")
        except ConfigError as e:
            print(f"⚠️  API key: {e}")

    except ConfigError as e:
        print(f"❌ Configuration error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
