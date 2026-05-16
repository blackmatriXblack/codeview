"""Project management for CodeView CLI.

Provides project initialization, configuration, and metadata management.
Supports .codeviewcli.yml project files with language settings, ignore patterns,
and custom commands.
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime


PROJECT_CONFIG_FILE = ".codeviewcli.yml"
PROJECT_CONFIG_JSON = ".codeviewcli.json"


DEFAULT_PROJECT_CONFIG = {
    "name": "",
    "description": "",
    "version": "1.0.0",
    "language": "",
    "source_dir": "src",
    "test_dir": "tests",
    "build_dir": "build",
    "ignore": [
        "__pycache__",
        "*.pyc",
        ".git",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "dist",
        "*.egg-info",
    ],
    "editor": {
        "tab_size": 4,
        "use_spaces": True,
        "line_numbers": True,
        "word_wrap": False,
        "theme": "",
    },
    "commands": {},
    "created": "",
    "modified": "",
}


def _load_yaml(filepath: Path) -> Dict[str, Any]:
    """Load a YAML file. Falls back to JSON if file is .json."""
    try:
        import yaml
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        if filepath.suffix == ".json":
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}


def _save_yaml(filepath: Path, data: Dict[str, Any]) -> None:
    """Save data to a YAML file."""
    try:
        import yaml
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        filepath = filepath.with_suffix(".json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def find_project_root(start_path: str = ".") -> Optional[Path]:
    """Find the project root directory by searching for config files."""
    current = Path(start_path).resolve()
    while True:
        for cfg in [PROJECT_CONFIG_FILE, PROJECT_CONFIG_JSON, ".git", ".hg", ".svn"]:
            if (current / cfg).exists():
                return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def get_project_config(project_dir: str = ".") -> Optional[Dict[str, Any]]:
    """Get the project configuration from a directory."""
    root = find_project_root(project_dir)
    if root is None:
        return None
    for cfg_name in [PROJECT_CONFIG_FILE, PROJECT_CONFIG_JSON]:
        cfg_path = root / cfg_name
        if cfg_path.exists():
            config = _load_yaml(cfg_path)
            config["_project_root"] = str(root)
            return config
    git_dir = root / ".git"
    if git_dir.exists():
        return {
            "_project_root": str(root),
            "name": root.name,
            "version": "0.1.0",
        }
    return None


def init_project(
    directory: str = ".",
    name: str = "",
    language: str = "",
    force: bool = False,
) -> Dict[str, Any]:
    """Initialize a new project with a .codeviewcli.yml file.

    Args:
        directory: Project directory
        name: Project name (defaults to directory name)
        language: Primary programming language
        force: Overwrite existing config

    Returns:
        The created project config
    """
    project_dir = Path(directory).resolve()
    config_path = project_dir / PROJECT_CONFIG_FILE

    if config_path.exists() and not force:
        existing = _load_yaml(config_path)
        existing["_project_root"] = str(project_dir)
        return existing

    project_dir.mkdir(parents=True, exist_ok=True)

    config = dict(DEFAULT_PROJECT_CONFIG)
    config["name"] = name or project_dir.name
    config["language"] = language
    config["created"] = datetime.now().isoformat()
    config["modified"] = datetime.now().isoformat()

    _save_yaml(config_path, config)
    config["_project_root"] = str(project_dir)
    return config


def update_project_config(directory: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update the project configuration."""
    root = find_project_root(directory)
    if root is None:
        raise FileNotFoundError("No project found. Use 'codeview init' first.")

    config_path = root / PROJECT_CONFIG_FILE
    if not config_path.exists():
        config_path = root / PROJECT_CONFIG_JSON

    config = _load_yaml(config_path) if config_path.exists() else dict(DEFAULT_PROJECT_CONFIG)
    config.update(updates)
    config["modified"] = datetime.now().isoformat()

    _save_yaml(root / PROJECT_CONFIG_FILE, config)
    config["_project_root"] = str(root)
    return config


def get_project_stats(directory: str = ".") -> Dict[str, Any]:
    """Get statistics for a project directory."""
    root = find_project_root(directory) or Path(directory).resolve()
    total_files = 0
    total_dirs = 0
    total_size = 0
    extensions: Dict[str, int] = {}
    for item in root.rglob("*"):
        if item.is_file():
            try:
                size = item.stat().st_size
                total_files += 1
                total_size += size
                ext = item.suffix.lower() or "(none)"
                extensions[ext] = extensions.get(ext, 0) + 1
            except OSError:
                pass
        elif item.is_dir():
            total_dirs += 1
    return {
        "root": str(root),
        "name": root.name,
        "total_files": total_files,
        "total_dirs": total_dirs,
        "total_size": total_size,
        "extensions": dict(sorted(extensions.items(), key=lambda x: x[1], reverse=True)[:20]),
    }
