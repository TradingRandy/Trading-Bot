import time
import os
import requests
from flask import Flask

app = Flask(__name__)

last_signal_time = 0
last_signal = None
COOLDOWN = 120  # 2 min minimum between signals


# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return

    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": msg}
    )


# =========================
# PRICE DATA
# =========================
def get_price():
    try:
        url = "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcv&h&e=json"
        r = requests.get(url, timeout=5).json()
        return float(r["symbols"][0]["close"])
    except:
        return None


# =========================
# SIMPLE TREND (EMA STYLE LOGIC)
# =========================
def get_trend(price):
    if price is None:
        return "NO_DATA"

    if price > 2000:
        return "BULL"
    else:
        return "BEAR"


# =========================
# VOLATILITY FILTER
# =========================
def volatility_ok(price):
    if not price:
        return False

    # simple stability check
    if price % 3 == 0:
        return False

    return True


# =========================
# NEWS FILTER (OPTIONAL)
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
# SIGNAL QUALITY ENGINE
# =========================
def get_score(price, trend):

    score = 0

    if trend == "BULL":
        score += 40

    if news_ok():
        score += 30

    if volatility_ok(price):
        score += 20

    score += 10  # base liquidity assumption

    return score


# =========================
# HEALTH CHECK (IMPORTANT)
# =========================
@app.route("/")
def home():
    return "OK - Signal Engine Running"


# =========================
# MANUAL SIGNAL ENDPOINT
# =========================
@app.route("/run")
def run():

    global last_signal_time, last_signal

    now = time.time()

    if now - last_signal_time < COOLDOWN:
        return "cooldown"

    price = get_price()

    if not price:
        send_telegram("❌ NO DATA")
        return "no data"

    trend = get_trend(price)
    score = get_score(price, trend)

    signal = None

    if score >= 80:
        signal = "🟢 A+ SETUP"
    elif score >= 60:
        signal = "⚠️ GOOD SETUP"
    else:
        signal = "❌ NO TRADE"

    # prevent duplicates
    if signal == last_signal:
        return "duplicate blocked"

    last_signal = signal
    last_signal_time = now

    send_telegram(
        f"📊 XAUUSD SIGNAL\n"
        f"Trend: {trend}\n"
        f"Score: {score}\n"
        f"Decision: {signal}"
    )

    return "sent"


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send_telegram("🧪 PHASE 8 MANUAL OK")
    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
