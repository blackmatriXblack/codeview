"""Configuration management for CodeView CLI."""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any


DEFAULT_CONFIG = {
    "theme": "monokai",
    "line_numbers": True,
    "true_color": True,
    "editor_command": "",
    "tab_size": 4,
    "wrap_lines": False,
    "pager": "auto",
    "respect_gitignore": True,
    "max_file_size_mb": 50,
    "fetch_timeout_seconds": 30,
    "history_file": "~/.codeview_history",
    "default_language": "text",
    "highlight_line": None,
}


def get_config_dir() -> Path:
    """Get the CodeView CLI config directory."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    config_dir = base / "codeviewcli"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_file() -> Path:
    """Get the path to the config file."""
    return get_config_dir() / "config.json"


def load_config() -> Dict[str, Any]:
    """Load configuration from file, merging with defaults."""
    config = dict(DEFAULT_CONFIG)
    config_file = get_config_file()

    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            config.update(user_config)
        except (json.JSONDecodeError, IOError):
            pass

    return config


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    config_file = get_config_file()
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_setting(key: str) -> Any:
    """Get a specific configuration value."""
    config = load_config()
    return config.get(key, DEFAULT_CONFIG.get(key))


def set_setting(key: str, value: Any) -> None:
    """Set a specific configuration value."""
    config = load_config()
    config[key] = value
    save_config(config)


def reset_config() -> None:
    """Reset configuration to defaults."""
    save_config(dict(DEFAULT_CONFIG))


def export_config() -> str:
    """Export the current configuration as JSON string."""
    config = load_config()
    return json.dumps(config, indent=2)
