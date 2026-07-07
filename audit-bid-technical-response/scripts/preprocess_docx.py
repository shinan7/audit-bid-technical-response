#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
import shutil
import sys
import tempfile

from docx_preprocessor.images import extract_images, merge_images_into_records
from docx_preprocessor.models import SCHEMA_VERSION, dumps_json, sha256_file
from docx_preprocessor.ooxml import InvalidDocxError, iter_body_blocks, parse_package
from docx_preprocessor.pagination import (
    extract_pdf_pages,
    map_records,
    unavailable_pagination,
)
from docx_preprocessor.serialize import write_document_outputs
from docx_preprocessor.structure import assign_structure, build_chunks
from docx_preprocessor.word_export import WordExportError, export_word_pdf


def chunk_chars(value: str) -> int:
    parsed = int(value)
    if parsed < 5000:
        raise argparse.ArgumentTypeError("--chunk-max-chars must be at least 5000")
    return parsed


def positive_images(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("--chunk-max-images must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministically preprocess procurement and bid DOCX files for technical-response auditing."
    )
    parser.add_argument("--procurement", required=True, type=Path)
    parser.add_argument("--bid", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--procurement-pdf", type=Path)
    parser.add_argument("--bid-pdf", type=Path)
    parser.add_argument(
        "--export-with-word",
        action="store_true",
        help="Use Microsoft Word to export PDFs only for roles without a supplied PDF.",
    )
    parser.add_argument("--chunk-max-chars", type=chunk_chars, default=20_000)
    parser.add_argument("--chunk-max-images", type=positive_images, default=12)
    return parser


def process_document(
    source: Path,
    role: str,
    output_dir: Path,
    *,
    max_chars: int,
    max_images: int,
    supplied_pdf: Path | None = None,
    export_with_word: bool = False,
    word_exporter=export_word_pdf,
) -> tuple[dict, list[dict]]:
    package = parse_package(source)
    raw_blocks = list(iter_body_blocks(source))
    records, sections = assign_structure(raw_blocks)
    images, warnings = extract_images(
        source, package, raw_blocks, records, output_dir
    )

    pagination = unavailable_pagination("No Microsoft Word PDF was supplied or exported")
    pdf_target = output_dir / "pagination" / "source.pdf"
    acquisition: str | None = None
    if supplied_pdf is not None:
        source_pdf = supplied_pdf.expanduser().resolve()
        if not source_pdf.is_file():
            raise FileNotFoundError(f"supplied PDF does not exist: {source_pdf}")
        pdf_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_pdf, pdf_target)
        acquisition = "user_provided"
    elif export_with_word:
        word_exporter(source, pdf_target)
        acquisition = "word_export"

    if acquisition is not None:
        pages = extract_pdf_pages(pdf_target)
        records, images, pagination = map_records(
            records,
            images,
            pages,
            acquisition=acquisition,
            pdf_file="pagination/source.pdf",
            pdf_sha256=sha256_file(pdf_target),
        )
        if pagination["status"] == "mismatch":
            raise ValueError(f"{role} PDF does not match its DOCX source")

    merged = merge_images_into_records(records, images)
    chunks = build_chunks(merged, max_chars=max_chars, max_images=max_images)
    manifest = write_document_outputs(
        output_dir,
        role=role,
        file_name=source.name,
        file_sha256=sha256_file(source),
        records=records,
        sections=sections,
        images=images,
        chunks=chunks,
        warnings=warnings,
        pagination=pagination,
    )
    return manifest, [asdict(warning) for warning in warnings]


def run(args: argparse.Namespace, *, word_exporter=export_word_pdf) -> None:
    output = args.output.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent)
    )
    try:
        manifests: dict[str, dict] = {}
        project_warnings: list[dict] = []
        for role, source, supplied_pdf in (
            (
                "procurement",
                args.procurement.expanduser().resolve(),
                args.procurement_pdf,
            ),
            ("bid", args.bid.expanduser().resolve(), args.bid_pdf),
        ):
            manifest, warnings = process_document(
                source,
                role,
                temp_dir / role,
                max_chars=args.chunk_max_chars,
                max_images=args.chunk_max_images,
                supplied_pdf=supplied_pdf,
                export_with_word=args.export_with_word,
                word_exporter=word_exporter,
            )
            manifests[role] = manifest
            project_warnings.extend({"role": role, **warning} for warning in warnings)

        project = {
            "schema_version": SCHEMA_VERSION,
            "documents": {
                role: {
                    "file_name": manifest["file_name"],
                    "sha256": manifest["sha256"],
                    "manifest": f"{role}/document.json",
                    "pagination_status": manifest["pagination"]["status"],
                }
                for role, manifest in manifests.items()
            },
            "warnings": project_warnings,
        }
        (temp_dir / "project.json").write_text(
            dumps_json(project), encoding="utf-8"
        )
        temp_dir.rename(output)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run(args)
    except (InvalidDocxError, FileExistsError, FileNotFoundError, ValueError, WordExportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"unexpected error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
