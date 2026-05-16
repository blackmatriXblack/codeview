"""File system watcher for CodeView CLI.

Monitors directories for file changes using polling and optionally
notifications. Supports filtering by pattern and event type.
"""

import os
import time
import threading
from pathlib import Path
from typing import Callable, List, Optional, Set, Dict, Any
from datetime import datetime
from collections import defaultdict


class FileWatcher:
    """Cross-platform file system watcher using polling."""

    def __init__(
        self,
        directory: str = ".",
        patterns: Optional[List[str]] = None,
        recursive: bool = True,
        ignore_hidden: bool = True,
        poll_interval: float = 1.0,
    ):
        self.directory = Path(directory).resolve()
        self.patterns = patterns or ["*"]
        self.recursive = recursive
        self.ignore_hidden = ignore_hidden
        self.poll_interval = poll_interval
        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._snapshot: Dict[str, float] = {}
        self._watch_count = 0

    def on(self, event_type: str, callback: Callable) -> None:
        """Register a callback for an event type."""
        self._callbacks[event_type].append(callback)

    def on_created(self, callback: Callable) -> None:
        """Register a callback for file creation events."""
        self.on("created", callback)

    def on_modified(self, callback: Callable) -> None:
        """Register a callback for file modification events."""
        self.on("modified", callback)

    def on_deleted(self, callback: Callable) -> None:
        """Register a callback for file deletion events."""
        self.on("deleted", callback)

    def on_any(self, callback: Callable) -> None:
        """Register a callback for all event types."""
        for event_type in ("created", "modified", "deleted"):
            self.on(event_type, callback)

    def _should_watch(self, path: Path) -> bool:
        """Check if a file should be watched."""
        if self.ignore_hidden and path.name.startswith("."):
            return False
        if not self.recursive and path.parent != self.directory:
            return False
        for pattern in self.patterns:
            if path.match(pattern):
                return True
        return False

    def _scan(self) -> Dict[str, float]:
        """Scan the directory and return file modification times."""
        files: Dict[str, float] = {}
        try:
            iterator = self.directory.rglob("*") if self.recursive else self.directory.glob("*")
            for filepath in iterator:
                if filepath.is_file() and self._should_watch(filepath):
                    try:
                        files[str(filepath)] = filepath.stat().st_mtime
                    except OSError:
                        pass
        except OSError:
            pass
        return files

    def _emit(self, event_type: str, filepath: str) -> None:
        """Emit an event to registered callbacks."""
        for callback in self._callbacks.get(event_type, []):
            try:
                callback(event_type, filepath)
            except Exception:
                pass

    def _poll_loop(self) -> None:
        """Main polling loop (runs in a background thread)."""
        self._snapshot = self._scan()
        while self._running:
            time.sleep(self.poll_interval)
            try:
                current = self._scan()
                current_set = set(current.keys())
                snapshot_set = set(self._snapshot.keys())
                created = current_set - snapshot_set
                deleted = snapshot_set - current_set
                for filepath in created:
                    self._emit("created", filepath)
                for filepath in deleted:
                    self._emit("deleted", filepath)
                for filepath in current_set & snapshot_set:
                    if current[filepath] != self._snapshot[filepath]:
                        self._emit("modified", filepath)
                self._snapshot = current
            except Exception:
                pass

    def start(self) -> None:
        """Start watching for file changes."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop watching for file changes."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._running

    def get_snapshot(self) -> Dict[str, float]:
        """Get the current file snapshot."""
        return dict(self._snapshot)

    def get_file_info(self, filepath: str) -> Dict[str, Any]:
        """Get detailed information about a watched file."""
        path = Path(filepath)
        if not path.exists():
            return {"exists": False}
        try:
            stat = path.stat()
            return {
                "exists": True,
                "path": str(path),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            }
        except OSError:
            return {"exists": False, "path": str(path)}


def watch_directory(
    directory: str,
    on_change: Optional[Callable] = None,
    patterns: Optional[List[str]] = None,
    duration: Optional[float] = None,
    poll_interval: float = 1.0,
) -> int:
    """Convenience function to watch a directory synchronously.

    Args:
        directory: Path to watch
        on_change: Callback called with (event_type, filepath)
        patterns: File patterns to watch
        duration: How long to watch in seconds (None = until KeyboardInterrupt)
        poll_interval: Seconds between scans

    Returns:
        Number of events detected
    """
    watcher = FileWatcher(
        directory=directory,
        patterns=patterns,
        poll_interval=poll_interval,
    )
    event_count = 0

    def _count(event_type: str, filepath: str) -> None:
        nonlocal event_count
        event_count += 1
        if on_change:
            on_change(event_type, filepath)

    watcher.on_any(_count)
    watcher.start()

    try:
        if duration is not None:
            time.sleep(duration)
        else:
            print(f"Watching {directory} for changes... Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        watcher.stop()

    return event_count
