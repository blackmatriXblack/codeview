"""File operations module for CodeView CLI.

Handles reading, writing, listing, and searching files on the local filesystem.
"""

import os
import glob as glob_module
from pathlib import Path
from typing import List, Tuple, Optional, Iterator
from datetime import datetime

import pathspec


def read_file(filepath: str, encoding: str = "utf-8") -> str:
    """Read a file from the filesystem and return its content."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    if not path.is_file():
        raise IsADirectoryError(f"Path is a directory: {filepath}")
    return path.read_text(encoding=encoding)


def read_file_with_info(filepath: str) -> Tuple[str, str, int, float]:
    """Read a file and return (content, encoding, size_bytes, modified_time)."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    content = path.read_text(encoding="utf-8")
    stat = path.stat()
    return content, "utf-8", stat.st_size, stat.st_mtime


def write_file(filepath: str, content: str, encoding: str = "utf-8") -> None:
    """Write content to a file, creating parent directories if needed."""
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)


def list_files(
    directory: str = ".",
    pattern: str = "*",
    recursive: bool = False,
    respect_gitignore: bool = True,
    max_depth: Optional[int] = None,
) -> List[str]:
    """List files in a directory, optionally recursively."""
    base = Path(directory).resolve()
    if not base.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    files = []
    gitignore_spec = None

    if respect_gitignore:
        gitignore_path = base / ".gitignore"
        if gitignore_path.exists():
            lines = gitignore_path.read_text(encoding="utf-8").splitlines()
            gitignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", lines)

    glob_pattern = f"**/{pattern}" if recursive else pattern
    for filepath in base.glob(glob_pattern):
        if filepath.is_file():
            rel_path = str(filepath.relative_to(base))
            if gitignore_spec and gitignore_spec.match_file(rel_path):
                continue
            files.append(rel_path)

    return sorted(files)


def list_files_with_details(
    directory: str = ".",
    pattern: str = "*",
    recursive: bool = False,
) -> List[dict]:
    """List files with details (size, modified time, etc.)."""
    base = Path(directory).resolve()
    if not base.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    results = []
    glob_pattern = f"**/{pattern}" if recursive else pattern

    for filepath in base.glob(glob_pattern):
        if filepath.is_file():
            stat = filepath.stat()
            rel_path = str(filepath.relative_to(base))
            results.append({
                "path": rel_path,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_binary": _is_binary(str(filepath)),
                "extension": filepath.suffix.lower(),
            })

    return sorted(results, key=lambda x: x["path"])


def search_files(
    directory: str = ".",
    query: str = "",
    file_pattern: str = "*",
    recursive: bool = True,
    case_sensitive: bool = False,
) -> List[Tuple[str, int, str]]:
    """Search for text in files. Returns list of (filepath, line_number, line_content)."""
    base = Path(directory).resolve()
    if not base.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    results = []
    search_query = query if case_sensitive else query.lower()
    glob_pattern = f"**/{file_pattern}" if recursive else file_pattern

    for filepath in base.glob(glob_pattern):
        if not filepath.is_file():
            continue
        if _is_binary(str(filepath)):
            continue
        try:
            content = filepath.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                line_to_check = line if case_sensitive else line.lower()
                if search_query in line_to_check:
                    rel_path = str(filepath.relative_to(base))
                    results.append((rel_path, i, line[:200]))
        except (UnicodeDecodeError, PermissionError):
            continue

    return results


def get_file_stats(filepath: str) -> dict:
    """Get detailed stats about a file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "name": path.name,
        "extension": path.suffix,
        "size_bytes": stat.st_size,
        "size_human": _format_size(stat.st_size),
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "accessed": datetime.fromtimestamp(stat.st_atime).isoformat(),
        "is_binary": _is_binary(str(path)),
        "parent_dir": str(path.parent),
    }


def tree_view(
    directory: str = ".",
    max_depth: int = 3,
    show_hidden: bool = False,
    dirs_only: bool = False,
) -> str:
    """Generate an ASCII tree view of a directory."""
    base = Path(directory).resolve()
    if not base.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    lines = [str(base.name)]

    def _build_tree(current: Path, prefix: str = "", depth: int = 0) -> List[str]:
        if max_depth is not None and depth >= max_depth:
            return []

        entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        result = []

        for i, entry in enumerate(entries):
            if not show_hidden and entry.name.startswith("."):
                continue
            if dirs_only and not entry.is_dir():
                continue

            is_last = i == len(entries) - 1
            connector = "+-- " if is_last else "|-- "
            result.append(f"{prefix}{connector}{entry.name}")
 
            if entry.is_dir():
                extension = "    " if is_last else "|   "
                result.extend(_build_tree(entry, prefix + extension, depth + 1))

        return result

    lines.extend(_build_tree(base))
    return "\n".join(lines)


def _is_binary(filepath: str) -> bool:
    """Check if a file is binary."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
        return False
    except Exception:
        return True


def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
