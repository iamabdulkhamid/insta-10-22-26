# Instagram → Telegram video bot

BotFather tokeni bilan Instagram'ning **hammaga ochiq** Reel va video postlarini Telegram chatga yuklaydigan shaxsiy bot. Instagram akkaunt paroli kerak emas. Video Instagram tomonidan cheklansa, **har bir havola ishlashi kafolatlanmaydi**.

## 1. BotFather'dan token oling

1. Telegram'da `@BotFather` ni oching.
2. `/newbot` yozing, bot nomi va `...bot` bilan tugaydigan username tanlang.
3. Berilgan tokenni maxfiy saqlang. **Tokenni GitHub'ga yoki ommaviy chatga joylamang.**

## 2. Render Free'ga joylash (tavsiya etilgan)

1. Shu papkadagi fayllarni yangi **private GitHub repository** ga yuklang. `render.yaml` ham bo'lsin.
2. Render Dashboard → **New → Blueprint** → GitHub repository ni tanlang.
3. `BOT_TOKEN` so'ralganda BotFather tokenini maxfiy qiymat sifatida kiriting.
4. Deploy tugaganda Render loglarida `Telegram webhook registered: https://.../telegram` yozuvini tekshiring.
5. Telegram'da botni oching → **Start** → ochiq `https://www.instagram.com/reel/.../` link yuboring.

Render `RENDER_EXTERNAL_URL` muhit o'zgaruvchisini o'zi beradi; URLni qo'lda kiritish shart emas. `Dockerfile` ffmpeg'ni o'rnatadi. `render.yaml` `free` web service ni yaratadi. Bu **haqiqiy botni avtomatik deploy qilmaydi**: uni GitHub va Render akkauntingizga siz ulashingiz kerak.

**Bepul Render cheklovi:** xizmatga 15 daqiqa kiruvchi so'rov bo'lmasa server uxlaydi. Telegram webhook xabari serverni uyg'otishi mumkin, ammo dastlabki javob kechikishi yoki ba'zan Telegram qayta urinishi mumkin. 24/7 kafolatli ishlashi uchun doim faol server/paid hosting kerak.

## 3. Faqat o'zingiz va oila a'zolaringiz uchun (ixtiyoriy)

1. Botda `/id` yozing; Telegram ID raqamingiz chiqadi.
2. Oila a'zongiz ham botga `/id` yuborsin.
3. Render → servis → **Environment** ga `ALLOWED_USER_IDS` degan qiymat qo'shing. Masalan: `123456789,987654321` (haqiqiy IDlarni yozing).
4. **Save, deploy** qiling. Endi faqat shu IDlar video yuklay oladi.

## 4. Kompyuterda sinash (Render'siz)

Python 3.11+ va `ffmpeg` o'rnatilgan bo'lsin.

```bash
pip install -r requirements.txt
```

Windows PowerShell:
```powershell
$env:BOT_TOKEN="BOTFATHER_TOKENINGIZ"
python local_bot.py
```

Linux/macOS:
```bash
export BOT_TOKEN="BOTFATHER_TOKENINGIZ"
python local_bot.py
```

Bir vaqtning o'zida Render webhook varianti va kompyuterdagi polling variantini ishlatmang. Kompyuterdagi bot faqat terminal ochiq va internet mavjud bo'lganda javob beradi.

## Buyruqlar va cheklovlar

- `/start` — ishga tushirish
- `/id` — Telegram user ID ni ko'rish
- Instagram Reel (`/reel/`), post (`/p/`), video (`/tv/`) havolalari qabul qilinadi. Post faqat foto bo'lsa video chiqmaydi.
- Private account video yuklanmaydi.
- Telegram Bot API limitiga mos ravishda 48 MiB gacha videolar yuboriladi.
- Faqat yuklab olish huquqingiz bo'lgan kontentdan foydalaning.

### Nosozliklarni aniqlash

- **Bot javob bermasa**: Render → service → Logs → `Telegram webhook registered` qatorini tekshiring, BotFather tokenini va Deploy holatini tekshiring.
- **Video yuklanmasa**: boshqa ochiq Reel link bilan sinang; Instagram IP yoki autentifikatsiya cheklovi bo'lishi mumkin.
- **403**: Telegram webhook uchun sirli sarlavha avtomatik tekshiriladi; qo'lda webhook endpointiga POST so'rovi yubormang.
- **Boshqa xizmatda deploy**: `PUBLIC_URL=https://sizning-https-domeningiz` o'rnating va `uvicorn main:api --host 0.0.0.0 --port 10000` bilan ishga tushiring.
