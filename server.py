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
# MARKET DATA (SIMPLIFIED LIVE)
# =========================
def get_price():
    try:
        url = "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcv&h&e=json"
        data = requests.get(url, timeout=5).json()
        return float(data["symbols"][0]["close"])
    except:
        return None


# =========================
# STRUCTURE ANALYSIS
# =========================
def get_volatility(price):
    # simple proxy (later real candles)
    return abs(price - (price * 0.995))


def get_trend_strength(price):
    # pseudo trend logic (upgrade later with EMA)
    if price > 2000:
        return 1
    return 0


# =========================
# NEWS FILTER
# =========================
def check_news():
    api_key = os.environ.get("NEWS_API_KEY")

    if not api_key:
        return "SAFE"

    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
        data = requests.get(url, timeout=5).json()

        bad = ["CPI", "inflation", "Fed", "interest rate", "NFP"]

        for a in data[:10]:
            t = a.get("headline", "")
            for b in bad:
                if b.lower() in t.lower():
                    return "RISKY"

        return "SAFE"

    except:
        return "SAFE"


# =========================
# RISK ENGINE (KILL SWITCH)
# =========================
def market_ok(price):

    if not price:
        return False

    if check_news() == "RISKY":
        return False

    volatility = get_volatility(price)

    # too chaotic market filter
    if volatility > 20:
        return False

    return True


# =========================
# FINAL SCORE ENGINE
# =========================
def get_score(price):

    score = 0

    if get_trend_strength(price):
        score += 40

    if check_news() == "SAFE":
        score += 30

    score += 20  # base liquidity assumption

    return score


# =========================
# ROUTE
# =========================
@app.route("/")
def home():

    price = get_price()

    if not market_ok(price):
        send_telegram("⛔ MARKET BLOCKED (NO TRADE ZONE)")
        return "blocked"

    score = get_score(price)

    if score >= 80:
        send_telegram(f"🟢 STRONG TRADE {score}")
    elif score >= 50:
        send_telegram(f"⚠️ WEAK TRADE {score}")
    else:
        send_telegram(f"❌ NO TRADE {score}")

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
