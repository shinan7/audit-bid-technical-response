from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"

_ID_PREFIXES = {
    "paragraph": ("P", 6),
    "table": ("T", 6),
    "image": ("IMG", 6),
    "chunk": ("CHUNK", 4),
}


def format_id(kind: str, index: int) -> str:
    if kind not in _ID_PREFIXES:
        raise ValueError(f"unknown id kind: {kind}")
    if index < 1:
        raise ValueError("index must be positive")
    prefix, width = _ID_PREFIXES[kind]
    return f"{prefix}-{index:0{width}d}"


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return value.as_posix()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def dumps_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=_json_default,
    ) + "\n"


def truncate_excerpt(text: str, max_chars: int = 100) -> str:
    """Return verbatim source text, truncating only when it exceeds the limit."""
    if max_chars < 3:
        raise ValueError("max_chars must be at least 3")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 2] + "……"


@dataclass(frozen=True)
class WarningRecord:
    code: str
    message: str
    source_id: str | None = None


@dataclass(frozen=True)
class HeadingCandidate:
    level: int | None
    confidence: str
    reasons: tuple[str, ...] = ()


@dataclass
class BlockRecord:
    id: str
    type: str
    order: int
    section_path: list[str] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    page_source: str | None = None
    page_confidence: str = "unmapped"
    page_match_method: str | None = None
    page_candidates: list[dict[str, int]] = field(default_factory=list)


@dataclass
class ParagraphRecord(BlockRecord):
    text: str = ""
    style_id: str | None = None
    style_name: str | None = None
    outline_level: int | None = None
    numbering: str | None = None
    bold: bool = False
    font_size_pt: float | None = None
    heading_candidate: HeadingCandidate | None = None


@dataclass
class TableRecord(BlockRecord):
    rows: list[list[str]] = field(default_factory=list)
    source_xml_index: int = 0


@dataclass
class ImageRecord(BlockRecord):
    anchor_block_id: str = ""
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)
    file: str = ""
    source_part: str = "word/document.xml"
    content_type: str = ""
    sha256: str = ""
    width_px: int | None = None
    height_px: int | None = None
    occurrence_count: int = 1
    decorative_candidate: bool = False
    decorative_reasons: list[str] = field(default_factory=list)
    analysis_status: str = "ready"


@dataclass
class ChunkRecord:
    id: str
    block_ids: list[str]
    char_count: int
    image_count: int
    file: str
    warnings: list[WarningRecord] = field(default_factory=list)
