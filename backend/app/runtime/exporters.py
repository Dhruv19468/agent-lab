"""Turn the agent's Markdown into Word, Excel, PDF or tidy Markdown.

The model only writes text (Markdown). Real .docx / .xlsx / .pdf files are built here, in
code, so one plan can be downloaded in any format without running the agent again.

A test plan (its title contains "test plan") is laid out like the human reference plans in
data/raw/*/..._TestPlan.docx:

    MASTER TEST PLAN                      bold title
    <project name>
    Version: ... / Application: ...       document-control lines
    References                            bold paragraph + text
    Section 1 – Test Objectives           Heading 1, numbered in order
    4.1 Test levels                       Heading 2
    - bullets, tables                     Word bullet lists and tables

Any other document keeps its own headings.

Flow:  Markdown --parse_markdown--> blocks --build_document--> Doc --to_docx / to_xlsx / to_pdf / to_markdown
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

# format -> (media type, file extension)
FORMATS: dict[str, tuple[str, str]] = {
    "md": ("text/markdown; charset=utf-8", ".md"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "pdf": ("application/pdf", ".pdf"),
}
SUFFIX_TO_FORMAT = {suffix: name for name, (_, suffix) in FORMATS.items()}

# --------------------------------------------------------------------------------------------
# 1. Markdown -> blocks
# --------------------------------------------------------------------------------------------


@dataclass
class Block:
    kind: str  # heading | paragraph | bullet | number | table
    text: str = ""
    level: int = 0  # heading: 1-6; bullet/number: nesting depth from 0
    marker: str = ""  # number: "1." as written
    rows: list[list[str]] = field(default_factory=list)  # table: first row = header


_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBER = re.compile(r"^(\s*)(\d+[.)])\s+(.*)$")
_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells = re.split(r"(?<!\\)\|", line)
    return [cell.strip().replace("\\|", "|") for cell in cells]


def parse_markdown(markdown: str) -> list[Block]:
    """Markdown -> blocks. Every non-empty line is its own paragraph (models rarely hard-wrap)."""
    blocks: list[Block] = []
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    index = 0
    in_code = False
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        index += 1
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            if stripped:
                blocks.append(Block("paragraph", stripped))
            continue
        if not stripped or _RULE.match(stripped):
            continue
        if stripped.startswith("|"):
            rows = [_split_row(stripped)]
            while index < len(lines) and lines[index].strip().startswith("|"):
                row_line = lines[index].strip()
                index += 1
                if not _TABLE_SEPARATOR.match(row_line):
                    rows.append(_split_row(row_line))
            width = max(len(row) for row in rows)
            blocks.append(Block("table", rows=[row + [""] * (width - len(row)) for row in rows]))
            continue
        if match := _HEADING.match(stripped):
            blocks.append(Block("heading", match.group(2).strip(), level=len(match.group(1))))
        elif match := _BULLET.match(line):
            blocks.append(Block("bullet", match.group(2).strip(), level=len(match.group(1).expandtabs(4)) // 2))
        elif match := _NUMBER.match(line):
            blocks.append(
                Block("number", match.group(3).strip(), level=len(match.group(1).expandtabs(4)) // 2, marker=match.group(2))
            )
        else:
            blocks.append(Block("paragraph", stripped))
    return blocks


# Inline Markdown: **bold**, *italic* / _italic_, `code`
_INLINE = re.compile(r"(\*\*.+?\*\*|__.+?__|`[^`]+`|(?<![\w*])\*(?!\s).+?(?<!\s)\*(?!\w)|(?<![\w_])_(?!\s).+?(?<!\s)_(?![\w]))")


@dataclass
class Span:
    text: str
    bold: bool = False
    italic: bool = False


def inline_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    for part in _INLINE.split(text):
        if not part:
            continue
        if (part.startswith("**") and part.endswith("**") or part.startswith("__") and part.endswith("__")) and len(part) > 4:
            spans.append(Span(part[2:-2], bold=True))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            spans.append(Span(part[1:-1]))
        elif (part.startswith("*") and part.endswith("*") or part.startswith("_") and part.endswith("_")) and len(part) > 2:
            spans.append(Span(part[1:-1], italic=True))
        else:
            spans.append(Span(part))
    return spans


def plain(text: str) -> str:
    """Inline Markdown removed: '**USD 50,000** limit' -> 'USD 50,000 limit'."""
    return "".join(span.text for span in inline_spans(text))


# --------------------------------------------------------------------------------------------
# 2. blocks -> document (reference test-plan layout)
# --------------------------------------------------------------------------------------------


@dataclass
class Section:
    heading: str  # as shown: "Section 3 – Test Assumptions", or the original heading
    title: str  # without numbering: "Test Assumptions"
    number: int | None
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Doc:
    test_plan: bool
    title: str  # "MASTER TEST PLAN" for a test plan, else the first heading
    subtitle: str  # the project name for a test plan
    front: list[Block] = field(default_factory=list)  # document-control lines before the first section
    references: list[Block] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)


_NUMBERING = re.compile(r"^(?:section\s+)?\d+(?:\.\d+)*[.)]?\s*(?:[–—:-]\s*)?", re.IGNORECASE)
_TITLE_SPLIT = re.compile(r"\s*:\s+|\s+[–—-]\s+")  # "Master Test Plan – X", "Test Plan: X"
_OWN_NUMBER = re.compile(r"^(?:section\s+)?(\d+)(?:[.)]|\s+[–—:-])?\s", re.IGNORECASE)


def _strip_numbering(heading: str) -> str:
    return _NUMBERING.sub("", plain(heading), count=1).strip() or plain(heading)


def build_document(markdown: str) -> Doc:
    blocks = parse_markdown(markdown)
    headings = [block for block in blocks if block.kind == "heading"]

    title_block = None
    if headings and headings[0].level == 1 and all(h.level > 1 for h in headings[1:]):
        title_block = headings[0]
    title_text = plain(title_block.text) if title_block else ""
    test_plan = "test plan" in title_text.lower() or (
        not title_block and any("test plan" in plain(b.text).lower() for b in blocks[:3])
    )

    if test_plan:
        # "Master Test Plan – Rebate Claim Validation" -> subtitle "Rebate Claim Validation"
        parts = _TITLE_SPLIT.split(title_text, maxsplit=1)
        doc = Doc(test_plan=True, title="MASTER TEST PLAN", subtitle=parts[1].strip() if len(parts) > 1 else "")
    else:
        doc = Doc(test_plan=False, title=title_text, subtitle="")

    body = [block for block in blocks if block is not title_block]
    section_level = min((b.level for b in body if b.kind == "heading"), default=2)

    target: list[Block] = doc.front
    number = 0
    for block in body:
        if block.kind == "heading" and block.level == section_level:
            name = _strip_numbering(block.text)
            lowered = name.lower()
            if doc.test_plan and lowered in {"document control", "document information", "document details"}:
                target = doc.front
                continue
            if doc.test_plan and lowered in {"references", "reference documents"}:
                target = doc.references
                continue
            if doc.test_plan:
                # keep the plan's own number ("## 21. Assumptions…") so cross-references
                # such as "see section 21" stay right; number in order only when it has none
                own = _OWN_NUMBER.match(plain(block.text).strip())
                number = int(own.group(1)) if own else number + 1
                section = Section(heading=f"Section {number} – {name}", title=name, number=number)
            else:
                section = Section(heading=plain(block.text), title=plain(block.text), number=None)
            doc.sections.append(section)
            target = section.blocks
            continue
        if block.kind == "heading":
            text = block.text
            if doc.test_plan and number and target is not doc.front and target is not doc.references:
                # keep sub-section numbers in step with the renumbered section: "5.1 Test levels" -> "3.1 …"
                text = re.sub(r"^\d+(?=\.\d)", str(number), plain(text))
            block = Block("heading", text, level=block.level - section_level + 1)  # 2 = sub-section
        target.append(block)
    return doc


# --------------------------------------------------------------------------------------------
# 3a. Markdown (tidy, reference headings)
# --------------------------------------------------------------------------------------------


def _blocks_to_markdown(blocks: list[Block]) -> list[str]:
    out: list[str] = []
    for block in blocks:
        if block.kind == "heading":
            out.append(f"{'#' * min(block.level + 1, 6)} {block.text}")
        elif block.kind == "bullet":
            out.append(f"{'  ' * block.level}- {block.text}")
        elif block.kind == "number":
            out.append(f"{'  ' * block.level}{block.marker} {block.text}")
        elif block.kind == "table":
            header, *rest = block.rows
            rows = ["| " + " | ".join(header) + " |", "|" + " --- |" * len(header)]
            rows += ["| " + " | ".join(row) + " |" for row in rest]
            out.append("\n".join(rows))  # one chunk: a blank line inside a table would split it
        else:
            out.append(block.text)
    return out


def to_markdown(doc: Doc) -> bytes:
    lines: list[str] = []
    if doc.title:
        lines.append(f"# {doc.title}")
    if doc.subtitle:
        lines.append(f"**{doc.subtitle}**")
    lines += _blocks_to_markdown(doc.front)
    if doc.references:
        lines.append("**References**")
        lines += _blocks_to_markdown(doc.references)
    for section in doc.sections:
        lines.append(f"## {section.heading}")
        lines += _blocks_to_markdown(section.blocks)
    return ("\n\n".join(lines) + "\n").encode("utf-8")


# --------------------------------------------------------------------------------------------
# 3b. Word
# --------------------------------------------------------------------------------------------


def _add_runs(paragraph, text: str, *, bold: bool = False) -> None:
    for span in inline_spans(text):
        run = paragraph.add_run(span.text)
        run.bold = bold or span.bold
        run.italic = span.italic


def _docx_blocks(document, blocks: list[Block]) -> None:
    for block in blocks:
        if block.kind == "heading":
            document.add_heading(plain(block.text), level=min(block.level, 4))
        elif block.kind in {"bullet", "number"}:
            base = "List Bullet" if block.kind == "bullet" else "List Number"
            style = base if block.level == 0 else f"{base} {min(block.level + 1, 3)}"
            _add_runs(document.add_paragraph(style=style), block.text)
        elif block.kind == "table":
            header, *rest = block.rows
            table = document.add_table(rows=1, cols=len(header))
            table.style = "Table Grid"
            for cell, text in zip(table.rows[0].cells, header, strict=False):
                cell.text = ""
                _add_runs(cell.paragraphs[0], text, bold=True)
            for row in rest:
                cells = table.add_row().cells
                for cell, text in zip(cells, row, strict=False):
                    cell.text = ""
                    _add_runs(cell.paragraphs[0], text)
            document.add_paragraph()
        else:
            _add_runs(document.add_paragraph(), block.text)


def to_docx(doc: Doc) -> bytes:
    from docx import Document
    from docx.shared import Pt

    document = Document()
    document.core_properties.title = f"{doc.title} – {doc.subtitle}".strip(" –") if doc.subtitle else doc.title
    if doc.title:
        run = document.add_paragraph().add_run(doc.title)
        run.bold = True
        run.font.size = Pt(16) if doc.test_plan else Pt(18)
    if doc.subtitle:
        run = document.add_paragraph().add_run(doc.subtitle)
        run.font.size = Pt(13)
    _docx_blocks(document, doc.front)
    if doc.references:
        document.add_paragraph().add_run("References").bold = True
        _docx_blocks(document, doc.references)
    for section in doc.sections:
        document.add_heading(section.heading, level=1)
        _docx_blocks(document, section.blocks)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------------------------
# 3c. Excel
# --------------------------------------------------------------------------------------------

_SHEET_FORBIDDEN = re.compile(r"[\[\]:*?/\\]")
EXCEL_CELL_LIMIT = 32_000


def _blocks_to_text(blocks: list[Block], table_note: str | None = None) -> str:
    out: list[str] = []
    for block in blocks:
        if block.kind == "heading":
            out.append(("\n" if out else "") + plain(block.text).upper())
        elif block.kind == "bullet":
            out.append(f"{'    ' * block.level}• {plain(block.text)}")
        elif block.kind == "number":
            out.append(f"{'    ' * block.level}{block.marker} {plain(block.text)}")
        elif block.kind == "table":
            out.append(table_note or "(table)")
        else:
            out.append(plain(block.text))
    return "\n".join(out)


def _sheet_name(base: str, used: set[str]) -> str:
    name = _SHEET_FORBIDDEN.sub("", base).strip()[:31] or "Sheet"
    candidate, counter = name, 2
    while candidate.lower() in used:
        suffix = f" ({counter})"
        candidate, counter = name[: 31 - len(suffix)] + suffix, counter + 1
    used.add(candidate.lower())
    return candidate


def to_xlsx(doc: Doc) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F3864")
    wrap = Alignment(wrap_text=True, vertical="top")

    def style_header(sheet, columns: int) -> None:
        for column in range(1, columns + 1):
            cell = sheet.cell(row=1, column=column)
            cell.font, cell.fill, cell.alignment = header_font, header_fill, wrap
        sheet.freeze_panes = "A2"

    workbook = Workbook()
    used: set[str] = set()

    plan = workbook.active
    plan.title = _sheet_name("Test Plan" if doc.test_plan else "Document", used)
    plan.append(["No.", "Section", "Content"])
    style_header(plan, 3)
    plan.column_dimensions["A"].width = 6
    plan.column_dimensions["B"].width = 34
    plan.column_dimensions["C"].width = 110

    control = workbook.create_sheet(_sheet_name("Document Control", used), 0 if not doc.test_plan else 1)
    control.append(["Field", "Value"])
    style_header(control, 2)
    control.column_dimensions["A"].width = 24
    control.column_dimensions["B"].width = 100
    if doc.title:
        control.append(["Title", f"{doc.title} – {doc.subtitle}" if doc.subtitle else doc.title])
    for block in doc.front:
        text = plain(block.text) if block.kind != "table" else ""
        if not text:
            continue
        key, separator, value = text.partition(":")
        control.append([key.strip(), value.strip()] if separator and len(key) <= 40 else ["", text])
    if doc.references:
        control.append(["References", _blocks_to_text(doc.references)])
    for row in control.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = wrap

    for section in doc.sections:
        tables = [block for block in section.blocks if block.kind == "table"]
        names: list[str] = []
        for table_number, table in enumerate(tables, start=1):
            label = f"{section.number}. {section.title}" if section.number else section.title
            if len(tables) > 1:
                label = f"{label} {table_number}"
            name = _sheet_name(label, used)
            names.append(name)
            sheet = workbook.create_sheet(name)
            for row in table.rows:
                sheet.append([plain(cell) for cell in row])
            style_header(sheet, len(table.rows[0]))
            for column in range(1, len(table.rows[0]) + 1):
                longest = max(len(plain(row[column - 1])) for row in table.rows)
                sheet.column_dimensions[get_column_letter(column)].width = min(max(12, longest + 2), 60)
            for row in sheet.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = wrap
        note = f"(table: see sheet '{names[0]}')" if len(names) == 1 else (f"(tables: see sheets {', '.join(names)})" if names else None)
        content = _blocks_to_text(section.blocks, note)
        if len(content) > EXCEL_CELL_LIMIT:
            content = content[:EXCEL_CELL_LIMIT] + "\n… (cut: Excel cells hold about 32,000 characters)"
        plan.append([section.number if section.number is not None else "", section.title, content])

    for row in plan.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = wrap
    workbook.active = workbook.index(plan)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------------------------
# 3d. PDF
# --------------------------------------------------------------------------------------------

# Regular + bold TrueType fonts with "–", "≥", "→". The first pair that exists is used.
FONT_CANDIDATES = [
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),  # Docker (Alpine)
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),  # Windows
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),  # macOS
]
_LATIN1_REPLACEMENTS = {"–": "-", "—": "-", "≥": ">=", "≤": "<=", "→": "->", "←": "<-", "✓": "v", "✗": "x", "•": "-"}


def _pdf_fonts() -> tuple[str, str, bool]:
    """(regular, bold, unicode_ok). Falls back to Helvetica (Latin-1 only) if no TTF is found."""
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "PlanSans" in pdfmetrics.getRegisteredFontNames():
        return "PlanSans", "PlanSans-Bold", True
    for regular, bold in FONT_CANDIDATES:
        if Path(regular).is_file() and Path(bold).is_file():
            pdfmetrics.registerFont(TTFont("PlanSans", regular))
            pdfmetrics.registerFont(TTFont("PlanSans-Bold", bold))
            for is_bold, is_italic, name in [(0, 0, "PlanSans"), (1, 0, "PlanSans-Bold"), (0, 1, "PlanSans"), (1, 1, "PlanSans-Bold")]:
                addMapping("PlanSans", is_bold, is_italic, name)
            return "PlanSans", "PlanSans-Bold", True
    return "Helvetica", "Helvetica-Bold", False


def to_pdf(doc: Doc) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    regular, bold, unicode_ok = _pdf_fonts()

    def markup(text: str) -> str:
        if not unicode_ok:
            for char, replacement in _LATIN1_REPLACEMENTS.items():
                text = text.replace(char, replacement)
            text = text.encode("latin-1", "replace").decode("latin-1")
        parts = []
        for span in inline_spans(text):
            piece = escape(span.text)
            if span.bold:
                piece = f"<b>{piece}</b>"
            if span.italic:
                piece = f"<i>{piece}</i>"
            parts.append(piece)
        return "".join(parts)

    base = ParagraphStyle("body", fontName=regular, fontSize=10, leading=14, spaceAfter=4, alignment=TA_LEFT)
    styles = {
        "title": ParagraphStyle("title", parent=base, fontName=bold, fontSize=18, leading=22, spaceAfter=6),
        "subtitle": ParagraphStyle("subtitle", parent=base, fontSize=13, leading=17, spaceAfter=10),
        "h1": ParagraphStyle("h1", parent=base, fontName=bold, fontSize=14, leading=18, spaceBefore=12, spaceAfter=6,
                             textColor=colors.HexColor("#1F3864")),
        "h2": ParagraphStyle("h2", parent=base, fontName=bold, fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base, fontName=bold, fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=3),
        "label": ParagraphStyle("label", parent=base, fontName=bold, spaceBefore=6),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.5, leading=11, spaceAfter=0),
        "head": ParagraphStyle("head", parent=base, fontName=bold, fontSize=8.5, leading=11, spaceAfter=0,
                               textColor=colors.white),
    }

    page_width = A4[0] - 36 * mm
    story: list = []

    def add_blocks(blocks: list[Block]) -> None:
        for block in blocks:
            if block.kind == "heading":
                story.append(Paragraph(markup(plain(block.text)), styles["h2" if block.level <= 2 else "h3"]))
            elif block.kind in {"bullet", "number"}:
                indent = 12 + 12 * block.level
                style = ParagraphStyle(f"list{block.level}", parent=base, leftIndent=indent, bulletIndent=indent - 10)
                bullet = "•" if block.kind == "bullet" else block.marker
                if not unicode_ok and bullet == "•":
                    bullet = "-"
                story.append(Paragraph(markup(block.text), style, bulletText=bullet))
            elif block.kind == "table":
                header, *rest = block.rows
                data = [[Paragraph(markup(cell), styles["head"]) for cell in header]]
                data += [[Paragraph(markup(cell), styles["cell"]) for cell in row] for row in rest]
                table = Table(data, colWidths=[page_width / len(header)] * len(header), repeatRows=1)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9AA5B8")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F4F8")]),
                        ]
                    )
                )
                story.extend([table, Spacer(1, 6)])
            else:
                story.append(Paragraph(markup(block.text), base))

    if doc.title:
        story.append(Paragraph(markup(doc.title), styles["title"]))
    if doc.subtitle:
        story.append(Paragraph(markup(doc.subtitle), styles["subtitle"]))
    add_blocks(doc.front)
    if doc.references:
        story.append(Paragraph("References", styles["label"]))
        add_blocks(doc.references)
    for section in doc.sections:
        story.append(Paragraph(markup(section.heading), styles["h1"]))
        add_blocks(section.blocks)

    def footer(canvas, template) -> None:
        canvas.saveState()
        canvas.setFont(regular, 8)
        canvas.setFillColor(colors.HexColor("#5D6F91"))
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {template.page}")
        canvas.restoreState()

    buffer = io.BytesIO()
    template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{doc.title} – {doc.subtitle}" if doc.subtitle else doc.title,
    )
    template.build(story or [Spacer(1, 1)], onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


# --------------------------------------------------------------------------------------------
# 4. one entry point
# --------------------------------------------------------------------------------------------

_RENDERERS = {"md": to_markdown, "docx": to_docx, "xlsx": to_xlsx, "pdf": to_pdf}


def export(markdown: str, fmt: str) -> bytes:
    """Markdown -> the bytes of a .md / .docx / .xlsx / .pdf file."""
    if fmt not in _RENDERERS:
        raise ValueError(f"Unknown format '{fmt}'. Use one of: {', '.join(FORMATS)}.")
    return _RENDERERS[fmt](build_document(markdown))
