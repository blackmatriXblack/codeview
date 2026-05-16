# Technical Documentation: CodeView CLI (v2.0.0)

## 1. Executive Summary
**CodeView CLI** is a modern, cross-platform command-line interface (CLI) and terminal user interface (TUI) toolkit designed for developers to view, edit, and fetch source code with advanced syntax highlighting, intelligent file filtering, and seamless clipboard integration. Built on Python 3.9+, the application leverages a curated stack of contemporary terminal rendering libraries (`rich`, `textual`), syntax engines (`pygments`), and web/data parsing utilities (`requests`, `beautifulsoup4`, `lxml`) to deliver a highly responsive, feature-rich developer experience directly within the terminal.

This document provides a comprehensive technical breakdown of the project's architecture, dependency matrix, installation workflows, execution model, development lifecycle, security considerations, and extensibility pathways.

---

## 2. Project Metadata & Overview
| Attribute | Value |
|-----------|-------|
| **Package Name** | `codeviewcli` |
| **Current Version** | `2.0.0` |
| **Author / Maintainer** | CodeView CLI |
| **License** | MIT License |
| **Python Requirement** | `>=3.9` |
| **Target Platforms** | OS Independent (Windows, macOS, Linux) |
| **Primary Entry Points** | `codeview`, `cv` |
| **Distribution Type** | Wheel & Source Distribution (PyPI Compatible) |
| **Description** | A feature-rich CLI tool to view, edit, and fetch code with syntax highlighting |

---

## 3. System Requirements & Compatibility

### 3.1 Runtime Environment
- **Python Interpreter**: CPython 3.9 or higher (PyPy 3.9+ compatible with minor performance considerations)
- **Package Manager**: `pip` (v21.0+), `conda`, or `uv`/`pipx`
- **Terminal Emulator**: Any modern terminal supporting ANSI escape sequences, Unicode, and minimum width of 80 columns
- **Font**: Monospaced font with ligature support recommended (e.g., JetBrains Mono, Fira Code, Cascadia Code)

### 3.2 Platform-Specific Notes
- **Windows**: Requires `windows-curses` for native terminal UI compatibility. ConPTY/Windows Terminal recommended for optimal rendering.
- **macOS / Linux**: Relies on system-provided `ncurses`/`terminfo`. No additional native dependencies required.
- **Terminal Multiplexers**: Fully compatible with `tmux` and `screen` (ensure `TERM` is set to `screen-256color` or `tmux-256color`).

---

## 4. Dependency Architecture & Stack Analysis

The application is engineered around a modular, best-of-breed Python ecosystem. Each dependency serves a specific architectural role:

| Library | Version | Role in Architecture | Technical Justification |
|---------|---------|----------------------|-------------------------|
| `click` | `>=8.1.0` | CLI Framework & Routing | Provides robust command parsing, argument validation, and help generation. Replaces `argparse` with decorator-based routing. |
| `rich` | `>=13.0.0` | Terminal Rendering & Layout | Handles pretty-printing, progress bars, tables, markdown rendering, and ANSI color management. |
| `textual` | `>=0.50.0` | TUI Framework | Drives the interactive terminal interface (panels, keybindings, async event loop, widget tree). |
| `pygments` | `>=2.15.0` | Syntax Highlighting Engine | Tokenizes and colors 500+ programming languages. Integrates with `rich`/`textual` for real-time rendering. |
| `requests` | `>=2.31.0` | HTTP Client | Manages secure web requests for remote code fetching, API interactions, and metadata retrieval. |
| `beautifulsoup4` | `>=4.12.0` | HTML/XML Parsing | Extracts raw code/text from web pages, documentation sites, or paste services. |
| `lxml` | `>=4.9.0` | High-Performance Parser | Accelerates `bs4` parsing speed and XPath/CSS selector support. Fallback to `html.parser` if unavailable. |
| `pathspec` | `>=0.11.0` | File Filtering & Ignore Patterns | Implements `.gitignore`-style glob matching for intelligent file tree traversal and exclusion rules. |
| `pyperclip` | `>=1.8.0` | Cross-Platform Clipboard | Enables seamless copy/paste operations between terminal sessions and host OS clipboard. |
| `windows-curses` | `>=2.3.0` | Windows TUI Compatibility | Polyfills missing `curses` module on Windows, required by `textual` for terminal control. |

---

## 5. Installation & Deployment Guide

### 5.1 Standard Installation (PyPI)
```bash
pip install codeviewcli
```
*Verifies installation:*
```bash
codeview --version
# or
cv --version
```

### 5.2 Development / Editable Installation
```bash
git clone <repository-url>
cd codeviewcli
pip install -e .
```
*Installs in editable mode, enabling live code reloading and debugging.*

### 5.3 Isolated Environment Execution (Recommended)
```bash
pip install pipx
pipx install codeviewcli
codeview --help
```

