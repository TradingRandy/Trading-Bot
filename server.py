import time
import os
import requests
from flask import Flask

app = Flask(__name__)

last_message_time = {}

# =========================
# TELEGRAM
# =========================
def send_telegram(message):
    global last_message_time

    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return

    now = time.time()
    if message in last_message_time:
        if now - last_message_time[message] < 5:
            return

    last_message_time[message] = now

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": message})


# =========================
# MARKET DATA
# =========================
def get_price():
    try:
        url = "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcv&h&e=json"
        data = requests.get(url, timeout=5).json()
        return float(data["symbols"][0]["close"])
    except:
        return None


# =========================
# REGIME DETECTION (NEW)
# =========================
def get_market_regime(price):

    change = price * 0.002  # fake volatility base

    if change > 5:
        return "HIGH_VOL"
    elif price % 2 == 0:
        return "TREND"
    else:
        return "RANGE"


# =========================
# SMART MONEY FILTER
# =========================
def smart_money_filter(price, regime):

    # chop filter
    if regime == "RANGE":
        return False

    # avoid high chaos
    if regime == "HIGH_VOL":
        return False

    return True


# =========================
# NEWS FILTER
# =========================
def news_ok():
    api_key = os.environ.get("NEWS_API_KEY")

    if not api_key:
        return True

    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
        data = requests.get(url, timeout=5).json()

        bad = ["CPI", "inflation", "Fed", "interest rate", "NFP"]

        for a in data[:10]:
            t = a.get("headline", "")
            for b in bad:
                if b.lower() in t.lower():
                    return False

        return True

    except:
        return True


# =========================
# SCORE ENGINE (PHASE 6)
# =========================
def get_score(price, regime):

    score = 0

    # trend bias
    if regime == "TREND":
        score += 40

    # regime quality
    if regime == "TREND":
        score += 20

    # news
    if news_ok():
        score += 30

    # base liquidity assumption
    score += 10

    return score


# =========================
# MAIN LOGIC
# =========================
@app.route("/")
def home():

    price = get_price()

    if not price:
        send_telegram("❌ NO DATA")
        return "no data"

    regime = get_market_regime(price)

    if not smart_money_filter(price, regime):
        send_telegram(f"⛔ MARKET BLOCKED ({regime})")
        return "blocked"

    score = get_score(price, regime)

    if score >= 80:
        send_telegram(f"🟢 STRONG TRADE | {regime} | Score {score}")
    elif score >= 50:
        send_telegram(f"⚠️ WEAK TRADE | {regime} | Score {score}")
    else:
        send_telegram(f"❌ NO TRADE | {regime} | Score {score}")

    return "Trading Bot läuft 🔥"


@app.route("/test")
def test():
    send_telegram("🧪 PHASE 6 TEST OK")
    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
