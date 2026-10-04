"""Original, project-owned normalized records for external crawler results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
        if number > 100_000_000_000:
            number /= 1000
        return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _source_url(platform: str, value: Any, external_id: str) -> str:
    candidate = _text(value)
    host = urlparse(candidate).hostname
    allowed = ("douyin.com",) if platform == "dy" else ("xiaohongshu.com", "rednote.com")
    if candidate.startswith("https://") and host and any(host == name or host.endswith("." + name) for name in allowed):
        # Remove temporary query tokens from stored and rendered links.
        parsed = urlparse(candidate)
        return parsed._replace(query="", fragment="").geturl()
    if platform == "dy":
        return f"https://www.douyin.com/video/{external_id}"
    return f"https://www.xiaohongshu.com/explore/{external_id}"


def item(platform: str, raw: dict[str, Any], source: str) -> dict[str, Any] | None:
    """Map MediaCrawler JSONL to one item contract."""
    if platform == "dy":
        external_id = _text(raw.get("aweme_id"))
        title = _text(raw.get("title") or raw.get("desc"))
        body = _text(raw.get("desc"))
        author_id = _text(raw.get("creator_hash"))
        url = _source_url(platform, raw.get("aweme_url"), external_id)
    elif platform == "xhs":
        external_id = _text(raw.get("note_id") or raw.get("id"))
        title = _text(raw.get("title"))
        body = _text(raw.get("desc"))
        author_id = _text(raw.get("creator_hash"))
        url = _source_url(platform, raw.get("note_url") or raw.get("url"), external_id)
    else:
        return None
    if not external_id:
        return None
    return {
        "platform": platform,
        "external_id": external_id,
        "title": title,
        "body": body,
        "author_id": author_id or None,
        "identity_kind": "anonymous_hash",
        "url": url,
        "published_at": _timestamp(raw.get("time") or raw.get("create_time")),
        "keyword": _text(raw.get("source_keyword")),
        "source": source,
    }


def comment(platform: str, raw: dict[str, Any], source: str, item_id: str = "") -> dict[str, Any] | None:
    """Ignore records without a stable comment ID or parent item ID."""
    if platform == "dy":
        external_id = _text(raw.get("comment_id") or raw.get("cid"))
        parent_id = _text(raw.get("aweme_id") or item_id)
        author_id = _text(raw.get("creator_hash"))
        body = _text(raw.get("content") or raw.get("text"))
        nickname = _text(raw.get("nickname"))
    elif platform == "xhs":
        external_id = _text(raw.get("comment_id") or raw.get("id"))
        parent_id = _text(raw.get("note_id") or item_id)
        author_id = _text(raw.get("creator_hash"))
        body = _text(raw.get("content"))
        nickname = _text(raw.get("nickname"))
    else:
        return None
    if not external_id or not parent_id:
        return None
    return {
        "platform": platform,
        "external_id": external_id,
        "item_id": parent_id,
        "author_id": author_id or None,
        "identity_kind": "anonymous_hash",
        "nickname": nickname,
        "body": body,
        "published_at": _timestamp(raw.get("create_time")),
        "source": source,
    }
