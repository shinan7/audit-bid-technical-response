from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from .models import BlockRecord, ImageRecord, ParagraphRecord, TableRecord


_WHITESPACE = re.compile(r"\s+")


def normalize_pdf_text(text: str) -> str:
    """Normalize layout-created whitespace for matching, never for quotation."""
    return _WHITESPACE.sub("", text or "")


@dataclass(frozen=True)
class PdfPage:
    number: int
    raw_text: str
    normalized_text: str

    @classmethod
    def from_text(cls, number: int, text: str) -> "PdfPage":
        return cls(number=number, raw_text=text or "", normalized_text=normalize_pdf_text(text))


@dataclass(frozen=True)
class PageMatch:
    page_start: int | None
    page_end: int | None
    confidence: str
    method: str | None
    candidates: tuple[tuple[int, int], ...] = ()
    stream_start: int | None = None
    stream_end: int | None = None


@dataclass(frozen=True)
class _PageStream:
    text: str
    pages_by_offset: tuple[int, ...]


def extract_pdf_pages(pdf_path: Path) -> list[PdfPage]:
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        return [
            PdfPage.from_text(index, page.extract_text() or "")
            for index, page in enumerate(pdf.pages, start=1)
        ]


def _build_stream(pages: Iterable[PdfPage]) -> _PageStream:
    text_parts: list[str] = []
    page_offsets: list[int] = []
    for page in pages:
        normalized = page.normalized_text
        text_parts.append(normalized)
        page_offsets.extend([page.number] * len(normalized))
    return _PageStream("".join(text_parts), tuple(page_offsets))


def _find_occurrences(needle: str, stream: _PageStream) -> list[tuple[int, int, int, int]]:
    if not needle or not stream.text:
        return []
    found: list[tuple[int, int, int, int]] = []
    start = 0
    while True:
        offset = stream.text.find(needle, start)
        if offset < 0:
            break
        end = offset + len(needle)
        found.append((offset, end, stream.pages_by_offset[offset], stream.pages_by_offset[end - 1]))
        start = offset + 1
    return found


def _match_text(
    text: str,
    stream: _PageStream,
    *,
    cursor: int | None = None,
    ordered: bool = False,
    next_text: str | None = None,
    allow_anchors: bool = False,
) -> PageMatch:
    needle = normalize_pdf_text(text)
    occurrences = _find_occurrences(needle, stream)
    if cursor is not None:
        occurrences = [item for item in occurrences if item[0] >= cursor]
    if not occurrences:
        if allow_anchors and len(needle) >= 48:
            head_occurrences = _find_occurrences(needle[:24], stream)
            tail_occurrences = _find_occurrences(needle[-24:], stream)
            if cursor is not None:
                head_occurrences = [item for item in head_occurrences if item[0] >= cursor]
            pairs: list[tuple[tuple[int, int, int, int], tuple[int, int, int, int]]] = []
            for head in head_occurrences:
                tails = [tail for tail in tail_occurrences if tail[0] >= head[1]]
                if tails:
                    pairs.append((head, min(tails, key=lambda item: item[0] - head[1])))
            ranges = tuple(dict.fromkeys((head[2], tail[3]) for head, tail in pairs))
            if len(ranges) == 1 and pairs:
                head, tail = min(pairs, key=lambda pair: pair[1][0] - pair[0][1])
                return PageMatch(
                    head[2], tail[3], "medium", "distinctive_anchors", (), head[0], tail[1]
                )
            if ranges:
                return PageMatch(None, None, "ambiguous", "distinctive_anchors", ranges)
        return PageMatch(None, None, "unmapped", None)

    ranges = tuple(dict.fromkeys((item[2], item[3]) for item in occurrences))
    selected: tuple[int, int, int, int] | None = None
    method = "exact_text"
    if len(occurrences) == 1:
        selected = occurrences[0]
    elif not ordered:
        return PageMatch(None, None, "ambiguous", "exact_text", ranges)
    else:
        following = _find_occurrences(normalize_pdf_text(next_text or ""), stream)
        if following:
            scored: list[tuple[int, tuple[int, int, int, int]]] = []
            for occurrence in occurrences:
                gaps = [item[0] - occurrence[1] for item in following if item[0] >= occurrence[1]]
                if gaps:
                    scored.append((min(gaps), occurrence))
            if scored:
                best_gap = min(item[0] for item in scored)
                best = [item[1] for item in scored if item[0] == best_gap]
                if len(best) == 1:
                    selected = best[0]
                    method = "ordered_exact_text_next_context"
        if selected is None and cursor is not None:
            gaps = [(item[0] - cursor, item) for item in occurrences]
            best_gap = min(item[0] for item in gaps)
            best = [item[1] for item in gaps if item[0] == best_gap]
            if len(best) == 1:
                selected = best[0]
                method = "ordered_exact_text_previous_context"
        if selected is None:
            return PageMatch(None, None, "ambiguous", "ordered_exact_text", ranges)

    confidence = "high" if len(needle) >= 4 else "medium"
    return PageMatch(
        selected[2],
        selected[3],
        confidence,
        method if ordered else "exact_text",
        (),
        selected[0],
        selected[1],
    )


