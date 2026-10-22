"""Instagram -> Telegram video bot.

Telegram Bot API webhook receives messages (compatible with Render Free waking up).
Files <= 48 MiB go through Bot API; larger files use Telethon/MTProto.
Large uploads are experimental on Render Free; do not assume 2 GB will work.
"""

import asyncio
import hashlib
import logging
import os
import secrets
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telethon import TelegramClient
from telethon.sessions import MemorySession
from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from instagram_urls import get_instagram_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BASE_URL = (
    os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or ""
).strip().rstrip("/")
API_ID_TEXT = os.environ.get("API_ID", "").strip()
API_HASH = os.environ.get("API_HASH", "").strip()
BOT_API_LIMIT = 48 * 1024 * 1024
MAX_ALLOWED_MIB = 1900  # Below Telegram's approximately 2 GB MTProto limit.


def video_limit_mib() -> int:
    try:
        requested = int(os.environ.get("MAX_VIDEO_SIZE_MB", "200"))
    except ValueError as exc:
        raise RuntimeError("MAX_VIDEO_SIZE_MB butun son bo'lishi kerak.") from exc
    return max(48, min(requested, MAX_ALLOWED_MIB))


MAX_VIDEO_SIZE_MIB = video_limit_mib()
MAX_VIDEO_SIZE = MAX_VIDEO_SIZE_MIB * 1024 * 1024


def parse_allowed_users(value: str) -> set[int]:
    return {int(item.strip()) for item in value.split(",") if item.strip()}


ALLOWED_USER_IDS = parse_allowed_users(os.environ.get("ALLOWED_USER_IDS", ""))
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest() if BOT_TOKEN else ""

# A single active download/upload limits pressure on Render Free memory/disk.
VIDEO_SEMAPHORE = asyncio.Semaphore(1)
telegram_app: Application | None = None
mtproto_client: TelegramClient | None = None


def download_video(url: str, output_dir: Path, max_size: int) -> Path:
    """Download one public Instagram video onto disk, not into RAM."""
    free_bytes = shutil.disk_usage(output_dir).free
    if free_bytes < 100 * 1024 * 1024:
        raise ValueError("Serverda yetarli vaqtinchalik disk joyi qolmagan.")

    def track_size(status: dict) -> None:
        if status.get("status") == "downloading":
            downloaded = int(status.get("downloaded_bytes") or 0)
            if downloaded > max_size:
                raise ValueError(f"Video {MAX_VIDEO_SIZE_MIB} MiB limitidan katta.")

    options = {
        "outtmpl": str(output_dir / "instagram_video.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
        "playlist_items": "1",
        "max_filesize": max_size,
        "progress_hooks": [track_size],
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
        file for file in output_dir.glob("instagram_video.*")
        if file.is_file() and file.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}
    ]
    if not candidates:
        raise ValueError("Video topilmadi yoki Instagram yuklashga ruxsat bermadi.")
    path = max(candidates, key=lambda file: file.stat().st_size)
    if path.stat().st_size > max_size:
        raise ValueError(f"Video {MAX_VIDEO_SIZE_MIB} MiB limitidan katta.")
    return path


def mtproto_peer_from_bot_api_chat_id(chat_id: int):
    """Bot API marked IDs to MTProto input peers, with bot-specific zero hash.

    A zero access hash is supported in certain bot contexts, but Telegram may
    still refuse it for some users/channels. This is not guaranteed to work.
    """
    if chat_id > 0:
        return InputPeerUser(chat_id, 0)
    if str(chat_id).startswith("-100"):
        return InputPeerChannel(int(str(chat_id)[4:]), 0)
    if chat_id < 0:
        return InputPeerChat(-chat_id)
    raise ValueError("Telegram chat ID noto'g'ri.")


