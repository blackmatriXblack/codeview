"""Code snippet manager for CodeView CLI.

Provides snippet storage, retrieval, listing, and insertion.
Snippets are stored as JSON files with metadata.
"""

import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from .config import get_config_dir


DEFAULT_SNIPPETS = {
    "python": [
        {
            "name": "main",
            "prefix": "main",
            "description": "Python main guard",
            "body": 'if __name__ == "__main__":\n    ${0:pass}',
        },
        {
            "name": "class",
            "prefix": "class",
            "description": "Python class with __init__",
            "body": "class ${1:ClassName}:\n    def __init__(self, ${2:args}):\n        ${0:pass}",
        },
        {
            "name": "def",
            "prefix": "def",
            "description": "Python function definition",
            "body": "def ${1:function_name}(${2:args}):\n    ${0:pass}",
        },
        {
            "name": "for",
            "prefix": "for",
            "description": "For loop with enumerate",
            "body": "for ${1:i}, ${2:item} in enumerate(${3:iterable}):\n    ${0:pass}",
        },
        {
            "name": "with",
            "prefix": "with",
            "description": "With context manager",
            "body": "with ${1:expression} as ${2:target}:\n    ${0:pass}",
        },
        {
            "name": "try",
            "prefix": "try",
            "description": "Try-except block",
            "body": "try:\n    ${1:pass}\nexcept ${2:Exception} as ${3:e}:\n    ${0:pass}",
        },
        {
            "name": "listcomp",
            "prefix": "lc",
            "description": "List comprehension",
            "body": "[${1:expr} for ${2:item} in ${3:iterable}]",
        },
        {
            "name": "dictcomp",
            "prefix": "dc",
            "description": "Dict comprehension",
            "body": "{${1:key}: ${2:value} for ${3:item} in ${4:iterable}}",
        },
        {
            "name": "lambda",
            "prefix": "lam",
            "description": "Lambda function",
            "body": "lambda ${1:args}: ${0:expr}",
        },
        {
            "name": "decorator",
            "prefix": "dec",
            "description": "Decorator function",
            "body": "def ${1:decorator}(func):\n    @functools.wraps(func)\n    def wrapper(*args, **kwargs):\n        ${0:pass}\n    return wrapper",
        },
    ],
    "javascript": [
        {
            "name": "function",
            "prefix": "func",
            "description": "JavaScript function",
            "body": "function ${1:name}(${2:params}) {\n    ${0}\n}",
        },
        {
            "name": "arrow",
            "prefix": "af",
            "description": "Arrow function",
            "body": "const ${1:name} = (${2:params}) => {\n    ${0}\n};",
        },
        {
            "name": "foreach",
            "prefix": "fe",
            "description": "ForEach loop",
            "body": "${1:arr}.forEach((${2:item}, ${3:index}) => {\n    ${0}\n});",
        },
        {
            "name": "map",
            "prefix": "map",
            "description": "Array map",
            "body": "${1:arr}.map((${2:item}) => ${0:item});",
        },
        {
            "name": "clog",
            "prefix": "clog",
            "description": "Console log",
            "body": "console.log('${1:label}:', ${0:value});",
        },
    ],
    "html": [
        {
            "name": "doctype",
            "prefix": "!",
            "description": "HTML5 boilerplate",
            "body": "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n    <title>${1:Document}</title>\n</head>\n<body>\n    ${0}\n</body>\n</html>",
        },
        {
            "name": "div",
            "prefix": "div",
            "description": "Div with class",
            "body": '<div class="${1:classname}">\n    ${0}\n</div>',
        },
    ],
}


def get_snippets_file() -> Path:
    """Get path to the snippets JSON file."""
    return get_config_dir() / "snippets.json"


def _load_raw() -> Dict:
    """Load raw snippets data from file or initialize defaults."""
    snippets_file = get_snippets_file()
    if snippets_file.exists():
        try:
            with open(snippets_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    _save_raw(DEFAULT_SNIPPETS)
    return dict(DEFAULT_SNIPPETS)


def _save_raw(data: Dict) -> None:
    """Save raw snippets data to file."""
    snippets_file = get_snippets_file()
    snippets_file.parent.mkdir(parents=True, exist_ok=True)
    with open(snippets_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def list_snippets(language: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all snippets, optionally filtered by language."""
    data = _load_raw()
    results = []
    for lang, snippets in data.items():
        if language and lang != language.lower():
            continue
        for s in snippets:
            s["language"] = lang
            results.append(s)
    return results


def get_snippet(language: str, name: str) -> Optional[Dict[str, Any]]:
    """Get a specific snippet by language and name."""
    data = _load_raw()
    lang_snippets = data.get(language.lower(), [])
    for s in lang_snippets:
        if s["name"] == name or s.get("prefix") == name:
            return s
    return None


def add_snippet(language: str, name: str, prefix: str, description: str, body: str) -> None:
    """Add a new snippet."""
    data = _load_raw()
    lang = language.lower()
    if lang not in data:
        data[lang] = []
    data[lang].append({
        "name": name,
        "prefix": prefix,
        "description": description,
        "body": body,
        "created": datetime.now().isoformat(),
    })
    _save_raw(data)


def remove_snippet(language: str, name: str) -> bool:
    """Remove a snippet. Returns True if found and removed."""
    data = _load_raw()
    lang = language.lower()
    if lang not in data:
        return False
    before = len(data[lang])
    data[lang] = [s for s in data[lang] if s["name"] != name]
    if len(data[lang]) == before:
        return False
    _save_raw(data)
    return True


def export_snippets(filepath: str) -> None:
    """Export all snippets to a file."""
    data = _load_raw()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def import_snippets(filepath: str) -> int:
    """Import snippets from a file. Returns count of imported snippets."""
    with open(filepath, "r", encoding="utf-8") as f:
        imported = json.load(f)
    data = _load_raw()
    count = 0
    for lang, snippets in imported.items():
        if lang not in data:
            data[lang] = []
        existing_names = {s["name"] for s in data[lang]}
        for s in snippets:
            if s["name"] not in existing_names:
                data[lang].append(s)
                count += 1
    _save_raw(data)
    return count


def get_languages() -> List[str]:
    """Get list of languages that have snippets."""
    data = _load_raw()
    return sorted(data.keys())


def clear_snippets(language: Optional[str] = None) -> int:
    """Clear snippets. Returns count removed."""
    data = _load_raw()
    if language:
        count = len(data.pop(language.lower(), []))
    else:
        count = sum(len(v) for v in data.values())
        data.clear()
    _save_raw(data)
    return count
