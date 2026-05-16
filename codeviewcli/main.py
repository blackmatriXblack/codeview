"""Main entry point for CodeView CLI.

codeview - A feature-rich CLI tool to view, edit, and fetch code
with syntax highlighting for 500+ programming languages.

Usage:
    codeview <file>              View a file with syntax highlighting
    codeview <url>               Fetch and view code from any code hosting platform
    codeview edit <file>         Open the TUI editor
    codeview tree <dir>          Show directory tree
    codeview search <q>          Search text in files
    codeview themes              List color themes
    codeview config              Manage configuration
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple

# Enable UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich import box

from . import __version__
from .highlighter import (
    detect_language,
    highlight_code,
    format_output,
    get_available_themes,
    get_available_languages,
)
from .fetcher import (
    fetch_repo_file,
    fetch_repo_tree,
    is_code_hosting_url,
    FetcherError,
)
from .fileops import (
    read_file,
    write_file,
    list_files,
    list_files_with_details,
    search_files,
    get_file_stats,
    tree_view,
)
from .themes import get_theme_info, list_themes_by_type, get_all_themes
from .config import (
    load_config,
    save_config,
    get_setting,
    set_setting,
    reset_config,
    export_config,
)

console = Console()


def print_banner():
    """Display the CodeView CLI banner."""
    banner = Text()
    banner.append("+==================================================+\n", style="bold cyan")
    banner.append("|          ", style="bold cyan")
    banner.append("CODEVIEW CLI", style="bold yellow")
    banner.append("                          |\n", style="bold cyan")
    banner.append("|        ", style="bold cyan")
    banner.append("View . Edit . Fetch . Highlight", style="bold green")
    banner.append("              |\n", style="bold cyan")
    banner.append("+==================================================+", style="bold cyan")
    console.print(banner)
    console.print()


def print_file_header(filepath: str, language: str, size: int = 0):
    """Print a file header with metadata."""
    path = Path(filepath)
    header_text = Text()
    header_text.append(" File: ", style="bold")
    header_text.append(str(path.resolve()), style="bold cyan")
    header_text.append(f"  |  Language: ", style="dim")
    header_text.append(language.title(), style="bold yellow")
    if size:
        size_str = format_size(size)
        header_text.append(f"  |  Size: ", style="dim")
        header_text.append(size_str, style="bold green")
    console.print(header_text)
    console.print("-" * min(console.width, 120))


def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def display_code(
    content: str,
    language: str = "text",
    filepath: str = "",
    theme: Optional[str] = None,
    line_numbers: Optional[bool] = None,
    start_line: int = 1,
    highlight_lines: Optional[List[int]] = None,
    show_header: bool = True,
):
    """Display code with syntax highlighting."""
    if theme is None:
        theme = get_setting("theme")
    if line_numbers is None:
        line_numbers = get_setting("line_numbers")

    # Truncate if too large
    max_size = get_setting("max_file_size_mb") * 1024 * 1024
    if len(content.encode("utf-8")) > max_size:
        content = content[:max_size]
        console.print("[bold yellow]Warning: File truncated (exceeds size limit)[/bold yellow]")

    if show_header and filepath:
        print_file_header(filepath, language, len(content.encode("utf-8")))

    syntax = format_output(
        code=content,
        language=language,
        theme=theme,
        line_numbers=line_numbers,
        start_line=start_line,
        highlight_lines=highlight_lines,
    )

    console.print(syntax)


def print_code_in_panel(
    content: str,
    language: str = "text",
    title: str = "",
    theme: Optional[str] = None,
    line_numbers: bool = True,
):
    """Display code inside a Rich Panel."""
    if theme is None:
        theme = get_setting("theme")

    syntax = format_output(
        code=content,
        language=language,
        theme=theme,
        line_numbers=line_numbers,
        title=title,
    )

    if title:
        console.print(Panel(syntax, title=title, border_style="cyan"))
    else:
        console.print(Panel(syntax, border_style="dim"))


@click.group(invoke_without_command=False)
@click.version_option(__version__, prog_name="codeview")
@click.pass_context
def cli(ctx):
    """CodeView CLI - View, edit, and fetch code with syntax highlighting.

    \b
    Commands:
      view <target>   View a file or URL with syntax highlighting
      edit <file>     Open the built-in TUI code editor
      tree <dir>      Show directory tree structure
      ls <dir>        List files in a directory
      search <q>      Search text in files
      info <file>     Show file information
      stats <dir>     Show code statistics
      diff <a> <b>     Show diff between two files
      fetch <url>     Fetch code from a hosting platform
      browse <url>    Browse a remote repository
      save <s> <d>    Save/copy a file
      clip <target>   Copy to clipboard
      themes          List available themes
      langs           List supported languages
      config          Manage configuration

    \b
    Examples:
      codeview view app.py
      codeview view --theme dracula main.js
      codeview view https://github.com/user/repo/blob/main/app.py
      codeview edit app.py
      codeview tree src/
      codeview search "TODO" .
    """


def _handle_url(
    url: str,
    language: Optional[str],
    theme: str,
    line_numbers: bool,
    highlight_lines: List[int],
    start_line: int,
):
    """Fetch and display code from a URL."""
    if not is_code_hosting_url(url):
        console.print("[bold red]Error:[/bold red] URL doesn't appear to be from a supported code hosting platform.")
        console.print("[dim]Supported: GitHub, GitLab, Bitbucket, Gitee, GitCode, SourceForge[/dim]")
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Fetching code...", total=None)
        try:
            content, filename, detected_lang = fetch_repo_file(url)
            progress.update(task, completed=True)
        except FetcherError as e:
            progress.update(task, completed=True)
            console.print(f"[bold red]Error:[/bold red] {e}")
            return

    lang = language or detect_language(filename, content) or detected_lang
    display_code(content, lang, filename, theme, line_numbers, start_line, highlight_lines)


def _handle_local_file(
    filepath: str,
    language: Optional[str],
    theme: str,
    line_numbers: bool,
    highlight_lines: List[int],
    start_line: int,
):
    """Read and display a local file."""
    path = Path(filepath)
    if not path.exists():
        console.print(f"[bold red]Error:[/bold red] File not found: {filepath}")
        return
    if path.is_dir():
        console.print(f"[bold yellow]'{filepath}' is a directory. Use 'codeview tree {filepath}' to browse.[/bold yellow]")
        return

    try:
        content = read_file(str(path))
        lang = language or detect_language(str(path), content)
        display_code(content, lang, str(path), theme, line_numbers, start_line, highlight_lines)
    except Exception as e:
        console.print(f"[bold red]Error reading file:[/bold red] {e}")


# =============================================================================
# View command (default when no subcommand given)
# =============================================================================

@cli.command("view")
@click.option("--theme", "-t", help="Color theme for syntax highlighting")
@click.option("--language", "-l", help="Force a specific language for highlighting")
@click.option("--no-line-numbers", is_flag=True, help="Hide line numbers")
@click.option("--highlight-line", "-H", type=int, multiple=True, help="Highlight specific lines")
@click.option("--start-line", "-s", type=int, default=1, help="Starting line number")
@click.argument("target")
def view_cmd(
    target: str,
    theme: Optional[str],
    language: Optional[str],
    no_line_numbers: bool,
    highlight_line: Tuple[int, ...],
    start_line: int,
):
    """View a file or URL with syntax highlighting.

    \b
    Examples:
      codeview view app.py
      codeview view --theme dracula main.js
      codeview view https://github.com/user/repo/blob/main/app.py
    """
    config = load_config()
    resolved_theme = theme or config.get("theme", "monokai")
    show_line_numbers = not no_line_numbers

    if target.startswith(("http://", "https://")):
        _handle_url(target, language, resolved_theme, show_line_numbers,
                     list(highlight_line), start_line)
    else:
        _handle_local_file(target, language, resolved_theme, show_line_numbers,
                           list(highlight_line), start_line)


# =============================================================================
# Edit command
# =============================================================================

@cli.command("edit")
@click.argument("filepath", required=False)
@click.option("--theme", "-t", help="Color theme for the editor")
@click.option("--curses", is_flag=True, help="Use the curses-based editor (more features)")
@click.pass_context
def edit_cmd(ctx, filepath: Optional[str], theme: Optional[str], curses: bool):
    """Open the TUI code editor.

    \b
    Examples:
      codeview edit
      codeview edit app.py
      codeview edit --theme nord script.js
      codeview edit --curses app.py
    """
    from .editor import launch_editor

    config = load_config()
    editor_theme = theme or config.get("theme", "monokai")

    if filepath:
        path = Path(filepath)
        if path.exists() and path.is_file():
            content = read_file(str(path))
            lang = detect_language(str(path), content)
            launch_editor(content, str(path), lang, editor_theme, str(path.parent), use_curses=curses)
        else:
            launch_editor("", filepath, "", editor_theme, ".", use_curses=curses)
    else:
        launch_editor("", "", "", editor_theme, ".", use_curses=curses)


# =============================================================================
# Tree command
# =============================================================================

@cli.command("tree")
@click.argument("directory", required=False, default=".")
@click.option("--depth", "-d", type=int, default=3, help="Maximum depth")
@click.option("--show-hidden/--no-show-hidden", default=False, help="Show hidden files")
@click.option("--dirs-only", is_flag=True, help="Show directories only")
def tree_cmd(directory: str, depth: int, show_hidden: bool, dirs_only: bool):
    """Display a directory tree structure.

    \b
    Examples:
      codeview tree
      codeview tree src/
      codeview tree --depth 2 --show-hidden
    """
    try:
        tree_str = tree_view(directory, max_depth=depth, show_hidden=show_hidden, dirs_only=dirs_only)
        console.print(Panel(tree_str, title=f"[bold]Directory Tree[/bold] - {Path(directory).resolve()}", border_style="cyan"))
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# List command
# =============================================================================

@cli.command("ls")
@click.argument("directory", required=False, default=".")
@click.option("--pattern", "-p", default="*", help="File pattern (e.g., *.py)")
@click.option("--recursive", "-r", is_flag=True, help="List files recursively")
@click.option("--details", "-l", is_flag=True, help="Show file details")
def list_cmd(directory: str, pattern: str, recursive: bool, details: bool):
    """List files in a directory.

    \b
    Examples:
      codeview ls
      codeview ls src/ --pattern "*.py"
      codeview ls -r -l
    """
    try:
        if details:
            files = list_files_with_details(directory, pattern, recursive)
            if not files:
                console.print("[dim]No files found.[/dim]")
                return

            table = Table(title=f"Files in {Path(directory).resolve()}", box=box.ROUNDED)
            table.add_column("Path", style="cyan")
            table.add_column("Size", style="green", justify="right")
            table.add_column("Modified", style="dim")
            table.add_column("Type", style="yellow")

            for f in files:
                size_str = format_size(f["size"])
                ext = f["extension"] if f["extension"] else "(none)"
                table.add_row(f["path"], size_str, f["modified"][:19], ext)

            console.print(table)
        else:
            files = list_files(directory, pattern, recursive)
            if not files:
                console.print("[dim]No files found.[/dim]")
                return

            file_list = []
            for f in files:
                ext = Path(f).suffix
                style = _get_extension_style(ext)
                file_list.append(f"[{style}]{f}[/{style}]")

            console.print(f"[bold]Files in {Path(directory).resolve()}:[/bold]")
            console.print(Columns(file_list, equal=False, expand=False))
            console.print(f"\n[dim]{len(files)} file(s)[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


def _get_extension_style(ext: str) -> str:
    """Get a color style for a file extension."""
    ext_styles = {
        ".py": "bold blue",
        ".js": "bold yellow",
        ".ts": "bold cyan",
        ".html": "bold red",
        ".css": "bold magenta",
        ".json": "bold green",
        ".md": "bold white",
        ".txt": "dim",
        ".sh": "bold green",
        ".rs": "bold red",
        ".go": "bold cyan",
        ".java": "bold yellow",
        ".cpp": "bold blue",
        ".c": "bold blue",
        ".rb": "bold red",
        ".php": "bold magenta",
        ".swift": "bold orange1",
        ".kt": "bold purple",
        ".yaml": "dim cyan",
        ".toml": "dim yellow",
        ".xml": "dim red",
        ".sql": "bold green",
        ".dockerfile": "bold blue",
    }
    return ext_styles.get(ext.lower(), "white")


# =============================================================================
# Search command
# =============================================================================

@cli.command("search")
@click.argument("query")
@click.argument("directory", required=False, default=".")
@click.option("--pattern", "-p", default="*", help="File pattern (e.g., *.py)")
@click.option("--case-sensitive/--no-case-sensitive", default=False, help="Case sensitive search")
def search_cmd(query: str, directory: str, pattern: str, case_sensitive: bool):
    """Search for text in files.

    \b
    Examples:
      codeview search "function" src/
      codeview search "TODO" . --pattern "*.py"
      codeview search "ClassName" --case-sensitive
    """
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"[cyan]Searching for '{query}'...", total=None)
            results = search_files(directory, query, pattern, True, case_sensitive)
            progress.update(task, completed=True)

        if not results:
            console.print(f"[dim]No results found for '{query}'[/dim]")
            return

        console.print(f"[bold]Found {len(results)} result(s) for '[yellow]{query}[/yellow]':[/bold]\n")

        current_file = ""
        for filepath, line_num, line_content in results:
            if filepath != current_file:
                current_file = filepath
                console.print(f"\n[bold cyan]  {filepath}[/bold cyan]")

            # Highlight the match
            display_line = line_content
            search_term = query if case_sensitive else query
            for term in [search_term, search_term.lower(), search_term.upper(), search_term.capitalize()]:
                if term in display_line:
                    display_line = display_line.replace(term, f"[bold yellow on #333333]{term}[/bold yellow on #333333]")
                    break

            console.print(f"  [dim]{line_num:>4}[/dim] │ {display_line.strip()}")

        console.print(f"\n[dim]{len(results)} match(es) in {len(set(r[0] for r in results))} file(s)[/dim]")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# Info command
# =============================================================================

@cli.command("info")
@click.argument("filepath")
def info_cmd(filepath: str):
    """Show detailed information about a file.

    \b
    Example:
      codeview info app.py
    """
    try:
        stats = get_file_stats(filepath)
        content = read_file(filepath)
        lang = detect_language(filepath, content)

        table = Table(title=f"[bold]File Info: {Path(filepath).name}[/bold]", box=box.ROUNDED)
        table.add_column("Property", style="bold cyan")
        table.add_column("Value", style="white")

        table.add_row("Full Path", stats["path"])
        table.add_row("Language", lang.title())
        table.add_row("Size", stats["size_human"])
        table.add_row("Extension", stats["extension"] or "(none)")
        table.add_row("Lines", str(len(content.splitlines())))
        table.add_row("Chars", str(len(content)))
        table.add_row("Binary", "Yes" if stats["is_binary"] else "No")
        table.add_row("Created", stats["created"])
        table.add_row("Modified", stats["modified"])
        table.add_row("Parent Dir", stats["parent_dir"])

        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# Stats command
# =============================================================================

@cli.command("stats")
@click.argument("directory", required=False, default=".")
@click.option("--pattern", "-p", default="*", help="File pattern (e.g., *.py)")
@click.option("--recursive/--no-recursive", default=True, help="Scan recursively")
def stats_cmd(directory: str, pattern: str, recursive: bool):
    """Show code statistics for a directory.

    \b
    Example:
      codeview stats src/
      codeview stats . --pattern "*.py"
    """
    try:
        files = list_files_with_details(directory, pattern, recursive)
        if not files:
            console.print("[dim]No files found.[/dim]")
            return

        total_size = sum(f["size"] for f in files)
        total_files = len(files)
        binary_count = sum(1 for f in files if f["is_binary"])

        # Count by extension
        ext_counts = {}
        for f in files:
            ext = f["extension"] or "(none)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

        # Count lines for text files
        total_lines = 0
        base = Path(directory).resolve()
        for f in files:
            if not f["is_binary"]:
                try:
                    fpath = base / f["path"]
                    content = fpath.read_text(encoding="utf-8")
                    total_lines += len(content.splitlines())
                except Exception:
                    pass

        table = Table(title=f"[bold]Code Statistics: {Path(directory).resolve()}[/bold]", box=box.ROUNDED)
        table.add_column("Metric", style="bold cyan")
        table.add_column("Value", style="white", justify="right")

        table.add_row("Total Files", str(total_files))
        table.add_row("Total Size", format_size(total_size))
        table.add_row("Total Lines", f"{total_lines:,}")
        table.add_row("Binary Files", str(binary_count))
        table.add_row("Text Files", str(total_files - binary_count))
        table.add_row("Average Size", format_size(total_size // max(total_files, 1)))

        console.print(table)

        # Extension breakdown
        if len(ext_counts) > 1:
            console.print("\n[bold]File Types:[/bold]")
            ext_table = Table(box=box.SIMPLE)
            ext_table.add_column("Extension", style="cyan")
            ext_table.add_column("Count", style="yellow", justify="right")
            ext_table.add_column("%", style="dim", justify="right")
            for ext, count in sorted(ext_counts.items(), key=lambda x: x[1], reverse=True)[:15]:
                pct = (count / total_files) * 100
                ext_table.add_row(ext, str(count), f"{pct:.1f}%")
            console.print(ext_table)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# Themes command
# =============================================================================

@cli.command("themes")
@click.option("--type", "-y", "theme_type", type=click.Choice(["dark", "light", "all"]), default="all", help="Filter by theme type")
@click.option("--set", "-s", "set_theme", help="Set default theme")
def themes_cmd(theme_type: str, set_theme: Optional[str]):
    """List or set available color themes.

    \b
    Examples:
      codeview themes
      codeview themes --type dark
      codeview themes --set dracula
    """
    if set_theme:
        all_themes = get_all_themes()
        if set_theme not in all_themes:
            console.print(f"[bold red]Theme '{set_theme}' not found.[/bold red]")
            console.print(f"[dim]Use 'codeview themes' to see available themes.[/dim]")
            return
        set_setting("theme", set_theme)
        console.print(f"[bold green]Theme set to '{set_theme}'[/bold green]")
        return

    themes = list_themes_by_type(theme_type)

    if not themes:
        console.print("[dim]No themes found.[/dim]")
        return

    config = load_config()
    current_theme = config.get("theme", "monokai")

    console.print(f"[bold]Available Themes ({len(themes)})[/bold]")
    console.print(f"[dim]Current: [bold]{current_theme}[/bold][/dim]\n")

    # Show popular themes first
    popular_ids = {"monokai", "one-dark", "dracula", "github-dark", "github-light",
                   "nord", "solarized-dark", "solarized-light", "gruvbox-dark", "material"}

    popular = [t for t in themes if t["id"] in popular_ids]
    other = [t for t in themes if t["id"] not in popular_ids]

    if popular:
        console.print("[bold]Popular Themes:[/bold]")
        for t in popular:
            marker = ">" if t["id"] == current_theme else " "
            type_icon = "[D]" if t["type"] == "dark" else "[L]"
            console.print(f"  {marker} [{t['type']}]{type_icon}[/{t['type']}] [bold]{t['name']}[/bold] [dim]({t['id']})[/dim]")

    if other:
        console.print("\n[bold]All Themes:[/bold]")
        cols = []
        for t in other:
            marker = ">" if t["id"] == current_theme else " "
            type_icon = "[D]" if t["type"] == "dark" else "[L]"
            cols.append(f"  {marker} [{t['type']}]{type_icon}[/{t['type']}] [bold]{t['id']}[/bold]")

        # Display in columns
        from rich.columns import Columns
        console.print(Columns(cols[:50], equal=False, expand=False))
        if len(cols) > 50:
            console.print(f"\n[dim]... and {len(cols) - 50} more[/dim]")


# =============================================================================
# Languages command
# =============================================================================

@cli.command("langs")
@click.option("--search", "-s", help="Search for a language")
def langs_cmd(search: Optional[str]):
    """List all supported programming languages.

    \b
    Examples:
      codeview langs
      codeview langs --search python
    """
    languages = get_available_languages()

    if search:
        languages = [l for l in languages if search.lower() in l[0].lower()]

    if not languages:
        console.print("[dim]No languages found.[/dim]")
        return

    console.print(f"[bold]Supported Languages ({len(languages)})[/bold]\n")

    table = Table(box=box.ROUNDED, show_header=True)
    table.add_column("Language", style="bold cyan")
    table.add_column("Aliases", style="dim")
    table.add_column("Extensions", style="green")

    for name, aliases, exts in languages[:100]:
        table.add_row(name, aliases[:40] if aliases else "-", exts[:40] if exts else "-")

    console.print(table)

    if len(languages) > 100:
        console.print(f"\n[dim]... and {len(languages) - 100} more languages. Use --search to filter.[/dim]")


# =============================================================================
# Config command
# =============================================================================

@cli.command("config")
@click.option("--list", "-l", "list_config", is_flag=True, help="List current configuration")
@click.option("--get", "-g", "get_key", help="Get a specific config value")
@click.option("--set", "-s", "set_pair", nargs=2, help="Set a config key=value pair")
@click.option("--reset", is_flag=True, help="Reset configuration to defaults")
@click.option("--export", "export_cfg", is_flag=True, help="Export configuration as JSON")
def config_cmd(
    list_config: bool,
    get_key: Optional[str],
    set_pair: Optional[Tuple[str, str]],
    reset: bool,
    export_cfg: bool,
):
    """Manage CodeView CLI configuration.

    \b
    Examples:
      codeview config --list
      codeview config --get theme
      codeview config --set theme dracula
      codeview config --reset
    """
    if reset:
        reset_config()
        console.print("[bold green]Configuration reset to defaults.[/bold green]")
        return

    if export_cfg:
        console.print(export_config())
        return

    if get_key:
        value = get_setting(get_key)
        console.print(f"[bold cyan]{get_key}[/bold cyan] = [bold yellow]{value}[/bold yellow]")
        return

    if set_pair:
        key, value = set_pair
        # Convert value to appropriate type
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        elif value.isdigit():
            value = int(value)
        set_setting(key, value)
        console.print(f"[bold green]{key} = {value}[/bold green]")
        return

    if list_config or True:
        config = load_config()
        table = Table(title="[bold]CodeView CLI Configuration[/bold]", box=box.ROUNDED)
        table.add_column("Key", style="bold cyan")
        table.add_column("Value", style="yellow")

        for key, value in config.items():
            if isinstance(value, bool):
                display = "[green]True[/green]" if value else "[red]False[/red]"
            else:
                display = str(value)
            table.add_row(key, display)

        table.add_row("Config File", str(Path.home() / ".config" / "codeviewcli" / "config.json"))
        console.print(table)


# =============================================================================
# Fetch command (explicit)
# =============================================================================

@cli.command("fetch")
@click.argument("url")
@click.option("--save", "-s", "save_path", help="Save the fetched code to a file")
@click.option("--theme", "-t", help="Theme for display")
@click.option("--language", "-l", help="Force language for highlighting")
@click.option("--no-display", is_flag=True, help="Don't display, just save")
def fetch_cmd(
    url: str,
    save_path: Optional[str],
    theme: Optional[str],
    language: Optional[str],
    no_display: bool,
):
    """Fetch code from a URL.

    \b
    Supported platforms:
    - GitHub (github.com)
    - GitLab (gitlab.com)
    - Bitbucket (bitbucket.org)
    - Gitee (gitee.com)
    - GitCode (gitcode.com)
    - SourceForge (sourceforge.net)
    - Any raw code URL

    \b
    Examples:
      codeview fetch https://github.com/user/repo/blob/main/app.py
      codeview fetch https://gitlab.com/user/repo/-/blob/main/src/main.py --save local.py
    """
    config = load_config()
    display_theme = theme or config.get("theme", "monokai")

    if not is_code_hosting_url(url):
        console.print("[bold yellow]URL doesn't appear to be from a known code hosting platform.[/bold yellow]")
        console.print("[dim]Attempting to fetch anyway...[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Fetching code...", total=None)
        try:
            content, filename, detected_lang = fetch_repo_file(url)
            progress.update(task, completed=True)
        except FetcherError as e:
            progress.update(task, completed=True)
            console.print(f"[bold red]Error:[/bold red] {e}")
            return

    lang = language or detect_language(filename, content) or detected_lang

    if save_path:
        try:
            write_file(save_path, content)
            console.print(f"[bold green]Saved to:[/bold green] {save_path}")
        except Exception as e:
            console.print(f"[bold red]Error saving:[/bold red] {e}")
            return

    if not no_display:
        display_code(content, lang, filename, display_theme)


# =============================================================================
# Save command
# =============================================================================

@cli.command("save")
@click.argument("source")
@click.argument("destination")
def save_cmd(source: str, destination: str):
    """Save/copy a file or fetched code to a new location.

    \b
    Examples:
      codeview save app.py backup/app.py
      codeview save https://github.com/user/repo/blob/main/app.py local.py
    """
    if source.startswith(("http://", "https://")):
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Fetching code...", total=None)
            try:
                content, filename, _ = fetch_repo_file(source)
                progress.update(task, completed=True)
            except FetcherError as e:
                progress.update(task, completed=True)
                console.print(f"[bold red]Error:[/bold red] {e}")
                return
    else:
        try:
            content = read_file(source)
        except Exception as e:
            console.print(f"[bold red]Error reading source:[/bold red] {e}")
            return

    try:
        write_file(destination, content)
        console.print(f"[bold green]Saved to:[/bold green] {destination}")
        console.print(f"[dim]{len(content.splitlines())} lines, {format_size(len(content.encode('utf-8')))}[/dim]")
    except Exception as e:
        console.print(f"[bold red]Error saving:[/bold red] {e}")


# =============================================================================
# Browse command (explore repo files)
# =============================================================================

@cli.command("browse")
@click.argument("url")
@click.option("--filter", "-f", "file_filter", default="*", help="Filter files (e.g., *.py)")
def browse_cmd(url: str, file_filter: str):
    """Browse files in a remote repository.

    Lists all files in a repository and lets you view them interactively.

    \b
    Examples:
      codeview browse https://github.com/user/repo
      codeview browse https://gitlab.com/user/repo --filter "*.py"
    """
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Fetching repository file tree...", total=None)
            files, platform, owner, repo = fetch_repo_tree(url)
            progress.update(task, completed=True)
    except FetcherError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        return

    # Filter files
    if file_filter != "*":
        import fnmatch
        files = [f for f in files if fnmatch.fnmatch(f, file_filter)]

    if not files:
        console.print("[dim]No files found matching the filter.[/dim]")
        return

    console.print(f"[bold]Repository:[/bold] [cyan]{owner}/{repo}[/cyan]")
    console.print(f"[bold]Platform:[/bold] [yellow]{platform.title()}[/yellow]")
    console.print(f"[bold]Files:[/bold] [green]{len(files)}[/green]\n")

    # Group files by directory
    from collections import defaultdict
    dirs = defaultdict(list)
    for f in files:
        dir_name = str(Path(f).parent) or "."
        dirs[dir_name].append(Path(f).name)

    for directory in sorted(dirs.keys()):
        console.print(f"[bold cyan]{directory}/[/bold cyan]")
        for fname in sorted(dirs[directory])[:10]:
            ext = Path(fname).suffix
            style = _get_extension_style(ext)
            console.print(f"  [{style}]{fname}[/{style}]")
        if len(dirs[directory]) > 10:
            console.print(f"  [dim]... and {len(dirs[directory]) - 10} more[/dim]")
        console.print()

    console.print(f"[dim]To view a file, use: codeview fetch <repo-url>/blob/main/<file-path>[/dim]")


# =============================================================================
# Diff command
# =============================================================================

@cli.command("diff")
@click.argument("file_a")
@click.argument("file_b")
@click.option("--context", "-c", type=int, default=3, help="Context lines")
def diff_cmd(file_a: str, file_b: str, context: int):
    """Show differences between two files.

    \b
    Example:
      codeview diff old.py new.py
    """
    try:
        content_a = read_file(file_a).splitlines()
        content_b = read_file(file_b).splitlines()
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        return

    import difflib
    differ = difflib.unified_diff(
        content_a, content_b,
        fromfile=file_a, tofile=file_b,
        n=context,
    )

    output_lines = list(differ)

    if not output_lines:
        console.print("[dim]Files are identical.[/dim]")
        return

    for line in output_lines:
        if line.startswith("---") or line.startswith("+++"):
            console.print(f"[bold]{line}[/bold]")
        elif line.startswith("@@"):
            console.print(f"[bold cyan]{line}[/bold cyan]")
        elif line.startswith("+"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-"):
            console.print(f"[red]{line}[/red]")
        else:
            console.print(f"[dim]{line}[/dim]")


# =============================================================================
# Clipboard command
# =============================================================================

@cli.command("clip")
@click.argument("target")
def clip_cmd(target: str):
    """Copy file content or URL code to clipboard.

    \b
    Example:
      codeview clip app.py
      codeview clip https://github.com/user/repo/blob/main/app.py
    """
    try:
        import subprocess
    except ImportError:
        pass

    if target.startswith(("http://", "https://")):
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Fetching code...", total=None)
            try:
                content, filename, _ = fetch_repo_file(target)
                progress.update(task, completed=True)
            except FetcherError as e:
                progress.update(task, completed=True)
                console.print(f"[bold red]Error:[/bold red] {e}")
                return
    else:
        try:
            content = read_file(target)
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            return

    try:
        if sys.platform == "win32":
            subprocess.run(["clip"], input=content, text=True, shell=True)
        elif sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=content, text=True)
        else:
            subprocess.run(["xclip", "-selection", "clipboard"], input=content, text=True)
        console.print(f"[bold green]Copied to clipboard![/bold green] ({len(content.splitlines())} lines)")
    except Exception as e:
        console.print(f"[bold red]Failed to copy to clipboard:[/bold red] {e}")


# =============================================================================
# Format command
# =============================================================================

@cli.command("format")
@click.argument("filepath")
@click.option("--in-place", "-i", "in_place", is_flag=True, help="Format file in-place")
@click.option("--indent", type=int, default=4, help="Indentation width")
@click.pass_context
def format_cmd(ctx, filepath: str, in_place: bool, indent: int):
    """Basic code formatting (indentation normalization).

    \b
    Examples:
      codeview format app.py
      codeview format app.py --in-place
      codeview format app.py --indent 2
    """
    path = Path(filepath)
    if not path.exists():
        console.print(f"[bold red]Error:[/bold red] File not found: {filepath}")
        return
    if not path.is_file():
        console.print(f"[bold red]Error:[/bold red] Not a file: {filepath}")
        return
    try:
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        formatted = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                formatted.append("")
                continue
            leading = len(line) - len(line.lstrip())
            new_indent = (leading // indent) * indent
            new_line = " " * new_indent + stripped
            formatted.append(new_line)
        result = "\n".join(formatted) + "\n" if content.endswith("\n") else "\n".join(formatted)

        if in_place:
            path.write_text(result, encoding="utf-8")
            console.print(f"[bold green]Formatted:[/bold green] {filepath}")
        else:
            display_code(result, detect_language(filepath, result), filepath, theme=get_setting("theme"))
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# Hex command
# =============================================================================

@cli.command("hex")
@click.argument("filepath")
@click.option("--offset", "-o", type=int, default=0, help="Starting byte offset")
@click.option("--size", "-s", type=int, default=65536, help="Bytes to display")
@click.option("--bytes-per-row", "-b", type=int, default=16, help="Bytes per row")
def hex_cmd(filepath: str, offset: int, size: int, bytes_per_row: int):
    """Display a hex dump of a binary file.

    \b
    Examples:
      codeview hex app.exe
      codeview hex data.bin --offset 1024 --size 512
      codeview hex file.bin --bytes-per-row 32
    """
    from .hexview import view_hex_file
    path = Path(filepath)
    if not path.exists():
        console.print(f"[bold red]Error:[/bold red] File not found: {filepath}")
        return
    try:
        result = view_hex_file(filepath, max_bytes=size, offset=offset,
                               bytes_per_row=bytes_per_row, rich_output=True)
        if result:
            console.print(Panel(result, title=f"[bold]Hex: {path.name}[/bold]", border_style="cyan"))
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# Base64 command
# =============================================================================

@cli.command("base64")
@click.argument("action", type=click.Choice(["encode", "decode", "e", "d"]))
@click.argument("target")
@click.option("--output", "-o", help="Output file path")
def base64_cmd(action: str, target: str, output: Optional[str]):
    """Base64 encode or decode strings and files.

    \b
    Examples:
      codeview base64 encode "Hello World"
      codeview base64 encode app.py
      codeview base64 decode "SGVsbG8="
      codeview base64 decode data.b64 --output data.bin
    """
    import base64
    action = action[0]
    path = Path(target)
    if path.exists() and path.is_file():
        content = path.read_bytes()
    else:
        content = target.encode("utf-8")

    try:
        if action == "e":
            result = base64.b64encode(content).decode("ascii")
        else:
            result = base64.b64decode(content)

        if output:
            out_path = Path(output)
            if isinstance(result, str):
                out_path.write_text(result, encoding="ascii")
            else:
                out_path.write_bytes(result)
            console.print(f"[bold green]Saved to:[/bold green] {output}")
        else:
            if isinstance(result, bytes):
                try:
                    result = result.decode("utf-8")
                    console.print(Panel(result, title="Decoded", border_style="green"))
                except UnicodeDecodeError:
                    console.print(f"[dim]Binary data ({len(result)} bytes)[/dim]")
            else:
                console.print(Panel(result, title="Encoded", border_style="cyan"))
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# Hash command
# =============================================================================

@cli.command("hash")
@click.argument("filepath")
@click.option("--algorithm", "-a", type=click.Choice(["md5", "sha1", "sha256", "sha512", "all"]),
              default="sha256", help="Hash algorithm")
def hash_cmd(filepath: str, algorithm: str):
    """Compute hash checksums for a file.

    \b
    Examples:
      codeview hash app.py
      codeview hash app.py --algorithm sha1
      codeview hash app.py --algorithm all
    """
    import hashlib
    path = Path(filepath)
    if not path.exists() or not path.is_file():
        console.print(f"[bold red]Error:[/bold red] File not found: {filepath}")
        return
    try:
        data = path.read_bytes()
        algorithms = {"md5": hashlib.md5, "sha1": hashlib.sha1,
                      "sha256": hashlib.sha256, "sha512": hashlib.sha512}
        if algorithm == "all":
            algs = algorithms.keys()
        else:
            algs = [algorithm]
        table = Table(title=f"[bold]Hash: {path.name}[/bold]", box=box.ROUNDED)
        table.add_column("Algorithm", style="bold cyan")
        table.add_column("Hash", style="yellow")
        for alg in algs:
            h = algorithms[alg](data).hexdigest()
            table.add_row(alg.upper(), h)
        console.print(table)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# Watch command
# =============================================================================

@cli.command("watch")
@click.argument("directory", required=False, default=".")
@click.option("--pattern", "-p", default="*", help="File pattern to watch")
@click.option("--duration", "-d", type=int, default=None, help="Duration in seconds")
@click.option("--interval", "-i", type=float, default=1.0, help="Poll interval")
def watch_cmd(directory: str, pattern: str, duration: Optional[int], interval: float):
    """Watch a directory for file changes.

    \b
    Examples:
      codeview watch src/
      codeview watch . --pattern "*.py"
      codeview watch src/ --duration 60
    """
    from .watcher import watch_directory
    try:
        def on_change(event_type: str, filepath: str):
            icon = {"created": "[green]+[/green]", "modified": "[yellow]~[/yellow]",
                    "deleted": "[red]-[/red]"}.get(event_type, "?")
            console.print(f"  {icon} {filepath}")
        patterns = [pattern] if pattern != "*" else None
        events = watch_directory(directory, on_change=on_change,
                                 patterns=patterns, duration=duration,
                                 poll_interval=interval)
        console.print(f"\n[dim]Watched for {events} change(s)[/dim]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# Snippets command
# =============================================================================

@cli.command("snippets")
@click.argument("action", required=False, default="list")
@click.option("--language", "-l", help="Filter by language")
@click.option("--add", "-a", nargs=4, metavar="LANG NAME PREFIX DESC",
              help="Add a snippet: LANG NAME PREFIX DESC")
@click.option("--remove", "-r", nargs=2, metavar="LANG NAME",
              help="Remove a snippet: LANG NAME")
@click.option("--export", "-e", "export_path", help="Export snippets to file")
@click.option("--import", "-i", "import_path", help="Import snippets from file")
def snippets_cmd(action: str, language: Optional[str], add: Optional[Tuple[str, str, str, str]],
                 remove: Optional[Tuple[str, str]], export_path: Optional[str],
                 import_path: Optional[str]):
    """Manage code snippets.

    \b
    Examples:
      codeview snippets
      codeview snippets --language python
      codeview snippets --add python mycls cls "My class snippet"
      codeview snippets --remove python mycls
      codeview snippets --export snippets.json
      codeview snippets --import my_snippets.json
    """
    from .snippets import (list_snippets, add_snippet, remove_snippet,
                           export_snippets, import_snippets, get_languages)

    if add:
        lang, name, prefix, desc = add
        add_snippet(lang, name, prefix, desc, "")
        console.print(f"[bold green]Added snippet:[/bold green] {lang}/{name}")
        return
    if remove:
        lang, name = remove
        if remove_snippet(lang, name):
            console.print(f"[bold green]Removed snippet:[/bold green] {lang}/{name}")
        else:
            console.print(f"[bold yellow]Snippet not found:[/bold yellow] {lang}/{name}")
        return
    if export_path:
        export_snippets(export_path)
        console.print(f"[bold green]Exported snippets to:[/bold green] {export_path}")
        return
    if import_path:
        count = import_snippets(import_path)
        console.print(f"[bold green]Imported {count} snippet(s)[/bold green]")
        return

    snippets = list_snippets(language)
    if not snippets:
        console.print("[dim]No snippets found. Use --add to create one.[/dim]")
        langs = get_languages()
        if langs:
            console.print(f"[dim]Available languages: {', '.join(langs)}[/dim]")
        return
    table = Table(title="[bold]Code Snippets[/bold]", box=box.ROUNDED)
    table.add_column("Language", style="bold cyan")
    table.add_column("Name", style="bold yellow")
    table.add_column("Prefix", style="green")
    table.add_column("Description", style="dim")
    for s in snippets:
        table.add_row(s.get("language", ""), s.get("name", ""),
                      s.get("prefix", ""), s.get("description", "")[:50])
    console.print(table)


# =============================================================================
# History command
# =============================================================================

@cli.command("history")
@click.option("--limit", "-n", type=int, default=20, help="Number of entries")
@click.option("--search", "-s", help="Search history")
@click.option("--clear", is_flag=True, help="Clear history")
@click.option("--stats", "show_stats", is_flag=True, help="Show statistics")
@click.option("--most", "show_most", is_flag=True, help="Show most opened files")
def history_cmd(limit: int, search: Optional[str], clear: bool,
                show_stats: bool, show_most: bool):
    """View and manage file open history.

    \b
    Examples:
      codeview history
      codeview history --limit 10
      codeview history --search todo.py
      codeview history --clear
      codeview history --stats
    """
    from .history import (get_history, search_history, clear_history,
                          get_stats, get_most_opened)

    if clear:
        count = clear_history()
        console.print(f"[bold green]Cleared {count} history entries[/bold green]")
        return
    if show_stats:
        stats = get_stats()
        console.print(f"[bold]History Stats[/bold]")
        console.print(f"  Total entries: [yellow]{stats['total']}[/yellow]")
        console.print(f"  Unique files: [yellow]{stats['unique_files']}[/yellow]")
        if stats["languages"]:
            console.print(f"  [bold]Languages:[/bold]")
            for lang, count in list(stats["languages"].items())[:10]:
                console.print(f"    {lang}: {count}")
        return
    if show_most:
        most = get_most_opened(limit)
        table = Table(title="[bold]Most Opened Files[/bold]", box=box.ROUNDED)
        table.add_column("File", style="bold cyan")
        table.add_column("Count", style="yellow", justify="right")
        table.add_column("Language", style="green")
        for entry in most:
            name = entry.get("name", Path(entry["path"]).name)
            table.add_row(name, str(entry["count"]), entry.get("language", ""))
        console.print(table)
        return

    if search:
        entries = search_history(search)
    else:
        entries = get_history(limit)
    if not entries:
        console.print("[dim]No history entries.[/dim]")
        return
    table = Table(title="[bold]File History[/bold]", box=box.ROUNDED)
    table.add_column("#", style="dim", justify="right")
    table.add_column("File", style="bold cyan")
    table.add_column("Language", style="yellow")
    table.add_column("Lines", style="green", justify="right")
    table.add_column("Last Opened", style="dim")
    for i, entry in enumerate(entries, 1):
        name = entry.get("name", Path(entry["path"]).name)
        ts = entry.get("timestamp", "")[:19]
        table.add_row(str(i), name, entry.get("language", ""),
                      str(entry.get("lines", "")), ts)
    console.print(table)


# =============================================================================
# Notes command
# =============================================================================

@cli.command("notes")
@click.argument("action", required=False, default="list")
@click.option("--tag", "-t", help="Filter by tag")
@click.option("--create", "-c", nargs=2, metavar="TITLE CONTENT",
              help="Create a note: TITLE CONTENT")
@click.option("--read", "-r", "read_id", help="Read a note by ID")
@click.option("--delete", "-d", "delete_id", help="Delete a note by ID")
@click.option("--search", "-s", "search_query", help="Search notes")
@click.option("--tags", "list_tags", is_flag=True, help="List all tags")
def notes_cmd(action: str, tag: Optional[str], create: Optional[Tuple[str, str]],
              read_id: Optional[str], delete_id: Optional[str],
              search_query: Optional[str], list_tags: bool):
    """Manage quick notes.

    \b
    Examples:
      codeview notes
      codeview notes --tag todo
      codeview notes --create "My Note" "Some content"
      codeview notes --read 20240501_120000
      codeview notes --delete 20240501_120000
      codeview notes --search "keyword"
      codeview notes --tags
    """
    from .notes import (list_notes, create_note, get_note, delete_note,
                        search_notes, get_all_tags)

    if list_tags:
        tags = get_all_tags()
        if tags:
            console.print("[bold]All Tags:[/bold]")
            for t in tags:
                console.print(f"  [cyan]#{t}[/cyan]")
        else:
            console.print("[dim]No tags found.[/dim]")
        return
    if create:
        title, content = create
        note = create_note(title, content)
        console.print(f"[bold green]Note created:[/bold green] {title}")
        console.print(f"[dim]ID: {note['id']}[/dim]")
        return
    if read_id:
        note = get_note(read_id)
        if note:
            console.print(Panel(note.get("content", ""),
                               title=f"[bold]{note['title']}[/bold]",
                               border_style="cyan"))
            tags_str = " ".join(f"#{t}" for t in note.get("tags", []))
            if tags_str:
                console.print(f"[dim]{tags_str}[/dim]")
        else:
            console.print(f"[bold yellow]Note not found:[/bold yellow] {read_id}")
        return
    if delete_id:
        if delete_note(delete_id):
            console.print(f"[bold green]Note deleted[/bold green]")
        else:
            console.print(f"[bold yellow]Note not found[/bold yellow]")
        return
    if search_query:
        notes = search_notes(search_query)
    else:
        notes = list_notes(tag)
    if not notes:
        console.print("[dim]No notes found.[/dim]")
        return
    table = Table(title="[bold]Notes[/bold]", box=box.ROUNDED)
    table.add_column("ID", style="dim")
    table.add_column("Title", style="bold cyan")
    table.add_column("Tags", style="yellow")
    table.add_column("Modified", style="dim")
    for n in notes:
        tags_str = ", ".join(n.get("tags", []))
        ts = n.get("modified", "")[:16]
        table.add_row(n["id"][:16], n["title"][:40], tags_str, ts)
    console.print(table)


# =============================================================================
# REPL command
# =============================================================================

@cli.command("repl")
@click.option("--theme", "-t", help="Syntax highlighting theme")
def repl_cmd(theme: Optional[str]):
    """Launch an interactive Python REPL with syntax highlighting.

    \b
    Example:
      codeview repl
      codeview repl --theme nord
    """
    import code
    from rich.console import Console as RichConsole
    from rich.syntax import Syntax
    repl_console = RichConsole(highlight=False)

    class RichConsoleInteractor(code.InteractiveConsole):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.theme = theme or get_setting("theme")

    variables = {"__name__": "__console__", "__doc__": None}
    console.print("[bold cyan]CodeView Python REPL[/bold cyan]")
    console.print("[dim]Type Python code. Ctrl+D or 'exit()' to quit.[/dim]\n")

    try:
        interp = code.InteractiveConsole(variables)
        interp.interact(banner="", exitmsg="")
    except (EOFError, SystemExit):
        pass
    console.print("\n[dim]REPL closed.[/dim]")


# =============================================================================
# Serve command
# =============================================================================

@cli.command("serve")
@click.argument("directory", required=False, default=".")
@click.option("--port", "-p", type=int, default=8080, help="Port to serve on")
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to")
@click.option("--browser", "-b", is_flag=True, help="Open in browser")
def serve_cmd(directory: str, port: int, host: str, browser: bool):
    """Serve a directory over HTTP with syntax highlighting.

    \b
    Examples:
      codeview serve
      codeview serve src/ --port 9000
      codeview serve . --browser
    """
    import http.server
    import socketserver
    import urllib.parse
    path = Path(directory).resolve()
    if not path.is_dir():
        console.print(f"[bold red]Error:[/bold red] Not a directory: {directory}")
        return
    html_template = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>CodeView Serve</title>
<style>body{{font-family:monospace;background:#1e1e1e;color:#d4d4d4;padding:20px}}
a{{color:#569cd6}}a:hover{{color:#9cdcfe}}.header{{border-bottom:1px solid #444;padding-bottom:10px;margin-bottom:20px}}
.file{{padding:4px 0}}.dir{{font-weight:bold}}.size{{color:#888;margin-left:10px}}</style></head>
<body><div class="header"><h2>CodeView Serve</h2></div>{content}</body></html>"""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(path), **kwargs)
        def log_message(self, format, *args):
            pass
    try:
        with socketserver.TCPServer((host, port), Handler) as httpd:
            url = f"http://{host}:{port}"
            console.print(f"[bold green]Serving:[/bold green] {path}")
            console.print(f"[bold cyan]URL:[/bold cyan] {url}")
            if browser:
                import webbrowser
                webbrowser.open(url)
            console.print("[dim]Press Ctrl+C to stop.[/dim]\n")
            httpd.serve_forever()
    except OSError as e:
        if "Address already in use" in str(e) or "10048" in str(e):
            console.print(f"[bold red]Error:[/bold red] Port {port} is already in use. Try: codeview serve --port {port + 1}")
        else:
            console.print(f"[bold red]Error:[/bold red] {e}")
    except KeyboardInterrupt:
        console.print("\n[dim]Server stopped.[/dim]")