def map_text(text: str, pages: Iterable[PdfPage]) -> PageMatch:
    """Map standalone text; repeated unresolved occurrences are returned as candidates."""
    return _match_text(text, _build_stream(pages))


def _record_text(record: BlockRecord) -> str:
    if isinstance(record, ParagraphRecord):
        return record.text
    if isinstance(record, TableRecord):
        return "".join(cell for row in record.rows for cell in row)
    return ""


def _apply_match(record: BlockRecord, match: PageMatch) -> None:
    record.page_start = match.page_start
    record.page_end = match.page_end
    record.page_source = (
        "microsoft_word_pdf"
        if match.page_start is not None or match.candidates
        else None
    )
    record.page_confidence = match.confidence
    record.page_match_method = match.method
    record.page_candidates = [
        {"page_start": page_start, "page_end": page_end}
        for page_start, page_end in match.candidates
    ]


def _confirmed_heading_mismatch(records: list[BlockRecord]) -> bool:
    headings = [
        record
        for record in records
        if isinstance(record, ParagraphRecord)
        and record.heading_candidate is not None
        and record.heading_candidate.confidence == "high"
    ]
    if not headings:
        return False
    edges = headings[:5] + headings[-5:]
    return not any(record.page_start is not None for record in edges)


def map_records(
    records: list[BlockRecord],
    images: list[ImageRecord],
    pages: list[PdfPage],
    *,
    acquisition: str | None = None,
    pdf_file: str | None = None,
    pdf_sha256: str | None = None,
) -> tuple[list[BlockRecord], list[ImageRecord], dict]:
    """Map DOCX source IDs to Word PDF physical pages in document order."""
    mapped_records = deepcopy(records)
    mapped_images = deepcopy(images)
    stream = _build_stream(pages)
    cursor: int | None = None

    text_records = [record for record in mapped_records if normalize_pdf_text(_record_text(record))]
    for index, record in enumerate(text_records):
        normalized_record_text = normalize_pdf_text(_record_text(record))
        if normalized_record_text.rstrip(":：") == "供应商（公章）":
            _apply_match(
                record,
                PageMatch(
                    None,
                    None,
                    "unmapped",
                    "non_locatable_repeated_boilerplate",
                ),
            )
            continue
        next_text = _record_text(text_records[index + 1]) if index + 1 < len(text_records) else None
        match = _match_text(
            _record_text(record),
            stream,
            cursor=cursor,
            ordered=True,
            next_text=next_text,
            allow_anchors=True,
        )
        _apply_match(record, match)
        if match.stream_end is not None and len(normalized_record_text) >= 4:
            cursor = match.stream_end

    for record in mapped_records:
        if not isinstance(record, TableRecord) or record.page_start is not None:
            continue
        cell_texts = sorted(
            {
                cell.strip()
                for row in record.rows
                for cell in row
                if len(normalize_pdf_text(cell)) >= 6
            },
            key=len,
            reverse=True,
        )
        anchor_ranges: list[tuple[int, int]] = []
        for cell_text in cell_texts[:24]:
            cell_match = _match_text(cell_text, stream, allow_anchors=True)
            if cell_match.page_start is not None:
                anchor_ranges.append(
                    (cell_match.page_start, cell_match.page_end or cell_match.page_start)
                )
            elif len(cell_match.candidates) == 1:
                anchor_ranges.append(cell_match.candidates[0])
        anchor_ranges = list(dict.fromkeys(anchor_ranges))
        if anchor_ranges:
            _apply_match(
                record,
                PageMatch(
                    min(item[0] for item in anchor_ranges),
                    max(item[1] for item in anchor_ranges),
                    "medium" if len(anchor_ranges) >= 2 else "low",
                    "table_cell_anchors",
                ),
            )

    for index, record in enumerate(mapped_records):
        if not isinstance(record, TableRecord) or record.page_start is not None:
            continue
        previous = next(
            (item for item in reversed(mapped_records[:index]) if item.page_start is not None),
            None,
        )
        following = next(
            (item for item in mapped_records[index + 1 :] if item.page_start is not None),
            None,
        )
        if previous is None and following is None:
            continue
        page_start = (
            previous.page_end or previous.page_start
            if previous is not None
            else following.page_start
        )
        page_end = (
            following.page_start
            if following is not None
            else previous.page_end or previous.page_start
        )
        if previous is not None and following is not None and abs(page_end - page_start) > 1:
            _apply_match(
                record,
                PageMatch(
                    None,
                    None,
                    "ambiguous",
                    "neighbor_context_too_wide",
                    (
                        (previous.page_start, previous.page_end or previous.page_start),
                        (following.page_start, following.page_end or following.page_start),
                    ),
                ),
            )
            continue
        _apply_match(
            record,
            PageMatch(
                min(page_start, page_end),
                max(page_start, page_end),
                "low",
                "neighbor_context_union",
            ),
        )

    by_id = {record.id: record for record in mapped_records}
    for image in mapped_images:
        anchor = by_id.get(image.anchor_block_id)
        ranges: list[tuple[int, int]] = []
        if anchor is not None and anchor.page_start is not None:
            ranges.append((anchor.page_start, anchor.page_end or anchor.page_start))

        caption: BlockRecord | None = None
        if image.context_after:
            candidate = by_id.get(image.context_after[0])
            if candidate is not None and re.match(r"^\s*[图表]\s*\d", _record_text(candidate)):
                caption = candidate
        if caption is not None and caption.page_start is not None:
            ranges.append((caption.page_start, caption.page_end or caption.page_start))

        if not ranges:
            nearest_ids = [
                *(image.context_before[-1:] if image.context_before else []),
                *(image.context_after[:1] if image.context_after else []),
            ]
            for source_id in nearest_ids:
                context = by_id.get(source_id)
                if context is not None and context.page_start is not None:
                    ranges.append((context.page_start, context.page_end or context.page_start))
        if not ranges:
            continue
        image.page_start = min(item[0] for item in ranges)
        image.page_end = max(item[1] for item in ranges)
        image.page_source = "microsoft_word_pdf"
        image.page_confidence = "low"
        image.page_match_method = (
            "anchor_caption_union" if anchor is not None and caption is not None else "anchor_inheritance"
        )

    mapped_count = sum(record.page_start is not None for record in text_records)
    total_count = len(text_records)
    coverage = mapped_count / total_count if total_count else 0.0
    normalized_pdf_chars = len(stream.text)
    if normalized_pdf_chars < 100:
        status = "unavailable"
    elif coverage < 0.20 or _confirmed_heading_mismatch(mapped_records):
        status = "mismatch"
    elif coverage < 0.85:
        status = "unreliable"
    else:
        status = "reliable"

    confidence_counts = {level: 0 for level in ("high", "medium", "low", "ambiguous", "unmapped")}
    for record in text_records:
        confidence_counts.setdefault(record.page_confidence, 0)
        confidence_counts[record.page_confidence] += 1

    warnings: list[str] = []
    if normalized_pdf_chars < 100:
        warnings.append("PDF text layer contains fewer than 100 normalized characters")
    if status == "mismatch":
        warnings.append("PDF content does not reliably correspond to the DOCX source")

    metadata = {
        "status": status,
        "source": "microsoft_word_pdf" if pages else None,
        "acquisition": acquisition,
        "pdf_file": pdf_file,
        "pdf_sha256": pdf_sha256,
        "page_count": len(pages),
        "mapped_text_blocks": mapped_count,
        "total_text_blocks": total_count,
        "coverage": round(coverage, 6),
        "confidence_counts": confidence_counts,
        "warnings": warnings,
    }
    return mapped_records, mapped_images, metadata


def unavailable_pagination(message: str | None = None) -> dict:
    return {
        "status": "unavailable",
        "source": None,
        "acquisition": None,
        "pdf_file": None,
        "pdf_sha256": None,
        "page_count": 0,
        "mapped_text_blocks": 0,
        "total_text_blocks": 0,
        "coverage": 0.0,
        "confidence_counts": {"high": 0, "medium": 0, "low": 0, "ambiguous": 0, "unmapped": 0},
        "warnings": [message] if message else [],
    }