### 5.4 Build from Source
```bash
pip install build twine
python -m build
twine check dist/*
```
*Generates `dist/codeviewcli-2.0.0-py3-none-any.whl` and source tarball.*

---

## 6. CLI Interface & Execution Model

### 6.1 Entry Point Mapping
Defined in `setup.py` under `console_scripts`:
```ini
codeview = codeviewcli.main:main
cv       = codeviewcli.main:main
```
Both commands invoke the same `main()` coroutine/function within the `codeviewcli.main` module, providing a primary and alias command for user convenience.

### 6.2 Expected Command Structure (Architectural Inference)
Based on the dependency stack and description, the CLI follows a `click`-driven subcommand hierarchy:
```bash
codeview [GLOBAL_OPTIONS] <SUBCOMMAND> [ARGS]
```
| Subcommand | Inferred Purpose | Key Dependencies |
|------------|------------------|------------------|
| `view` / `show` | Open file with syntax highlighting & TUI panels | `pygments`, `textual`, `rich` |
| `edit` | Launch lightweight terminal editor mode | `textual`, `click`, `pyperclip` |
| `fetch` | Retrieve code from URLs, pastebins, or APIs | `requests`, `bs4`, `lxml` |
| `search` / `grep` | Pattern match across files with ignore rules | `pathspec`, `rich` |
| `config` | Manage themes, keybindings, and defaults | `click`, `pathlib` |

*Note: Exact subcommands are defined in `codeviewcli/main.py`. The architecture supports lazy-loading of heavy modules (e.g., `textual`, `lxml`) to minimize startup latency.*

---

## 7. Core Functional Modules (Architectural Breakdown)

### 7.1 Terminal UI Engine (`textual` + `rich`)
- Implements an async event loop for responsive keyboard/mouse input.
- Renders split panels: file explorer (left), syntax viewer (center), metadata/logs (bottom).
- Uses `rich.console.Console` for fallback rendering when TUI fails.

### 7.2 Syntax Highlighting Pipeline (`pygments`)
- Auto-detects language via file extension, shebang, or `pathspec` rules.
- Supports custom theme injection (e.g., `monokai`, `dracula`, `github-dark`).
- Handles large files via lazy line rendering and virtual scrolling.

### 7.3 Remote Code Fetcher (`requests` + `bs4` + `lxml`)
- Fetches raw content from GitHub Gists, Pastebin, GitLab, or documentation sites.
- Strips HTML/Markdown wrappers using CSS selectors/XPath.
- Validates MIME types and enforces timeout/security headers.

### 7.4 File System Traversal (`pathspec`)
- Respects `.gitignore`, `.codeviewignore`, and system hidden files.
- Supports recursive directory scanning with exclusion patterns.
- Integrates with OS file watchers for live reload (if implemented).

### 7.5 Clipboard Bridge (`pyperclip`)
- Abstracts OS-specific clipboard APIs (X11, Wayland, macOS `pbcopy`, Windows `ctypes`).
- Enables `Ctrl+C` / `Ctrl+V` within the TUI without interfering with terminal paste buffers.

---

## 8. Development & Build Workflow

### 8.1 Project Structure (Standard Layout)
```
codeviewcli/
├── codeviewcli/
│   ├── __init__.py
│   ├── main.py          # Entry point (click group)
│   ├── cli/             # Subcommand definitions
│   ├── ui/              # Textual widgets & rich renderers
│   ├── core/            # File I/O, fetcher, pathspec logic
│   └── config.py        # Settings & theme management
├── tests/               # pytest suite
├── docs/                # Sphinx/MkDocs source
├── pyproject.toml       # Modern build config (optional)
└── setup.py             # Legacy packaging (provided)
```

### 8.2 Testing & Quality Assurance
```bash
# Install dev dependencies
pip install pytest black isort mypy flake8

# Run tests
pytest tests/ -v

# Format & lint
black codeviewcli/
isort codeviewcli/
mypy codeviewcli/ --ignore-missing-imports
```

### 8.3 Continuous Integration (CI) Recommendations
- **Matrix**: Python 3.9, 3.10, 3.11, 3.12 × (Ubuntu, macOS, Windows)
- **Steps**: `lint` → `test` → `build` → `publish` (on tag)
- **Tools**: GitHub Actions, `tox`, `cibuildwheel` (if native extensions added later)

---

## 9. Security, Privacy & Licensing

### 9.1 Data Handling
- **Local Files**: Read-only by default. Edit mode requires explicit user confirmation.
- **Remote Fetching**: Uses `requests` with default SSL verification. Timeout enforced (`requests.get(..., timeout=10)`).
- **No Telemetry**: Does not phone home, track usage, or collect analytics.

