"""TUI Code Editor using Textual.

Provides full terminal-based code editing with syntax highlighting,
line numbers, search/replace, and multi-file support.
"""

from pathlib import Path
from typing import Optional, List

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Header,
    Footer,
    TextArea,
    Static,
    Input,
    Button,
    Label,
    Select,
    Tree,
    DirectoryTree,
)
from textual.screen import ModalScreen
from textual.binding import Binding
from textual import events
from textual.reactive import reactive
from textual.message import Message
from rich.syntax import Syntax
from rich.text import Text as RichText

from .highlighter import detect_language, get_available_themes


class SaveDialog(ModalScreen[str]):
    """Modal dialog for saving files."""

    def __init__(self, current_path: str = ""):
        super().__init__()
        self.current_path = current_path

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Save File As", classes="dialog-title"),
            Input(value=self.current_path, placeholder="Enter file path...", id="save_path"),
            Horizontal(
                Button("Save", variant="primary", id="btn_save"),
                Button("Cancel", variant="default", id="btn_cancel"),
                classes="dialog-buttons",
            ),
            classes="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_save":
            path = self.query_one("#save_path", Input).value
            if path:
                self.dismiss(path)
        elif event.button.id == "btn_cancel":
            self.dismiss("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value:
            self.dismiss(event.value)

    class CSS:
        CSS = """
        .dialog {
            width: 60;
            height: auto;
            padding: 1 2;
            background: $surface;
            border: solid $primary;
            align: center middle;
        }
        .dialog-title {
            text-align: center;
            padding: 1;
            text-style: bold;
            color: $primary;
        }
        .dialog-buttons {
            padding-top: 1;
            align: right middle;
        }
        #save_path {
            width: 100%;
            margin: 1 0;
        }
        Button {
            margin-left: 1;
        }
        """


class SearchDialog(ModalScreen[str]):
    """Modal dialog for searching text."""

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Search in File", classes="dialog-title"),
            Input(placeholder="Search text...", id="search_input"),
            Horizontal(
                Button("Find Next", variant="primary", id="btn_search"),
                Button("Cancel", variant="default", id="btn_cancel"),
                classes="dialog-buttons",
            ),
            classes="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_search":
            text = self.query_one("#search_input", Input).value
            self.dismiss(text)
        elif event.button.id == "btn_cancel":
            self.dismiss("")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    class CSS:
        CSS = """
        .dialog {
            width: 50;
            height: auto;
            padding: 1 2;
            background: $surface;
            border: solid $primary;
            align: center middle;
        }
        .dialog-title {
            text-align: center;
            padding: 1;
            text-style: bold;
            color: $primary;
        }
        .dialog-buttons {
            padding-top: 1;
            align: right middle;
        }
        #search_input {
            width: 100%;
            margin: 1 0;
        }
        Button {
            margin-left: 1;
        }
        """


class GotoLineDialog(ModalScreen[int]):
    """Modal dialog for jumping to a line."""

    def compose(self) -> ComposeResult:
        yield Container(
            Label("Go to Line", classes="dialog-title"),
            Input(placeholder="Enter line number...", id="goto_input", type="integer"),
            Horizontal(
                Button("Go", variant="primary", id="btn_go"),
                Button("Cancel", variant="default", id="btn_cancel"),
                classes="dialog-buttons",
            ),
            classes="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_go":
            try:
                line = int(self.query_one("#goto_input", Input).value)
                self.dismiss(line)
            except ValueError:
                self.dismiss(0)
        elif event.button.id == "btn_cancel":
            self.dismiss(0)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        try:
            self.dismiss(int(event.value))
        except ValueError:
            self.dismiss(0)

    class CSS:
        CSS = """
        .dialog {
            width: 40;
            height: auto;
            padding: 1 2;
            background: $surface;
            border: solid $primary;
            align: center middle;
        }
        .dialog-title {
            text-align: center;
            padding: 1;
            text-style: bold;
            color: $primary;
        }
        .dialog-buttons {
            padding-top: 1;
            align: right middle;
        }
        #goto_input {
            width: 100%;
            margin: 1 0;
        }
        Button {
            margin-left: 1;
        }
        """


class FileSelectDialog(ModalScreen[str]):
    """Modal dialog for selecting a file from a list."""

    def __init__(self, files: List[str]):
        super().__init__()
        self.files = files

    def compose(self) -> ComposeResult:
        options = [(f, f) for f in self.files]
        yield Container(
            Label("Select File to Open", classes="dialog-title"),
            Select(options, id="file_select"),
            Horizontal(
                Button("Open", variant="primary", id="btn_open"),
                Button("Cancel", variant="default", id="btn_cancel"),
                classes="dialog-buttons",
            ),
            classes="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_open":
            sel = self.query_one("#file_select", Select)
            if sel.value != Select.BLANK:
                self.dismiss(str(sel.value))
        elif event.button.id == "btn_cancel":
            self.dismiss("")

    class CSS:
        CSS = """
        .dialog {
            width: 50;
            height: auto;
            max-height: 30;
            padding: 1 2;
            background: $surface;
            border: solid $primary;
            align: center middle;
        }
        .dialog-title {
            text-align: center;
            padding: 1;
            text-style: bold;
            color: $primary;
        }
        .dialog-buttons {
            padding-top: 1;
            align: right middle;
        }
        #file_select {
            width: 100%;
            margin: 1 0;
        }
        Button {
            margin-left: 1;
        }
        """


class StatusBar(Static):
    """Custom status bar showing file info."""

    file_path = reactive("")
    language = reactive("")
    line_count = reactive(0)
    cursor_pos = reactive((1, 0))

    def watch_file_path(self, value: str) -> None:
        self.refresh()

    def watch_language(self, value: str) -> None:
        self.refresh()

    def watch_line_count(self, value: int) -> None:
        self.refresh()

    def watch_cursor_pos(self, value: tuple) -> None:
        self.refresh()

    def render(self) -> RichText:
        text = RichText()
        file_label = self.file_path if self.file_path else "Untitled"
        text.append(f" {file_label} ")
        if self.language:
            text.append(f"| {self.language} ")
        text.append(f"| {self.line_count} lines ")
        text.append(f"| Ln {self.cursor_pos[0]}, Col {self.cursor_pos[1]} ")
        return text


class CodeEditor(App):
    """A terminal-based code editor with syntax highlighting."""

    CSS = """
    #editor_container {
        height: 1fr;
    }
    #code_area {
        height: 1fr;
        border: none;
    }
    #status_bar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text;
    }
    #file_tree {
        width: 30;
        border-right: solid $primary;
        background: $surface;
        height: 1fr;
    }
    .hidden {
        display: none;
    }
    TextArea {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save", show=True),
        Binding("ctrl+o", "open_dialog", "Open", show=True),
        Binding("ctrl+f", "search", "Search", show=True),
        Binding("ctrl+g", "goto_line", "Go to Line", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+t", "toggle_tree", "Toggle File Tree", show=True),
        Binding("ctrl+n", "new_file", "New File", show=True),
        Binding("ctrl+b", "toggle_sidebar", "Toggle Sidebar", show=False),
        Binding("escape", "focus_editor", "Focus Editor", show=False),
    ]

    def __init__(
        self,
        content: str = "",
        file_path: str = "",
        language: str = "",
        theme: str = "monokai",
        workdir: str = ".",
    ):
        super().__init__()
        self.initial_content = content
        self.initial_file_path = file_path
        self.initial_language = language
        self.theme_name = theme
        self.workdir = workdir
        self.show_tree = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield Vertical(id="file_tree", classes="hidden")
            with Vertical(id="editor_container"):
                yield TextArea.code_editor(
                    self.initial_content,
                    id="code_area",
                    language=self.initial_language or None,
                )
        yield StatusBar(id="status_bar")
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        text_area = self.query_one("#code_area", TextArea)
        text_area.focus()

        # Set up status bar
        status_bar = self.query_one("#status_bar", StatusBar)
        if self.initial_file_path:
            status_bar.file_path = str(Path(self.initial_file_path).resolve())
        status_bar.language = self.initial_language or "text"
        status_bar.line_count = len(self.initial_content.split("\n"))

        # Set up file tree
        self._build_file_tree()

        # Watch for cursor changes
        self.set_interval(0.5, self._update_cursor_pos)

    def _update_cursor_pos(self) -> None:
        """Update the cursor position in the status bar."""
        text_area = self.query_one("#code_area", TextArea)
        status_bar = self.query_one("#status_bar", StatusBar)
        status_bar.cursor_pos = text_area.cursor_location
        status_bar.line_count = text_area.document.line_count

    def _build_file_tree(self) -> None:
        """Build the file tree for the working directory."""
        tree_container = self.query_one("#file_tree", Vertical)
        try:
            tree = DirectoryTree(self.workdir)
            tree_container.mount(tree)
        except Exception:
            pass

    def _get_text(self) -> str:
        """Get the current text from the editor."""
        text_area = self.query_one("#code_area", TextArea)
        return text_area.text

    def _set_text(self, text: str) -> None:
        """Set the text in the editor."""
        text_area = self.query_one("#code_area", TextArea)
        text_area.load_text(text)

    def _get_language(self) -> str:
        """Detect the language from the current file."""
        status_bar = self.query_one("#status_bar", StatusBar)
        path = status_bar.file_path
        if path:
            return detect_language(path, self._get_text())
        return "text"

    def action_save(self) -> None:
        """Save the current file."""
        status_bar = self.query_one("#status_bar", StatusBar)
        file_path = status_bar.file_path

        if not file_path or file_path == "Untitled":
            self.action_save_as()
            return

        try:
            content = self._get_text()
            Path(file_path).write_text(content, encoding="utf-8")
            self.notify(f"Saved: {file_path}", title="Save", severity="information")
        except Exception as e:
            self.notify(f"Failed to save: {e}", title="Error", severity="error")

    def action_save_as(self) -> None:
        """Save file with a new name."""

        def save_callback(path: str) -> None:
            if path:
                try:
                    content = self._get_text()
                    Path(path).write_text(content, encoding="utf-8")
                    status_bar = self.query_one("#status_bar", StatusBar)
                    status_bar.file_path = str(Path(path).resolve())
                    status_bar.language = self._get_language()
                    self.notify(f"Saved: {path}", title="Save", severity="information")
                except Exception as e:
                    self.notify(f"Failed to save: {e}", title="Error", severity="error")

        status_bar = self.query_one("#status_bar", StatusBar)
        dialog = SaveDialog(status_bar.file_path)
        self.push_screen(dialog, save_callback)

    def action_open_dialog(self) -> None:
        """Open a file dialog."""
        from .fileops import list_files

        files = list_files(self.workdir, recursive=True)

        def open_callback(selected: str) -> None:
            if selected:
                filepath = Path(self.workdir) / selected
                if filepath.is_file():
                    try:
                        content = filepath.read_text(encoding="utf-8")
                        self._set_text(content)
                        status_bar = self.query_one("#status_bar", StatusBar)
                        status_bar.file_path = str(filepath.resolve())
                        status_bar.language = detect_language(str(filepath), content)
                        self.notify(f"Opened: {filepath}", title="Open", severity="information")
                    except Exception as e:
                        self.notify(f"Failed to open: {e}", title="Error", severity="error")

        dialog = FileSelectDialog(files)
        self.push_screen(dialog, open_callback)

    def action_search(self) -> None:
        """Search for text in the file."""

        def search_callback(query: str) -> None:
            if query:
                text_area = self.query_one("#code_area", TextArea)
                text = self._get_text()
                idx = text.find(query)
                if idx == -1:
                    self.notify("Text not found", title="Search", severity="warning")
                else:
                    # Count lines to find line number
                    line_num = text[:idx].count("\n") + 1
                    text_area.cursor_location = (line_num, idx - text[:idx].rfind("\n") - 1 if "\n" in text[:idx] else idx)
                    self.notify(f"Found at line {line_num}", title="Search")

        dialog = SearchDialog()
        self.push_screen(dialog, search_callback)

    def action_goto_line(self) -> None:
        """Jump to a specific line."""

        def goto_callback(line: int) -> None:
            if line > 0:
                text_area = self.query_one("#code_area", TextArea)
                max_lines = text_area.document.line_count
                target = min(line, max_lines)
                text_area.cursor_location = (target, 0)
                self.notify(f"Jumped to line {target}", title="Go to Line")

        dialog = GotoLineDialog()
        self.push_screen(dialog, goto_callback)

    def action_toggle_tree(self) -> None:
        """Toggle the file tree sidebar."""
        self.show_tree = not self.show_tree
        tree = self.query_one("#file_tree", Vertical)
        if self.show_tree:
            tree.remove_class("hidden")
            if not tree.children:
                self._build_file_tree()
        else:
            tree.add_class("hidden")

    def action_toggle_sidebar(self) -> None:
        """Toggle the sidebar."""
        self.action_toggle_tree()

    def action_new_file(self) -> None:
        """Create a new blank file."""
        self._set_text("")
        status_bar = self.query_one("#status_bar", StatusBar)
        status_bar.file_path = "Untitled"
        status_bar.language = "text"
        self.notify("New file created", title="New File")

    def action_quit(self) -> None:
        """Quit with optional save prompt."""
        self.exit()

    def action_focus_editor(self) -> None:
        """Focus the editor text area."""
        text_area = self.query_one("#code_area", TextArea)
        text_area.focus()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection from the directory tree."""
        path = Path(str(event.path))
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
                self._set_text(content)
                status_bar = self.query_one("#status_bar", StatusBar)
                status_bar.file_path = str(path.resolve())
                status_bar.language = detect_language(str(path), content)
                self.notify(f"Opened: {path.name}", title="Open")
            except Exception as e:
                self.notify(f"Failed to open: {e}", title="Error", severity="error")


def launch_editor(
    content: str = "",
    file_path: str = "",
    language: str = "",
    theme: str = "monokai",
    workdir: str = ".",
    use_curses: bool = False,
) -> None:
    """Launch the TUI code editor.

    Args:
        content: Initial file content
        file_path: Path to the file being edited
        language: Programming language for syntax highlighting
        theme: Color theme name
        workdir: Working directory
        use_curses: If True, use the curses-based editor instead of Textual
    """
    if use_curses:
        from .editor_curses import launch_curses_editor
        launch_curses_editor(
            content=content,
            file_path=file_path,
            language=language,
            theme=theme,
            workdir=workdir,
        )
        return

    editor = CodeEditor(
        content=content,
        file_path=file_path,
        language=language,
        theme=theme,
        workdir=workdir,
    )
    editor.run()
