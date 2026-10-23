"""Render a memo written in simple Markdown to PDF.

Handles only what the memos use: # and ## headings, paragraphs, - bullets, tables,
images, **bold**, *italic* and `code`.

    python scripts/build_memo.py docs/LULU_memo.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

INK = colors.HexColor("#0b0b0b")
INK_2 = colors.HexColor("#52514e")
RULE = colors.HexColor("#c3c2b7")
HEADER = colors.HexColor("#eef2f7")
WIDTH = letter[0] - 1.6 * inch

base = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("title", parent=base["Title"], fontSize=18, leading=22,
                            alignment=0, textColor=INK, spaceAfter=4),
    "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=12.5, leading=16,
                         textColor=INK, spaceBefore=10, spaceAfter=4, keepWithNext=1),
    "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=10, leading=14,
                           textColor=INK, spaceAfter=6),
    "byline": ParagraphStyle("byline", parent=base["BodyText"], fontSize=9.5,
                             textColor=INK_2, spaceAfter=8),
    "cell": ParagraphStyle("cell", parent=base["BodyText"], fontSize=9, leading=11.5,
                           textColor=INK),
}


def inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    return re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", text)


def table(rows: list[str]) -> Table:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [r for r in cells if not all(set(c) <= set("-: ") for c in r)]
    data = [[Paragraph(inline(c), STYLES["cell"]) for c in r] for r in cells]
    n = len(cells[0])
    first = WIDTH * (0.5 if n > 2 else 0.6)
    t = Table(data, colWidths=[first] + [(WIDTH - first) / (n - 1)] * (n - 1), hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def image(path: Path) -> Image:
    img = Image(str(path))
    width = WIDTH * 0.62
    img.drawWidth, img.drawHeight = width, img.imageHeight * width / img.imageWidth
    return img


def build(src: Path, dst: Path) -> Path:
    lines = src.read_text(encoding="utf-8").splitlines()
    story, bullets, rows, para = [], [], [], []

    def flush() -> None:
        if para:
            story.append(Paragraph(inline(" ".join(para)), STYLES["body"]))
            para.clear()
        if bullets:
            story.append(ListFlowable(
                [ListItem(Paragraph(inline(b), STYLES["body"]), leftIndent=12) for b in bullets],
                bulletType="bullet", start="•", leftIndent=12, bulletFontSize=8))
            bullets.clear()
        if rows:
            story.extend([table(rows), Spacer(1, 8)])
            rows.clear()

    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            flush()
        elif s.startswith("# "):
            flush()
            story.append(Paragraph(inline(s[2:]), STYLES["title"]))
        elif s.startswith("## "):
            flush()
            story.append(Paragraph(inline(s[3:]), STYLES["h2"]))
        elif s.startswith("!["):
            flush()
            story.extend([image(src.parent / re.search(r"\((.+?)\)", s).group(1)), Spacer(1, 6)])
        elif s.startswith("|"):
            rows.append(s)
        elif s.startswith("- "):
            bullets.append(s[2:])
        elif i == 2:  # byline under the title
            story.append(Paragraph(inline(s), STYLES["byline"]))
        else:
            para.append(s)
    flush()

    SimpleDocTemplate(str(dst), pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                      topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                      title=src.stem.replace("_", " "), author="Aasa Singh").build(story)
    return dst


if __name__ == "__main__":
    src = Path(sys.argv[1])
    print(build(src, src.with_suffix(".pdf")))
