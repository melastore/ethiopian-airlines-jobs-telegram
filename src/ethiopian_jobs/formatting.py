from __future__ import annotations

from html import escape

from ethiopian_jobs.models import JobPost, PostKind

# Telegram rejects captions longer than this.
CAPTION_LIMIT = 1024


def _link(url: str, text: str) -> str:
    return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>'


def format_telegram(post: JobPost) -> str:
    """Build the Telegram HTML message for one post."""
    if post.kind is PostKind.VACANCY:
        heading = "-------- Vacancies --------"
        detail_label = "Registration Date"
    else:
        heading = "-------- Result --------"
        detail_label = "Announcement"

    lines = [
        f"<b>{heading}</b>",
        "",
        f"<b>Position:</b> {escape(post.position)}",
        "",
        f"<b>{detail_label}:</b> {escape(post.detail)}",
        "",
        f"<b>Location:</b> {escape(post.location)}",
    ]
    for label, value in post.extras:
        lines += ["", f"<b>{escape(label)}:</b> {escape(value)}"]
    lines += ["", f"<b>URL:</b> {_link(post.source_url, post.source_url)}"]
    if post.attachment_url:
        lines += ["", f"<b>Name list:</b> {_link(post.attachment_url, 'Open the PDF')}"]
    return "\n".join(lines)


def fits_caption(text: str) -> bool:
    return len(text) <= CAPTION_LIMIT
