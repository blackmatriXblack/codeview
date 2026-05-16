"""Advanced curses-based code editor for CodeView CLI.

A full-featured terminal code editor with syntax highlighting, multi-tab,
split panes, command palette, find/replace, git integration, and more.

Uses curses for low-level terminal control with Pygments for syntax highlighting.
"""

import os
import sys
import re
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum, auto

try:
    import curses
    import curses.ascii
    import curses.textpad
except ImportError:
    print("Error: curses is not available. Install 'windows-curses' on Windows.")
    print("  pip install windows-curses")
    sys.exit(1)

from pygments import highlight
from pygments.lexers import (
    get_lexer_for_filename,
    get_lexer_by_name,
    guess_lexer,
    PythonLexer,
)
from pygments.token import Token, is_token_subtype
from pygments.util import ClassNotFound

from .highlighter import detect_language
from .config import load_config, get_setting
from .fileops import read_file, write_file, list_files
from .history import add_to_history


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

MAX_TABS = 20
TAB_MAX_WIDTH = 30
MINIMAP_WIDTH = 10
MIN_EDITOR_WIDTH = 20
SIDEBAR_WIDTH = 30
SCROLL_OFF = 4


class EditorMode(Enum):
    NORMAL = auto()
    INSERT = auto()
    VISUAL = auto()
    COMMAND = auto()
    SEARCH = auto()


# ──────────────────────────────────────────────
# Syntax highlighting
# ──────────────────────────────────────────────

def get_token_color(token_type, theme="dark") -> int:
    """Map a Pygments token type to a curses color pair index."""
    if theme == "dark":
        if is_token_subtype(token_type, Token.Keyword) or \
           is_token_subtype(token_type, Token.Keyword.Constant):
            return 1
        elif is_token_subtype(token_type, Token.Name.Function) or \
             is_token_subtype(token_type, Token.Name.Class):
            return 2
        elif is_token_subtype(token_type, Token.Literal.String) or \
             is_token_subtype(token_type, Token.Literal.String.Single) or \
             is_token_subtype(token_type, Token.Literal.String.Double):
            return 3
        elif is_token_subtype(token_type, Token.Comment) or \
             is_token_subtype(token_type, Token.Comment.Single) or \
             is_token_subtype(token_type, Token.Comment.Multiline):
            return 4
        elif is_token_subtype(token_type, Token.Literal.Number) or \
             is_token_subtype(token_type, Token.Literal.Number.Integer) or \
             is_token_subtype(token_type, Token.Literal.Number.Float):
            return 5
        elif is_token_subtype(token_type, Token.Name.Decorator):
            return 6
        elif is_token_subtype(token_type, Token.Operator) or \
             is_token_subtype(token_type, Token.Punctuation):
            return 7
        elif is_token_subtype(token_type, Token.Name.Builtin):
            return 8
        elif is_token_subtype(token_type, Token.Name.Namespace):
            return 9
        else:
            return 0
    else:
        return 0


