from ethiopian_jobs.formatting import format_telegram, make_inline_keyboard
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

    assert "ETHIOPIAN AIRLINES • VACANCY" in message
    assert "<b>Registration Date:</b> July 13 &amp; 17" in message
    assert "Driver &lt;I&gt;" in message
    assert "Head &lt;Office&gt;" in message
    assert 'href="https://example.com/jobs?a=1&amp;b=2"' in message


def test_result_uses_announcement_label_and_blockquotes() -> None:
    post = JobPost(
        kind=PostKind.RESULT,
        position="Driver I",
        detail="Call for interview",
        location="Head Office",
        source_url="https://example.com/results",
        extras=(("Details", "Please arrive on time <09:00 AM>."),),
    )

    message = format_telegram(post)

    assert "ETHIOPIAN AIRLINES • RECRUITMENT RESULT" in message
    assert "<b>Announcement:</b> Call for interview" in message
    assert "<blockquote>Please arrive on time &lt;09:00 AM&gt;.</blockquote>" in message


def test_name_list_link_is_added_when_a_file_is_attached() -> None:
    post = JobPost(
        kind=PostKind.RESULT,
        position="Cabin Crew",
        location="Head Office",
        detail="Screening",
        source_url="https://example.com/results",
        attachment_url="https://example.com/docs/names.pdf",
    )
    message = format_telegram(post)
    assert "Name list:" in message
    assert 'href="https://example.com/docs/names.pdf"' in message


def test_channel_tag_included_in_footer() -> None:
    post = JobPost(
        kind=PostKind.VACANCY,
        position="Driver I",
        location="Head Office",
        detail="July 13",
        source_url="https://example.com/vacancies",
    )
    message = format_telegram(post, channel_tag="@ethiopian_channel")
    assert "<b>@ethiopian_channel</b>" in message


def test_make_inline_keyboard_generates_action_and_share_buttons() -> None:
    post = JobPost(
        kind=PostKind.VACANCY,
        position="Driver I",
        location="Head Office",
        detail="July 13 to 17",
        source_url="https://corporate.ethiopianairlines.com/vacancies#panel_1",
        attachment_url="https://corporate.ethiopianairlines.com/docs/list.pdf",
    )
    keyboard = make_inline_keyboard(post)
    assert "inline_keyboard" in keyboard
    rows = keyboard["inline_keyboard"]
    assert len(rows) == 2
    assert rows[0][0]["text"] == "🌐 View Vacancy"
    assert rows[0][0]["url"] == post.source_url
    assert rows[0][1]["text"] == "📄 Official PDF"
    assert rows[0][1]["url"] == post.attachment_url
    assert rows[1][0]["text"] == "↗️ Share Post"
    assert "t.me/share/url" in rows[1][0]["url"]
