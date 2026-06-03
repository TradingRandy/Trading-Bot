import time
import os
import requests
from flask import Flask

app = Flask(__name__)

last_signal_time = 0
last_signal = None
COOLDOWN = 300


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
# MULTI TIMEFRAME SIMULATION
# =========================
def timeframe_alignment(price):

    if not price:
        return "NO_DATA"

    tf_1m = price % 3
    tf_5m = price % 7
    tf_15m = price % 11

    bullish = tf_1m < 2 and tf_5m < 4 and tf_15m < 6
    bearish = tf_1m > 2 and tf_5m > 4 and tf_15m > 6

    if bullish:
        return "BULLISH_ALIGNMENT"
    if bearish:
        return "BEARISH_ALIGNMENT"

    return "MIXED"


# =========================
# VOLATILITY REGIME
# =========================
def volatility_regime(price):

    if not price:
        return "UNKNOWN"

    if price % 2 == 0:
        return "TRENDING"

    if price % 3 == 0:
        return "VOLATILE"

    return "RANGING"


# =========================
# SESSION FILTER
# =========================
def session():

    h = time.gmtime().tm_hour

    if 7 <= h <= 11:
        return "LONDON"
    if 13 <= h <= 17:
        return "NEW_YORK"
    return "ASIA"


# =========================
# SCORE ENGINE
# =========================
def score(tf, vol, sess):

    s = 0

    if tf in ["BULLISH_ALIGNMENT", "BEARISH_ALIGNMENT"]:
        s += 50

    if vol == "TRENDING":
        s += 30
    elif vol == "VOLATILE":
        s -= 20

    if sess in ["LONDON", "NEW_YORK"]:
        s += 20

    return s


# =========================
# HOME
# =========================
@app.route("/")
def home():
    return "PHASE 11 MANUAL ACTIVE"


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

    tf = timeframe_alignment(price)
    vol = volatility_regime(price)
    sess = session()

    score_value = score(tf, vol, sess)

    if tf != "MIXED" and vol == "TRENDING" and score_value >= 80:
        signal = "🟢 A+ INSTITUTIONAL SETUP"
    elif score_value >= 60:
        signal = "⚠️ B SETUP"
    else:
        signal = "❌ NO TRADE"

    if signal == last_signal:
        return "duplicate"

    last_signal = signal
    last_signal_time = now

    send(
        f"🏦 PHASE 11 SIGNAL\n"
        f"TF: {tf}\n"
        f"Volatility: {vol}\n"
        f"Session: {sess}\n"
        f"Score: {score_value}\n"
        f"Signal: {signal}"
    )

    return "sent"


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send("🧪 PHASE 11 OK")
    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
