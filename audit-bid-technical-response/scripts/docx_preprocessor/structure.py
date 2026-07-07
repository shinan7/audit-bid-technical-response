from __future__ import annotations

import re
from typing import Iterable

from .models import (
    BlockRecord,
    ChunkRecord,
    HeadingCandidate,
    ImageRecord,
    ParagraphRecord,
    TableRecord,
    WarningRecord,
    format_id,
)
from .ooxml import RawBlock


_HEADING_STYLE_RE = re.compile(r"^(?:heading|标题)\s*([1-9])$", re.IGNORECASE)
_NUMBERED_TEXT_RE = re.compile(
    r"^\s*(?:第[一二三四五六七八九十百]+[章节部分]|(?:\d+[.、])+(?:\d+)?|[一二三四五六七八九十]+、)"
)


def classify_heading(block: RawBlock) -> HeadingCandidate:
    if block.kind != "paragraph" or not block.text.strip():
        return HeadingCandidate(None, "low", ("not_text_paragraph",))

    style = (block.style_name or block.style_id or "").strip()
    normalized_style = style.lower().replace("_", " ")
    if normalized_style.startswith("toc") or normalized_style.startswith("目录"):
        return HeadingCandidate(None, "high", ("toc_style",))

    if block.outline_level is not None and 0 <= block.outline_level <= 8:
        return HeadingCandidate(block.outline_level + 1, "high", ("outline_level",))

    compact_style = re.sub(r"\s+", " ", style).strip()
    match = _HEADING_STYLE_RE.match(compact_style)
    if not match:
        match = re.match(r"^Heading([1-9])$", block.style_id or "", re.IGNORECASE)
    if match:
        return HeadingCandidate(int(match.group(1)), "high", ("heading_style",))

    short = len(block.text.strip()) <= 80
    visually_prominent = block.bold or (block.font_size_pt or 0) >= 14
    if block.numbering_id is not None and short and visually_prominent:
        level = (block.numbering_level or 0) + 1
        return HeadingCandidate(min(max(level, 1), 9), "medium", ("numbering", "visual_prominence"))

    if short and visually_prominent and _NUMBERED_TEXT_RE.match(block.text):
        return HeadingCandidate(1, "medium", ("numbered_text", "visual_prominence"))

    return HeadingCandidate(None, "low", ("no_heading_signal",))


def _numbering_text(block: RawBlock) -> str | None:
    match = re.match(r"^\s*((?:\d+[.、])+(?:\d+)?)", block.text)
    return match.group(1).rstrip(".、") if match else None


def assign_structure(raw_blocks: Iterable[RawBlock]):
    records: list[BlockRecord] = []
    sections: list[dict] = []
    section_stack: list[tuple[int, str, str]] = []
    paragraph_index = 0
    table_index = 0
    order = 0

    for raw in raw_blocks:
        if raw.kind == "paragraph" and not raw.text and not raw.image_relationship_ids:
            continue
        order += 1
        if raw.kind == "paragraph":
            paragraph_index += 1
            record_id = format_id("paragraph", paragraph_index)
            candidate = classify_heading(raw)
            record_section_path = [item[1] for item in section_stack]
            if candidate.level is not None:
                affects_hierarchy = candidate.confidence == "high"
                if affects_hierarchy:
                    while section_stack and section_stack[-1][0] >= candidate.level:
                        section_stack.pop()
                    section_stack.append((candidate.level, raw.text.strip(), record_id))
                    record_section_path = [item[1] for item in section_stack]
                else:
                    record_section_path = [*record_section_path, raw.text.strip()]
                sections.append(
                    {
                        "level": candidate.level,
                        "title": raw.text.strip(),
                        "heading_id": record_id,
                        "confidence": candidate.confidence,
                        "reasons": list(candidate.reasons),
                        "affects_hierarchy": affects_hierarchy,
                        "section_path": record_section_path,
                    }
                )
            records.append(
                ParagraphRecord(
                    id=record_id,
                    type="paragraph",
                    order=order,
                    section_path=record_section_path,
                    text=raw.text,
                    style_id=raw.style_id,
                    style_name=raw.style_name,
                    outline_level=raw.outline_level,
                    numbering=_numbering_text(raw),
                    bold=raw.bold,
                    font_size_pt=raw.font_size_pt,
                    heading_candidate=candidate,
                )
            )
        elif raw.kind == "table":
            table_index += 1
            records.append(
                TableRecord(
                    id=format_id("table", table_index),
                    type="table",
                    order=order,
                    section_path=[item[1] for item in section_stack],
                    rows=raw.rows,
                    source_xml_index=raw.xml_index,
                )
            )
    return records, sections


def block_char_count(record: BlockRecord) -> int:
    if isinstance(record, ParagraphRecord):
        return len(record.text)
    if isinstance(record, TableRecord):
        return sum(len(cell) for row in record.rows for cell in row)
    return 0


def build_chunks(
    records: list[BlockRecord],
    *,
    max_chars: int = 20_000,
    max_images: int = 12,
) -> list[ChunkRecord]:
    if max_chars < 1 or max_images < 1:
        raise ValueError("chunk limits must be positive")

    chunks: list[ChunkRecord] = []
    current: list[BlockRecord] = []
    char_count = 0
    image_count = 0

    def flush() -> None:
        nonlocal current, char_count, image_count
        if not current:
            return
        chunk_id = format_id("chunk", len(chunks) + 1)
        warnings: list[WarningRecord] = []
        if len(current) == 1 and (
            char_count > max_chars or image_count > max_images
        ):
            warnings.append(
                WarningRecord(
                    code="oversized_block",
                    message="A single source block exceeds the configured chunk limit and was kept intact.",
                    source_id=current[0].id,
                )
            )
        chunks.append(
            ChunkRecord(
                id=chunk_id,
                block_ids=[record.id for record in current],
                char_count=char_count,
                image_count=image_count,
                file=f"chunks/{chunk_id}.md",
                warnings=warnings,
            )
        )
        current = []
        char_count = 0
        image_count = 0

    for record in records:
        chars = block_char_count(record)
        images = 1 if isinstance(record, ImageRecord) else 0
        if current and (char_count + chars > max_chars or image_count + images > max_images):
            flush()
        current.append(record)
        char_count += chars
        image_count += images
        if len(current) == 1 and (char_count > max_chars or image_count > max_images):
            flush()
    flush()
    return chunks
