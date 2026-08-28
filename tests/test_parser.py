from pathlib import Path

import pytest

from ethiopian_jobs.models import PostKind
from ethiopian_jobs.parser import ParseError, parse_local_vacancies, parse_results


def test_vacancies_include_only_local_section(fixture_dir: Path) -> None:
    posts = parse_local_vacancies((fixture_dir / "vacancies.html").read_text())

    assert len(posts) == 1
    assert posts[0].kind is PostKind.VACANCY
    assert posts[0].position == "Driver I"
    assert posts[0].detail == "July 13, 2026, to July 17, 2026"
    assert "Expat" not in posts[0].position


def test_results_accept_source_typo_and_correct_spelling(fixture_dir: Path) -> None:
    posts = parse_results((fixture_dir / "results.html").read_text())

    assert [post.position for post in posts] == [
        "Jr. Quality & Safety Assurance Officer",
        "Industrial Nurse",
    ]
    assert posts[0].detail == "CALL FOR PRE-EMPLOYMENT PROCESS & ORIGINAL DOCUMENT VERIFICATION"


def test_missing_local_section_fails_loudly() -> None:
    with pytest.raises(ParseError, match="Local Job Openings"):
        parse_local_vacancies("<h1>International Job Openings</h1>")


def test_empty_results_fail_loudly() -> None:
    with pytest.raises(ParseError, match="no recognizable result"):
        parse_results("<html></html>")

