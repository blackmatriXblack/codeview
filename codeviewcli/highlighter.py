"""Syntax highlighting engine using Pygments with Rich integration.

Supports 500+ programming languages with customizable color themes.
"""

from pathlib import Path
from typing import Optional, List, Tuple

from pygments import highlight
from pygments.lexers import (
    get_lexer_for_filename,
    get_lexer_by_name,
    guess_lexer,
    get_all_lexers,
)
from pygments.formatters import Terminal256Formatter, TerminalTrueColorFormatter
from pygments.styles import get_style_by_name, get_all_styles
from pygments.token import Token
from pygments.util import ClassNotFound

from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Map of file extensions to language names for quick lookup
EXTENSION_MAP = {
    ".py": "python", ".pyw": "python", ".pyx": "cython",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".html": "html", ".htm": "html", ".xhtml": "html",
    ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    ".json": "json", ".jsonc": "jsonc", ".json5": "json5",
    ".xml": "xml", ".xsl": "xml", ".xslt": "xml",
    ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".ini": "ini", ".cfg": "ini", ".conf": "ini",
    ".md": "markdown", ".markdown": "markdown", ".mdx": "markdown",
    ".sql": "sql", ".psql": "postgresql",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash", ".fish": "fish",
    ".ps1": "powershell", ".psm1": "powershell", ".psd1": "powershell",
    ".bat": "batch", ".cmd": "batch",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cxx": "cpp", ".cc": "cpp", ".c++": "cpp", ".hpp": "cpp",
    ".cs": "csharp",
    ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby", ".rake": "ruby", ".gemspec": "ruby",
    ".php": "php", ".phtml": "php",
    ".swift": "swift",
    ".r": "r",
    ".scala": "scala",
    ".dart": "dart",
    ".lua": "lua",
    ".pl": "perl", ".pm": "perl",
    ".ex": "elixir", ".exs": "elixir",
    ".erl": "erlang", ".hrl": "erlang",
    ".hs": "haskell", ".lhs": "haskell",
    ".clj": "clojure", ".cljs": "clojure", ".cljc": "clojure", ".edn": "clojure",
    ".elm": "elm",
    ".fs": "fsharp", ".fsi": "fsharp",
    ".nim": "nim",
    ".zig": "zig",
    ".v": "v",
    ".vue": "vue",
    ".svelte": "svelte",
    ".tf": "terraform", ".tfvars": "terraform",
    ".Dockerfile": "docker", "Dockerfile": "docker",
    ".dockerfile": "docker",
    ".cmake": "cmake", "CMakeLists.txt": "cmake",
    ".makefile": "makefile", "Makefile": "makefile", ".mk": "makefile",
    ".gradle": "groovy", ".groovy": "groovy",
    ".proto": "protobuf",
    ".graphql": "graphql", ".gql": "graphql",
    ".wgsl": "wgsl",
    ".tex": "latex",
    ".asm": "nasm", ".s": "nasm", ".S": "nasm",
    ".wasm": "wast",
    ".diff": "diff", ".patch": "diff",
    ".nginx": "nginx",
    ".env": "ini",
    ".editorconfig": "ini",
    ".gitignore": "gitignore",
    ".gitattributes": "gitattributes",
    ".prisma": "prisma",
    ".wiki": "wikitext",
    ".pug": "pug", ".jade": "pug",
    ".jl": "julia",
    ".cr": "crystal",
    ".coffee": "coffeescript",
    ".rkt": "racket",
    ".scm": "scheme",
    ".ml": "ocaml", ".mli": "ocaml",
    ".odin": "odin",
    ".pas": "pascal", ".pp": "pascal",
    ".vb": "vbnet",
    ".ahk": "autohotkey",
    ".ino": "arduino",
    ".sol": "solidity",
    ".purs": "purescript",
    ".pony": "pony",
    ".re": "reason",
    ".res": "rescript",
    ".cbl": "cobol", ".cob": "cobol",
    ".f": "fortran", ".f90": "fortran", ".f95": "fortran",
    ".ada": "ada",
    ".vhd": "vhdl", ".vhdl": "vhdl",
    ".sv": "systemverilog", ".v": "verilog",
    ".matlab": "matlab", ".m": "objective-c",
    ".apl": "apl",
    ".rpg": "rpgle",
    ".sqlpl": "plpgsql",
    ".st": "smalltalk",
    ".tcl": "tcl",
    ".forth": "forth",
    ".sas": "sas",
    ".jl": "julia",
    ".hx": "haxe",
    ".vala": "vala",
    ".gd": "gdscript",
    ".ejs": "ejs",
    ".qml": "qml",
    ".nix": "nix",
    ".pon": "pony",
    ".wren": "wren",
    ".raku": "raku", ".rakumod": "raku", ".rakutest": "raku",
    ".cb": "crystal",
    ".sp": "sourcepawn",
}

