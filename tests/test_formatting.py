from ethiopian_jobs.formatting import format_telegram
from ethiopian_jobs.models import JobPost, PostKind


def test_vacancy_format_matches_requested_shape_and_escapes_html() -> None:
    post = JobPost(
        kind=PostKind.VACANCY,
        position="Driver <I>",
        detail="July 13 & 17",
        location="Head <Office>",
        source_url="https://example.com/jobs?a=1&b=2",
    )

    message = format_telegram(post)

    assert "-------- Vacancies --------" in message
    assert "<b>Registration Date:</b> July 13 &amp; 17" in message
    assert "Driver &lt;I&gt;" in message
    assert (
        '<a href="https://example.com/jobs?a=1&amp;b=2">'
        "https://example.com/jobs?a=1&amp;b=2</a>" in message
    )


def test_result_uses_announcement_label() -> None:
    post = JobPost(
        kind=PostKind.RESULT,
        position="Driver I",
        detail="Call for interview",
        location="Head Office",
        source_url="https://example.com/results",
    )

    message = format_telegram(post)

    assert "-------- Result --------" in message
    assert "<b>Announcement:</b> Call for interview" in message
