from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from ethiopian_jobs.models import JobPost, PostKind, normalize

VACANCIES_URL = "https://corporate.ethiopianairlines.com/AboutEthiopian/careers/vacancies"
RESULTS_URL = "https://corporate.ethiopianairlines.com/AboutEthiopian/careers/results"

_HEADINGS = ("h1", "h2")
_LOCAL_HEADING = "local job openings"
_SECTION_HEADINGS = frozenset({_LOCAL_HEADING, "international job openings"})
_VACANCY_FIELDS = ("position", "location", "registration date")
_RESULT_FIELDS = ("position", "location", "announcement")
_PDF_HREF = re.compile(r"\.pdf(\?|$)", re.IGNORECASE)
_CANDIDATE_LABEL = "candidate_list"
# The description repeats the whole announcement. Keep enough to be useful.
_DESCRIPTION_LIMIT = 700


class ParseError(RuntimeError):
    """Raised when the source page no longer has the expected structure."""


def _label_value(strong: Tag) -> str:
    pieces: list[str] = []
    for sibling in strong.next_siblings:
        if isinstance(sibling, Tag) and sibling.name in {"br", "strong"}:
            break
        text = sibling.get_text(" ", strip=True) if isinstance(sibling, Tag) else str(sibling)
        if text:
            pieces.append(text)
    return normalize(" ".join(pieces))


def _clean_label(strong: Tag) -> str:
    label = normalize(strong.get_text(" ", strip=True)).removesuffix(":").strip().casefold()
    # The results page has shipped this typo for years.
    return "position" if label == "postion" else label


def _fields(header: Tag) -> dict[str, str]:
    result: dict[str, str] = {}
    anchor = header.find("a") or header
    for strong in anchor.find_all("strong", recursive=False):
        result[_clean_label(strong)] = _label_value(strong)
    return result


def _panel(header: Tag) -> Tag:
    return header.find_parent("div", class_="panel") or header


def _body_blocks(panel: Tag) -> dict[str, Tag]:
    """Label to block for the expandable part of a card."""
    body = panel.find("div", class_="panel-body")
    if body is None:
        return {}
    blocks: dict[str, Tag] = {}
    for block in body.find_all("div", class_="Mylead"):
        strong = block.find("strong")
        if strong is not None:
            blocks.setdefault(_clean_label(strong), block)
    return blocks


def _block_text(block: Tag) -> str:
    strong = block.find("strong")
    if strong is not None:
        strong.extract()
    return normalize(block.get_text(" ", strip=True))


def _card_url(panel: Tag, source_url: str) -> str:
    """Link straight to the card. The site has no permanent per-job page."""
    panel_id = panel.get("id")
    return f"{source_url}#{panel_id}" if panel_id else source_url


def _attachment(panel: Tag, source_url: str) -> str:
    link = panel.find("a", href=_PDF_HREF)
    return urljoin(source_url, str(link["href"]).strip()) if link is not None else ""


def _candidate_rows(panel: Tag) -> tuple[tuple[str, ...], ...]:
    """The published name list, when the card carries it as a table."""
    block = _body_blocks(panel).get(_CANDIDATE_LABEL)
    table = block.find("table") if block is not None else None
    if table is None:
        return ()
    rows = []
    for row in table.find_all("tr"):
        cells = tuple(
            normalize(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])
        )
        if any(cells):
            rows.append(cells)
    return tuple(rows)


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: text.rfind(" ", 0, limit)].rstrip(" ,.;:") + "..."


def _source_key(panel: Tag) -> str:
    """The whole card, so a repeated headline with a new schedule is not missed."""
    return normalize(panel.get_text(" ", strip=True))


def _unique(posts: Iterator[JobPost]) -> list[JobPost]:
    unique: dict[str, JobPost] = {}
    for post in posts:
        unique.setdefault(post.content_key, post)
    return list(unique.values())


def _heading_text(tag: Tag) -> str:
    return normalize(tag.get_text(" ", strip=True)).casefold()


def _headers_after_local_heading(soup: BeautifulSoup) -> Iterator[Tag]:
    local_heading = next(
        (tag for tag in soup.find_all(_HEADINGS) if _heading_text(tag) == _LOCAL_HEADING),
        None,
    )
    if local_heading is None:
        raise ParseError("Could not find the 'Local Job Openings' section")

    # Walk forward lazily instead of materializing every later node in the document.
    for node in local_heading.next_elements:
        if not isinstance(node, Tag):
            continue
        if node.name in _HEADINGS:
            if _heading_text(node) in _SECTION_HEADINGS:
                return
        elif node.name == "div" and "card-header" in node.get("class", ()):
            yield node


def parse_local_vacancies(html: str, source_url: str = VACANCIES_URL) -> list[JobPost]:
    """Parse only the cards under the page's Local Job Openings heading."""
    soup = BeautifulSoup(html, "html.parser")

    def posts() -> Iterator[JobPost]:
        for header in _headers_after_local_heading(soup):
            values = _fields(header)
            if not all(values.get(field) for field in _VACANCY_FIELDS):
                continue
            panel = _panel(header)
            blocks = _body_blocks(panel)
            extras = []
            closing = blocks.get("closing date")
            if closing is not None:
                extras.append(("Closing Date", _block_text(closing)))
            yield JobPost(
                kind=PostKind.VACANCY,
                position=values["position"],
                location=values["location"],
                detail=values["registration date"],
                source_url=_card_url(panel, source_url),
                source_key=_source_key(panel),
                extras=tuple(pair for pair in extras if pair[1]),
            )

    result = _unique(posts())
    if not result:
        raise ParseError("The Local Job Openings section contained no recognizable vacancy cards")
    return result


def parse_results(html: str, source_url: str = RESULTS_URL) -> list[JobPost]:
    """Parse recruitment result cards, including the published name list."""
    soup = BeautifulSoup(html, "html.parser")

    def posts() -> Iterator[JobPost]:
        for header in soup.select("div.card-header"):
            values = _fields(header)
            if not all(values.get(field) for field in _RESULT_FIELDS):
                continue
            panel = _panel(header)
            blocks = _body_blocks(panel)
            rows = _candidate_rows(panel)
            extras = []
            description = blocks.get("description")
            if description is not None:
                extras.append(("Details", _shorten(_block_text(description), _DESCRIPTION_LIMIT)))
            if rows:
                # The header row is not a candidate.
                extras.append(("Candidates listed", str(max(len(rows) - 1, 0))))
            yield JobPost(
                kind=PostKind.RESULT,
                position=values["position"],
                location=values["location"],
                detail=values["announcement"],
                source_url=_card_url(panel, source_url),
                source_key=_source_key(panel),
                attachment_url=_attachment(panel, source_url),
                extras=tuple(pair for pair in extras if pair[1]),
                candidate_rows=rows,
            )

    result = _unique(posts())
    if not result:
        raise ParseError("The results page contained no recognizable result cards")
    return result


def attachment_filename(url: str) -> str:
    """A readable name for the uploaded document."""
    name = urlsplit(url).path.rsplit("/", 1)[-1] or "attachment.pdf"
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"
