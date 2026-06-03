import time
import os
import requests
from flask import Flask

app = Flask(__name__)

# =========================
# GLOBAL STATE
# =========================
last_message_time = {}

# =========================
# TELEGRAM
# =========================
def send_telegram(message):
    global last_message_time

    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Missing Telegram env vars")
        return

    # 🧠 anti-spam (5 sec rule)
    now = time.time()
    last = last_message_time.get(message, 0)

    if now - last < 5:
        print("Duplicate blocked:", message)
        return

    last_message_time[message] = now

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, data={
            "chat_id": chat_id,
            "text": message
        })
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
# PHASE 3 — MARKET BRAIN
# =========================

def get_trend_score():
    ema_fast = 100
    ema_slow = 95

    diff = ema_fast - ema_slow

    if diff > 5:
        return 30
    elif diff > 2:
        return 20
    elif diff > 0:
        return 10
    return 0


def get_liquidity_score():
    return 10


def get_session_score():
    hour = int(time.strftime("%H"))

    # London + NY session logic
    if 8 <= hour <= 11:
        return 20
    elif 14 <= hour <= 17:
        return 20
    else:
        return 5


def get_trade_score():
    score = 0

    score += get_trend_score()
    score += get_liquidity_score()

    if check_news_risk() == "SAFE":
        score += 20

    score += get_session_score()

    return score

# =========================
# ROUTES
# =========================

@app.route("/")
def home():

    score = get_trade_score()

    if score >= 80:
        send_telegram(f"🟢 STRONG TRADE (Score {score})")
    elif score >= 50:
        send_telegram(f"⚠️ WEAK TRADE (Score {score})")
    else:
        send_telegram(f"❌ NO TRADE (Score {score})")

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
