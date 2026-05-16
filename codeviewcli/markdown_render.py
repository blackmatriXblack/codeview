"""Markdown rendering utilities for CodeView CLI.

Provides terminal-friendly markdown rendering using Rich,
converting markdown text to styled terminal output.
"""

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table


def render_markdown(
    content: str,
    title: str = "",
    width: Optional[int] = None,
    code_theme: str = "monokai",
) -> str:
    """Render markdown content to terminal output.

    Uses Rich's Markdown renderer which handles headings, lists,
    code blocks, tables, links, and more.

    Args:
        content: Markdown text to render
        title: Optional title for the output panel
        width: Maximum output width (defaults to terminal width)
        code_theme: Syntax highlighting theme for code blocks

    Returns:
        Rendered string (with ANSI codes) or the raw content
    """
    console = Console(width=width, force_terminal=True)
    with console.capture() as capture:
        md = Markdown(content, code_theme=code_theme)
        if title:
            console.print(Panel(md, title=title, border_style="cyan"))
        else:
            console.print(md)
    return capture.get()


def render_markdown_file(
    filepath: str,
    title: str = "",
    code_theme: str = "monokai",
) -> Optional[str]:
    """Read and render a markdown file to terminal output."""
    path = Path(filepath)
    if not path.exists() or not path.is_file():
        return None
    content = path.read_text(encoding="utf-8")
    return render_markdown(content, title=title or path.name, code_theme=code_theme)


def extract_code_blocks(content: str) -> list:
    """Extract all code blocks from markdown content.

    Returns list of (language, code) tuples.
    """
    import re
    pattern = r'```(\w*)\n(.*?)\n```'
    matches = re.findall(pattern, content, re.DOTALL)
    return [(lang or "text", code) for lang, code in matches]


def count_markdown_stats(content: str) -> dict:
    """Get statistics about markdown content."""
    lines = content.splitlines()
    headings = sum(1 for l in lines if l.startswith("#"))
    code_blocks = len(extract_code_blocks(content))
    word_count = len(content.split())
    char_count = len(content)
    return {
        "lines": len(lines),
        "headings": headings,
        "code_blocks": code_blocks,
        "word_count": word_count,
        "char_count": char_count,
    }


def render_table_of_contents(content: str) -> str:
    """Generate a table of contents from markdown headings."""
    import re
    lines = content.splitlines()
    toc_lines = ["# Table of Contents\n"]
    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$')
    for line in lines:
        match = heading_pattern.match(line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            anchor = title.lower().replace(" ", "-")
            indent = "  " * (level - 1)
            toc_lines.append(f"{indent}- [{title}](#{anchor})")
    return "\n".join(toc_lines)
