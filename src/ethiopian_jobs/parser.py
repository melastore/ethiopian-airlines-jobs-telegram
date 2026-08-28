from __future__ import annotations

from collections.abc import Iterator

from bs4 import BeautifulSoup, Tag

from ethiopian_jobs.models import JobPost, PostKind, normalize

VACANCIES_URL = "https://corporate.ethiopianairlines.com/AboutEthiopian/careers/vacancies"
RESULTS_URL = "https://corporate.ethiopianairlines.com/AboutEthiopian/careers/results"

_HEADINGS = ("h1", "h2")
_LOCAL_HEADING = "local job openings"
_SECTION_HEADINGS = frozenset({_LOCAL_HEADING, "international job openings"})
_VACANCY_FIELDS = ("position", "location", "registration date")
_RESULT_FIELDS = ("position", "location", "announcement")


class ParseError(RuntimeError):
    """Raised when the source page no longer has the expected structure."""


def _label_value(strong: Tag) -> str:
    pieces: list[str] = []
    for sibling in strong.next_siblings:
        if isinstance(sibling, Tag) and sibling.name == "br":
            break
        if isinstance(sibling, Tag) and sibling.name == "strong":
            break
        text = sibling.get_text(" ", strip=True) if isinstance(sibling, Tag) else str(sibling)
        if text:
            pieces.append(text)
    return normalize(" ".join(pieces))


def _fields(header: Tag) -> dict[str, str]:
    result: dict[str, str] = {}
    anchor = header.find("a") or header
    for strong in anchor.find_all("strong", recursive=False):
        label = normalize(strong.get_text(" ", strip=True)).removesuffix(":").strip().casefold()
        if label == "postion":  # The results page currently uses this typo.
            label = "position"
        result[label] = _label_value(strong)
    return result


def _source_key(header: Tag) -> str:
    """Capture the full card so repeated headlines with new schedules are not missed."""
    card = header.find_parent("div", class_="panel") or header
    return normalize(card.get_text(" ", strip=True))


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


def _unique(posts: Iterator[JobPost]) -> list[JobPost]:
    unique: dict[str, JobPost] = {}
    for post in posts:
        unique.setdefault(post.content_key, post)
    return list(unique.values())


def parse_local_vacancies(html: str, source_url: str = VACANCIES_URL) -> list[JobPost]:
    """Parse only cards under the page's Local Job Openings heading."""
    soup = BeautifulSoup(html, "html.parser")

    def posts() -> Iterator[JobPost]:
        for header in _headers_after_local_heading(soup):
            values = _fields(header)
            if not all(values.get(field) for field in _VACANCY_FIELDS):
                continue
            yield JobPost(
                kind=PostKind.VACANCY,
                position=values["position"],
                location=values["location"],
                detail=values["registration date"],
                source_url=source_url,
                source_key=_source_key(header),
            )

    result = _unique(posts())
    if not result:
        raise ParseError("The Local Job Openings section contained no recognizable vacancy cards")
    return result


def parse_results(html: str, source_url: str = RESULTS_URL) -> list[JobPost]:
    """Parse recruitment-result summary cards."""
    soup = BeautifulSoup(html, "html.parser")

    def posts() -> Iterator[JobPost]:
        for header in soup.select("div.card-header"):
            values = _fields(header)
            if not all(values.get(field) for field in _RESULT_FIELDS):
                continue
            yield JobPost(
                kind=PostKind.RESULT,
                position=values["position"],
                location=values["location"],
                detail=values["announcement"],
                source_url=source_url,
                source_key=_source_key(header),
            )

    result = _unique(posts())
    if not result:
        raise ParseError("The results page contained no recognizable result cards")
    return result