def init_colors():
    """Initialize curses color pairs for syntax highlighting."""
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    try:
        curses.init_pair(0, curses.COLOR_WHITE, -1)
        curses.init_pair(1, curses.COLOR_MAGENTA, -1)
        curses.init_pair(2, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
        curses.init_pair(4, curses.COLOR_BLUE, -1)
        curses.init_pair(5, curses.COLOR_RED, -1)
        curses.init_pair(6, curses.COLOR_YELLOW, -1)
        curses.init_pair(7, curses.COLOR_WHITE, -1)
        curses.init_pair(8, curses.COLOR_MAGENTA, -1)
        curses.init_pair(9, curses.COLOR_BLUE, -1)
        curses.init_pair(10, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(11, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(12, curses.COLOR_YELLOW, curses.COLOR_BLUE)
        curses.init_pair(13, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(14, curses.COLOR_BLACK, curses.COLOR_RED)
        curses.init_pair(15, curses.COLOR_BLACK, curses.COLOR_YELLOW)
        curses.init_pair(16, curses.COLOR_GREEN, -1)
        curses.init_pair(17, curses.COLOR_RED, -1)
        curses.init_pair(18, curses.COLOR_CYAN, -1)
    except Exception:
        pass


COLOR_KEYWORD = 1
COLOR_FUNC = 2
COLOR_STRING = 3
COLOR_COMMENT = 4
COLOR_NUMBER = 5
COLOR_DECORATOR = 6
COLOR_OPERATOR = 7
COLOR_BUILTIN = 8
COLOR_NAMESPACE = 9
COLOR_SELECTION = 10
COLOR_STATUSBAR = 11
COLOR_LINENUM = 12
COLOR_GIT_ADDED = 13
COLOR_GIT_REMOVED = 14
COLOR_GIT_MODIFIED = 15
COLOR_MATCH = 16
COLOR_ERROR = 17
COLOR_INFO = 18


# ──────────────────────────────────────────────
# Text Buffer
# ──────────────────────────────────────────────

@dataclass
class BufferState:
    """Snapshot of buffer state for undo/redo."""
    lines: List[str]
    cursor_row: int
    cursor_col: int


class TextBuffer:
    """Text buffer with undo/redo support."""

    def __init__(self, text: str = ""):
        self.lines: List[str] = text.split("\n") if text else [""]
        self._undo_stack: List[BufferState] = []
        self._redo_stack: List[BufferState] = []
        self._save_state()
        self._modified = False
        self._max_undo = 500

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @text.setter
    def text(self, value: str):
        self.lines = value.split("\n") if value else [""]
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._save_state()
        self._modified = True

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def modified(self) -> bool:
        return self._modified

    def set_modified(self, val: bool):
        self._modified = val

    def get_line(self, row: int) -> str:
        if 0 <= row < len(self.lines):
            return self.lines[row]
        return ""

    def insert_char(self, row: int, col: int, char: str) -> None:
        if row >= len(self.lines):
            return
        line = self.lines[row]
        col = min(col, len(line))
        self.lines[row] = line[:col] + char + line[col:]
        self._modified = True

    def delete_char(self, row: int, col: int) -> Optional[str]:
        if row >= len(self.lines):
            return None
        line = self.lines[row]
        if col > 0 and col <= len(line):
            deleted = line[col - 1]
            self.lines[row] = line[:col - 1] + line[col:]
            self._modified = True
            return deleted
        elif col == 0 and row > 0:
            prev_line = self.lines[row - 1]
            deleted = "\n"
            self.lines[row - 1] = prev_line + line
            self.lines.pop(row)
            self._modified = True
            return deleted
        return None

    def delete_forward(self, row: int, col: int) -> Optional[str]:
        if row >= len(self.lines):
            return None
        line = self.lines[row]
        if col < len(line):
            deleted = line[col]
            self.lines[row] = line[:col] + line[col + 1:]
            self._modified = True
            return deleted
        elif row < len(self.lines) - 1:
            deleted = "\n"
            self.lines[row] = line + self.lines[row + 1]
            self.lines.pop(row + 1)
            self._modified = True
            return deleted
        return None

    def insert_line(self, row: int, col: int) -> None:
        if row >= len(self.lines):
            self.lines.append("")
            self._modified = True
            return
        line = self.lines[row]
        self.lines[row] = line[:col]
        self.lines.insert(row + 1, line[col:])
        self._modified = True

    def delete_line(self, row: int) -> Optional[str]:
        if 0 <= row < len(self.lines):
            deleted = self.lines.pop(row)
            if not self.lines:
                self.lines = [""]
            self._modified = True
            return deleted
        return None

    def insert_text(self, row: int, col: int, text: str) -> None:
        text_lines = text.split("\n")
        if row >= len(self.lines):
            return
        line = self.lines[row]
        if len(text_lines) == 1:
            self.lines[row] = line[:col] + text + line[col:]
        else:
            self.lines[row] = line[:col] + text_lines[0]
            for i, tl in enumerate(text_lines[1:-1], 1):
                self.lines.insert(row + i, tl)
            last_line = text_lines[-1] + line[col:]
            self.lines.insert(row + len(text_lines) - 1, last_line)
        self._modified = True

    def get_text_range(self, start_row: int, start_col: int,
                       end_row: int, end_col: int) -> str:
        if start_row == end_row:
            return self.lines[start_row][start_col:end_col]
        parts = [self.lines[start_row][start_col:]]
        for r in range(start_row + 1, end_row):
            parts.append(self.lines[r])
        parts.append(self.lines[end_row][:end_col])
        return "\n".join(parts)

    def delete_range(self, start_row: int, start_col: int,
                     end_row: int, end_col: int) -> str:
        text = self.get_text_range(start_row, start_col, end_row, end_col)
        if start_row == end_row:
            line = self.lines[start_row]
            self.lines[start_row] = line[:start_col] + line[end_col:]
        else:
            self.lines[start_row] = self.lines[start_row][:start_col] + \
                                     self.lines[end_row][end_col:]
            del self.lines[start_row + 1:end_row + 1]
        if not self.lines:
            self.lines = [""]
        self._modified = True
        return text

    def _save_state(self, cursor_row: int = 0, cursor_col: int = 0):
        state = BufferState(
            lines=list(self.lines),
            cursor_row=cursor_row,
            cursor_col=cursor_col,
        )
        self._undo_stack.append(state)
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def save_undo_state(self, cursor_row: int = 0, cursor_col: int = 0):
        self._save_state(cursor_row, cursor_col)

    def undo(self) -> Optional[BufferState]:
        if len(self._undo_stack) <= 1:
            return None
        current = self._undo_stack.pop()
        self._redo_stack.append(current)
        prev = self._undo_stack[-1]
        self.lines = list(prev.lines)
        self._modified = True
        return prev

    def redo(self) -> Optional[BufferState]:
        if not self._redo_stack:
            return None
        state = self._redo_stack.pop()
        self._undo_stack.append(state)
        self.lines = list(state.lines)
        self._modified = True
        return state

    def find(self, query: str, start_row: int = 0, start_col: int = 0,
             case_sensitive: bool = True) -> Optional[Tuple[int, int, int, int]]:
        """Find text. Returns (start_row, start_col, end_row, end_col)."""
        if not query:
            return None
        search = query if case_sensitive else query.lower()
        for r in range(start_row, len(self.lines)):
            line = self.lines[r] if case_sensitive else self.lines[r].lower()
            sc = start_col if r == start_row else 0
            idx = line.find(search, sc)
            if idx != -1:
                return (r, idx, r, idx + len(query))
        for r in range(0, start_row):
            line = self.lines[r] if case_sensitive else self.lines[r].lower()
            ec = start_col if r == start_row else len(line)
            idx = line.find(search, 0, ec if r == start_row else len(line))
            if idx != -1:
                return (r, idx, r, idx + len(query))
        return None

    def replace(self, old: str, new: str, start_row: int = 0,
                start_col: int = 0, case_sensitive: bool = True) -> int:
        """Replace all occurrences. Returns count."""
        count = 0
        for r in range(start_row, len(self.lines)):
            line = self.lines[r] if case_sensitive else self.lines[r].lower()
            if old in line:
                orig = self.lines[r]
                search_line = orig if case_sensitive else orig.lower()
                new_line = search_line.replace(old, new)
                if search_line != new_line:
                    idx = 0
                    result = []
                    while idx < len(orig):
                        if case_sensitive:
                            found = orig.find(old, idx)
                        else:
                            found = orig.lower().find(old.lower(), idx)
                        if found == -1:
                            result.append(orig[idx:])
                            break
                        result.append(orig[idx:found])
                        result.append(new)
                        idx = found + len(old)
                        count += 1
                    self.lines[r] = "".join(result)
        self._modified = True
        return count

    def auto_indent(self, row: int) -> str:
        """Get auto-indentation for a new line after the given row."""
        if row < 0 or row >= len(self.lines):
            return ""
        line = self.lines[row]
        indent = ""
        for ch in line:
            if ch in " \t":
                indent += ch
            else:
                break
        stripped = line.strip()
        if stripped.endswith(":") or stripped.endswith("{"):
            tab = " " * 4
            indent += tab
        return indent


# ──────────────────────────────────────────────
# Cursor & Selection
# ──────────────────────────────────────────────

@dataclass
class Cursor:
    row: int = 0
    col: int = 0
    preferred_col: int = 0

    def clamp(self, buffer: TextBuffer):
        self.row = max(0, min(self.row, buffer.line_count - 1))
        self.col = max(0, min(self.col, len(buffer.get_line(self.row))))


@dataclass
class Selection:
    start_row: int = 0
    start_col: int = 0
    end_row: int = 0
    end_col: int = 0
    active: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.active or \
               (self.start_row == self.end_row and self.start_col == self.end_col)

    def clear(self):
        self.active = False

    def normalized(self) -> Tuple[int, int, int, int]:
        if (self.start_row, self.start_col) <= (self.end_row, self.end_col):
            return self.start_row, self.start_col, self.end_row, self.end_col
        return self.end_row, self.end_col, self.start_row, self.start_col


# ──────────────────────────────────────────────
# Viewport
# ──────────────────────────────────────────────

@dataclass
class Viewport:
    top_row: int = 0
    left_col: int = 0

    def scroll_to_cursor(self, cursor: Cursor, visible_rows: int, visible_cols: int):
        if cursor.row < self.top_row:
            self.top_row = cursor.row
        elif cursor.row >= self.top_row + visible_rows - 1:
            self.top_row = max(0, cursor.row - visible_rows + 1)
        if cursor.col < self.left_col:
            self.left_col = cursor.col
        elif cursor.col >= self.left_col + visible_cols - 5:
            self.left_col = max(0, cursor.col - visible_cols + 5)


# ──────────────────────────────────────────────
# Editor Tab
# ──────────────────────────────────────────────

@dataclass
class EditorTab:
    filepath: str = ""
    buffer: TextBuffer = field(default_factory=TextBuffer)
    cursor: Cursor = field(default_factory=Cursor)
    selection: Selection = field(default_factory=Selection)
    viewport: Viewport = field(default_factory=Viewport)
    language: str = ""
    search_query: str = ""
    search_cursor: Cursor = field(default_factory=Cursor)
    search_match: Optional[Tuple[int, int, int, int]] = None

    @property
    def name(self) -> str:
        return Path(self.filepath).name if self.filepath else "Untitled"

    @property
    def dirty(self) -> bool:
        return self.buffer.modified

    @property
    def line_count(self) -> int:
        return self.buffer.line_count

    def open_file(self, filepath: str) -> bool:
        path = Path(filepath)
        if not path.exists() or not path.is_file():
            return False
        try:
            content = path.read_text(encoding="utf-8")
            self.buffer.text = content
            self.filepath = str(path.resolve())
            self.language = detect_language(str(path), content)
            self.cursor = Cursor()
            self.viewport = Viewport()
            self.selection = Selection()
            self.buffer.set_modified(False)
            add_to_history(str(path), self.language, self.line_count)
            return True
        except Exception:
            return False

    def save(self) -> bool:
        if not self.filepath:
            return False
        try:
            Path(self.filepath).write_text(self.buffer.text, encoding="utf-8")
            self.buffer.set_modified(False)
            self.language = detect_language(self.filepath, self.buffer.text)
            return True
        except Exception:
            return False

    def save_as(self, new_path: str) -> bool:
        path = Path(new_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.buffer.text, encoding="utf-8")
            self.filepath = str(path.resolve())
            self.buffer.set_modified(False)
            self.language = detect_language(str(path), self.buffer.text)
            return True
        except Exception:
            return False


# ──────────────────────────────────────────────
# Curses Editor Application
# ──────────────────────────────────────────────

class CursesEditor:
    """Feature-rich terminal code editor using curses."""

    def __init__(self, filepath: str = "", content: str = "",
                 language: str = "", theme: str = "dark",
                 workdir: str = "."):
        self.workdir = str(Path(workdir).resolve())
        self.theme_name = theme
        self.tabs: List[EditorTab] = []
        self.active_tab = 0
        self.mode = EditorMode.INSERT
        self.sidebar_visible = False
        self.file_list: List[str] = []
        self.file_list_scroll = 0
        self.command_text = ""
        self.command_history: List[str] = []
        self.command_idx = -1
        self.status_message = ""
        self.status_timeout = 0
        self.show_line_numbers = True
        self.word_wrap = False
        self.show_whitespace = False
        self.tab_size = get_setting("tab_size") or 4
        self.running = False
        self.macro_recording: List[str] = []
        self.is_recording = False
        self.last_search = ""
        self.git_diff_data: Dict[str, List[int]] = {}
        self.stdscr: Optional[Any] = None
        self._clipboard = ""
        self._wheel_rows = 0
        self.lexer = None

        for i in range(10):
            if s := self._get_clipboard():
                self._clipboard = s
                break

        if content or filepath:
            tab = EditorTab()
            if filepath and Path(filepath).exists():
                tab.open_file(filepath)
            elif content:
                tab.buffer.text = content
                tab.language = language or detect_language(filepath or "", content)
                if filepath:
                    tab.filepath = str(Path(filepath).resolve())
            self.tabs.append(tab)
        else:
            self.tabs.append(EditorTab(language=language))

        if self.tabs and not self.tabs[0].language:
            self.tabs[0].language = language or "text"

    def _get_clipboard(self) -> Optional[str]:
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["powershell", "-Command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0:
                    return result.stdout
            elif sys.platform == "darwin":
                result = subprocess.run(["pbpaste"], capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout
            else:
                for cmd in [["xclip", "-o", "-selection", "clipboard"],
                           ["xsel", "-b"]]:
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            return result.stdout
                    except FileNotFoundError:
                        continue
        except Exception:
            pass
        return None

    def _set_clipboard(self, text: str) -> bool:
        try:
            if sys.platform == "win32":
                subprocess.run(["clip"], input=text, text=True, shell=True)
                return True
            elif sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=text, text=True)
                return True
            else:
                for cmd in [["xclip", "-selection", "clipboard"],
                           ["xsel", "-b", "-i"]]:
                    try:
                        subprocess.run(cmd, input=text, text=True)
                        return True
                    except FileNotFoundError:
                        continue
        except Exception:
            pass
        self._clipboard = text
        return True

    @property
    def tab(self) -> EditorTab:
        return self.tabs[self.active_tab]

    def _tab(self, idx: int) -> Optional[EditorTab]:
        return self.tabs[idx] if 0 <= idx < len(self.tabs) else None

    # ── Curses setup ──

    def run(self):
        """Start the curses editor."""
        try:
            self.stdscr = curses.initscr()
            curses.noecho()
            curses.cbreak()
            curses.curs_set(1)
            self.stdscr.keypad(True)
            self.stdscr.nodelay(False)
            curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
            init_colors()
            self.stdscr.clear()
            self.stdscr.refresh()
            curses.halfdelay(1)
            self.running = True
            self._main_loop()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            self._shutdown()
            print(f"Editor error: {e}")
            import traceback
            traceback.print_exc()
            return
        finally:
            self._shutdown()

    def _shutdown(self):
        self.running = False
        try:
            curses.nocbreak()
            curses.echo()
            curses.endwin()
            curses.curs_set(1)
        except Exception:
            pass

    def _main_loop(self):
        while self.running:
            self._render()
            try:
                self.stdscr.timeout(50)
                ch = self.stdscr.getch()
                if ch == -1:
                    continue
                self._handle_key(ch)
            except KeyboardInterrupt:
                break
            except Exception as e:
                if self.running:
                    self.status_message = f"Error: {e}"

    # ── Rendering ──

    def _render(self):
        if not self.stdscr:
            return
        self.stdscr.erase()
        max_y, max_x = self.stdscr.getmaxyx()
        if max_y < 5 or max_x < 20:
            self.stdscr.addstr(0, 0, "Terminal too small")
            self.stdscr.refresh()
            return

        tab_bar_h = 1
        status_h = 1
        cmd_h = 3 if self.mode == EditorMode.COMMAND else 0
        search_h = 3 if self.mode == EditorMode.SEARCH else 0
        editor_top = tab_bar_h
        editor_bottom = max_y - status_h - cmd_h - search_h - 1

        sidebar_w = SIDEBAR_WIDTH if self.sidebar_visible else 0
        line_num_w = len(str(self.tab.line_count)) + 2 if self.show_line_numbers else 0
        editor_left = sidebar_w + line_num_w
        editor_width = max_x - editor_left
        editor_height = editor_bottom - editor_top

        if editor_width < 10 or editor_height < 1:
            self.stdscr.refresh()
            return

        self._render_tab_bar(max_x)
        self._render_sidebar(0, editor_top, sidebar_w, editor_height, max_x)
        self._render_editor(editor_left, editor_top, editor_width, editor_height, line_num_w)
        self._render_status_bar(max_y - status_h - cmd_h - search_h - 1, max_x)
        self._render_command_line(max_y - status_h - cmd_h - search_h, max_x)
        self._render_search_bar(max_y - status_h - search_h - 1, max_x)

        if self.mode == EditorMode.INSERT:
            editor_row = editor_top + (self.tab.cursor.row - self.tab.viewport.top_row)
            editor_col = editor_left + (self.tab.cursor.col - self.tab.viewport.left_col)
            if 0 <= editor_row < editor_bottom and 0 <= editor_col < max_x:
                try:
                    self.stdscr.move(editor_row, editor_col)
                except curses.error:
                    pass

        self.stdscr.refresh()

    def _render_tab_bar(self, max_x: int):
        attr = curses.color_pair(COLOR_STATUSBAR) | curses.A_REVERSE
        self.stdscr.addstr(0, 0, " " * max_x, attr)
        x = 0
        for i, tab in enumerate(self.tabs):
            name = tab.name
            if tab.dirty:
                name = "* " + name
            display = name[:TAB_MAX_WIDTH]
            style = curses.A_BOLD if i == self.active_tab else curses.A_NORMAL
            tab_attr = curses.color_pair(COLOR_STATUSBAR)
            if i == self.active_tab:
                tab_attr |= curses.A_REVERSE
            if x + len(display) + 1 >= max_x:
                break
            self.stdscr.addstr(0, x, f" {display} ", tab_attr | style)
            x += len(display) + 2
        if x < max_x:
            try:
                self.stdscr.addstr(0, x, " " * (max_x - x), attr)
            except curses.error:
                pass

    def _render_sidebar(self, x: int, y: int, w: int, h: int, max_x: int):
        if not self.sidebar_visible or w <= 0:
            return
        try:
            for row in range(h):
                self.stdscr.addstr(y + row, x, " " * w)
        except curses.error:
            pass
        dir_label = f" {self.workdir} "
        try:
            self.stdscr.addstr(y, x, dir_label[:w], curses.color_pair(COLOR_STATUSBAR) | curses.A_REVERSE)
        except curses.error:
            pass
        if not self.file_list:
            self._refresh_file_list()
        visible = h - 1
        fs = max(0, self.file_list_scroll)
        for i in range(min(visible, len(self.file_list) - fs)):
            fname = self.file_list[fs + i]
            display = f"  {fname}"
            if len(display) > w:
                display = display[:w - 3] + "..."
            if fs + i == self._selected_file_idx:
                attr = curses.color_pair(COLOR_SELECTION) | curses.A_REVERSE
            elif Path(fname).suffix in (".py", ".js", ".ts", ".html", ".css", ".json", ".md"):
                attr = curses.color_pair(COLOR_FUNC)
            else:
                attr = 0
            try:
                self.stdscr.addstr(y + 1 + i, x, display[:w], attr)
            except curses.error:
                pass
        try:
            self.stdscr.addstr(y, x + w, "│", curses.A_DIM)
            for r in range(y + 1, y + h):
                self.stdscr.addstr(r, x + w, "│", curses.A_DIM)
        except curses.error:
            pass

    def _render_editor(self, x: int, y: int, w: int, h: int, line_num_w: int):
        self.tab.viewport.scroll_to_cursor(self.tab.cursor, h, w)
        vr = self.tab.viewport.top_row
        vc = self.tab.viewport.left_col

        try:
            tokens_by_line = self._tokenize_lines(vr, vr + h, w + vc)
        except Exception:
            tokens_by_line = {}

        sel = self.tab.selection
        sr, sc, er, ec = sel.normalized() if sel.active else (0, 0, 0, 0)

        for visual_row in range(h):
            buf_row = vr + visual_row
            screen_y = y + visual_row

            if line_num_w > 0 and buf_row < self.tab.line_count:
                ln_str = f"{buf_row + 1:>{line_num_w - 1}} "
                ln_attr = curses.color_pair(COLOR_LINENUM)
                if buf_row == self.tab.cursor.row:
                    ln_attr |= curses.A_BOLD
                try:
                    self.stdscr.addstr(screen_y, x - line_num_w, ln_str[:line_num_w], ln_attr)
                except curses.error:
                    pass

            if x + w > 0 and screen_y < y + h:
                try:
                    self.stdscr.addstr(screen_y, x, " " * w)
                except curses.error:
                    pass

            if buf_row >= self.tab.line_count:
                continue

            line = self.tab.buffer.get_line(buf_row)
            if vc > 0 and vc > len(line):
                continue

            visible_line = line[vc:vc + w] if vc < len(line) else ""
            tokens = tokens_by_line.get(buf_row, [])

            col_offset = 0
            for token_type, token_text in tokens:
                tok_start = token_text[0] if isinstance(token_text, tuple) and len(token_text) > 2 else 0
                tok_text = token_text if isinstance(token_text, str) else token_text[1] if len(token_text) > 1 else ""

                if not isinstance(token_text, str):
                    tok_start = token_text[2]
                    tok_end = token_text[3]
                    tok_text = line[tok_start:tok_end]

                display_start = max(0, min(col_offset, len(visible_line)))
                display_text = tok_text
                if col_offset < vc:
                    skip = vc - col_offset
                    display_text = display_text[skip:]
                if len(display_text) > w - (col_offset - vc):
                    display_text = display_text[:w - max(0, col_offset - vc)]

                if display_text:
                    attr = curses.color_pair(get_token_color(token_type))
                    if sel.active:
                        if self._in_selection(buf_row, col_offset, sel):
                            attr |= curses.A_REVERSE
                    try:
                        screen_x = x + max(0, col_offset - vc)
                        self.stdscr.addstr(screen_y, screen_x, display_text, attr)
                    except curses.error:
                        pass
                col_offset += len(tok_text) if tok_text else len(token_text) if isinstance(token_text, str) else 0

            if not tokens and visible_line:
                attr = 0
                if sel.active and self._in_line_selection(buf_row, sr, er):
                    attr |= curses.A_REVERSE
                try:
                    self.stdscr.addstr(screen_y, x, visible_line, attr)
                except curses.error:
                    pass

    def _tokenize_lines(self, start: int, end: int, _max_chars: int) -> Dict[int, List]:
        """Tokenize multiple lines using Pygments for syntax highlighting."""
        result: Dict[int, List] = {}
        try:
            lang = self.tab.language or "text"
            if lang == "text":
                try:
                    lexer = guess_lexer(self.tab.buffer.text)
                except ClassNotFound:
                    return result
            else:
                try:
                    lexer = get_lexer_by_name(lang, stripall=False, ensurenl=False)
                except ClassNotFound:
                    try:
                        lexer = get_lexer_by_name("text")
                    except ClassNotFound:
                        return result

            text_chunk = "\n".join(self.tab.buffer.lines[start:end])
            tokens = list(lexer.get_tokens(text_chunk))
            line_idx = start
            col = 0
            for token_type, token_text in tokens:
                token_lines = token_text.split("\n")
                for i, tline in enumerate(token_lines):
                    if i > 0:
                        line_idx += 1
                        col = 0
                    if tline and line_idx < end:
                        if line_idx not in result:
                            result[line_idx] = []
                        result[line_idx].append((token_type, tline))
                    col += len(tline)
        except Exception:
            pass
        return result

    def _in_selection(self, row: int, col: int, sel: Selection) -> bool:
        if not sel.active:
            return False
        sr, sc, er, ec = sel.normalized()
        if sr <= row <= er:
            if row == sr and row == er:
                return sc <= col < ec
            elif row == sr:
                return col >= sc
            elif row == er:
                return col < ec
            return True
        return False

    def _in_line_selection(self, row: int, sr: int, er: int) -> bool:
        return sr <= row <= er

    def _render_status_bar(self, y: int, max_x: int):
        tab = self.tab
        try:
            self.stdscr.addstr(y, 0, " " * max_x,
                              curses.color_pair(COLOR_STATUSBAR) | curses.A_REVERSE)
        except curses.error:
            pass
        mode_str = {
            EditorMode.NORMAL: " NORMAL ",
            EditorMode.INSERT: " INSERT ",
            EditorMode.VISUAL: " VISUAL ",
            EditorMode.COMMAND: " COMMAND ",
            EditorMode.SEARCH: " SEARCH ",
        }.get(self.mode, " ? ")
        left = f"{mode_str} "
        left += f"{tab.filepath or 'Untitled'} "
        if tab.dirty:
            left += "[+] "
        left += f"| {tab.language} "
        right = f" Ln {tab.cursor.row + 1}, Col {tab.cursor.col + 1} "
        right += f"| {tab.line_count} lines "
        right += f"| {len(self.tabs)} tabs "
        right += f"| UTF-8 "
        if self.is_recording:
            right += "| REC "
        try:
            self.stdscr.addstr(y, 0, left[:max_x - 1],
                              curses.color_pair(COLOR_STATUSBAR) | curses.A_REVERSE)
            self.stdscr.addstr(y, max_x - len(right) - 1, right,
                              curses.color_pair(COLOR_STATUSBAR) | curses.A_REVERSE)
        except curses.error:
            pass
        if self.status_message:
            msg = f" {self.status_message[:max_x - 2]} "
            try:
                self.stdscr.addstr(y + 1, 0, msg[:max_x - 1],
                                  curses.color_pair(COLOR_INFO))
            except curses.error:
                pass
            self.status_message = ""

    def _render_command_line(self, y: int, max_x: int):
        if self.mode != EditorMode.COMMAND:
            return
        try:
            self.stdscr.addstr(y, 0, " " * max_x, curses.A_REVERSE)
            prefix = "> "
            self.stdscr.addstr(y, 0, prefix, curses.A_BOLD)
            self.stdscr.addstr(y, len(prefix), self.command_text[:max_x - len(prefix)])
            if curses.curs_set(0) is not None:
                curses.curs_set(1)
                self.stdscr.move(y, len(prefix) + len(self.command_text))
        except curses.error:
            pass

    def _render_search_bar(self, y: int, max_x: int):
        if self.mode != EditorMode.SEARCH:
            return
        try:
            self.stdscr.addstr(y, 0, " " * max_x, curses.A_REVERSE)
            prefix = "/ "
            self.stdscr.addstr(y, 0, prefix, curses.A_BOLD)
            self.stdscr.addstr(y, len(prefix), self.command_text[:max_x - len(prefix)])
            curses.curs_set(1)
            self.stdscr.move(y, len(prefix) + len(self.command_text))
        except curses.error:
            pass

    # ── File operations ──

    def _refresh_file_list(self):
        try:
            self.file_list = list_files(self.workdir, recursive=False)
            base = Path(self.workdir)
            all_items = []
            for d in sorted(base.iterdir()):
                if d.is_dir():
                    all_items.append(f"{d.name}/")
            for fname in self.file_list:
                all_items.append(fname)
            self.file_list = all_items
        except Exception:
            self.file_list = []

    @property
    def _selected_file_idx(self) -> int:
        return self.file_list_scroll

    def _open_selected_file(self):
        if not self.file_list:
            return
        idx = self._selected_file_idx
        if idx < len(self.file_list):
            fname = self.file_list[idx].rstrip("/")
            full_path = str(Path(self.workdir) / fname)
            if Path(full_path).is_file():
                self._open_file(full_path)

    def _open_file(self, filepath: str):
        path = Path(filepath)
        if not path.is_file():
            return
        for i, tab in enumerate(self.tabs):
            if tab.filepath and Path(tab.filepath).resolve() == path.resolve():
                self.active_tab = i
                self.status_message = f"Switched to {path.name}"
                return
        if len(self.tabs) < MAX_TABS:
            tab = EditorTab()
            if tab.open_file(filepath):
                self.tabs.append(tab)
                self.active_tab = len(self.tabs) - 1
                self.status_message = f"Opened {path.name}"
            self._refresh_file_list()

    def _save_file(self):
        if self.tab.filepath:
            if self.tab.save():
                self.status_message = "Saved"
            else:
                self.status_message = "Save failed"
        else:
            self._command_save_as()

    def _close_tab(self, idx: Optional[int] = None):
        idx = idx if idx is not None else self.active_tab
        if len(self.tabs) <= 1:
            self.tab.buffer.text = ""
            self.tab.filepath = ""
            self.tab.language = "text"
            self.tab.cursor = Cursor()
            self.tab.buffer.set_modified(False)
            self.status_message = "New file"
            return
        if 0 <= idx < len(self.tabs):
            self.tabs.pop(idx)
            if self.active_tab >= len(self.tabs):
                self.active_tab = len(self.tabs) - 1
            self._refresh_file_list()

    def _new_tab(self):
        if len(self.tabs) < MAX_TABS:
            self.tabs.append(EditorTab())
            self.active_tab = len(self.tabs) - 1

    def _next_tab(self):
        self.active_tab = (self.active_tab + 1) % len(self.tabs)

    def _prev_tab(self):
        self.active_tab = (self.active_tab - 1) % len(self.tabs)

    # ── Undo / Redo ──

    def _undo(self):
        state = self.tab.buffer.undo()
        if state:
            self.tab.cursor.row = state.cursor_row
            self.tab.cursor.col = state.cursor_col
            self.tab.cursor.clamp(self.tab.buffer)
            self.status_message = "Undo"

    def _redo(self):
        state = self.tab.buffer.redo()
        if state:
            self.tab.cursor.row = state.cursor_row
            self.tab.cursor.col = state.cursor_col
            self.tab.cursor.clamp(self.tab.buffer)
            self.status_message = "Redo"

    # ── Search ──

    def _search(self, query: str):
        if not query:
            return
        self.last_search = query
        self.tab.search_query = query
        match = self.tab.buffer.find(
            query, self.tab.search_cursor.row,
            self.tab.search_cursor.col
        )
        if match:
            self.tab.search_match = match
            self.tab.cursor.row = match[0]
            self.tab.cursor.col = match[2]
            self.tab.cursor.clamp(self.tab.buffer)
            self.tab.viewport.scroll_to_cursor(self.tab.cursor, self._editor_height(), self._editor_width())
            self.tab.search_cursor.row = match[0]
            self.tab.search_cursor.col = match[2]
            self.status_message = f"Found: '{query}'"
        else:
            self.tab.search_cursor = Cursor()
            self.status_message = f"Not found: '{query}'"

    def _search_next(self):
        if self.tab.search_query:
            self.tab.search_cursor.col += 1
            self._search(self.tab.search_query)

    def _search_prev(self):
        if self.tab.search_query:
            self.tab.search_cursor.col -= 1
            self._search(self.tab.search_query)

    def _replace_all(self, old: str, new: str):
        count = self.tab.buffer.replace(old, new,
                                        case_sensitive=self._search_case_sensitive)
        self.status_message = f"Replaced {count} occurrences"

    @property
    def _search_case_sensitive(self) -> bool:
        return True

    # ── Editor dimensions ──

    def _editor_height(self) -> int:
        max_y, _ = self.stdscr.getmaxyx() if self.stdscr else (24, 80)
        cmd_h = 3 if self.mode == EditorMode.COMMAND else 0
        search_h = 3 if self.mode == EditorMode.SEARCH else 0
        return max_y - 3 - cmd_h - search_h

    def _editor_width(self) -> int:
        _, max_x = self.stdscr.getmaxyx() if self.stdscr else (24, 80)
        sidebar_w = SIDEBAR_WIDTH if self.sidebar_visible else 0
        line_num_w = len(str(self.tab.line_count)) + 2 if self.show_line_numbers else 0
        return max_x - sidebar_w - line_num_w

    # ── Key handling ──

    def _handle_key(self, ch: int):
        if self.is_recording and ch not in (curses.KEY_MOUSE, -1):
            self.macro_recording.append(str(ch))

        if self.mode == EditorMode.SEARCH:
            self._handle_search_key(ch)
            return
        if self.mode == EditorMode.COMMAND:
            self._handle_command_key(ch)
            return

        if self.mode == EditorMode.NORMAL:
            handled = self._handle_normal_key(ch)
            if handled:
                return
        if self.mode == EditorMode.VISUAL:
            handled = self._handle_visual_key(ch)
            if handled:
                return

        self._handle_edit_key(ch)

    def _handle_normal_key(self, ch: int) -> bool:
        if ch == ord("i"):
            self.mode = EditorMode.INSERT
            self.status_message = "INSERT"
            return True
        if ch == ord("v"):
            self.mode = EditorMode.VISUAL
            self.tab.selection.active = True
            self.tab.selection.start_row = self.tab.cursor.row
            self.tab.selection.start_col = self.tab.cursor.col
            self.tab.selection.end_row = self.tab.cursor.row
            self.tab.selection.end_col = self.tab.cursor.col
            self.status_message = "VISUAL"
            return True
        if ch == ord("h") or ch == curses.KEY_LEFT:
            self._move_cursor(0, -1)
            return True
        if ch == ord("l") or ch == curses.KEY_RIGHT:
            self._move_cursor(0, 1)
            return True
        if ch == ord("k") or ch == curses.KEY_UP:
            self._move_cursor(-1, 0)
            return True
        if ch == ord("j") or ch == curses.KEY_DOWN:
            self._move_cursor(1, 0)
            return True
        if ch == ord("w"):
            buff = self.tab.buffer
            line = buff.get_line(self.tab.cursor.row)
            for ci in range(self.tab.cursor.col + 1, len(line)):
                if line[ci].isalnum() or line[ci] == "_":
                    self.tab.cursor.col = ci
                    break
            else:
                self._move_cursor(1, 0)
            self.tab.cursor.clamp(buff)
            return True
        if ch == ord("b"):
            buff = self.tab.buffer
            line = buff.get_line(self.tab.cursor.row)
            for ci in range(self.tab.cursor.col - 1, -1, -1):
                if line[ci].isalnum() or line[ci] == "_":
                    self.tab.cursor.col = ci
                    break
            else:
                self._move_cursor(-1, 0)
            self.tab.cursor.clamp(buff)
            return True
        if ch == ord("x"):
            self._delete_forward_char()
            return True
        if ch == ord("d") and len(self.macro_recording) < 2:
            self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
            self.tab.buffer.delete_line(self.tab.cursor.row)
            self.tab.cursor.clamp(self.tab.buffer)
            return True
        if ch == ord("y"):
            line = self.tab.buffer.get_line(self.tab.cursor.row)
            self._clipboard_copy(line + "\n")
            self.status_message = "Line yanked"
            return True
        if ch == ord("p"):
            if self._clipboard:
                self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
                self._move_cursor(1, 0)
                self.tab.buffer.insert_text(self.tab.cursor.row, 0, self._clipboard.rstrip("\n"))
            return True
        if ch == ord("o"):
            self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
            self._move_cursor(1, 0)
            self.tab.buffer.insert_line(self.tab.cursor.row - 1, 0)
            ind = self.tab.buffer.auto_indent(self.tab.cursor.row - 1)
            if ind:
                self.tab.buffer.lines[self.tab.cursor.row] = ind
            self.mode = EditorMode.INSERT
            return True
        if ch == ord("O"):
            self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
            self.tab.buffer.insert_line(self.tab.cursor.row - 1, 0)
            ind = self.tab.buffer.auto_indent(max(0, self.tab.cursor.row - 2))
            if ind:
                self.tab.buffer.lines[self.tab.cursor.row] = ind
            self.mode = EditorMode.INSERT
            return True
        if ch == ord("0"):
            self.tab.cursor.col = 0
            return True
        if ch == ord("$"):
            buff = self.tab.buffer
            self.tab.cursor.col = len(buff.get_line(self.tab.cursor.row))
            return True
        if ch == ord("g"):
            self.tab.cursor.row = 0
            self.tab.cursor.col = 0
            self.tab.cursor.clamp(self.tab.buffer)
            return True
        if ch == ord("G"):
            buff = self.tab.buffer
            self.tab.cursor.row = buff.line_count - 1
            self.tab.cursor.col = 0
            self.tab.cursor.clamp(buff)
            return True
        if ch == ord("/"):
            self.mode = EditorMode.SEARCH
            self.command_text = ""
            return True
        if ch == ord("u"):
            self._undo()
            return True
        if ch == 18:
            self._redo()
            return True
        if ch == ord(":"):
            self.mode = EditorMode.COMMAND
            self.command_text = ""
            return True
        if ch == 27:
            return True
        return False

    def _handle_visual_key(self, ch: int) -> bool:
        if ch == 27:
            self.mode = EditorMode.NORMAL
            self.tab.selection.clear()
            return True
        if ch in (ord("h"), curses.KEY_LEFT, ord("l"), curses.KEY_RIGHT,
                  ord("k"), curses.KEY_UP, ord("j"), curses.KEY_DOWN):
            self._handle_normal_key(ch)
            self.tab.selection.end_row = self.tab.cursor.row
            self.tab.selection.end_col = self.tab.cursor.col
            return True
        if ch == ord("y"):
            sr, sc, er, ec = self.tab.selection.normalized()
            text = self.tab.buffer.get_text_range(sr, sc, er, ec)
            self._clipboard_copy(text)
            self.mode = EditorMode.NORMAL
            self.tab.selection.clear()
            self.status_message = "Yanked"
            return True
        if ch == ord("d"):
            sr, sc, er, ec = self.tab.selection.normalized()
            self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
            text = self.tab.buffer.delete_range(sr, sc, er, ec)
            self._clipboard_copy(text)
            self.tab.cursor.row = sr
            self.tab.cursor.col = sc
            self.tab.cursor.clamp(self.tab.buffer)
            self.mode = EditorMode.NORMAL
            self.tab.selection.clear()
            self.status_message = "Deleted"
            return True
        if ch == ord("c"):
            sr, sc, er, ec = self.tab.selection.normalized()
            self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
            text = self.tab.buffer.delete_range(sr, sc, er, ec)
            self._clipboard_copy(text)
            self.tab.cursor.row = sr
            self.tab.cursor.col = sc
            self.tab.cursor.clamp(self.tab.buffer)
            self.mode = EditorMode.INSERT
            self.tab.selection.clear()
            return True
        return False

    def _handle_edit_key(self, ch: int):
        if self.mode != EditorMode.INSERT:
            return

        tab = self.tab

        if ch == 27:
            self.mode = EditorMode.NORMAL
            return

        if ch == 19:
            self._save_file()
            self.status_message = "Saved"
            return

        if ch == 26:
            self._undo()
            return

        if ch == 25:
            self._redo()
            return

        if ch == 24:
            self._clipboard_cut()
            self.status_message = "Cut"
            return

        if ch == 3:
            self._clipboard_copy_selection()
            return

        if ch == 22:
            self._clipboard_paste()
            self.status_message = "Pasted"
            return

        if ch == 12:
            self.show_line_numbers = not self.show_line_numbers
            self.status_message = "Line numbers " + ("on" if self.show_line_numbers else "off")
            return

        if ch == 17:
            self.running = False
            return

        if ch == 20:
            if len(self.tabs) < MAX_TABS:
                self.tabs.append(EditorTab())
                self.active_tab = len(self.tabs) - 1
                self.status_message = "New tab"
            return

        if ch == 4:
            self._duplicate_line()
            self.status_message = "Line duplicated"
            return

        if ch == 7:
            ly, lx = self.stdscr.getmaxyx() if self.stdscr else (24, 80)
            self.mode = EditorMode.COMMAND
            self.command_text = ""
            self.status_message = "Enter line number"
            return

        if ch == 1:
            self._move_cursor(0, 0)
            return

        if ch == 5:
            buff = tab.buffer
            self.tab.cursor.col = len(buff.get_line(tab.cursor.row))
            return

        if ch == 6:
            self.mode = EditorMode.SEARCH
            self.command_text = ""
            self.status_message = "Search: /"
            return

        if ch == 18:
            self.mode = EditorMode.SEARCH
            self.command_text = ""
            self.status_message = "Replace: :%s/old/new/g"
            return

        if ch == 2:
            self.sidebar_visible = not self.sidebar_visible
            if self.sidebar_visible:
                self._refresh_file_list()
            self.status_message = "Sidebar " + ("shown" if self.sidebar_visible else "hidden")
            return

        if ch == 14:
            self._move_cursor(-1, 0)
            return

        if ch == 16:
            self._move_cursor(1, 0)
            return

        if ch == 23:
            buff = tab.buffer
            line = buff.get_line(tab.cursor.row)
            start = tab.cursor.col
            while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
                start -= 1
            if start < tab.cursor.col:
                text = line[start:tab.cursor.col]
                tab.buffer.save_undo_state(tab.cursor.row, tab.cursor.col)
                for _ in range(tab.cursor.col - start):
                    tab.buffer.delete_char(tab.cursor.row, tab.cursor.col)
                self._clipboard_copy(text)
                tab.cursor.col = start
            return

        if ch == 21:
            tab.buffer.save_undo_state(tab.cursor.row, tab.cursor.col)
            tab.buffer.delete_line(tab.cursor.row)
            tab.cursor.col = 0
            tab.cursor.clamp(tab.buffer)
            return

        if ch == 8 or ch == 127 or ch == curses.KEY_BACKSPACE:
            tab.buffer.save_undo_state(tab.cursor.row, tab.cursor.col)
            tab.buffer.delete_char(tab.cursor.row, tab.cursor.col)
            if tab.cursor.col > 0:
                tab.cursor.col -= 1
            elif tab.cursor.row > 0:
                tab.cursor.row -= 1
                tab.cursor.col = len(tab.buffer.get_line(tab.cursor.row))
            tab.cursor.clamp(tab.buffer)
            return

        if ch == curses.KEY_DC:
            tab.buffer.save_undo_state(tab.cursor.row, tab.cursor.col)
            tab.buffer.delete_forward(tab.cursor.row, tab.cursor.col)
            return

        if ch == 10 or ch == 13:
            tab.buffer.save_undo_state(tab.cursor.row, tab.cursor.col)
            ind = tab.buffer.auto_indent(tab.cursor.row)
            tab.buffer.insert_line(tab.cursor.row, tab.cursor.col)
            tab.cursor.row += 1
            tab.cursor.col = 0
            if ind:
                tab.buffer.insert_text(tab.cursor.row, 0, ind)
                tab.cursor.col = len(ind)
            tab.cursor.clamp(tab.buffer)
            return

        if ch == 9:
            tab.buffer.save_undo_state(tab.cursor.row, tab.cursor.col)
            spaces = " " * self.tab_size
            tab.buffer.insert_text(tab.cursor.row, tab.cursor.col, spaces)
            tab.cursor.col += self.tab_size
            tab.cursor.clamp(tab.buffer)
            return

        if ch in (curses.KEY_LEFT,):
            self._move_cursor(0, -1)
            return
        if ch in (curses.KEY_RIGHT,):
            self._move_cursor(0, 1)
            return
        if ch in (curses.KEY_UP,):
            self._move_cursor(-1, 0)
            return
        if ch in (curses.KEY_DOWN,):
            self._move_cursor(1, 0)
            return

        if ch == curses.KEY_HOME or ch == 527:
            self.tab.cursor.col = 0
            return
        if ch == curses.KEY_END or ch == 525:
            self.tab.cursor.col = len(tab.buffer.get_line(tab.cursor.row))
            return
        if ch == curses.KEY_PPAGE:
            self.tab.cursor.row = max(0, tab.cursor.row - self._editor_height())
            self.tab.cursor.clamp(tab.buffer)
            return
        if ch == curses.KEY_NPAGE:
            self.tab.cursor.row = min(tab.buffer.line_count - 1,
                                       tab.cursor.row + self._editor_height())
            self.tab.cursor.clamp(tab.buffer)
            return

        if 32 <= ch <= 126 or ch > 255:
            if ch <= 126:
                char = chr(ch)
            else:
                char = chr(ch)
            tab.buffer.save_undo_state(tab.cursor.row, tab.cursor.col)
            if char == "}" or char == "]" or char == ")" or char == "\"" or char == "'":
                line = tab.buffer.get_line(tab.cursor.row)
                pairs = {"}": "{", "]": "[", ")": "(", "\"": "\"", "'": "'"}
                if tab.cursor.col < len(line) and line[tab.cursor.col] == char:
                    tab.cursor.col += 1
                    return
            tab.buffer.insert_char(tab.cursor.row, tab.cursor.col, char)
            tab.cursor.col += 1
            if char in ("{", "[", "("):
                closer = {"{": "}", "[": "]", "(": ")"}[char]
                tab.buffer.insert_char(tab.cursor.row, tab.cursor.col, closer)
            elif char == "\"":
                tab.buffer.insert_char(tab.cursor.row, tab.cursor.col, "\"")
            elif char == "'":
                tab.buffer.insert_char(tab.cursor.row, tab.cursor.col, "'")
            tab.cursor.clamp(tab.buffer)
            return

    def _handle_search_key(self, ch: int):
        if ch == 27:
            self.mode = EditorMode.NORMAL
            self.command_text = ""
            return
        if ch == 10 or ch == 13:
            self._search(self.command_text)
            self.mode = EditorMode.NORMAL
            return
        if ch == curses.KEY_UP:
            pass
        if ch == curses.KEY_DOWN:
            pass
        if ch in (8, 127, curses.KEY_BACKSPACE):
            if self.command_text:
                self.command_text = self.command_text[:-1]
            return
        if 32 <= ch <= 126:
            self.command_text += chr(ch)
            return

    def _handle_command_key(self, ch: int):
        if ch == 27:
            self.mode = EditorMode.NORMAL
            self.command_text = ""
            self.command_idx = -1
            return
        if ch == 10 or ch == 13:
            cmd = self.command_text.strip()
            if cmd:
                self.command_history.append(cmd)
            self._execute_command(cmd)
            self.mode = EditorMode.NORMAL
            self.command_text = ""
            self.command_idx = -1
            return
        if ch == curses.KEY_UP:
            if self.command_history and (self.command_idx == -1 or self.command_idx > 0):
                if self.command_idx == -1:
                    self.command_idx = len(self.command_history)
                self.command_idx -= 1
                self.command_text = self.command_history[self.command_idx]
            return
        if ch == curses.KEY_DOWN:
            if self.command_history and self.command_idx < len(self.command_history) - 1:
                self.command_idx += 1
                self.command_text = self.command_history[self.command_idx]
            elif self.command_idx >= len(self.command_history) - 1:
                self.command_idx = -1
                self.command_text = ""
            return
        if ch in (8, 127, curses.KEY_BACKSPACE):
            if self.command_text:
                self.command_text = self.command_text[:-1]
            return
        if 32 <= ch <= 126:
            self.command_text += chr(ch)
            return

    def _execute_command(self, cmd: str):
        parts = cmd.split()
        if not parts:
            return
        c = parts[0].lower()
        args = parts[1:]

        commands = {
            "w": self._command_save,
            "q": self._command_quit,
            "wq": self._command_save_quit,
            "q!": self._command_force_quit,
            "e": self._command_edit,
            "e!": self._command_reload,
            "w!": self._command_save_as_admin,
            "n": self._command_new,
            "saveas": self._command_save_as,
            "bn": self._command_next_tab,
            "bp": self._command_prev_tab,
            "bd": self._command_close_tab,
            "badd": self._command_edit,
            "tabnew": self._command_new,
            "tabclose": self._command_close_tab,
            "tabnext": self._command_next_tab,
            "tabprev": self._command_prev_tab,
            "set": self._command_set,
            "theme": self._command_theme,
            "goto": self._command_goto,
            "vsplit": self._command_split,
            "hsplit": self._command_hsplit,
            "find": self._command_find,
            "replace": self._command_replace,
            "language": self._command_language,
            "tabsize": self._command_tabsize,
            "fold": self._command_fold,
            "sort": self._command_sort,
            "unique": self._command_unique,
            "join": self._command_join,
            "lower": self._command_lower,
            "upper": self._command_upper,
            "toggle": self._command_toggle,
            "map": self._command_map,
            "rec": self._command_record,
            "register": self._command_register,
            "diff": self._command_diff,
            "copy": self._command_copy_path,
            "gitlog": self._command_git_log,
            "gitdiff": self._command_git_diff,
            "gitblame": self._command_git_blame,
            "help": self._command_help,
            "about": self._command_about,
            "quit": self._command_quit,
            "exit": self._command_quit,
            "save": self._command_save,
            "open": self._command_edit,
            "close": self._command_close_tab,
        }

        if c in commands:
            commands[c](args) if args else commands[c]()
        elif c.isdigit():
            line = int(c)
            buff = self.tab.buffer
            self.tab.cursor.row = max(0, min(line - 1, buff.line_count - 1))
            self.tab.cursor.col = 0
            self.tab.cursor.clamp(buff)
            self.tab.viewport.top_row = max(0, self.tab.cursor.row - self._editor_height() // 2)
        else:
            self.status_message = f"Unknown command: {c}"

    def _command_save(self, args=None):
        self._save_file()

    def _command_quit(self, args=None):
        if any(t.dirty for t in self.tabs):
            self.status_message = "Unsaved changes! Use :q! to force quit"
            return
        self.running = False

    def _command_save_quit(self, args=None):
        for tab in self.tabs:
            if tab.dirty:
                if not tab.filepath:
                    self.status_message = "Unsaved file. Use :w filename first"
                    return
                tab.save()
        self.running = False

    def _command_force_quit(self, args=None):
        self.running = False

    def _command_edit(self, args=None):
        if args:
            filepath = args[0]
            path = Path(filepath)
            if not path.is_absolute():
                path = Path(self.workdir) / filepath
            self._open_file(str(path))

    def _command_reload(self, args=None):
        if self.tab.filepath:
            self.tab.open_file(self.tab.filepath)
            self.status_message = "Reloaded"

    def _command_save_as_admin(self, args=None):
        pass

    def _command_new(self, args=None):
        self._new_tab()

    def _command_save_as(self, args=None):
        if args:
            new_path = args[0]
            if self.tab.save_as(new_path):
                self.status_message = f"Saved as {new_path}"
            else:
                self.status_message = "Save as failed"

    def _command_next_tab(self, args=None):
        self._next_tab()

    def _command_prev_tab(self, args=None):
        self._prev_tab()

    def _command_close_tab(self, args=None):
        if args:
            try:
                idx = int(args[0]) - 1
                self._close_tab(idx)
            except ValueError:
                pass
        else:
            self._close_tab()

    def _command_set(self, args=None):
        if not args:
            return
        if args[0] == "number" or args[0] == "nu":
            self.show_line_numbers = True
        elif args[0] == "nonumber" or args[0] == "nonu":
            self.show_line_numbers = False
        elif args[0] == "wrap":
            self.word_wrap = True
        elif args[0] == "nowrap":
            self.word_wrap = False
        elif args[0] == "list":
            self.show_whitespace = True
        elif args[0] == "nolist":
            self.show_whitespace = False
        elif args[0] == "tabstop" or args[0] == "ts":
            if len(args) > 1:
                try:
                    self.tab_size = int(args[1])
                except ValueError:
                    pass

    def _command_theme(self, args=None):
        if args:
            self.theme_name = args[0]

    def _command_goto(self, args=None):
        if args:
            try:
                line = int(args[0])
                buff = self.tab.buffer
                self.tab.cursor.row = max(0, min(line - 1, buff.line_count - 1))
                self.tab.cursor.col = 0
                self.tab.cursor.clamp(buff)
                self.tab.viewport.top_row = max(0, self.tab.cursor.row - self._editor_height() // 2)
            except ValueError:
                pass

    def _command_split(self, args=None):
        self.status_message = "Split not yet implemented"

    def _command_hsplit(self, args=None):
        self.status_message = "HSplit not yet implemented"

    def _command_find(self, args=None):
        if args:
            self._search(" ".join(args))

    def _command_replace(self, args=None):
        if len(args) >= 2:
            self._replace_all(args[0], args[1])

    def _command_language(self, args=None):
        if args:
            self.tab.language = args[0]

    def _command_tabsize(self, args=None):
        if args:
            try:
                self.tab_size = int(args[0])
            except ValueError:
                pass

    def _command_fold(self, args=None):
        self.status_message = "Folding not yet implemented"

    def _command_sort(self, args=None):
        if self.tab.selection.active:
            sr, sc, er, ec = self.tab.selection.normalized()
        else:
            sr, sc = 0, 0
            er = self.tab.buffer.line_count - 1
        self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
        lines = self.tab.buffer.lines[sr:er + 1]
        sorted_lines = sorted(lines)
        for i, l in enumerate(sorted_lines):
            self.tab.buffer.lines[sr + i] = l
        self.tab.buffer.set_modified(True)
        self.status_message = f"Sorted {len(lines)} lines"

    def _command_unique(self, args=None):
        if self.tab.selection.active:
            sr, sc, er, ec = self.tab.selection.normalized()
        else:
            return
        self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
        lines = self.tab.buffer.lines[sr:er + 1]
        unique_lines = list(dict.fromkeys(lines))
        del self.tab.buffer.lines[sr:er + 1]
        for i, l in enumerate(unique_lines):
            self.tab.buffer.lines.insert(sr + i, l)
        self.tab.buffer.set_modified(True)
        self.tab.cursor.row = min(sr + len(unique_lines), self.tab.buffer.line_count - 1)
        self.tab.selection.clear()
        self.status_message = f"Removed {len(lines) - len(unique_lines)} duplicates"

    def _command_join(self, args=None):
        self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
        r = self.tab.cursor.row
        if r < self.tab.buffer.line_count - 1:
            cur_line = self.tab.buffer.lines[r]
            next_line = self.tab.buffer.lines[r + 1].lstrip()
            self.tab.buffer.lines[r] = cur_line + " " + next_line
            self.tab.buffer.lines.pop(r + 1)
            self.tab.buffer.set_modified(True)

    def _command_lower(self, args=None):
        if self.tab.selection.active:
            sr, sc, er, ec = self.tab.selection.normalized()
        else:
            sr, sc = self.tab.cursor.row, 0
            er = self.tab.cursor.row
        self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
        for r in range(sr, er + 1):
            self.tab.buffer.lines[r] = self.tab.buffer.lines[r].lower()
        self.tab.buffer.set_modified(True)

    def _command_upper(self, args=None):
        if self.tab.selection.active:
            sr, sc, er, ec = self.tab.selection.normalized()
        else:
            sr, sc = self.tab.cursor.row, 0
            er = self.tab.cursor.row
        self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
        for r in range(sr, er + 1):
            self.tab.buffer.lines[r] = self.tab.buffer.lines[r].upper()
        self.tab.buffer.set_modified(True)

    def _command_toggle(self, args=None):
        if not args:
            return
        option = args[0].lower()
        if option in ("sidebar", "tree", "filetree"):
            self.sidebar_visible = not self.sidebar_visible
            if self.sidebar_visible:
                self._refresh_file_list()
        elif option in ("linenumbers", "linenos", "number"):
            self.show_line_numbers = not self.show_line_numbers
        elif option in ("wrap", "wordwrap"):
            self.word_wrap = not self.word_wrap
        elif option in ("whitespace", "ws"):
            self.show_whitespace = not self.show_whitespace

    def _command_map(self, args=None):
        self.status_message = "Key mapping not yet implemented"

    def _command_record(self, args=None):
        if self.is_recording:
            self.is_recording = False
            self.status_message = f"Recorded {len(self.macro_recording)} keys"
        else:
            self.is_recording = True
            self.macro_recording = []
            self.status_message = "Recording macro..."

    def _command_register(self, args=None):
        self.status_message = "Registers not yet implemented"

    def _command_diff(self, args=None):
        if not self.tab.filepath:
            self.status_message = "No file to diff"
            return
        try:
            import subprocess
            result = subprocess.run(
                ["git", "diff", "--no-color", self.tab.filepath],
                capture_output=True, text=True, timeout=5,
                cwd=str(Path(self.tab.filepath).parent)
            )
            if result.stdout:
                self.status_message = "Git diff available (see terminal)"
        except Exception:
            self.status_message = "Git not available"

    def _command_copy_path(self, args=None):
        if self.tab.filepath:
            self._clipboard_copy(self.tab.filepath)
            self.status_message = "Path copied to clipboard"

    def _command_git_log(self, args=None):
        if not self.tab.filepath:
            return
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10", self.tab.filepath],
                capture_output=True, text=True, timeout=5,
                cwd=str(Path(self.tab.filepath).parent)
            )
            if result.stdout:
                self.status_message = result.stdout.split("\n")[0][:50] if result.stdout.split("\n") else "No commits"
        except Exception:
            self.status_message = "Git not available"

    def _command_git_diff(self, args=None):
        self._command_diff(args)

    def _command_git_blame(self, args=None):
        if not self.tab.filepath:
            return
        try:
            result = subprocess.run(
                ["git", "blame", "--line-porcelain", "-L",
                 f"{self.tab.cursor.row + 1},{self.tab.cursor.row + 1}",
                 self.tab.filepath],
                capture_output=True, text=True, timeout=5,
                cwd=str(Path(self.tab.filepath).parent)
            )
            if result.stdout:
                for line in result.stdout.split("\n"):
                    if line.startswith("author "):
                        self.status_message = f"Author: {line[7:]}"
                        break
        except Exception:
            self.status_message = "Git not available"

    def _command_help(self, args=None):
        help_text = (
            "Commands: :w save | :q quit | :wq save+quit | :q! force quit | "
            ":e file open | :n new tab | :bn/bp next/prev tab | "
            ":set nu/nonu number | :goto N | :sort | "
            ":find text | :replace old new | :language lang | "
            ":toggle sidebar/number/wrap | :theme name | :tabsize N"
        )
        self.status_message = help_text[:120]

    def _command_about(self, args=None):
        self.status_message = "CodeView CLI Editor v3.0 | Curses Edition"

    # ── Move cursor ──

    def _move_cursor(self, drow: int, dcol: int):
        self.tab.cursor.row += drow
        self.tab.cursor.col += dcol
        self.tab.cursor.clamp(self.tab.buffer)
        self.tab.cursor.preferred_col = self.tab.cursor.col

    def _delete_forward_char(self):
        tab = self.tab
        tab.buffer.save_undo_state(tab.cursor.row, tab.cursor.col)
        tab.buffer.delete_forward(tab.cursor.row, tab.cursor.col)
        tab.cursor.clamp(tab.buffer)

    # ── Clipboard ──

    def _clipboard_copy(self, text: str):
        self._clipboard = text
        self._set_clipboard(text)

    def _clipboard_paste(self):
        if self.mode != EditorMode.INSERT:
            return
        text = self._get_clipboard()
        if text:
            self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
            self.tab.buffer.insert_text(self.tab.cursor.row, self.tab.cursor.col, text)
            self.tab.cursor.row += text.count("\n")
            last_line = text.split("\n")[-1]
            self.tab.cursor.col = len(last_line)
            self.tab.cursor.clamp(self.tab.buffer)

    def _clipboard_cut(self):
        if self.tab.selection.active:
            sr, sc, er, ec = self.tab.selection.normalized()
            self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
            text = self.tab.buffer.delete_range(sr, sc, er, ec)
            self._clipboard_copy(text)
            self.tab.cursor.row = sr
            self.tab.cursor.col = sc
            self.tab.cursor.clamp(self.tab.buffer)
            self.tab.selection.clear()

    def _clipboard_copy_selection(self):
        if self.tab.selection.active:
            sr, sc, er, ec = self.tab.selection.normalized()
            text = self.tab.buffer.get_text_range(sr, sc, er, ec)
            self._clipboard_copy(text)
            self.status_message = "Copied"

    def _duplicate_line(self):
        self.tab.buffer.save_undo_state(self.tab.cursor.row, self.tab.cursor.col)
        line = self.tab.buffer.get_line(self.tab.cursor.row)
        self.tab.buffer.lines.insert(self.tab.cursor.row + 1, line)
        self.tab.cursor.row += 1
        self.tab.buffer.set_modified(True)

    def _move_line_up(self):
        r = self.tab.cursor.row
        if r <= 0:
            return
        self.tab.buffer.save_undo_state(r, self.tab.cursor.col)
        self.tab.buffer.lines[r], self.tab.buffer.lines[r - 1] = \
            self.tab.buffer.lines[r - 1], self.tab.buffer.lines[r]
        self.tab.cursor.row -= 1
        self.tab.buffer.set_modified(True)

    def _move_line_down(self):
        r = self.tab.cursor.row
        if r >= self.tab.buffer.line_count - 1:
            return
        self.tab.buffer.save_undo_state(r, self.tab.cursor.col)
        self.tab.buffer.lines[r], self.tab.buffer.lines[r + 1] = \
            self.tab.buffer.lines[r + 1], self.tab.buffer.lines[r]
        self.tab.cursor.row += 1
        self.tab.buffer.set_modified(True)

    def _toggle_comment(self):
        r = self.tab.cursor.row
        self.tab.buffer.save_undo_state(r, self.tab.cursor.col)
        line = self.tab.buffer.get_line(r)
        stripped = line.lstrip()
        if stripped.startswith("#"):
            idx = line.index("#")
            self.tab.buffer.lines[r] = line[:idx] + line[idx + 1:]
        else:
            ind = len(line) - len(stripped)
            self.tab.buffer.lines[r] = line[:ind] + "# " + stripped
        self.tab.buffer.set_modified(True)


# ──────────────────────────────────────────────
# Launch function
# ──────────────────────────────────────────────

def launch_curses_editor(
    content: str = "",
    file_path: str = "",
    language: str = "",
    theme: str = "dark",
    workdir: str = ".",
) -> None:
    """Launch the curses-based code editor."""
    editor = CursesEditor(
        filepath=file_path,
        content=content,
        language=language,
        theme=theme,
        workdir=workdir,
    )
    editor.run()
