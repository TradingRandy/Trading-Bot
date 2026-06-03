import os
import requests
from flask import Flask

app = Flask(__name__)

# =========================
# TELEGRAM
# =========================
def send_telegram(message):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Missing Telegram env vars")
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={
            "chat_id": chat_id,
            "text": message
        })
        print("Telegram response:", r.text)
    except Exception as e:
        print("Telegram error:", e)

# =========================
# NEWS RISK ENGINE
# =========================
def check_news_risk():
    api_key = os.environ.get("NEWS_API_KEY")

    if not api_key:
        return "SAFE"

    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
        data = requests.get(url, timeout=5).json()

        risky_keywords = ["CPI", "inflation", "Fed", "interest rate", "NFP"]

        for article in data[:10]:
            headline = article.get("headline", "")

            for word in risky_keywords:
                if word.lower() in headline.lower():
                    return "RISKY"

        return "SAFE"

    except:
        return "SAFE"

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    market_state = check_news_risk()

    if market_state == "RISKY":
        send_telegram("⚠️ NEWS RISK ACTIVE – NO TRADE")
    else:
        send_telegram("🧠 Trading Bot ONLINE – Market SAFE")

    return "Trading Bot läuft 🔥"


@app.route("/test")
def test():
    send_telegram("🧪 TEST OK")
    return "sent"

# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

import time

last_message_time = {}
