from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Callable


class WordExportError(RuntimeError):
    pass


class WordExportUnavailable(WordExportError):
    pass


_WORD_EXPORT_SCRIPT = r'''
on run argv
    set inputPath to item 1 of argv
    set outputPath to item 2 of argv
    tell application "Microsoft Word"
        open (POSIX file inputPath) read only true
        set docRef to active document
        try
            save as docRef file name outputPath file format format PDF
        on error errorMessage number errorNumber
            close docRef saving no
            error errorMessage number errorNumber
        end try
        close docRef saving no
    end tell
end run
'''.strip()


def export_word_pdf(
    source_docx: Path,
    output_pdf: Path,
    *,
    runner: Callable = subprocess.run,
    platform: str | None = None,
    timeout: int = 300,
) -> Path:
    """Export a DOCX using Microsoft Word without altering the source file."""
    platform = platform or sys.platform
    if platform != "darwin":
        raise WordExportUnavailable("Microsoft Word PDF export requires macOS")

    source = source_docx.expanduser().resolve()
    output = output_pdf.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"DOCX source does not exist: {source}")
    if output.exists():
        raise FileExistsError(f"PDF output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "/usr/bin/osascript",
        "-e",
        _WORD_EXPORT_SCRIPT,
        str(source),
        str(output),
    ]
    try:
        result = runner(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise WordExportUnavailable("osascript is unavailable on this macOS system") from exc
    except subprocess.TimeoutExpired as exc:
        raise WordExportError(f"Microsoft Word PDF export timed out after {timeout} seconds") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown AppleScript error").strip()
        raise WordExportError(f"Microsoft Word PDF export failed: {detail}")
    if not output.is_file() or output.stat().st_size == 0:
        raise WordExportError("Microsoft Word reported success but did not create a non-empty PDF")
    return output