# =============================================================================
# Colors command
# =============================================================================

@cli.command("colors")
def colors_cmd():
    """Display a color palette and theme preview.

    \b
    Example:
      codeview colors
    """
    console.print("[bold]256-Color Palette[/bold]\n")
    from rich.color import Color
    for base in range(0, 256, 36):
        line = []
        for i in range(36):
            idx = base + i
            if idx >= 256:
                break
            try:
                line.append(f"[on color({idx})]  [/on color({idx})]")
            except Exception:
                line.append(f"[on color({idx})]  [/]")
        console.print("".join(line))
    console.print("\n[bold]Grayscale[/bold]")
    gray_line = "".join(f"[on color({i})]  [/on color({i})]" for i in range(232, 256))
    console.print(gray_line)


# =============================================================================
# Git Log command
# =============================================================================

@cli.command("git-log")
@click.argument("directory", required=False, default=".")
@click.option("--limit", "-n", type=int, default=20, help="Number of commits")
@click.option("--oneline", is_flag=True, help="One line per commit")
@click.option("--file", "-f", "gitlog_file", help="Show log for specific file")
def git_log_cmd(directory: str, limit: int, oneline: bool, gitlog_file: Optional[str]):
    """Show git commit log with formatting.

    \b
    Examples:
      codeview git-log
      codeview git-log --limit 10
      codeview git-log --file app.py
    """
    try:
        cmd = ["git", "-C", directory, "log", f"-{limit}"]
        if oneline:
            cmd.append("--oneline")
        else:
            cmd.extend(["--pretty=format:%h %ad %s (%an)", "--date=short"])
        if gitlog_file:
            cmd.extend(["--", gitlog_file])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            console.print(f"[bold yellow]Git error:[/bold yellow] {result.stderr.strip()}")
            return
        output = result.stdout.strip()
        if not output:
            console.print("[dim]No commits found.[/dim]")
            return
        if oneline:
            for line in output.splitlines()[:20]:
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    console.print(f"  [yellow]{parts[0]}[/yellow] {parts[1][:100]}")
                else:
                    console.print(f"  {line[:100]}")
        else:
            lines = output.splitlines()
            for line in lines:
                if line.startswith("commit "):
                    console.print(f"\n[bold cyan]{line}[/bold cyan]")
                elif line.startswith("Author:") or line.startswith("Date:"):
                    console.print(f"  [dim]{line}[/dim]")
                elif line.strip():
                    console.print(f"    {line.strip()[:120]}")
        console.print(f"\n[dim]{len(lines) if oneline else len([l for l in lines if l.strip()])} entries[/dim]")
    except FileNotFoundError:
        console.print("[bold yellow]Git is not installed or not in PATH.[/bold yellow]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# Bookmark command
# =============================================================================

@cli.command("bookmark")
@click.argument("target", required=False)
@click.option("--list", "-l", "list_bookmarks", is_flag=True, help="List all bookmarks")
@click.option("--remove", "-r", "remove_name", help="Remove a bookmark by name")
@click.option("--name", "-n", default="", help="Bookmark name")
@click.option("--clear", is_flag=True, help="Clear all bookmarks")
def bookmark_cmd(target: Optional[str], list_bookmarks: bool,
                 remove_name: Optional[str], name: str, clear: bool):
    """Manage directory and file bookmarks for quick navigation.

    \b
    Examples:
      codeview bookmark src/ --name project_src
      codeview bookmark --list
      codeview bookmark --remove project_src
      codeview bookmark --clear
    """
    from .config import get_config_dir
    bm_file = get_config_dir() / "bookmarks.json"
    bookmarks = {}
    if bm_file.exists():
        try:
            bookmarks = json.loads(bm_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            pass

    if clear:
        bookmarks = {}
        bm_file.write_text("{}", encoding="utf-8")
        console.print("[bold green]All bookmarks cleared.[/bold green]")
        return
    if remove_name:
        if remove_name in bookmarks:
            del bookmarks[remove_name]
            bm_file.write_text(json.dumps(bookmarks, indent=2, ensure_ascii=False), encoding="utf-8")
            console.print(f"[bold green]Removed bookmark:[/bold green] {remove_name}")
        else:
            console.print(f"[bold yellow]Bookmark not found:[/bold yellow] {remove_name}")
        return
    if target:
        bm_name = name or Path(target).name
        target_path = str(Path(target).resolve())
        bookmarks[bm_name] = target_path
        bm_file.parent.mkdir(parents=True, exist_ok=True)
        bm_file.write_text(json.dumps(bookmarks, indent=2, ensure_ascii=False), encoding="utf-8")
        console.print(f"[bold green]Bookmarked:[/bold green] {bm_name} -> {target_path}")
        return
    if not bookmarks:
        console.print("[dim]No bookmarks. Add one with: codeview bookmark <path> --name <name>[/dim]")
        return
    console.print("[bold]Bookmarks:[/bold]")
    for bm_name, bm_path in bookmarks.items():
        exists = Path(bm_path).exists()
        icon = "[green](exists)[/green]" if exists else "[red](missing)[/red]"
        console.print(f"  [bold cyan]{bm_name}[/bold cyan] -> {bm_path} {icon}")


# =============================================================================
# Project command
# =============================================================================

@cli.command("project")
@click.argument("action", required=False, default="info")
@click.option("--name", "-n", help="Project name")
@click.option("--language", "-l", help="Primary language")
@click.option("--init", "init_proj", is_flag=True, help="Initialize a new project")
@click.option("--force", "-f", is_flag=True, help="Force overwrite")
def project_cmd(action: str, name: Optional[str], language: Optional[str],
                init_proj: bool, force: bool):
    """Manage project configuration.

    \b
    Examples:
      codeview project
      codeview project --init --name myapp --language python
      codeview project --init --force
    """
    from .project import get_project_config, init_project, get_project_stats
    if init_proj:
        config = init_project(".", name=name or "", language=language or "", force=force)
        console.print(f"[bold green]Project initialized:[/bold green] {config.get('name', '')}")
        console.print(f"[dim]Root: {config.get('_project_root', '')}[/dim]")
        return
    config = get_project_config()
    if config:
        table = Table(title="[bold]Project Info[/bold]", box=box.ROUNDED)
        table.add_column("Property", style="bold cyan")
        table.add_column("Value", style="white")
        for key, value in config.items():
            if key.startswith("_"):
                continue
            if isinstance(value, dict):
                continue
            table.add_row(key, str(value))
        table.add_row("Root", config.get("_project_root", ""))
        console.print(table)
    else:
        stats = get_project_stats()
        console.print(f"[bold]Directory:[/bold] [cyan]{stats['root']}[/cyan]")
        console.print(f"  Files: [yellow]{stats['total_files']}[/yellow]")
        console.print(f"  Dirs: [yellow]{stats['total_dirs']}[/yellow]")
        console.print(f"  Size: [yellow]{format_size(stats['total_size'])}[/yellow]")
        if stats["extensions"]:
            exts = ", ".join(f"{e}({c})" for e, c in list(stats["extensions"].items())[:10])
            console.print(f"  Types: [dim]{exts}[/dim]")
        console.print(f"\n[dim]No project config found. Use 'codeview project --init' to create one.[/dim]")


# =============================================================================
# Markdown command
# =============================================================================

@cli.command("md")
@click.argument("filepath")
@click.option("--theme", "-t", help="Code theme for syntax blocks")
@click.option("--toc", is_flag=True, help="Show table of contents")
@click.option("--stats", "show_stats", is_flag=True, help="Show markdown statistics")
def md_cmd(filepath: str, theme: Optional[str], toc: bool, show_stats: bool):
    """Render a Markdown file in the terminal.

    \b
    Examples:
      codeview md README.md
      codeview md docs/guide.md --toc
      codeview md README.md --stats
    """
    from .markdown_render import (render_markdown_file, render_table_of_contents,
                                   count_markdown_stats)
    path = Path(filepath)
    if not path.exists() or not path.is_file():
        console.print(f"[bold red]Error:[/bold red] File not found: {filepath}")
        return
    try:
        content = path.read_text(encoding="utf-8")
        if show_stats:
            stats = count_markdown_stats(content)
            table = Table(title=f"[bold]Markdown Stats: {path.name}[/bold]", box=box.ROUNDED)
            table.add_column("Metric", style="bold cyan")
            table.add_column("Value", style="yellow", justify="right")
            table.add_row("Lines", str(stats["lines"]))
            table.add_row("Headings", str(stats["headings"]))
            table.add_row("Code Blocks", str(stats["code_blocks"]))
            table.add_row("Words", str(stats["word_count"]))
            table.add_row("Characters", str(stats["char_count"]))
            console.print(table)
            return
        if toc:
            toc_str = render_table_of_contents(content)
            console.print(Panel(toc_str, title=f"[bold]TOC: {path.name}[/bold]", border_style="cyan"))
            return
        result = render_markdown_file(filepath, code_theme=theme or get_setting("theme"))
        if result:
            console.print(result)
        else:
            console.print(f"[dim]Could not render {filepath}[/dim]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")


# =============================================================================
# Main entry point
# =============================================================================

# Known subcommands for auto-routing
_SUBCOMMANDS = {"view", "edit", "tree", "ls", "search", "info", "stats",
                "diff", "fetch", "browse", "save", "clip", "themes", "langs", "config",
                "format", "hex", "base64", "hash", "watch", "snippets", "history",
                "notes", "repl", "serve", "colors", "git-log", "bookmark", "project", "md"}


def main():
    """Entry point for the CLI. Auto-routes bare file/URL args to the view command."""
    # Smart routing: if first arg is not a known subcommand or option,
    # treat it as a file/URL and route to the 'view' command.
    raw_args = sys.argv[1:]
    if raw_args and raw_args[0] not in _SUBCOMMANDS and not raw_args[0].startswith("-"):
        # Insert 'view' before the first positional argument
        sys.argv.insert(1, "view")

    try:
        cli()
    except SystemExit as e:
        if e.code != 0:
            sys.exit(e.code)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/dim]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Unexpected error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