async def send_mtproto(chat_id: int, file_path: Path) -> None:
    if mtproto_client is None or not mtproto_client.is_connected():
        raise RuntimeError("MTProto ulanmagan. Render API_ID/API_HASH va Logs'ni tekshiring.")
    try:
        destination = await mtproto_client.get_input_entity(chat_id)
    except (ValueError, TypeError):
        destination = mtproto_peer_from_bot_api_chat_id(chat_id)
    is_mp4 = file_path.suffix.lower() == ".mp4"
    await mtproto_client.send_file(
        destination,
        str(file_path),
        caption="✅ Instagram'dan yuklandi",
        force_document=not is_mp4,
        supports_streaming=is_mp4,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        await update.effective_message.reply_text(
            "🔒 Bu shaxsiy bot. /id orqali Telegram ID raqamingizni bilib olishingiz mumkin."
        )
        return
    await update.effective_message.reply_text(
        "👋 Salom! Instagram'dagi ochiq Reel yoki video post havolasini yuboring. "
        "Men videoni yuklab, shu chatga jo‘nataman.\n\n"
        "🔗 Masalan: https://www.instagram.com/reel/ABC123/\n"
        f"📦 Hozirgi limit: {MAX_VIDEO_SIZE_MIB} MiB. "
        "Katta fayllar MTProto orqali yuboriladi.\n"
        "ℹ️ Faqat hammaga ochiq videolar. /id — shaxsiy Telegram ID."
    )


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user:
        await update.effective_message.reply_text(
            f"Sizning Telegram ID raqamingiz: {update.effective_user.id}"
        )


async def send_bot_api_video(message, video_path: Path) -> None:
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
        await message.reply_text(
            "Instagram Reels yoki video post havolasini yuboring. "
            "Masalan: https://www.instagram.com/reel/ABC123/"
        )
        return

    progress = await message.reply_text("⏳ Video yuklanmoqda…")
    success = False
    try:
        async with VIDEO_SEMAPHORE:
            with tempfile.TemporaryDirectory(prefix="igbot_") as folder:
                max_size = MAX_VIDEO_SIZE if mtproto_client is not None else BOT_API_LIMIT
                video_path = await asyncio.to_thread(
                    download_video, url, Path(folder), max_size
                )
                size = video_path.stat().st_size
                if size <= BOT_API_LIMIT:
                    await send_bot_api_video(message, video_path)
                else:
                    await progress.edit_text("📤 Katta video MTProto orqali yuborilmoqda…")
                    await send_mtproto(message.chat_id, video_path)
                success = True
    except (DownloadError, ValueError) as exc:
        logger.warning("Instagram download issue: %s", exc)
        await progress.edit_text(
            "❌ Video yuklanmadi. Instagram posti ochiq ekanligini, "
            f"video {MAX_VIDEO_SIZE_MIB} MiB dan kichikligini tekshiring."
        )
    except Exception as exc:
        logger.exception("Video transfer error: %s", exc)
        await progress.edit_text(
            "❌ Video yuborilmadi. Katta fayl bo'lsa MTProto ulanishi, "
            "Render Logs va vaqtinchalik diskni tekshiring. "
            "48 MiB dan kichik video bilan qayta sinab ko'ring."
        )
    finally:
        if success:
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app, mtproto_client
    if not BASE_URL.startswith("https://"):
        raise RuntimeError("PUBLIC_URL yoki RENDER_EXTERNAL_URL HTTPS bo'lishi shart.")
    telegram_app = build_telegram_app(webhook=True)
    await telegram_app.initialize()
    await telegram_app.start()
    try:
        # Keep MTProto optional: bot still handles 48-MiB files if it is unavailable.
        if API_ID_TEXT and API_HASH:
            try:
                api_id = int(API_ID_TEXT)
                mtproto_client = TelegramClient(
                    MemorySession(), api_id, API_HASH, receive_updates=False
                )
                await mtproto_client.start(bot_token=BOT_TOKEN)
                logger.info("MTProto connected for large file uploads")
            except Exception:
                logger.exception("MTProto login failed; only <=48 MiB uploads available")
                if mtproto_client is not None:
                    await mtproto_client.disconnect()
                mtproto_client = None
        else:
            logger.warning("Missing API_ID or API_HASH: uploads limited to 48 MiB")

        await telegram_app.bot.set_webhook(
            url=f"{BASE_URL}/telegram",
            secret_token=WEBHOOK_SECRET,
            allowed_updates=["message"],
            max_connections=10,
        )
        logger.info("Telegram webhook registered: %s/telegram", BASE_URL)
        yield
    finally:
        if mtproto_client is not None:
            await mtproto_client.disconnect()
        await telegram_app.stop()
        await telegram_app.shutdown()


api = FastAPI(lifespan=lifespan)


@api.get("/")
async def health():
    return {
        "status": "ok",
        "service": "instagram-telegram-video-bot",
        "mtproto_connected": bool(mtproto_client and mtproto_client.is_connected()),
        "max_video_size_mib": MAX_VIDEO_SIZE_MIB,
    }


@api.post("/telegram")
async def telegram_webhook(request: Request):
    supplied_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secrets.compare_digest(supplied_secret, WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")
    update = Update.de_json(await request.json(), bot=telegram_app.bot)
    if update is not None:
        await telegram_app.update_queue.put(update)
    return {"ok": True}
