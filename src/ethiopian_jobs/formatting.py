from __future__ import annotations

from html import escape

from ethiopian_jobs.models import JobPost, PostKind


def format_telegram(post: JobPost) -> str:
    """Create a compact Telegram HTML message."""
    if post.kind is PostKind.VACANCY:
        heading = "-------- Vacancies --------"
        detail_label = "Registration Date"
    else:
        heading = "-------- Result --------"
        detail_label = "Announcement"

    return "\n".join(
        (
            f"<b>{heading}</b>",
            "",
            f"<b>Position:</b> {escape(post.position)}",
            "",
            f"<b>{detail_label}:</b> {escape(post.detail)}",
            "",
            f"<b>Location:</b> {escape(post.location)}",
            "",
            f'<b>URL:</b> <a href="{escape(post.source_url, quote=True)}">'
            f"{escape(post.source_url)}</a>",
        )
    )