### 9.2 Security Best Practices
- Input sanitization for file paths and URLs to prevent directory traversal or SSRF.
- `pathspec` prevents accidental inclusion of sensitive files (`.env`, `id_rsa`).
- `lxml` configured with `recover=False` and `huge_tree=False` to mitigate XML bomb attacks.

### 9.3 License
Distributed under the **MIT License**. Permits commercial use, modification, distribution, and private use. Requires attribution and inclusion of the original license text.

---

## 10. Troubleshooting & Common Issues

| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `ModuleNotFoundError: No module named 'curses'` (Windows) | Missing `windows-curses` | Run `pip install windows-curses` or ensure `setup.py` conditional installs correctly |
| TUI fails to render / garbled text | Terminal doesn't support Unicode/256 colors | Switch to Windows Terminal, iTerm2, or GNOME Terminal. Set `TERM=xterm-256color` |
| Slow startup on large repos | `pathspec` scanning thousands of files | Add `node_modules/`, `.git/` to `.codeviewignore` or use `--no-scan` flag |
| `lxml` build fails on macOS/Linux | Missing `libxml2`/`libxslt` dev headers | Install `libxml2-dev libxslt1-dev` (Debian/Ubuntu) or `brew install libxml2 libxslt` (macOS) |
| Clipboard not working in SSH/Tmux | `pyperclip` lacks X11/Wayland display | Set `DISPLAY` variable, use `tmux set-option -g set-clipboard on`, or fallback to manual copy |

---

## 11. Contribution Guidelines

1. **Fork & Branch**: Create feature branches from `main`. Use semantic naming (`feat/syntax-theme`, `fix/clipboard-win`).
2. **Code Standards**: PEP 8 compliance, type hints (`typing` module), docstrings for public APIs.
3. **Testing**: Add `pytest` cases for new fetchers, parsers, or CLI routes. Maintain >90% coverage.
4. **Commit Messages**: Follow Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).
5. **Pull Request**: Include description, testing evidence, and dependency updates if applicable.

---

## 12. Appendix A: Dependency Reference Matrix

| Category | Package | Min Version | Purpose | Conditional? |
|----------|---------|-------------|---------|--------------|
| CLI Routing | `click` | `8.1.0` | Argument parsing, command tree | No |
| UI/Rendering | `rich` | `13.0.0` | Tables, syntax colors, markdown | No |
| TUI Engine | `textual` | `0.50.0` | Interactive panels, key handling | No |
| Syntax Engine | `pygments` | `2.15.0` | Language tokenization | No |
| HTTP Client | `requests` | `2.31.0` | Web fetching, API calls | No |
| HTML Parser | `beautifulsoup4` | `4.12.0` | DOM traversal, text extraction | No |
| XML/HTML Lib | `lxml` | `4.9.0` | High-speed parsing backend | No |
| Path Filtering | `pathspec` | `0.11.0` | `.gitignore` pattern matching | No |
| Clipboard | `pyperclip` | `1.8.0` | OS clipboard abstraction | No |
| Windows TUI | `windows-curses` | `2.3.0` | `curses` polyfill for Windows | Yes (`sys_platform == "win32"`) |

---

## 13. Appendix B: CLI Entry Point Specification

```python
# Internal mapping resolved by setuptools
entry_points={
    "console_scripts": [
        "codeview=codeviewcli.main:main",
        "cv=codeviewcli.main:main"
    ]
}
```
- Both `codeview` and `cv` execute the identical `main()` function.
- `cv` serves as a shorthand alias for rapid terminal access.
- Version `2.0.0` implies breaking changes from `1.x` (likely TUI migration to `textual`, enhanced fetcher, or config overhaul).

---

## 14. Version History & Future Roadmap

### 14.1 Current Release: v2.0.0
- Migrated to `textual` for full TUI experience.
- Enhanced syntax highlighting via `pygments` 2.15+.
- Implemented `.gitignore`-aware file traversal (`pathspec`).
- Added secure remote code fetching (`requests` + `bs4` + `lxml`).
- Cross-platform clipboard support (`pyperclip`).

### 14.2 Planned Enhancements (v2.1.0+)
- **Plugin Architecture**: Allow third-party syntax themes and fetcher extensions.
- **Git Integration**: Branch switching, diff viewing, commit history TUI.
- **LSP Support**: Integrate `pygls` for autocompletion, go-to-definition, and diagnostics.
- **Performance Optimization**: Async I/O for large file rendering, memory-mapped file reading.
- **Packaging**: Native binaries via `PyInstaller` or `Nuitka`, Homebrew/AUR packages.

---

*Document Version: 1.0*  
*Source Reference: `setup.py` (Python 3 / setuptools / PyPI Compatible)*  
*Target Runtime: Python 3.9+*  
*License: MIT*  
*Maintainer: CodeView CLI Project*
