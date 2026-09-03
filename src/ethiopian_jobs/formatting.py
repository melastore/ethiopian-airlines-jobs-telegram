from __future__ import annotations

from html import escape
from urllib.parse import quote

from ethiopian_jobs.models import JobPost, PostKind

# Telegram rejects captions longer than this.
CAPTION_LIMIT = 1024
_DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━━━"


def _link(url: str, text: str) -> str:
    return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>'


def format_telegram(post: JobPost, channel_tag: str = "") -> str:
    """Build the Telegram HTML message for one post."""
    if post.kind is PostKind.VACANCY:
        header = "✈️ <b>ETHIOPIAN AIRLINES • VACANCY</b>"
        detail_label = "📅 <b>Registration Date:</b>"
    else:
        header = "📋 <b>ETHIOPIAN AIRLINES • RECRUITMENT RESULT</b>"
        detail_label = "📢 <b>Announcement:</b>"

    lines = [
        header,
        _DIVIDER,
        "",
        f"💼 <b>Position:</b> {escape(post.position)}",
        f"{detail_label} {escape(post.detail)}",
        f"📍 <b>Location:</b> {escape(post.location)}",
    ]

    details_block = ""
    for label, value in post.extras:
        key = label.lower().strip()
        if key == "closing date":
            lines.append(f"⏰ <b>Closing Date:</b> {escape(value)}")
        elif key == "candidates listed":
            lines.append(f"👥 <b>Candidates Listed:</b> {escape(value)}")
        elif key == "details":
            details_block = f"\n📝 <b>Details:</b>\n<blockquote>{escape(value)}</blockquote>"
        else:
            lines.append(f"🔹 <b>{escape(label)}:</b> {escape(value)}")

    if details_block:
        lines.append(details_block)

    lines.append("")
    lines.append(_DIVIDER)

    if post.attachment_url:
        lines.append(f"📄 <b>Name list:</b> {_link(post.attachment_url, 'Open the PDF')}")
    elif post.candidate_rows:
        lines.append("📎 <i>Official candidate list PDF attached below.</i>")

    lines.append(f"🔗 <b>Careers Portal:</b> {_link(post.source_url, 'View on official website')}")

    if channel_tag:
        tag = channel_tag if channel_tag.startswith("@") else f"@{channel_tag}"
        lines.append(f"🔔 <i>Stay updated:</i> <b>{escape(tag)}</b>")

    return "\n".join(lines)


def make_inline_keyboard(post: JobPost) -> dict:
    """Buttons under the message: the card, the PDF, and a share link."""
    view_label = "🌐 View Vacancy" if post.kind is PostKind.VACANCY else "🌐 View Result"
    row1 = [{"text": view_label, "url": post.source_url}]
    if post.attachment_url:
        row1.append({"text": "📄 Official PDF", "url": post.attachment_url})

    share_text = f"Ethiopian Airlines {post.kind.value.capitalize()}: {post.position}"
    u_enc = quote(post.source_url, safe="")
    t_enc = quote(share_text, safe="")
    share_url = f"https://t.me/share/url?url={u_enc}&text={t_enc}"
    row2 = [{"text": "↗️ Share Post", "url": share_url}]

    return {"inline_keyboard": [row1, row2]}


def fits_caption(text: str) -> bool:
    return len(text) <= CAPTION_LIMIT
