"""File history tracking for CodeView CLI.

Tracks recently opened/edited files with timestamps and metadata.
Supports searching, clearing, and managing history entries.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta

from .config import get_config_dir


MAX_HISTORY = 500


def get_history_file() -> Path:
    """Get path to the history JSON file."""
    return get_config_dir() / "history.json"


def _load() -> List[Dict[str, Any]]:
    """Load history entries."""
    history_file = get_history_file()
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, IOError):
            pass
    return []


def _save(data: List[Dict[str, Any]]) -> None:
    """Save history entries."""
    history_file = get_history_file()
    history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(data[-MAX_HISTORY:], f, indent=2, ensure_ascii=False)


def add_to_history(filepath: str, language: str = "", lines: int = 0) -> None:
    """Add a file to the open history."""
    data = _load()
    resolved = str(Path(filepath).resolve())
    now = datetime.now().isoformat()
    data = [e for e in data if e.get("path") != resolved]
    data.append({
        "path": resolved,
        "name": Path(filepath).name,
        "language": language,
        "lines": lines,
        "timestamp": now,
    })
    _save(data)


def get_history(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    """Get recent file history entries, most recent first."""
    data = _load()
    data.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return data[offset:offset + limit]


def search_history(query: str) -> List[Dict[str, Any]]:
    """Search history entries by filename or path."""
    data = _load()
    query_lower = query.lower()
    results = []
    for entry in data:
        name = entry.get("name", "").lower()
        path_str = entry.get("path", "").lower()
        if query_lower in name or query_lower in path_str:
            results.append(entry)
    results.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return results


def clear_history() -> int:
    """Clear all history. Returns number of entries removed."""
    data = _load()
    count = len(data)
    _save([])
    return count


def remove_from_history(filepath: str) -> bool:
    """Remove a specific entry from history."""
    resolved = str(Path(filepath).resolve())
    data = _load()
    before = len(data)
    data = [e for e in data if e.get("path") != resolved]
    _save(data)
    return len(data) < before


def get_stats() -> Dict[str, Any]:
    """Get history statistics."""
    data = _load()
    if not data:
        return {"total": 0, "unique_files": 0, "languages": {}}
    languages = {}
    paths = set()
    for entry in data:
        lang = entry.get("language", "unknown")
        languages[lang] = languages.get(lang, 0) + 1
        paths.add(entry.get("path", ""))
    return {
        "total": len(data),
        "unique_files": len(paths),
        "languages": dict(sorted(languages.items(), key=lambda x: x[1], reverse=True)),
    }


def get_most_opened(limit: int = 10) -> List[Dict[str, Any]]:
    """Get most frequently opened files."""
    data = _load()
    counts = {}
    for entry in data:
        path = entry.get("path", "")
        if path not in counts:
            counts[path] = {"count": 0, "name": entry.get("name", ""), "language": entry.get("language", "")}
        counts[path]["count"] += 1
    ranked = sorted(counts.items(), key=lambda x: x[1]["count"], reverse=True)
    return [{"path": path, **info} for path, info in ranked[:limit]]
