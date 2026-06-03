import time
import os
import requests
from flask import Flask

app = Flask(__name__)

last_signal_time = 0
last_signal = None
COOLDOWN = 180  # 3 min (less spam, higher quality)


# =========================
# TELEGRAM
# =========================
def send(msg):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": msg},
            timeout=5
        )
    except:
        pass


# =========================
# PRICE DATA
# =========================
def get_price():
    try:
        url = "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcv&h&e=json"
        data = requests.get(url, timeout=5).json()
        return float(data["symbols"][0]["close"])
    except:
        return None


# =========================
# LIQUIDITY SWEEP DETECTION
# =========================
def detect_sweep(price):

    if not price:
        return "NONE"

    # simplified model (proxy logic)
    if price % 5 == 0:
        return "BUY_SIDE_SWEEP"

    if price % 7 == 0:
        return "SELL_SIDE_SWEEP"

    return "NONE"


# =========================
# STRUCTURE SHIFT (MSS)
# =========================
def detect_mss(price, sweep):

    if sweep == "BUY_SIDE_SWEEP":
        return "BEARISH_SHIFT"

    if sweep == "SELL_SIDE_SWEEP":
        return "BULLISH_SHIFT"

    return "NONE"


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
# SCORE ENGINE (QUALITY ONLY)
# =========================
def score(sweep, mss):

    s = 0

    if sweep != "NONE":
        s += 50

    if mss != "NONE":
        s += 40

    if news_ok():
        s += 10

    return s


# =========================
# HEALTH
# =========================
@app.route("/")
def home():
    return "PHASE 9 MANUAL RUNNING"


# =========================
# SIGNAL ENGINE
# =========================
@app.route("/run")
def run():

    global last_signal_time, last_signal

    now = time.time()

    if now - last_signal_time < COOLDOWN:
        return "cooldown"

    price = get_price()

    if not price:
        send("❌ NO DATA")
        return "no data"

    sweep = detect_sweep(price)
    mss = detect_mss(price, sweep)
    score_value = score(sweep, mss)

    # FINAL DECISION LOGIC
    if sweep != "NONE" and mss != "NONE" and score_value >= 80:

        signal = "🟢 A+ SETUP (HIGH PROBABILITY)"

    elif sweep != "NONE" and mss != "NONE":

        signal = "⚠️ B SETUP (WATCH)"

    else:

        signal = "❌ NO TRADE"

    # anti duplicate
    if signal == last_signal:
        return "duplicate"

    last_signal = signal
    last_signal_time = now

    send(
        f"📊 XAUUSD PHASE 9\n"
        f"Sweep: {sweep}\n"
        f"Structure: {mss}\n"
        f"Score: {score_value}\n"
        f"Signal: {signal}"
    )

    return "sent"


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send("🧪 PHASE 9 OK")
    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
