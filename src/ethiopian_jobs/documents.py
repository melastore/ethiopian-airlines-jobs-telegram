from __future__ import annotations

import re
import unicodedata

from fpdf import FPDF

from ethiopian_jobs.models import JobPost

_SAFE_NAME = re.compile(r"[^a-z0-9]+")
# The built in fonts cover Latin-1, which is every name the airline publishes.
_FALLBACK_CHARACTER = "?"
_MAX_COLUMNS = 8
_CELL_LIMIT = 120
_ROW_HEIGHT = 5.0
_WIDTH_SAMPLE = 200


def _printable(text: str) -> str:
    """Drop accents and anything the built in fonts cannot draw."""
    stripped = "".join(
        character
        for character in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(character)
    )
    return "".join(
        character if character.encode("latin-1", "ignore") else _FALLBACK_CHARACTER
        for character in stripped
    )


def _table_rows(rows: tuple[tuple[str, ...], ...]) -> list[list[str]]:
    width = min(max((len(row) for row in rows), default=0), _MAX_COLUMNS)
    prepared = []
    for row in rows:
        cells = [_printable(cell)[:_CELL_LIMIT] for cell in row[:width]]
        cells += [""] * (width - len(cells))
        prepared.append(cells)
    return prepared


def render_candidate_pdf(post: JobPost) -> bytes:
    """Lay the published name list out as a table people can read on a phone."""
    rows = _table_rows(post.candidate_rows)
    if not rows:
        raise ValueError("There is no name list to render")

    pdf = FPDF(orientation="landscape", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.set_title(_printable(f"{post.position} name list"))
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 13)
    pdf.multi_cell(0, 6, _printable(post.position), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 5, _printable(post.detail), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 5, _printable(post.location), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    _draw_table(pdf, rows)
    return bytes(pdf.output())


def _column_widths(pdf: FPDF, rows: list[list[str]], available: float) -> list[float]:
    """Size columns from a sample. Measuring ten thousand rows is not worth the wait."""
    columns = len(rows[0])
    weights = []
    for index in range(columns):
        widest = max(
            (pdf.get_string_width(row[index]) for row in rows[: _WIDTH_SAMPLE]),
            default=1.0,
        )
        weights.append(max(widest, 8.0))
    total = sum(weights)
    return [available * weight / total for weight in weights]


def _draw_table(pdf: FPDF, rows: list[list[str]]) -> None:
    heading, *body = rows
    available = pdf.w - pdf.l_margin - pdf.r_margin
    widths = _column_widths(pdf, rows, available)

    def draw_heading() -> None:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(230, 230, 230)
        for width, cell in zip(widths, heading, strict=True):
            pdf.cell(width, _ROW_HEIGHT, cell, border=1, fill=True)
        pdf.ln(_ROW_HEIGHT)
        pdf.set_font("Helvetica", "", 8)

    draw_heading()
    for row in body:
        if pdf.get_y() + _ROW_HEIGHT > pdf.h - pdf.b_margin:
            pdf.add_page()
            draw_heading()
        for width, cell in zip(widths, row, strict=True):
            pdf.cell(width, _ROW_HEIGHT, _fit(pdf, cell, width), border=1)
        pdf.ln(_ROW_HEIGHT)


def _fit(pdf: FPDF, text: str, width: float) -> str:
    """Trim a cell that would spill into its neighbour."""
    if pdf.get_string_width(text) <= width - 2:
        return text
    while text and pdf.get_string_width(text + "...") > width - 2:
        text = text[:-1]
    return text + "..."


def candidate_filename(post: JobPost) -> str:
    stem = _SAFE_NAME.sub("-", post.position.casefold()).strip("-") or "candidates"
    return f"{stem[:60]}-name-list.pdf"
