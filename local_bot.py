"""Run the bot locally (do not run simultaneously with the Render deployment)."""
from main import build_telegram_app

if __name__ == "__main__":
    build_telegram_app(webhook=False).run_polling(drop_pending_updates=False)
