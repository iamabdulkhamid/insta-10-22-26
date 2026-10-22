"""Instagram -> Telegram video bot. Webhook mode for Render's free web service."""

import asyncio
import hashlib
import logging
import os
import secrets
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from instagram_urls import get_instagram_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BASE_URL = (os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
MAX_VIDEO_SIZE = 48 * 1024 * 1024  # Leave a safety margin below the 50 MB Bot API upload limit.


def parse_allowed_users(value: str) -> set[int]:
    return {int(item.strip()) for item in value.split(",") if item.strip()}


ALLOWED_USER_IDS = parse_allowed_users(os.environ.get("ALLOWED_USER_IDS", ""))
# Telegram requires [A-Za-z0-9_-] for secret_token; hexadecimal fits.
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest() if BOT_TOKEN else ""


def download_video(url: str, output_dir: Path) -> Path:
    """Download a single public video to a temporary directory (runs in a thread)."""
    options = {
        "outtmpl": str(output_dir / "instagram_video.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
        "playlist_items": "1",
        "max_filesize": MAX_VIDEO_SIZE,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 2,
        "merge_output_format": "mp4",
    }
    with YoutubeDL(options) as ydl:
        ydl.download([url])

    candidates = [
        p for p in output_dir.glob("instagram_video.*")
        if p.is_file() and p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
    ]
    if not candidates:
        raise ValueError("Video topilmadi yoki Instagram yuklab olishga ruxsat bermadi.")
    path = max(candidates, key=lambda p: p.stat().st_size)
    if path.stat().st_size > MAX_VIDEO_SIZE:
        raise ValueError("Video 48 MB dan katta. Kichikroq videoni yuboring.")
    return path


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        await update.effective_message.reply_text("🔒 Bu shaxsiy bot. /id orqali Telegram ID raqamingizni bilib olishingiz mumkin.")
        return
    await update.effective_message.reply_text(
        "👋 Salom! Instagram'dagi ochiq Reel yoki video post havolasini yuboring. "
        "Men videoni yuklab, shu chatga jo‘nataman.\n\n"
        "🔗 Masalan: https://www.instagram.com/reel/ABC123/\n"
        "ℹ️ Faqat hammaga ochiq videolar. /id — shaxsiy Telegram ID."
    )


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user:
        await update.effective_message.reply_text(f"Sizning Telegram ID raqamingiz: {update.effective_user.id}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.text:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        await message.reply_text("🔒 Bu shaxsiy bot.")
        return

    url = get_instagram_url(message.text)
    if not url:
        await message.reply_text("Instagram Reels yoki video post havolasini yuboring. Masalan: https://www.instagram.com/reel/ABC123/")
        return

    progress = await message.reply_text("⏳ Video yuklanmoqda…")
    try:
        with tempfile.TemporaryDirectory(prefix="igbot_") as folder:
            video_path = await asyncio.to_thread(download_video, url, Path(folder))
            with video_path.open("rb") as video:
                if video_path.suffix.lower() == ".mp4":
                    await message.reply_video(
                        video=video,
                        caption="✅ Instagram'dan yuklandi",
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120,
                    )
                else:
                    await message.reply_document(
                        document=video,
                        caption="✅ Instagram'dan yuklandi",
                        read_timeout=120,
                        write_timeout=120,
                    )
    except (DownloadError, ValueError) as exc:
        logger.warning("Video download issue: %s", exc)
        await progress.edit_text(
            "❌ Video yuklanmadi. Post hammaga ochiqligini tekshiring. "
            "Instagram ayrim videolar uchun kirishni cheklashi yoki video mavjud bo‘lmasligi mumkin. "
            "48 MB dan kattalari ham yuborilmaydi."
        )
    except Exception:
        logger.exception("Unexpected video processing error")
        await progress.edit_text("❌ Xatolik yuz berdi. Birozdan keyin qayta urinib ko‘ring.")
    else:
        try:
            await progress.delete()
        except Exception:
            pass


def build_telegram_app(*, webhook: bool) -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN muhit o‘zgaruvchisi kiritilmagan.")
    builder = Application.builder().token(BOT_TOKEN).concurrent_updates(2)
    if webhook:
        builder = builder.updater(None)
    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app


telegram_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app
    if not BASE_URL.startswith("https://"):
        raise RuntimeError("PUBLIC_URL yoki RENDER_EXTERNAL_URL HTTPS manzilini belgilash kerak.")
    telegram_app = build_telegram_app(webhook=True)
    await telegram_app.initialize()
    await telegram_app.start()
    try:
        await telegram_app.bot.set_webhook(
            url=f"{BASE_URL}/telegram",
            secret_token=WEBHOOK_SECRET,
            allowed_updates=["message"],
            max_connections=10,
        )
        logger.info("Telegram webhook registered: %s/telegram", BASE_URL)
        yield
    finally:
        await telegram_app.stop()
        await telegram_app.shutdown()


api = FastAPI(lifespan=lifespan)


@api.get("/")
async def health():
    return {"status": "ok", "service": "instagram-telegram-video-bot"}


@api.post("/telegram")
async def telegram_webhook(request: Request):
    supplied_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secrets.compare_digest(supplied_secret, WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")
    update = Update.de_json(await request.json(), bot=telegram_app.bot)
    if update is not None:
        await telegram_app.update_queue.put(update)
    return {"ok": True}
