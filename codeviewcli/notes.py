"""Quick notes manager for CodeView CLI.

Lightweight note-taking system that stores notes as markdown files
with tags, timestamps, and searchable metadata.
"""

import json
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime

from .config import get_config_dir


NOTES_DIR_NAME = "notes"
INDEX_FILE = "index.json"


def get_notes_dir() -> Path:
    """Get path to the notes directory."""
    notes_dir = get_config_dir() / NOTES_DIR_NAME
    notes_dir.mkdir(parents=True, exist_ok=True)
    return notes_dir


def get_index_file() -> Path:
    """Get path to the notes index file."""
    return get_notes_dir() / INDEX_FILE


def _load_index() -> List[Dict[str, Any]]:
    """Load the notes index."""
    index_file = get_index_file()
    if index_file.exists():
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def _save_index(data: List[Dict[str, Any]]) -> None:
    """Save the notes index."""
    index_file = get_index_file()
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _sanitize_filename(name: str) -> str:
    """Create a safe filename from a note title."""
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    safe = re.sub(r'\s+', '_', safe.strip())
    safe = re.sub(r'_+', '_', safe)
    return safe[:100] or "untitled"


def create_note(title: str, content: str = "", tags: Optional[List[str]] = None) -> Dict[str, Any]:
    """Create a new note. Returns the note metadata."""
    notes_dir = get_notes_dir()
    safe_name = _sanitize_filename(title)
    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{safe_name}.md"
    filepath = notes_dir / filename
    full_content = f"# {title}\n\n{content}\n"
    filepath.write_text(full_content, encoding="utf-8")
    note = {
        "id": timestamp,
        "title": title,
        "filename": filename,
        "tags": tags or [],
        "created": now.isoformat(),
        "modified": now.isoformat(),
        "size": len(full_content),
    }
    index = _load_index()
    index.insert(0, note)
    _save_index(index)
    return note


def get_note(note_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific note by ID."""
    index = _load_index()
    for note in index:
        if note["id"] == note_id:
            content = _read_note_content(note["filename"])
            note["content"] = content
            return note
    return None


def _read_note_content(filename: str) -> str:
    """Read the content of a note file."""
    filepath = get_notes_dir() / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


def list_notes(tag: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """List notes, optionally filtered by tag."""
    index = _load_index()
    if tag:
        index = [n for n in index if tag in n.get("tags", [])]
    return index[:limit]


def update_note(note_id: str, title: Optional[str] = None,
                content: Optional[str] = None,
                tags: Optional[List[str]] = None) -> bool:
    """Update an existing note. Returns True if successful."""
    index = _load_index()
    for note in index:
        if note["id"] == note_id:
            if title is not None:
                note["title"] = title
            if tags is not None:
                note["tags"] = tags
            if content is not None:
                note["modified"] = datetime.now().isoformat()
                filepath = get_notes_dir() / note["filename"]
                full = f"# {note['title']}\n\n{content}\n"
                filepath.write_text(full, encoding="utf-8")
                note["size"] = len(full)
            _save_index(index)
            return True
    return False


def delete_note(note_id: str) -> bool:
    """Delete a note. Returns True if found and deleted."""
    index = _load_index()
    for i, note in enumerate(index):
        if note["id"] == note_id:
            filepath = get_notes_dir() / note["filename"]
            if filepath.exists():
                filepath.unlink()
            index.pop(i)
            _save_index(index)
            return True
    return False


def search_notes(query: str) -> List[Dict[str, Any]]:
    """Search notes by title or content."""
    query_lower = query.lower()
    index = _load_index()
    results = []
    for note in index:
        title_match = query_lower in note["title"].lower()
        tag_match = any(query_lower in t.lower() for t in note.get("tags", []))
        content = _read_note_content(note["filename"])
        content_match = query_lower in content.lower()
        if title_match or content_match or tag_match:
            note["content"] = content
            results.append(note)
    return results


def get_all_tags() -> List[str]:
    """Get all unique tags used across notes."""
    index = _load_index()
    tags = set()
    for note in index:
        for tag in note.get("tags", []):
            tags.add(tag)
    return sorted(tags)