# Mapping of common aliases
LANGUAGE_ALIASES = {
    "py": "python", "python3": "python",
    "js": "javascript", "node": "javascript",
    "ts": "typescript",
    "rb": "ruby",
    "cs": "csharp", "c#": "csharp",
    "c++": "cpp",
    "objc": "objective-c", "obj-c": "objective-c",
    "f#": "fsharp",
    "vb": "vbnet", "vb.net": "vbnet",
    "ps": "powershell",
    "shell": "bash", "bash": "bash", "zsh": "bash",
    "terminal": "bash",
}


def detect_language(filename: str, content: str = "") -> str:
    """Detect the programming language from filename or content."""
    path = Path(filename)

    # Special case for Dockerfile, Makefile, etc.
    if path.name == "Dockerfile":
        return "docker"
    if path.name == "Makefile":
        return "makefile"
    if path.name == "CMakeLists.txt":
        return "cmake"
    if path.name == "Vagrantfile":
        return "ruby"
    if path.name == "Gemfile":
        return "ruby"
    if path.name == "Rakefile":
        return "ruby"
    if path.name == "Jenkinsfile":
        return "groovy"

    # Check suffix map
    suffix = path.suffix.lower()
    if suffix in EXTENSION_MAP:
        return EXTENSION_MAP[suffix]

    # Double extension check (e.g., .test.js)
    if len(path.suffixes) > 1:
        double_suffix = "".join(path.suffixes[-2:]).lower()
        if double_suffix in EXTENSION_MAP:
            return EXTENSION_MAP[double_suffix]
        last_suffix = path.suffixes[-1].lower()
        if last_suffix in EXTENSION_MAP:
            return EXTENSION_MAP[last_suffix]

    # No extension, try to guess from content
    if content:
        try:
            lexer = guess_lexer(content)
            return lexer.aliases[0] if lexer.aliases else "text"
        except ClassNotFound:
            pass

    return "text"


def resolve_language(language: str) -> str:
    """Resolve language aliases to canonical names."""
    lang = language.lower().strip()
    if lang in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[lang]
    return lang


def highlight_code(
    code: str,
    language: str = "text",
    theme: str = "monokai",
    line_numbers: bool = True,
    start_line: int = 1,
    true_color: bool = True,
    highlight_lines: Optional[List[int]] = None,
) -> Syntax:
    """Create a Rich Syntax object with syntax highlighting."""
    lang = resolve_language(language)

    if true_color:
        syntax = Syntax(
            code, lang,
            theme=theme,
            line_numbers=line_numbers,
            start_line=start_line,
            highlight_lines=set(highlight_lines or []),
            word_wrap=False,
            background_color="default",
        )
    else:
        syntax = Syntax(
            code, lang,
            theme=theme,
            line_numbers=line_numbers,
            start_line=start_line,
            highlight_lines=set(highlight_lines or []),
            word_wrap=False,
        )

    return syntax


def highlight_code_pygments(
    code: str,
    language: str = "text",
    style: str = "monokai",
    true_color: bool = True,
) -> str:
    """Highlight code using Pygments directly, returns colored string."""
    lang = resolve_language(language)
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        try:
            lexer = guess_lexer(code)
        except ClassNotFound:
            lexer = get_lexer_by_name("text")

    if true_color:
        formatter = TerminalTrueColorFormatter(style=style)
    else:
        formatter = Terminal256Formatter(style=style)

    return highlight(code, lexer, formatter)


def get_available_themes() -> List[str]:
    """Return list of all available Pygments themes."""
    return sorted(get_all_styles())


def get_available_languages() -> List[Tuple[str, str, str]]:
    """Return list of all supported languages with their aliases and extensions."""
    langs = []
    for lexer in sorted(get_all_lexers(), key=lambda x: x[0].lower()):
        name = lexer[0]
        aliases = lexer[1]
        file_patterns = lexer[2] if len(lexer) > 2 else []
        langs.append((name, ", ".join(aliases[:5]), ", ".join(file_patterns[:5])))
    return langs


def format_output(
    code: str,
    language: str = "text",
    theme: str = "monokai",
    line_numbers: bool = True,
    start_line: int = 1,
    pad_line: int = 1,
    title: str = "",
    true_color: bool = True,
    highlight_lines: Optional[List[int]] = None,
) -> Syntax:
    """Format code as a Rich Syntax with optional panel title."""
    syntax = highlight_code(
        code, language, theme, line_numbers, start_line,
        true_color, highlight_lines,
    )
    return syntax


def get_lexer_class(language: str):
    """Get the Pygments lexer class for a language."""
    lang = resolve_language(language)
    try:
        return get_lexer_by_name(lang)
    except ClassNotFound:
        return get_lexer_by_name("text")
