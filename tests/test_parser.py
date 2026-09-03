from pathlib import Path

import pytest

from ethiopian_jobs.models import PostKind
from ethiopian_jobs.parser import (
    ParseError,
    _shorten,
    attachment_filename,
    parse_local_vacancies,
    parse_results,
)


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


def test_result_card_exposes_its_pdf_name_list(fixture_dir: Path) -> None:
    posts = parse_results((fixture_dir / "results.html").read_text())
    with_files = [post for post in posts if post.attachment_url]
    for post in with_files:
        assert post.attachment_url.startswith("https://")
        assert ".pdf" in post.attachment_url.lower()


VACANCY_PANEL = """
<h2>Local Job Openings</h2>
<div class="panel panel-default" id="panel_4">
  <div class="card-header">
    <a href="#collapse_4">
      <strong>Position : </strong> Driver I<br/>
      <strong>Location : </strong> Head Quarter<br/>
      <strong>Registration Date : </strong> July 13, 2026 to July 17, 2026<br/>
    </a>
  </div>
  <div class="collapse"><div class="panel-body">
    <div class="Mylead"><strong>Closing Date : </strong> July 17, 2026</div>
  </div></div>
</div>
"""

RESULT_PANEL = """
<div class="panel panel-default" id="panel_2">
  <div class="card-header">
    <a href="#collapse_2">
      <strong>Postion : </strong> Spa Therapist<br/>
      <strong>Location : </strong> Skylight Hotel<br/>
      <strong>Announcement : </strong> CALL FOR INTERVIEW<br/>
    </a>
  </div>
  <div class="collapse"><div class="panel-body">
    <div class="Mylead"><strong>Description : </strong> Report on Friday at 04:00.</div>
    <div class="Mylead"><strong>Candidate_List : </strong>
      <table><tbody>
        <tr><td>SER NO.</td><td>FULL NAME</td></tr>
        <tr><td>1</td><td>Abebe K.</td></tr>
        <tr><td>2</td><td>Sara T.</td></tr>
      </tbody></table>
    </div>
  </div></div>
</div>
"""


def test_vacancy_links_to_its_own_card_and_carries_the_closing_date() -> None:
    post = parse_local_vacancies(VACANCY_PANEL)[0]
    assert post.source_url.endswith("/vacancies#panel_4")
    assert post.extras == (("Closing Date", "July 17, 2026"),)


def test_result_carries_the_description_and_the_name_list() -> None:
    post = parse_results(RESULT_PANEL)[0]
    assert post.source_url.endswith("/results#panel_2")
    assert dict(post.extras)["Details"] == "Report on Friday at 04:00."
    assert dict(post.extras)["Candidates listed"] == "2"
    assert post.candidate_rows[1] == ("1", "Abebe K.")


def test_a_card_without_a_panel_falls_back_to_the_page_url(fixture_dir: Path) -> None:
    post = parse_local_vacancies((fixture_dir / "vacancies.html").read_text())[0]
    assert post.source_url.endswith("/vacancies")
    assert post.extras == ()


def test_attachment_filename_drops_the_query_string() -> None:
    url = "https://example.com/docs/list-of-names.pdf?sfvrsn=bddc173a_2"
    assert attachment_filename(url) == "list-of-names.pdf"


def test_shorten_without_spaces_does_not_slice_negative_index() -> None:
    text = "A" * 100
    shortened = _shorten(text, limit=20)
    assert len(shortened) == 23
    assert shortened == "A" * 20 + "..."


def test_candidate_list_with_space_label_is_parsed() -> None:
    html = """
    <div class="panel panel-default" id="panel_1">
      <div class="card-header">
        <a href="#collapse_1">
          <strong>Postion : </strong> Accountant<br/>
          <strong>Location : </strong> Head Office<br/>
          <strong>Announcement : </strong> Exam<br/>
        </a>
      </div>
      <div class="collapse"><div class="panel-body">
        <div class="Mylead"><strong>Candidate List : </strong>
          <table><tbody>
            <tr><td>SER NO.</td><td>FULL NAME</td></tr>
            <tr><td>1</td><td>Abebe K.</td></tr>
          </tbody></table>
        </div>
      </div></div>
    </div>
    """
    post = parse_results(html)[0]
    assert len(post.candidate_rows) == 2
    assert post.candidate_rows[1] == ("1", "Abebe K.")
