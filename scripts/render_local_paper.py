"""Render the local English paper or evidence sheet using ReportLab.

The input is a deliberately small, auditable Markdown subset: headings,
paragraphs, emphasis, inline code, links, lists, block quotes, fenced code,
pipe tables and standalone local images. Figures must already exist; this
script never downloads images or executes Markdown. Use plain-text equations
or pre-rendered equation figures rather than unprocessed LaTeX math blocks.

Examples (run only after the PDF authoring marker has been recorded):
    python scripts/render_local_paper.py --input manuscript/PAPER.md \
        --output output/pdf/local-reasoning-pilot.pdf --title "Reasoning Prefixes"
    python scripts/render_local_paper.py --input manuscript/PORTFOLIO_EVIDENCE_SHEET.md \
        --output output/pdf/portfolio-evidence-sheet.pdf --compact

For portable links to repository files, pass --source-url-base with the
repository's immutable GitHub blob URL ending in a commit hash and slash.
Without it, local Markdown links retain their labels but are not made into
machine-specific PDF links. A successful build still requires visual QA.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re
import textwrap
from urllib.parse import quote, urlsplit

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
    XPreformatted,
)


# TTF fonts provide the Greek letters, diacritics and operators used in the
# manuscript. Normalize dash variants to the PDF skill's ASCII convention.
ASCII_TRANSLATION = str.maketrans({
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2212": "-", "\u00ad": "",
    "\u00a0": " ", "\u202f": " ", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
})
LINK_RE = re.compile(r"\[([^\]]+)\]\(((?:[^()\s]|\([^()]*\))+)\)")
IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(((?:[^()]|\([^()]*\))+)\)\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LIST_RE = re.compile(r"^(\s*)([-+*]|\d+[.)])\s+(.+)$")
TABLE_DIVIDER_RE = re.compile(r"^\s*:?-{3,}:?\s*$")


def normalized(text: str) -> str:
    return text.translate(ASCII_TRANSLATION)


def register_fonts() -> dict[str, str]:
    """Register a complete font family, preferring installed Windows TTFs."""
    candidates = [
        (Path("C:/Windows/Fonts"), ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
         "RUTime"),
        (Path("/usr/share/fonts/truetype/liberation2"),
         ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf",
          "LiberationSerif-Italic.ttf", "LiberationSerif-BoldItalic.ttf"), "RULiberation"),
        (Path("/usr/share/fonts/truetype/dejavu"),
         ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSerif-Italic.ttf",
          "DejaVuSerif-BoldItalic.ttf"), "RUDejaVu"),
    ]
    for directory, files, prefix in candidates:
        if all((directory / file).is_file() for file in files):
            names = [prefix, prefix + "-Bold", prefix + "-Italic", prefix + "-BoldItalic"]
            for name, file in zip(names, files):
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(directory / file)))
            pdfmetrics.registerFontFamily(prefix, normal=names[0], bold=names[1],
                                         italic=names[2], boldItalic=names[3])
            body = prefix
            break
    else:
        body = "Times-Roman"
    code = "Courier"
    for path in (Path("C:/Windows/Fonts/consola.ttf"),
                 Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")):
        if path.is_file():
            code = "RUMono"
            if code not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(code, str(path)))
            break
    return {"body": body, "code": code}


def find_repository_root(input_path: Path) -> Path:
    for directory in (input_path.parent, *input_path.parent.parents):
        if (directory / ".git").exists():
            return directory
    return input_path.parent


class MarkdownPaper:
    def __init__(self, input_path: Path, width: float, available_height: float,
                 fonts: dict[str, str], *, compact: bool = False,
                 source_url_base: str | None = None, repo_root: Path | None = None):
        self.input_path = input_path.resolve()
        self.width, self.available_height = width, available_height
        self.fonts = fonts
        self.source_url_base = source_url_base.rstrip("/") + "/" if source_url_base else None
        self.repo_root = (repo_root or find_repository_root(self.input_path)).resolve()
        size, leading = (9.4, 12.2) if compact else (10.5, 13.4)
        base = dict(fontName=fonts["body"], fontSize=size, leading=leading,
                    textColor=colors.HexColor("#18212b"), splitLongWords=True,
                    allowWidows=0, allowOrphans=0, spaceAfter=5.0)
        self.styles = {
            "body": ParagraphStyle("paper-body", alignment=TA_JUSTIFY, **base),
            "left": ParagraphStyle("paper-left", alignment=TA_LEFT, **base),
            "title": ParagraphStyle("paper-title", fontName=fonts["body"],
                                    fontSize=18 if compact else 20, leading=22 if compact else 24,
                                    spaceAfter=12, alignment=TA_CENTER, keepWithNext=True,
                                    textColor=colors.HexColor("#142a40")),
            "heading": ParagraphStyle("paper-heading", fontName=fonts["body"],
                                      fontSize=12 if compact else 13, leading=15.5,
                                      spaceBefore=11, spaceAfter=5, keepWithNext=True,
                                      textColor=colors.HexColor("#142a40")),
            "subheading": ParagraphStyle("paper-subheading", fontName=fonts["body"],
                                         fontSize=10.5 if compact else 11.5, leading=14,
                                         spaceBefore=8, spaceAfter=4, keepWithNext=True,
                                         textColor=colors.HexColor("#142a40")),
            "caption": ParagraphStyle("paper-caption", fontName=fonts["body"],
                                      fontSize=8.4 if compact else 9, leading=11.2,
                                      textColor=colors.HexColor("#344454"), alignment=TA_LEFT,
                                      spaceBefore=4, spaceAfter=9,
                                      allowWidows=0, allowOrphans=0, splitLongWords=True),
            "table": ParagraphStyle("paper-table", fontName=fonts["body"],
                                    fontSize=8.0 if compact else 8.7,
                                    leading=10.0 if compact else 11.1,
                                    spaceAfter=0, allowWidows=1, allowOrphans=1,
                                    splitLongWords=True, alignment=TA_LEFT),
            "code": ParagraphStyle("paper-code", fontName=fonts["code"],
                                   fontSize=7.5, leading=10, spaceBefore=4, spaceAfter=8,
                                   backColor=colors.HexColor("#f3f5f7"),
                                   borderPadding=7, splitLongWords=True),
        }
        self.styles["bullet"] = ParagraphStyle("paper-bullet", parent=self.styles["left"],
                                                leftIndent=13, firstLineIndent=0,
                                                bulletIndent=1, spaceAfter=3)
        self.styles["reference"] = ParagraphStyle("paper-reference", parent=self.styles["bullet"],
                                                  fontSize=9.5, leading=11.5, spaceAfter=3)
        self.styles["quote"] = ParagraphStyle("paper-quote", parent=self.styles["left"],
                                               leftIndent=12, rightIndent=12,
                                               textColor=colors.HexColor("#344454"))

    def link_target(self, target: str) -> str | None:
        target = target.strip().strip("<>")
        scheme = urlsplit(target).scheme.lower()
        if scheme in ("http", "https", "mailto"):
            return target
        if scheme or target.startswith("#") or not self.source_url_base:
            return None
        path, separator, anchor = target.partition("#")
        resolved = (self.input_path.parent / path).resolve()
        try:
            relative = resolved.relative_to(self.repo_root).as_posix()
        except ValueError:
            return None
        return self.source_url_base + quote(relative, safe="/") + (
            "#" + quote(anchor, safe="-_") if separator else "")

    def inline(self, text: str) -> str:
        """Escape all source HTML, permitting only generated formatting tags."""
        text = normalized(text)
        result: list[str] = []
        index = 0
        while index < len(text):
            if text[index] == "\\" and index + 1 < len(text):
                result.append(html.escape(text[index + 1]))
                index += 2
                continue
            if text[index] == "`":
                end = text.find("`", index + 1)
                if end >= 0:
                    code = html.escape(text[index + 1:end])
                    result.append(f'<font name="{self.fonts["code"]}" size="8.2">{code}</font>')
                    index = end + 1
                    continue
            link = LINK_RE.match(text, index)
            if link:
                label, target = link.groups()
                href = self.link_target(target)
                shown = self.inline(label)
                result.append(f'<link href="{html.escape(href, quote=True)}" '
                              f'color="#185580">{shown}</link>' if href else shown)
                index = link.end()
                continue
            if text.startswith("**", index):
                end = text.find("**", index + 2)
                if end >= 0:
                    result.append("<b>" + self.inline(text[index + 2:end]) + "</b>")
                    index = end + 2
                    continue
            if text[index] == "*":
                end = text.find("*", index + 1)
                if end >= 0:
                    result.append("<i>" + self.inline(text[index + 1:end]) + "</i>")
                    index = end + 1
                    continue
            if text[index:index + 4].lower() == "<br>":
                result.append("<br/>")
                index += 4
                continue
            result.append(html.escape(text[index]))
            index += 1
        return "".join(result)

    def paragraph(self, text: str, style: str = "body", **kwargs) -> Paragraph:
        return Paragraph(self.inline(text), self.styles[style], **kwargs)

    @staticmethod
    def table_cells(line: str) -> list[str]:
        cells, current = [], []
        escaped = in_code = False
        for char in line.strip().strip("|"):
            if escaped:
                current.extend(("\\", char))
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "`":
                in_code = not in_code
                current.append(char)
            elif char == "|" and not in_code:
                cells.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        if escaped:
            current.append("\\")
        cells.append("".join(current).strip())
        return cells

    def is_table_start(self, lines: list[str], index: int) -> bool:
        return (index + 1 < len(lines) and "|" in lines[index]
                and len(self.table_cells(lines[index])) >= 2
                and all(TABLE_DIVIDER_RE.fullmatch(cell)
                        for cell in self.table_cells(lines[index + 1])))

    def table(self, rows: list[list[str]]) -> LongTable:
        count = len(rows[0])
        if any(len(row) != count for row in rows):
            raise ValueError("Markdown table rows have unequal column counts")
        # Keep numeric columns compact while giving prose columns room. The
        # square root stops a single unusually long cell dominating the page.
        lengths = []
        for column in range(count):
            values = sorted(len(re.sub(r"[`*]", "", row[column])) for row in rows)
            representative = values[min(len(values) - 1, math.floor(0.8 * len(values)))]
            lengths.append(math.sqrt(min(100, max(8, representative)) + 8))
        minimum = min(48.0, self.width / count)
        remaining = self.width - minimum * count
        widths = [minimum + remaining * length / sum(lengths) for length in lengths]
        content = [[self.paragraph(("**" + cell + "**") if index == 0 else cell, "table")
                    for cell in row] for index, row in enumerate(rows)]
        table = LongTable(content, colWidths=widths, repeatRows=1,
                          hAlign="LEFT", spaceBefore=5, spaceAfter=10,
                          splitByRow=1, splitInRow=1)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef4")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.65, colors.HexColor("#8b9cac")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d8dfe6")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return table

    def figure(self, alt: str, target: str, caption: str | None = None) -> KeepTogether:
        supplied_path = Path(target.strip())
        if urlsplit(target).scheme and not supplied_path.is_absolute():
            raise ValueError("Figures must be local files; remote images are not fetched")
        path = (supplied_path if supplied_path.is_absolute()
                else self.input_path.parent / supplied_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Figure is missing: {path}")
        image = Image(str(path), lazy=2)
        max_height = self.available_height * 0.70
        scale = min(self.width / image.imageWidth, max_height / image.imageHeight, 1.0)
        image.drawWidth, image.drawHeight = image.imageWidth * scale, image.imageHeight * scale
        image.hAlign = "CENTER"
        contents = [Spacer(1, 5), image]
        if caption or alt:
            contents.append(self.paragraph(caption or alt, "caption"))
        else:
            contents.append(Spacer(1, 8))
        return KeepTogether(contents)

    def starts_block(self, lines: list[str], index: int) -> bool:
        line = lines[index].strip()
        return (not line or bool(HEADING_RE.match(line)) or line.startswith(("```", "~~~", ">"))
                or bool(IMAGE_RE.match(line)) or bool(LIST_RE.match(lines[index]))
                or self.is_table_start(lines, index)
                or bool(re.fullmatch(r"(?:-\s*){3,}|(?:\*\s*){3,}", line)))

    def parse(self, markdown: str, title_override: str | None = None) -> tuple[list, str]:
        lines = markdown.replace("\r\n", "\n").splitlines()
        story = []
        title = title_override
        title_written = False
        references = False
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if not line:
                index += 1
                continue
            if line.startswith("$$"):
                raise ValueError("Render LaTeX math blocks as figures or use plain-text equations")
            heading = HEADING_RE.match(line)
            if heading:
                level, text = len(heading[1]), heading[2]
                references = text.strip().lower() == "references"
                if not title_written and level == 1:
                    title = title_override or text
                    story.append(self.paragraph(title, "title"))
                    title_written = True
                else:
                    if not title_written and title:
                        story.append(self.paragraph(title, "title"))
                        title_written = True
                    story.append(self.paragraph(text, "heading" if level <= 2 else "subheading"))
                index += 1
                continue
            if not title_written and title:
                story.append(self.paragraph(title, "title"))
                title_written = True
            if self.is_table_start(lines, index):
                rows = [self.table_cells(lines[index])]
                index += 2
                while index < len(lines) and lines[index].strip() and "|" in lines[index]:
                    rows.append(self.table_cells(lines[index]))
                    index += 1
                table = self.table(rows)
                story.append(KeepTogether([table]) if len(rows) <= 5 else table)
                continue
            figure = IMAGE_RE.match(line)
            if figure:
                alt, target = figure.groups()
                index += 1
                next_index = index
                while next_index < len(lines) and not lines[next_index].strip():
                    next_index += 1
                caption = None
                if next_index < len(lines) and re.match(r"^\*?(?:Figure|Fig\.)\s+\d", lines[next_index].strip()):
                    caption = lines[next_index].strip()
                    index = next_index + 1
                    while index < len(lines) and not self.starts_block(lines, index):
                        caption += " " + lines[index].strip()
                        index += 1
                story.append(self.figure(alt, target, caption))
                continue
            if line.startswith(("```", "~~~")):
                delimiter = line[:3]
                code = []
                index += 1
                while index < len(lines) and not lines[index].lstrip().startswith(delimiter):
                    code.extend(textwrap.wrap(normalized(lines[index]), width=105,
                                              replace_whitespace=False, drop_whitespace=False)
                                or [""])
                    index += 1
                if index == len(lines):
                    raise ValueError("Unclosed Markdown code fence")
                story.append(XPreformatted(html.escape("\n".join(code)), self.styles["code"]))
                index += 1
                continue
            if re.fullmatch(r"(?:-\s*){3,}|(?:\*\s*){3,}", line):
                story.append(HRFlowable(width="100%", thickness=0.4,
                                        color=colors.HexColor("#b8c4ce"), spaceBefore=5, spaceAfter=7))
                index += 1
                continue
            bullet = LIST_RE.match(lines[index])
            if bullet:
                marker, text = bullet[2], bullet[3]
                index += 1
                while index < len(lines) and not self.starts_block(lines, index):
                    text += " " + lines[index].strip()
                    index += 1
                marker = "-" if marker in ("-", "+", "*") else marker
                story.append(self.paragraph(text, "reference" if references else "bullet", bulletText=marker))
                continue
            if line.startswith(">"):
                quoted = []
                while index < len(lines) and lines[index].strip().startswith(">"):
                    quoted.append(lines[index].strip()[1:].lstrip())
                    index += 1
                story.append(self.paragraph(" ".join(quoted), "quote"))
                continue
            paragraph = [line]
            index += 1
            while index < len(lines) and not self.starts_block(lines, index):
                paragraph.append(lines[index].strip())
                index += 1
            story.append(self.paragraph(" ".join(paragraph)))
        if not story:
            raise ValueError("Markdown input is empty")
        return story, normalized(title or self.input_path.stem.replace("_", " "))


def page_decoration(title: str, fonts: dict[str, str], margin: float, footer: str):
    def decorate(canvas, document):
        canvas.saveState()
        width, height = document.pagesize
        canvas.setFillColor(colors.HexColor("#5a6774"))
        canvas.setFont(fonts["body"], 8)
        if document.page > 1:
            shown = normalized(title)
            while shown and pdfmetrics.stringWidth(shown, fonts["body"], 8) > width - 2 * margin:
                shown = shown[:-2]
            canvas.drawString(margin, height - margin + 9, shown)
        canvas.setStrokeColor(colors.HexColor("#c9d1d9"))
        canvas.setLineWidth(0.35)
        canvas.line(margin, margin - 9, width - margin, margin - 9)
        canvas.drawString(margin, margin - 21, normalized(footer))
        canvas.drawRightString(width - margin, margin - 21, str(document.page))
        canvas.restoreState()
    return decorate


def render(input_path: Path, output_path: Path, *, title: str | None = None,
           author: str = "Reasoning Universalis", compact: bool = False,
           source_url_base: str | None = None, repo_root: Path | None = None,
           footer: str = "Reasoning Universalis") -> dict:
    source = input_path.read_text(encoding="utf-8-sig")
    fonts = register_fonts()
    margin = 18 * mm if compact else 19 * mm
    width, height = A4
    renderer = MarkdownPaper(input_path, width - 2 * margin, height - 2 * margin,
                             fonts, compact=compact, source_url_base=source_url_base,
                             repo_root=repo_root)
    story, resolved_title = renderer.parse(source, title)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(str(output_path), pagesize=A4,
                                 leftMargin=margin, rightMargin=margin,
                                 topMargin=margin + 3, bottomMargin=margin + 3,
                                 title=resolved_title, author=author,
                                 subject="Exploratory reasoning-prefix research",
                                 pageCompression=1)
    decorate = page_decoration(resolved_title, fonts, margin, footer)
    document.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return {"input": str(input_path.resolve()), "output": str(output_path.resolve()),
            "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            "pdf_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "title": resolved_title, "fonts": fonts,
            "visual_review_required": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="English manuscript Markdown")
    parser.add_argument("--output", required=True, type=Path, help="Final PDF under output/pdf/")
    parser.add_argument("--title", help="Override the source's first H1 title")
    parser.add_argument("--author", default="Reasoning Universalis")
    parser.add_argument("--compact", action="store_true", help="Denser layout for the evidence sheet")
    parser.add_argument("--source-url-base", help="Immutable repository blob URL for local source links")
    parser.add_argument("--repo-root", type=Path, help="Repository root for portable source links")
    parser.add_argument("--footer", default="Reasoning Universalis")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".pdf":
        parser.error("--output must have the .pdf suffix")
    result = render(args.input, args.output, title=args.title, author=args.author,
                    compact=args.compact, source_url_base=args.source_url_base,
                    repo_root=args.repo_root, footer=args.footer)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
