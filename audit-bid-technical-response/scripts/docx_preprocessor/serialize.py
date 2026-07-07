from __future__ import annotations

from dataclasses import asdict
from html import escape
from pathlib import Path
from typing import Iterable

from .models import (
    BlockRecord,
    ChunkRecord,
    ImageRecord,
    ParagraphRecord,
    TableRecord,
    WarningRecord,
    dumps_json,
)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def validate_manifest(
    records: list[BlockRecord],
    images: list[ImageRecord],
    chunks: list[ChunkRecord],
) -> None:
    source_ids = [record.id for record in records] + [image.id for image in images]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("duplicate source IDs in document manifest")
    known = set(source_ids)
    previous_order = 0
    for record in records:
        if record.order <= previous_order:
            raise ValueError("source block order is not strictly increasing")
        previous_order = record.order
    for image in images:
        if image.anchor_block_id not in known:
            raise ValueError(f"image anchor does not exist: {image.anchor_block_id}")
    for chunk in chunks:
        missing = [block_id for block_id in chunk.block_ids if block_id not in known]
        if missing:
            raise ValueError(f"chunk {chunk.id} references missing IDs: {missing}")


def render_outline(sections: list[dict]) -> str:
    lines = ["# Document outline", ""]
    if not sections:
        lines.append("_No explicit headings detected; review heading candidates in document.json._")
    for section in sections:
        indent = "  " * max(0, int(section["level"]) - 1)
        path = " > ".join(section["section_path"])
        lines.append(
            f"{indent}- [{section['heading_id']}] {section['title']} "
            f"(confidence: {section['confidence']}; path: {path})"
        )
    return "\n".join(lines) + "\n"


def _escape_cell(value: str) -> str:
    return escape(value, quote=False).replace("|", "\\|").replace("\n", " / ")


def _untrusted_content(source_id: str, content: str) -> list[str]:
    """Render extracted source text inside an explicit, non-forgeable data boundary."""
    return [
        f'<UNTRUSTED_DOCUMENT_CONTENT source_id="{source_id}">',
        escape(content, quote=False),
        "</UNTRUSTED_DOCUMENT_CONTENT>",
    ]


def _page_label(record: BlockRecord) -> str:
    if record.page_start is not None:
        if record.page_end is not None and record.page_end != record.page_start:
            return f"pages {record.page_start}-{record.page_end}"
        return f"pages {record.page_start}"
    if record.page_candidates:
        candidates = ", ".join(
            str(item["page_start"])
            if item["page_start"] == item["page_end"]
            else f"{item['page_start']}-{item['page_end']}"
            for item in record.page_candidates
        )
        return f"page candidates {candidates}"
    return "page unavailable"


def _render_table(table: TableRecord) -> list[str]:
    lines = [
        f"### [{table.id}] [{_page_label(table)}] Table",
        "",
        f'<UNTRUSTED_DOCUMENT_CONTENT source_id="{table.id}">',
    ]
    if not table.rows:
        return lines + ["_(empty table)_", "</UNTRUSTED_DOCUMENT_CONTENT>", ""]
    width = max(len(row) for row in table.rows)
    rows = [row + [""] * (width - len(row)) for row in table.rows]
    lines.append("| " + " | ".join(_escape_cell(cell) for cell in rows[0]) + " |")
    lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
    for row in rows[1:]:
        lines.append("| " + " | ".join(_escape_cell(cell) for cell in row) + " |")
    lines.extend(["</UNTRUSTED_DOCUMENT_CONTENT>", ""])
    return lines


def render_chunk(
    chunk: ChunkRecord,
    lookup: dict[str, BlockRecord],
) -> str:
    lines = [f"# {chunk.id}", ""]
    for block_id in chunk.block_ids:
        record = lookup[block_id]
        section = " > ".join(record.section_path) or "(root)"
        if isinstance(record, ParagraphRecord):
            lines.extend(
                [
                    f"[{record.id}] [{_page_label(record)}] [{section}]",
                    *_untrusted_content(record.id, record.text or "_(image-only paragraph)_"),
                    "",
                ]
            )
        elif isinstance(record, TableRecord):
            lines.extend([f"Section: {section}", "", *_render_table(record)])
        elif isinstance(record, ImageRecord):
            status = record.analysis_status
            lines.extend(
                [
                    f"### [{record.id}] Image",
                    "",
                    f"Page: {_page_label(record)}",
                    f"Section: {section}",
                    f"Anchor: {record.anchor_block_id}",
                    f"Analysis status: {status}",
                    f"Decorative candidate: {str(record.decorative_candidate).lower()}",
                    f'<UNTRUSTED_DOCUMENT_IMAGE source_id="{record.id}">',
                    f"![{record.id}](../{record.file})",
                    "</UNTRUSTED_DOCUMENT_IMAGE>",
                    "",
                ]
            )
    for warning in chunk.warnings:
        lines.append(f"> Warning `{warning.code}`: {warning.message}")
    return "\n".join(lines).rstrip() + "\n"


def write_document_outputs(
    output_dir: Path,
    *,
    role: str,
    file_name: str,
    file_sha256: str,
    records: list[BlockRecord],
    sections: list[dict],
    images: list[ImageRecord],
    chunks: list[ChunkRecord],
    warnings: Iterable[WarningRecord],
    pagination: dict | None = None,
) -> dict:
    validate_manifest(records, images, chunks)
    warning_list = list(warnings)
    manifest = {
        "schema_version": "1.0",
        "role": role,
        "file_name": file_name,
        "sha256": file_sha256,
        "blocks": [asdict(record) for record in records],
        "sections": sections,
        "images": [asdict(image) for image in images],
        "chunks": [asdict(chunk) for chunk in chunks],
        "warnings": [asdict(warning) for warning in warning_list],
        "pagination": pagination
        or {
            "status": "unavailable",
            "source": None,
            "acquisition": None,
            "pdf_file": None,
            "pdf_sha256": None,
            "page_count": 0,
            "mapped_text_blocks": 0,
            "total_text_blocks": 0,
            "coverage": 0.0,
            "confidence_counts": {
                "high": 0,
                "medium": 0,
                "low": 0,
                "ambiguous": 0,
                "unmapped": 0,
            },
            "warnings": [],
        },
    }
    _write_text(output_dir / "document.json", dumps_json(manifest))
    _write_text(output_dir / "outline.md", render_outline(sections))
    lookup = {record.id: record for record in [*records, *images]}
    for chunk in chunks:
        _write_text(output_dir / chunk.file, render_chunk(chunk, lookup))
    return manifest
