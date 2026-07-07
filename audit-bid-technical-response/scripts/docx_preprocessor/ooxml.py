from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree


REQUIRED_PARTS = {
    "[Content_Types].xml",
    "word/document.xml",
    "word/_rels/document.xml.rels",
}


class InvalidDocxError(ValueError):
    pass


@dataclass(frozen=True)
class PackageInfo:
    path: Path
    names: frozenset[str]
    relationships: dict[str, str]


@dataclass
class RawBlock:
    kind: str
    xml_index: int
    text: str = ""
    rows: list[list[str]] = field(default_factory=list)
    style_id: str | None = None
    style_name: str | None = None
    outline_level: int | None = None
    numbering_id: str | None = None
    numbering_level: int | None = None
    bold: bool = False
    font_size_pt: float | None = None
    image_relationship_ids: list[str] = field(default_factory=list)


def _read_relationships(data: bytes) -> dict[str, str]:
    root = etree.fromstring(data)
    relationships: dict[str, str] = {}
    for rel in root:
        rel_id = rel.get("Id")
        target = rel.get("Target")
        if rel_id and target:
            relationships[rel_id] = target
    return relationships


def parse_package(path: str | Path) -> PackageInfo:
    source = Path(path)
    if not source.is_file():
        raise InvalidDocxError(f"DOCX not found: {source}")
    try:
        with ZipFile(source) as archive:
            names = frozenset(archive.namelist())
            missing = sorted(REQUIRED_PARTS - names)
            if missing:
                raise InvalidDocxError(f"invalid DOCX; missing parts: {', '.join(missing)}")
            relationships = _read_relationships(
                archive.read("word/_rels/document.xml.rels")
            )
    except (BadZipFile, OSError, etree.XMLSyntaxError) as exc:
        raise InvalidDocxError(f"invalid DOCX package: {source.name}") from exc
    return PackageInfo(path=source, names=names, relationships=relationships)


def _outline_level(paragraph: Paragraph) -> int | None:
    p_pr = paragraph._p.pPr
    if p_pr is None:
        return None
    node = p_pr.find(qn("w:outlineLvl"))
    if node is None:
        return None
    value = node.get(qn("w:val"))
    return int(value) if value is not None and value.isdigit() else None


def _numbering(paragraph: Paragraph) -> tuple[str | None, int | None]:
    p_pr = paragraph._p.pPr
    if p_pr is None or p_pr.numPr is None:
        return None, None
    num_id = p_pr.numPr.numId
    ilvl = p_pr.numPr.ilvl
    return (
        num_id.val if num_id is not None else None,
        int(ilvl.val) if ilvl is not None else None,
    )


def _image_relationship_ids(paragraph: Paragraph) -> list[str]:
    return _element_image_relationship_ids(paragraph._p)


def _element_image_relationship_ids(element) -> list[str]:
    result: list[str] = []
    for node in element.iter(qn("a:blip")):
        rel_id = node.get(qn("r:embed")) or node.get(qn("r:link"))
        if rel_id:
            result.append(rel_id)
    return result


def _paragraph_block(paragraph: Paragraph, index: int) -> RawBlock:
    sizes = [run.font.size.pt for run in paragraph.runs if run.font.size]
    num_id, num_level = _numbering(paragraph)
    return RawBlock(
        kind="paragraph",
        xml_index=index,
        text=paragraph.text.strip(),
        style_id=paragraph.style.style_id if paragraph.style else None,
        style_name=paragraph.style.name if paragraph.style else None,
        outline_level=_outline_level(paragraph),
        numbering_id=str(num_id) if num_id is not None else None,
        numbering_level=num_level,
        bold=bool(paragraph.runs) and all(run.bold is True for run in paragraph.runs if run.text),
        font_size_pt=max(sizes) if sizes else None,
        image_relationship_ids=_image_relationship_ids(paragraph),
    )


def _table_block(table: Table, index: int) -> RawBlock:
    rows = [
        [cell.text.replace("\n", " / ").strip() for cell in row.cells]
        for row in table.rows
    ]
    return RawBlock(
        kind="table",
        xml_index=index,
        rows=rows,
        image_relationship_ids=_element_image_relationship_ids(table._tbl),
    )


def iter_body_blocks(path: str | Path):
    parse_package(path)
    document = Document(str(path))
    body = document.element.body
    for index, child in enumerate(body.iterchildren()):
        if child.tag == qn("w:p"):
            yield _paragraph_block(Paragraph(child, document), index)
        elif child.tag == qn("w:tbl"):
            yield _table_block(Table(child, document), index)
