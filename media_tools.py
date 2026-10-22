"""Download media to temporary disk, keeping strict per-item limits.

No user cookies, logins, or account credentials are collected.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".heic"}
SUPPORTED_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


class UserDownloadError(Exception):
    pass


def ensure_disk_room(folder: Path, requested: int) -> None:
    # Best-effort only: another application can still consume space afterwards.
    if shutil.disk_usage(folder).free < min(requested + 50 * 1024 * 1024, 350 * 1024 * 1024):
        raise UserDownloadError("Render serverida vaqtinchalik disk joyi kam.")


def download_video(url: str, folder: Path, max_bytes: int, platform: str) -> Path:
    ensure_disk_room(folder, max_bytes)

    def on_progress(status: dict) -> None:
        downloaded = int(status.get("downloaded_bytes") or 0)
        if downloaded > max_bytes:
            raise UserDownloadError("Fayl belgilangan hajmdan oshib ketdi.")

    def check_known_size(info: dict, *, incomplete: bool = False) -> None:
        size = info.get("filesize") or info.get("filesize_approx")
        if size and int(size) > max_bytes:
            raise UserDownloadError("Fayl belgilangan hajmdan oshib ketdi.")

    options = {
        "outtmpl": str(folder / "media.%(ext)s"),
        "format": ("bv*[height<=1080]+ba/b[height<=1080]/best" if platform == "youtube" else "best[ext=mp4]/best"),
        "noplaylist": True,
        "playlist_items": "1",
        "max_filesize": max_bytes,
        "progress_hooks": [on_progress],
        "match_filter": check_known_size,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 25,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 2,
        "merge_output_format": "mp4",
    }
    try:
        with YoutubeDL(options) as ydl:
            ydl.download([url])
    except (DownloadError, UserDownloadError) as exc:
        raise UserDownloadError("Video topilmadi, kirish cheklangan yoki hajmi limitdan katta.") from exc
    videos = [p for p in folder.glob("media.*") if p.is_file() and p.suffix.lower() in SUPPORTED_VIDEO_EXT]
    if not videos:
        raise UserDownloadError("Bu havolada ochiq video topilmadi. Rasm bo‘lsa, «Rasm»ni tanlang.")
    file = max(videos, key=lambda p: p.stat().st_size)
    if file.stat().st_size > max_bytes:
        raise UserDownloadError("Video hajmi limitdan katta.")
    return file


def download_gallery(url: str, folder: Path, max_bytes: int, max_items: int = 20) -> list[Path]:
    ensure_disk_room(folder, max_bytes)
    gallery_folder = folder / "gallery"
    gallery_folder.mkdir()
    args = [
        sys.executable, "-m", "gallery_dl",
        "-D", str(gallery_folder),
        "--range", f"1-{max_items}",
        "--filesize-max", str(max_bytes),
        url,
    ]
    try:
        process = subprocess.run(args, capture_output=True, text=True, timeout=300, check=False)
    except subprocess.TimeoutExpired as exc:
        raise UserDownloadError("Rasmlarni yuklash uchun belgilangan vaqt tugadi.") from exc
    files = sorted(
        (p for p in gallery_folder.rglob("*") if p.is_file() and p.suffix.lower() in (SUPPORTED_IMAGE_EXT | SUPPORTED_VIDEO_EXT)),
        key=lambda p: str(p),
    )
    if not files:
        raise UserDownloadError("Bu postdan ochiq rasm yoki video olinmadi. Post yopiq bo‘lishi mumkin.")
    if process.returncode:
        # Some items can fail individually; send the downloaded ones.
        return files[:max_items]
    return files[:max_items]


def extract_mp3(video: Path, folder: Path, max_bytes: int) -> Path:
    output = folder / "audio.mp3"
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video), "-vn", "-codec:a", "libmp3lame", "-b:a", "160k", str(output)]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=300, check=False)
    except subprocess.TimeoutExpired as exc:
        raise UserDownloadError("MP3 tayyorlash uchun vaqt yetmadi.") from exc
    if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
        raise UserDownloadError("Bu videodan ovoz ajratib bo‘lmadi.")
    if output.stat().st_size > max_bytes:
        raise UserDownloadError("Audio hajmi limitdan katta.")
    return output
