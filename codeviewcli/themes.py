"""Theme management for CodeView CLI.

Supports custom themes and all Pygments built-in themes.
"""

from typing import List, Dict
from pathlib import Path

from pygments.styles import get_all_styles, get_style_by_name
from pygments.style import Style
from pygments.token import Token


# Pre-configured popular themes
POPULAR_THEMES = {
    "monokai": {
        "name": "Monokai",
        "description": "Dark theme inspired by Sublime Text's Monokai",
        "type": "dark",
        "background": "#272822",
        "foreground": "#f8f8f2",
    },
    "one-dark": {
        "name": "One Dark",
        "description": "Atom's iconic One Dark theme",
        "type": "dark",
        "background": "#282c34",
        "foreground": "#abb2bf",
    },
    "dracula": {
        "name": "Dracula",
        "description": "Popular Dracula color scheme",
        "type": "dark",
        "background": "#282a36",
        "foreground": "#f8f8f2",
    },
    "github-dark": {
        "name": "GitHub Dark",
        "description": "GitHub's dark mode theme",
        "type": "dark",
        "background": "#0d1117",
        "foreground": "#c9d1d9",
    },
    "github-light": {
        "name": "GitHub Light",
        "description": "GitHub's light mode theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#24292f",
    },
    "nord": {
        "name": "Nord",
        "description": "Arctic, north-bluish color palette",
        "type": "dark",
        "background": "#2e3440",
        "foreground": "#d8dee9",
    },
    "solarized-dark": {
        "name": "Solarized Dark",
        "description": "Precision colors for machines and people",
        "type": "dark",
        "background": "#002b36",
        "foreground": "#839496",
    },
    "solarized-light": {
        "name": "Solarized Light",
        "description": "Solarized light variant",
        "type": "light",
        "background": "#fdf6e3",
        "foreground": "#657b83",
    },
    "gruvbox-dark": {
        "name": "Gruvbox Dark",
        "description": "Retro groove color scheme (dark)",
        "type": "dark",
        "background": "#282828",
        "foreground": "#ebdbb2",
    },
    "gruvbox-light": {
        "name": "Gruvbox Light",
        "description": "Retro groove color scheme (light)",
        "type": "light",
        "background": "#fbf1c7",
        "foreground": "#3c3836",
    },
    "material": {
        "name": "Material",
        "description": "Material Design color palette",
        "type": "dark",
        "background": "#263238",
        "foreground": "#eeffff",
    },
    "vim": {
        "name": "Vim",
        "description": "Classic Vim color theme",
        "type": "dark",
        "background": "#000000",
        "foreground": "#ffffff",
    },
    "zenburn": {
        "name": "Zenburn",
        "description": "Low-contrast theme for long coding sessions",
        "type": "dark",
        "background": "#3f3f3f",
        "foreground": "#dcdccc",
    },
    "fruity": {
        "name": "Fruity",
        "description": "Bright and colorful theme",
        "type": "dark",
        "background": "#111111",
        "foreground": "#ffffff",
    },
    "native": {
        "name": "Native",
        "description": "Native terminal colors",
        "type": "dark",
        "background": "#202020",
        "foreground": "#d0d0d0",
    },
    "vs": {
        "name": "Visual Studio",
        "description": "Visual Studio light theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "xcode": {
        "name": "Xcode",
        "description": "Xcode default theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "paraiso-dark": {
        "name": "Paraiso Dark",
        "description": "Warm color palette",
        "type": "dark",
        "background": "#2f1e2e",
        "foreground": "#a39e9b",
    },
    "paraiso-light": {
        "name": "Paraiso Light",
        "description": "Warm color palette (light)",
        "type": "light",
        "background": "#e7e9db",
        "foreground": "#2f1e2e",
    },
    "rainbow_dash": {
        "name": "Rainbow Dash",
        "description": "Colorful, rainbow-inspired theme",
        "type": "dark",
        "background": "#2a2a2a",
        "foreground": "#f8f8f2",
    },
    "stata-dark": {
        "name": "Stata Dark",
        "description": "Stata IDE dark theme",
        "type": "dark",
        "background": "#232629",
        "foreground": "#dfdfdf",
    },
    "stata-light": {
        "name": "Stata Light",
        "description": "Stata IDE light theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "inkpot": {
        "name": "Inkpot",
        "description": "Dark purple theme from Vim",
        "type": "dark",
        "background": "#1e1e27",
        "foreground": "#cfbfad",
    },
    "manni": {
        "name": "Manni",
        "description": "Light, colorful theme",
        "type": "light",
        "background": "#f0f3f3",
        "foreground": "#000000",
    },
    "rrt": {
        "name": "RRT",
        "description": "Red/green terminal theme",
        "type": "dark",
        "background": "#000000",
        "foreground": "#ffffff",
    },
    "perldoc": {
        "name": "Perldoc",
        "description": "Perl documentation color theme",
        "type": "light",
        "background": "#eeeedd",
        "foreground": "#000000",
    },
    "borland": {
        "name": "Borland",
        "description": "Borland IDE theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "tango": {
        "name": "Tango",
        "description": "Tango Desktop Project colors",
        "type": "light",
        "background": "#f8f8f8",
        "foreground": "#000000",
    },
    "emacs": {
        "name": "Emacs",
        "description": "Classic Emacs color theme",
        "type": "dark",
        "background": "#000000",
        "foreground": "#ffffff",
    },
    "colorful": {
        "name": "Colorful",
        "description": "Very colorful syntax theme",
        "type": "dark",
        "background": "#2a2a2a",
        "foreground": "#bbbbbb",
    },
    "autumn": {
        "name": "Autumn",
        "description": "Warm autumn colors",
        "type": "dark",
        "background": "#111111",
        "foreground": "#ffffff",
    },
    "murphy": {
        "name": "Murphy",
        "description": "Murphy's law color scheme",
        "type": "dark",
        "background": "#000000",
        "foreground": "#ffffff",
    },
    "bw": {
        "name": "Black & White",
        "description": "Plain black and white",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "pastie": {
        "name": "Pastie",
        "description": "Pastie bin theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "trac": {
        "name": "Trac",
        "description": "Trac syntax theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "igor": {
        "name": "Igor",
        "description": "Igor Pro theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "friendly_grayscale": {
        "name": "Friendly Grayscale",
        "description": "High-contrast grayscale theme",
        "type": "dark",
        "background": "#333333",
        "foreground": "#dddddd",
    },
    "friendly": {
        "name": "Friendly",
        "description": "Warm, friendly color scheme",
        "type": "dark",
        "background": "#222222",
        "foreground": "#f0f0f0",
    },
    "algol": {
        "name": "ALGOL",
        "description": "ALGOL publication style",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "algol_nu": {
        "name": "ALGOL Nu",
        "description": "ALGOL with additional colors",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "arduino": {
        "name": "Arduino",
        "description": "Arduino IDE theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#434f54",
    },
    "lovelace": {
        "name": "Lovelace",
        "description": "Ada Lovelace inspired theme",
        "type": "dark",
        "background": "#1d1f28",
        "foreground": "#fdfdfd",
    },
    "abap": {
        "name": "ABAP",
        "description": "ABAP development theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
    "staroffice": {
        "name": "StarOffice",
        "description": "StarOffice/OpenOffice theme",
        "type": "light",
        "background": "#ffffff",
        "foreground": "#000000",
    },
}


def get_all_themes() -> Dict[str, dict]:
    """Get all available themes (both Pygments and custom)."""
    themes = dict(POPULAR_THEMES)

    # Add all Pygments styles
    for style_name in get_all_styles():
        if style_name not in themes:
            try:
                style_cls = get_style_by_name(style_name)
                bg = getattr(style_cls, "background_color", "#1e1e1e")
                themes[style_name] = {
                    "name": style_name.replace("_", " ").title(),
                    "description": f"Pygments built-in theme: {style_name}",
                    "type": "dark" if _is_dark(bg) else "light",
                    "background": bg,
                    "foreground": "#ffffff" if _is_dark(bg) else "#000000",
                }
            except Exception:
                pass

    return themes


def get_theme_info(theme_name: str) -> Optional[dict]:
    """Get information about a specific theme."""
    themes = get_all_themes()
    return themes.get(theme_name)


def list_themes_by_type(theme_type: str = "all") -> List[Dict[str, str]]:
    """List themes filtered by type (dark, light, all)."""
    themes = get_all_themes()
    result = []
    for key, info in themes.items():
        if theme_type == "all" or info.get("type") == theme_type:
            result.append({
                "id": key,
                "name": info["name"],
                "type": info.get("type", "unknown"),
                "background": info.get("background", ""),
            })
    return sorted(result, key=lambda x: x["name"])


def _is_dark(hex_color: str) -> bool:
    """Determine if a hex color is dark."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) < 6:
        return True
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance < 0.5
