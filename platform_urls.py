"""Strict URL parser for one-item public social posts.

Restrict the entry points to known sites and individual media pages rather than
feeding arbitrary URLs to downloaders (which can otherwise access internal URLs).
"""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
IG_ID = re.compile(r"[A-Za-z0-9_-]{3,}\Z")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{6,}\Z")
DIGITS = re.compile(r"\d{5,}\Z")


@dataclass(frozen=True)
class MediaLink:
    platform: str
    url: str
    kind: str


def parse_media_url(text: str) -> MediaLink | None:
    for candidate in URL_PATTERN.findall(text):
        candidate = candidate.rstrip(".,;!?)]}\u201d\u2019")
        try:
            parsed = urlsplit(candidate)
            host = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port
        except ValueError:
            continue
        if parsed.scheme.lower() not in {"http", "https"}:
            continue
        if parsed.username or parsed.password or port not in (None, 80, 443):
            continue
        parts = [p for p in parsed.path.split("/") if p]
        if host in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
            if len(parts) == 2 and parts[0] in {"p", "reel", "reels", "tv"} and IG_ID.fullmatch(parts[1]):
                kind = "reel" if parts[0] == "reels" else parts[0]
                return MediaLink("instagram", f"https://www.instagram.com/{kind}/{parts[1]}/", kind)
        elif host in {"tiktok.com", "www.tiktok.com", "m.tiktok.com"}:
            if len(parts) == 3 and parts[0].startswith("@") and parts[1] == "video" and DIGITS.fullmatch(parts[2]):
                if re.fullmatch(r"@[a-zA-Z0-9._]{2,32}", parts[0]):
                    return MediaLink("tiktok", f"https://www.tiktok.com/{parts[0]}/video/{parts[2]}", "video")
        elif host in {"vm.tiktok.com", "vt.tiktok.com"}:
            if len(parts) == 1 and VIDEO_ID.fullmatch(parts[0]):
                return MediaLink("tiktok", f"https://{host}/{parts[0]}/", "video")
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if len(parts) == 2 and parts[0] == "shorts" and VIDEO_ID.fullmatch(parts[1]):
                return MediaLink("youtube", f"https://www.youtube.com/shorts/{parts[1]}", "shorts")
        elif host in {"youtu.be", "www.youtu.be"}:
            if len(parts) == 1 and VIDEO_ID.fullmatch(parts[0]):
                return MediaLink("youtube", f"https://www.youtube.com/shorts/{parts[0]}", "shorts")
        elif host == "pin.it" or host == "www.pin.it":
            if len(parts) == 1 and re.fullmatch(r"[a-zA-Z0-9]{5,25}", parts[0]):
                return MediaLink("pinterest", f"https://pin.it/{parts[0]}", "pin")
        elif host == "pinterest.com" or host.endswith(".pinterest.com"):
            if len(parts) >= 2 and parts[0] == "pin" and DIGITS.fullmatch(parts[1]):
                return MediaLink("pinterest", f"https://www.pinterest.com/pin/{parts[1]}/", "pin")
    return None


def allowed_modes(link: MediaLink) -> tuple[str, ...]:
    if link.platform == "pinterest":
        return ("video", "photos", "all")
    if link.platform == "instagram" and link.kind == "p":
        return ("video", "audio", "photos", "all")
    return ("video", "audio")
