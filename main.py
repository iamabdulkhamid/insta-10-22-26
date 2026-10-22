"""Instagram / Pinterest / TikTok / YouTube Shorts downloader Telegram bot.

Render Free webhook + Bot API small uploads + Telethon MTProto large uploads.
The site extractors can break when websites change; use only public media that
users have permission to save.
"""

import asyncio
import hashlib
import logging
import os
import secrets
import tempfile
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telethon import TelegramClient
from telethon.sessions import MemorySession
from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser

from media_tools import (
    SUPPORTED_IMAGE_EXT, SUPPORTED_VIDEO_EXT, UserDownloadError,
    download_gallery, download_video, extract_mp3,
)
from platform_urls import MediaLink, allowed_modes, parse_media_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("universal_bot")
# httpx logs can include full Telegram Bot API URLs (and therefore secret token).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
BASE_URL = (os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
API_ID_TEXT = os.environ.get("API_ID", "").strip()
API_HASH = os.environ.get("API_HASH", "").strip()
ALLOWED_USER_IDS = {int(x.strip()) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip()}
WEBHOOK_SECRET = hashlib.sha256(BOT_TOKEN.encode()).hexdigest() if BOT_TOKEN else ""
BOT_API_LIMIT = 48 * 1024 * 1024  # safety margin below official hosted Bot API 50MB upload ceiling
BOT_PHOTO_LIMIT = 9 * 1024 * 1024
MAX_VIDEO_MIB = min(1900, max(48, int(os.environ.get("MAX_VIDEO_SIZE_MB", "200"))))
MAX_VIDEO_BYTES = MAX_VIDEO_MIB * 1024 * 1024
JOB_LOCK = asyncio.Lock()  # 1 active job; others immediately receive 'busy' message
telegram_app: Application | None = None
mtproto_client: TelegramClient | None = None


PLATFORM_LABELS = {
    "instagram": "Instagram", "pinterest": "Pinterest",
    "tiktok": "TikTok", "youtube": "YouTube Shorts",
}
MODE_LABELS = {"video": "🎬 Video", "audio": "🎵 MP3", "photos": "🖼 Rasmlar", "all": "📦 Hammasi"}


def is_authorized(user_id: int | None) -> bool:
    return not ALLOWED_USER_IDS or user_id in ALLOWED_USER_IDS


def build_mode_keyboard(link: MediaLink, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    modes = list(allowed_modes(link))
    for offset in range(0, len(modes), 2):
        rows.append([
            InlineKeyboardButton(MODE_LABELS[mode], callback_data=f"get:{mode}:{user_id}")
            for mode in modes[offset:offset + 2]
        ])
    return InlineKeyboardMarkup(rows)


def input_peer_from_chat_id(chat_id: int):
    if chat_id > 0:
        return InputPeerUser(chat_id, 0)
    if str(chat_id).startswith("-100"):
        return InputPeerChannel(int(str(chat_id)[4:]), 0)
    if chat_id < 0:
        return InputPeerChat(-chat_id)
    raise ValueError("Invalid chat ID")


async def send_mtproto(chat_id: int, file: Path, label: str) -> None:
    if mtproto_client is None or not mtproto_client.is_connected():
        raise UserDownloadError("Katta fayllarni yuborish uchun MTProto hozir ulanmagan.")
    try:
        peer = await mtproto_client.get_input_entity(chat_id)
    except (ValueError, TypeError):
        peer = input_peer_from_chat_id(chat_id)
    is_mp4 = file.suffix.lower() == ".mp4"
    await mtproto_client.send_file(peer, str(file), caption=f"✅ {label}",
                                   force_document=not is_mp4, supports_streaming=is_mp4)


async def send_one_file(message, file: Path, label: str) -> None:
    if file.stat().st_size > BOT_API_LIMIT:
        await send_mtproto(message.chat_id, file, label)
        return
    ext = file.suffix.lower()
    with file.open("rb") as stream:
        if ext in {".jpg", ".jpeg", ".png"} and file.stat().st_size <= BOT_PHOTO_LIMIT:
            await message.reply_photo(stream, caption=f"✅ {label}", read_timeout=180, write_timeout=180)
        elif ext == ".mp3":
            await message.reply_audio(stream, caption=f"✅ {label}", read_timeout=180, write_timeout=180)
        elif ext == ".mp4":
            await message.reply_video(stream, caption=f"✅ {label}", supports_streaming=True,
                                      read_timeout=180, write_timeout=180)
        else:
            await message.reply_document(stream, caption=f"✅ {label}", read_timeout=180, write_timeout=180)


async def send_files(message, files: list[Path], label: str) -> None:
    """Send images as albums (up to 10) and videos in sequence. Clean up after job."""
    i = 0
    while i < len(files):
        group: list[Path] = []
        while i < len(files) and len(group) < 10:
            p = files[i]
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"} and p.stat().st_size <= BOT_PHOTO_LIMIT:
                group.append(p)
                i += 1
            else:
                break
        if len(group) >= 2:
            with ExitStack() as opened:
                photos = [InputMediaPhoto(opened.enter_context(p.open("rb"))) for p in group]
                await message.get_bot().send_media_group(chat_id=message.chat_id, media=photos,
                                                         read_timeout=180, write_timeout=180)
        elif group:
            await send_one_file(message, group[0], label)
        else:
            await send_one_file(message, files[i], label)
            i += 1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id if update.effective_user else None):
        await update.effective_message.reply_text("🔒 Bot shaxsiy foydalanish uchun yopiq.")
        return
    await update.effective_message.reply_text(
        "👋 Universal video va rasm bot!\n\n"
        "🔗 Instagram Reels/post, Pinterest pin, TikTok video yoki YouTube Shorts linkini yuboring.\n"
        "Keyin Video, MP3, Rasmlar yoki Hammasi tugmasini tanlang.\n\n"
        "🎵 MP3 — videodagi ovoz, qo‘shiqning to‘liq nusxasi emas.\n"
        f"📦 Bitta fayl chegarasi: {MAX_VIDEO_MIB} MiB (katta fayl MTProto orqali).\n"
        "ℹ️ Faqat hammaga ochiq va yuklashga ruxsatli materiallar. /id — ID raqamingiz."
    )


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user:
        await update.effective_message.reply_text(f"Telegram ID raqamingiz: {update.effective_user.id}")


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.text:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not is_authorized(user_id):
        await msg.reply_text("🔒 Bot shaxsiy foydalanish uchun yopiq.")
        return
    link = parse_media_url(msg.text)
    if link is None:
        await msg.reply_text("❌ Link topilmadi. Instagram post/Reel, Pinterest pin, TikTok video yoki YouTube Shorts havolasini yuboring.")
        return
    await msg.reply_text(
        f"📎 {PLATFORM_LABELS[link.platform]}\n🔗 {link.url}\n\nNimani yuklab beray?",
        reply_markup=build_mode_keyboard(link, user_id),
        disable_web_page_preview=True,
    )


async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    values = (query.data or "").split(":")
    if len(values) != 3 or values[0] != "get" or not values[2].isdigit():
        await query.answer("Noto‘g‘ri tanlov", show_alert=True)
        return
    mode, user_id_text = values[1], values[2]
    current_user = query.from_user.id
    if current_user != int(user_id_text) or not is_authorized(current_user):
        await query.answer("Bu tugma boshqa foydalanuvchi uchun.", show_alert=True)
        return
    link = parse_media_url(query.message.text or "") if query.message else None
    if link is None or mode not in allowed_modes(link):
        await query.answer("Link eskirgan yoki noto‘g‘ri.", show_alert=True)
        return
    if JOB_LOCK.locked():
        await query.answer("Bot hozir band. Birozdan keyin qayta bosing.", show_alert=True)
        return
    # Acquire synchronously before first await so no other callback sneaks in.
    await JOB_LOCK.acquire()
    message = query.message
    progress = None
    success = False
    try:
        await query.answer("Yuklash boshlandi")
        progress = await message.reply_text("⏳ Media tayyorlanmoqda...")
        with tempfile.TemporaryDirectory(prefix="unibot_") as folder_text:
            folder = Path(folder_text)
            label = PLATFORM_LABELS[link.platform]
            if mode == "video":
                media = await asyncio.to_thread(download_video, link.url, folder, MAX_VIDEO_BYTES, link.platform)
                await progress.edit_text("📤 Video Telegramga yuborilmoqda...")
                await send_one_file(message, media, label)
            elif mode == "audio":
                media = await asyncio.to_thread(download_video, link.url, folder, MAX_VIDEO_BYTES, link.platform)
                audio = await asyncio.to_thread(extract_mp3, media, folder, MAX_VIDEO_BYTES)
                await progress.edit_text("🎵 MP3 Telegramga yuborilmoqda...")
                await send_one_file(message, audio, "Videodagi audio")
            else:
                assets = await asyncio.to_thread(download_gallery, link.url, folder, MAX_VIDEO_BYTES)
                if mode == "photos":
                    assets = [p for p in assets if p.suffix.lower() in SUPPORTED_IMAGE_EXT]
                if not assets:
                    raise UserDownloadError("Ushbu postda rasm topilmadi.")
                await progress.edit_text(f"📤 {len(assets)} ta fayl yuborilmoqda...")
                await send_files(message, assets, label)
            success = True
    except UserDownloadError as exc:
        logger.warning("Media unavailable: %s", exc)
        if progress:
            await progress.edit_text(f"❌ {exc} Boshqa ochiq postni sinang.")
    except Exception:
        logger.exception("Media processing or Telegram transfer failed")
        if progress:
            await progress.edit_text("❌ Yuklashda xatolik chiqdi. Render Logs'ni tekshiring; servisni qayta deploy qilish shart emas.")
    finally:
        JOB_LOCK.release()
        if success and progress:
            try:
                await progress.delete()
            except Exception:
                pass


def build_telegram_app(*, webhook: bool) -> Application:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN Render Environment'da ko‘rsatilmagan")
    builder = Application.builder().token(BOT_TOKEN).concurrent_updates(4)
    if webhook:
        builder = builder.updater(None)
    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CallbackQueryHandler(handle_choice, pattern=r"^get:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    return app


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app, mtproto_client
    if not BASE_URL.startswith("https://"):
        raise RuntimeError("PUBLIC_URL / RENDER_EXTERNAL_URL HTTPS manzil bo‘lishi kerak.")
    telegram_app = build_telegram_app(webhook=True)
    await telegram_app.initialize()
    await telegram_app.start()
    try:
        if API_ID_TEXT and API_HASH:
            try:
                mtproto_client = TelegramClient(MemorySession(), int(API_ID_TEXT), API_HASH,
                                                 receive_updates=False)
                await mtproto_client.start(bot_token=BOT_TOKEN)
                logger.info("MTProto connected for large file uploads")
            except Exception:
                logger.exception("MTProto startup failed; only small uploads available")
                if mtproto_client is not None:
                    await mtproto_client.disconnect()
                mtproto_client = None
        else:
            logger.warning("Missing API_ID/API_HASH; uploads limited to 48 MiB")
        await telegram_app.bot.set_webhook(
            url=f"{BASE_URL}/telegram", secret_token=WEBHOOK_SECRET,
            allowed_updates=["message", "callback_query"], max_connections=10,
        )
        logger.info("Webhook configured")
        yield
    finally:
        if mtproto_client is not None:
            await mtproto_client.disconnect()
        await telegram_app.stop()
        await telegram_app.shutdown()


api = FastAPI(lifespan=lifespan)


@api.get("/")
@api.head("/")
async def health():
    return {"status": "ok", "service": "universal-social-downloader",
            "mtproto_connected": bool(mtproto_client and mtproto_client.is_connected()),
            "max_video_size_mib": MAX_VIDEO_MIB}


@api.post("/telegram")
async def telegram_webhook(request: Request):
    supplied_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secrets.compare_digest(supplied_secret, WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")
    update = Update.de_json(await request.json(), bot=telegram_app.bot)
    if update is not None:
        await telegram_app.update_queue.put(update)
    return {"ok": True}
