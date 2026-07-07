from __future__ import annotations

from collections import Counter
from hashlib import sha256
from io import BytesIO
import mimetypes
from pathlib import Path, PurePosixPath
import posixpath
from zipfile import ZipFile

from PIL import Image, UnidentifiedImageError
from docx.oxml.ns import qn
from lxml import etree

from .models import (
    BlockRecord,
    ImageRecord,
    ParagraphRecord,
    TableRecord,
    WarningRecord,
    format_id,
)
from .ooxml import PackageInfo, RawBlock


READY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _part_name(target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("word", target))


def _dimensions(data: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(BytesIO(data)) as image:
            return image.width, image.height
    except (UnidentifiedImageError, OSError):
        return None, None


def _header_footer_image_count(archive: ZipFile) -> int:
    count = 0
    for name in archive.namelist():
        if not (
            name.startswith("word/header") or name.startswith("word/footer")
        ) or not name.endswith(".xml"):
            continue
        try:
            root = etree.fromstring(archive.read(name))
        except etree.XMLSyntaxError:
            continue
        count += sum(1 for _ in root.iter(qn("a:blip")))
    return count


def _anchor_mapping(raw_blocks: list[RawBlock], records: list[BlockRecord]):
    paragraph_records = iter(
        record for record in records if isinstance(record, ParagraphRecord)
    )
    table_records = iter(record for record in records if isinstance(record, TableRecord))
    result: list[tuple[RawBlock, BlockRecord]] = []
    for raw in raw_blocks:
        if raw.kind == "paragraph" and (raw.text or raw.image_relationship_ids):
            result.append((raw, next(paragraph_records)))
        elif raw.kind == "table":
            result.append((raw, next(table_records)))
    return result


def extract_images(
    docx_path: str | Path,
    package: PackageInfo,
    raw_blocks: list[RawBlock],
    records: list[BlockRecord],
    output_root: Path,
) -> tuple[list[ImageRecord], list[WarningRecord]]:
    images_dir = output_root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[WarningRecord] = []
    images: list[ImageRecord] = []
    ordered_records = sorted(records, key=lambda record: record.order)
    record_positions = {record.id: index for index, record in enumerate(ordered_records)}

    with ZipFile(docx_path) as archive:
        excluded = _header_footer_image_count(archive)
        if excluded:
            warnings.append(
                WarningRecord(
                    code="header_footer_images_excluded",
                    message=f"Excluded {excluded} header/footer image occurrence(s) from audit evidence.",
                )
            )

        for raw, anchor in _anchor_mapping(raw_blocks, records):
            for relationship_id in raw.image_relationship_ids:
                target = package.relationships.get(relationship_id)
                if not target:
                    warnings.append(
                        WarningRecord(
                            code="unresolved_image_relationship",
                            message=f"Image relationship {relationship_id} has no target.",
                            source_id=anchor.id,
                        )
                    )
                    continue
                part_name = _part_name(target)
                if part_name not in package.names:
                    warnings.append(
                        WarningRecord(
                            code="missing_image_part",
                            message=f"Image part is missing from the package: {part_name}",
                            source_id=anchor.id,
                        )
                    )
                    continue

                data = archive.read(part_name)
                digest = sha256(data).hexdigest()
                extension = PurePosixPath(part_name).suffix.lower() or ".bin"
                image_id = format_id("image", len(images) + 1)
                relative_file = f"images/{image_id}{extension}"
                (output_root / relative_file).write_bytes(data)
                width, height = _dimensions(data)
                status = "ready" if extension in READY_EXTENSIONS else "unsupported_format"
                if status != "ready":
                    warnings.append(
                        WarningRecord(
                            code="unsupported_image_format",
                            message=f"{image_id} uses unsupported format {extension}.",
                            source_id=image_id,
                        )
                    )
                position = record_positions[anchor.id]
                context_before = [
                    record.id for record in ordered_records[max(0, position - 2) : position]
                ]
                context_after = [
                    record.id for record in ordered_records[position + 1 : position + 3]
                ]
                images.append(
                    ImageRecord(
                        id=image_id,
                        type="image",
                        order=anchor.order,
                        section_path=list(anchor.section_path),
                        anchor_block_id=anchor.id,
                        context_before=context_before,
                        context_after=context_after,
                        file=relative_file,
                        source_part="word/document.xml",
                        content_type=mimetypes.guess_type(part_name)[0]
                        or "application/octet-stream",
                        sha256=digest,
                        width_px=width,
                        height_px=height,
                        analysis_status=status,
                    )
                )

    occurrence_counts = Counter(image.sha256 for image in images)
    for image in images:
        image.occurrence_count = occurrence_counts[image.sha256]
        if (
            image.occurrence_count >= 3
            and image.width_px is not None
            and image.height_px is not None
            and image.width_px <= 96
            and image.height_px <= 96
        ):
            image.decorative_candidate = True
            image.decorative_reasons.append("tiny_repeated_image")
    return images, warnings


def merge_images_into_records(
    records: list[BlockRecord], images: list[ImageRecord]
) -> list[BlockRecord]:
    by_anchor: dict[str, list[ImageRecord]] = {}
    for image in images:
        by_anchor.setdefault(image.anchor_block_id, []).append(image)
    merged: list[BlockRecord] = []
    for record in sorted(records, key=lambda item: item.order):
        merged.append(record)
        merged.extend(by_anchor.get(record.id, []))
    return merged
