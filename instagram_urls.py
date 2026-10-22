"""Extract and normalize public Instagram post/reel/video links."""

import re
from urllib.parse import urlsplit

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+\Z")
_VALID_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}
_VALID_PATH_KINDS = {"reel", "reels", "p", "tv"}


def get_instagram_url(text: str) -> str | None:
    """Return a canonical Instagram URL, or None if no supported link is found."""
    for match in _URL_PATTERN.finditer(text):
        raw_url = match.group(0).rstrip(".,;!?)]}")
        try:
            parsed = urlsplit(raw_url)
            hostname = (parsed.hostname or "").lower()
        except ValueError:
            continue
        if parsed.scheme.lower() not in {"http", "https"} or hostname not in _VALID_HOSTS:
            continue
        segments = parsed.path.strip("/").split("/")
        if len(segments) != 2:
            continue
        kind, shortcode = segments
        if kind not in _VALID_PATH_KINDS or not _ID_PATTERN.fullmatch(shortcode):
            continue
        if kind == "reels":
            kind = "reel"
        return f"https://www.instagram.com/{kind}/{shortcode}/"
    return None
