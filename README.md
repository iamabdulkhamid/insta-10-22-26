# Bitta universal Telegram bot — Instagram / Pinterest / TikTok / YouTube Shorts

Bu ZIP oldin 97 MiB atrofida videoni MTProto orqali yuborgan
`iamabdulkhamid/insta-10-22-26` Render botining **yangilash versiyasi**.
Mavjud BotFather boti va Render servisini saqlab qolish mumkin.

## Imkoniyatlar

- Instagram: **Reels**, oddiy **video post**, rasmli post va karusel; **videodagi audioni MP3** qilib ajratish.
- Pinterest: bitta pin rasmi yoki videosi; pin ichidagi mavjud media.
- TikTok: umumiy ko‘rinadigan video.
- YouTube: **Shorts** havolasidagi video va ixtiyoriy MP3.
- Foydalanuvchi link yuboradi va **Video / MP3 / Rasmlar / Hammasi** tugmalaridan birini tanlaydi.
  Platformaga qarab tegishli tugmalar chiqadi. Bot ishlatayotgan paytda yangi so‘rov uchun **«band»** deydi —
  Render Free'dagi 512 MB RAM'ni ortiqcha yuklamaslik uchun.
- Katta fayllar eski ishlayotgan MTProto yo‘li orqali; kichik fayllar Telegram Bot API orqali.
- Vaqtinchalik fayllar har bir operatsiya tugagandan keyin `TemporaryDirectory` orqali o‘chiriladi.
- `/id` va `ALLOWED_USER_IDS` funksiyalari saqlangan. Port `/telegram`, `GET /` va `HEAD /` tayyor.

## O‘rnatish — eski botni saqlab qolamiz

1. ZIP faylni **oching**. Ichidagi `main.py`, `media_tools.py`, `platform_urls.py`,
   `instagram_urls.py`, `requirements.txt`, `Dockerfile`, `render.yaml`, `local_bot.py`
   va boshqa `.py`/`.md` fayllarni GitHub repozitoriyangiz **asosiy (root) papkasiga** joylang.
2. GitHub -> `https://github.com/iamabdulkhamid/insta-10-22-26` -> `Add file` ->
   `Upload files` -> barcha fayllarni yuklang, eski `main.py`, `requirements.txt`, `Dockerfile`
   bilan **almashtiring** -> `Commit changes`.
3. Render -> mavjud Web Service -> **Environment**:
   - `BOT_TOKEN` — BotFather tokeni, **maxfiy**.
   - `API_ID` va `API_HASH` — my.telegram.org bergan ma’lumotlar, **maxfiy**.
   - `MAX_VIDEO_SIZE_MB` — dastlab `200` qoldirish tavsiya qilinadi.
   - `ALLOWED_USER_IDS` — ixtiyoriy, faqat o‘zingiz va oilangiz (masalan `123456789,987654321`).
4. Render -> `Events`: yangi deploy muvaffaqiyatli tugaganini tekshiring.
   Avtomatik deploy bo‘lmasa, `Manual Deploy` -> `Deploy latest commit`.
5. Telegram'da `/start` yuboring, so‘ng bittadan Instagram / Pinterest / TikTok / YouTube Shorts ochiq havolasini yuborib,
   tegishli tugmalarni sinang.

**MUHIM xavfsizlik:** Eski suhbatda Render loglaridan `BOT_TOKEN` ochiq chiqib ketgan edi.
Uni `@BotFather` orqali **revoke/regenerate** qilib, yangi tokenni faqat Render Environment'ga kiriting.
Bot tokenini GitHub'ga, README'ga yoki loglarga joylamang.
`httpx` INFO logi o‘chirildi: u aks holda tokenli Telegram URLlarini chiqarishi mumkin.

## Amaliy cheklovlar

- Yuqoridagi platformalarning qoidalari, loginga ehtiyoj, DRM, botga qarshi himoya yoki hududiy bloklash sababli ayrim havolalar ishlamasligi mumkin.
- YouTube Shorts uchun `yt-dlp`ga qo‘shimcha `Deno` JavaScript runtime kerak. Dockerfile uni build paytida o‘rnatishga **urinadi**.
  O‘rnatish ishlamasa, ayrim Shorts'lar ochilmaydi.
- Instagram karusellar va Pinterest rasmlari `gallery-dl` orqali olinadi.
  Instagram o‘zgarsa, shu kutubxonani yangilash talab qilinishi mumkin.
- **MP3 — bu videoning ovozi**, alohida to‘liq qo‘shiqni qidirib beruvchi servis emas.
- Hajm limiti 200 **MiB** (taxminan 210 MB) bo‘lib, u `MAX_VIDEO_SIZE_MB` orqali belgilanadi.
  Telegram Bot API orqali yuborishda 48 MiB xavfsizlik chegarasi ishlatiladi.
  2 GB katta fayllar Render Free'da sinovdan o‘tmagan; ilgari 97 MB video muvaffaqiyatli yuborilgan.
- Shu ZIP'ni ishlab chiqqanda URL-parser testlari va kod sintaksisi tekshiriladi.
  **Haqiqiy TikTok, Pinterest, YouTube Shorts va Instagram rasm postlari uchun jonli server sinovi o'tkazilmagan.**
- Faqat ommaga ochiq yoki saqlashga ruxsatingiz bor kontentdan foydalaning.

## Sozlash / nosozlik

- Yuklash tugmalari ishlamasa: Render Logs va `allowed_updates=["message", "callback_query"]` kodiga qarang.
- `ModuleNotFoundError`: GitHub'dagi `requirements.txt`ni yangi versiyaga almashtirganingizni tekshiring.
- Video yuborilmasa: `Render Logs`dagi so‘nggi xatoni (tokenni berkitib) tekshiring.
- Render Free uyqu rejimiga o‘tganda dastlabki javob kechikishi mumkin.
- Yangi versiya ishlamasa, Render -> Events orqali oldingi ishlab turgan versiyaga **rollback** qilish yoki GitHub'ning oldingi commitiga qaytish mumkin.

## Lokal testlar

```shell
python -m unittest discover -v
python -m py_compile main.py media_tools.py platform_urls.py
```

## Texnologiya

`python-telegram-bot` webhook, `yt-dlp[default]` video, `gallery-dl` rasmlar,
`ffmpeg` MP3, `Telethon` MTProto, `FastAPI` / `uvicorn`, `Deno` YouTube EJS.
