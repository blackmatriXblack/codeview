"""Hex dump viewer for CodeView CLI.

Provides formatted hex dump output with ASCII sidebar, offset headers,
and configurable bytes-per-row display.
"""

import os
from pathlib import Path
from typing import Optional, List, Tuple, Generator


def format_hexdump(
    data: bytes,
    offset: int = 0,
    bytes_per_row: int = 16,
    show_header: bool = True,
    show_ascii: bool = True,
    colorize: bool = False,
) -> str:
    """Format binary data as a hex dump string.

    Args:
        data: Raw bytes to display
        offset: Starting offset to display
        bytes_per_row: Number of bytes per row
        show_header: Include column header
        show_ascii: Include ASCII representation
        colorize: Add ANSI color codes (if True, returns list of format codes)

    Returns:
        Formatted hex dump string
    """
    lines: List[str] = []

    if show_header:
        header = f"{'Offset':>8}  "
        header += " ".join(f"{i:02X}" for i in range(bytes_per_row))
        if show_ascii:
            header += "  " + "".join(f"{i:X}" for i in range(bytes_per_row))
        lines.append(header)
        lines.append("=" * len(header))

    for row_start in range(0, len(data), bytes_per_row):
        chunk = data[row_start:row_start + bytes_per_row]
        row_offset = offset + row_start
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        hex_part = hex_part.ljust(bytes_per_row * 3 - 1)
        ascii_part = "".join(_to_printable(b) for b in chunk)
        line = f"{row_offset:08X}  {hex_part}"
        if show_ascii:
            line += f"  |{ascii_part}|"
        lines.append(line)

    if len(data) > 0:
        lines.append(f"\nTotal: {len(data)} bytes ({_format_size(len(data))})")

    return "\n".join(lines)


def format_hexdump_rich(
    data: bytes,
    offset: int = 0,
    bytes_per_row: int = 16,
) -> str:
    """Format hex dump with Rich markup for colored output.

    Returns a string with Rich-style markup tags.
    """
    rows: List[str] = []
    row_count = (len(data) + bytes_per_row - 1) // bytes_per_row

    for row_idx in range(row_count):
        row_start = row_idx * bytes_per_row
        chunk = data[row_start:row_start + bytes_per_row]
        row_offset = offset + row_start
        hex_cells = []
        ascii_cells = []
        for i, b in enumerate(chunk):
            if b == 0x00:
                hex_cells.append(f"[dim]{b:02X}[/dim]")
                ascii_cells.append(f"[dim].[/dim]")
            elif 0x20 <= b <= 0x7E:
                hex_cells.append(f"{b:02X}")
                ascii_cells.append(chr(b))
            elif b == 0xFF:
                hex_cells.append(f"[bold]{b:02X}[/bold]")
                ascii_cells.append(".")
            else:
                hex_cells.append(f"[yellow]{b:02X}[/yellow]")
                ascii_cells.append(".")
        hex_str = " ".join(hex_cells).ljust(bytes_per_row * 3 - 1)
        ascii_str = "".join(ascii_cells)
        rows.append(f"[cyan]{row_offset:08X}[/cyan]  {hex_str}  |{ascii_str}|")

    return "\n".join(rows)


def _to_printable(b: int) -> str:
    """Convert a byte to a printable ASCII character or dot."""
    if 0x20 <= b <= 0x7E:
        return chr(b)
    return "."


def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def read_file_chunk(
    filepath: str,
    offset: int = 0,
    size: int = 1024,
) -> bytes:
    """Read a chunk of a file and return raw bytes."""
    with open(filepath, "rb") as f:
        f.seek(offset)
        return f.read(size)


def stream_hexdump(
    filepath: str,
    chunk_size: int = 4096,
    bytes_per_row: int = 16,
) -> Generator[str, None, None]:
    """Stream a hex dump of a large file in chunks.

    Yields formatted string chunks suitable for incremental display.
    """
    file_size = os.path.getsize(filepath)
    offset = 0
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield format_hexdump(chunk, offset=offset, bytes_per_row=bytes_per_row)
            offset += len(chunk)


def view_hex_file(
    filepath: str,
    max_bytes: int = 65536,
    offset: int = 0,
    bytes_per_row: int = 16,
    rich_output: bool = False,
) -> Optional[str]:
    """View a file as hex dump.

    Args:
        filepath: Path to the file
        max_bytes: Maximum bytes to read
        offset: Starting byte offset
        bytes_per_row: Bytes per row
        rich_output: Use Rich markup for colors

    Returns:
        Formatted hex dump string, or None if file not found
    """
    path = Path(filepath)
    if not path.exists():
        return None
    if path.is_dir():
        return None
    file_size = path.stat().st_size
    read_size = min(max_bytes, file_size - offset)
    if read_size <= 0:
        return f"File size: {file_size} bytes (offset {offset} is beyond file end)"
    with open(filepath, "rb") as f:
        f.seek(offset)
        data = f.read(read_size)
    formatter = format_hexdump_rich if rich_output else format_hexdump
    header = f"File: {path.name} ({_format_size(file_size)})\n"
    if file_size > max_bytes:
        header += f"Showing {_format_size(read_size)} of {_format_size(file_size)} bytes\n"
    header += "-" * 80 + "\n"
    return header + formatter(data, offset=offset, bytes_per_row=bytes_per_row)


def hex_search(filepath: str, pattern: bytes, max_bytes: int = 1048576) -> List[int]:
    """Search for a byte pattern in a file. Returns list of offset positions."""
    positions = []
    with open(filepath, "rb") as f:
        offset = 0
        while offset < max_bytes:
            chunk = f.read(65536)
            if not chunk:
                break
            pos = 0
            while True:
                pos = chunk.find(pattern, pos)
                if pos == -1:
                    break
                positions.append(offset + pos)
                pos += 1
            offset += len(chunk)
    return positions
