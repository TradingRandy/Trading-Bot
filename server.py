import time
import os
import requests
from flask import Flask

app = Flask(__name__)

# =========================
# MEMORY (TRADING JOURNAL)
# =========================
trade_log = []

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
# SESSION DETECTION
# =========================
def session():
    h = time.gmtime().tm_hour

    if 7 <= h <= 11:
        return "LONDON"
    if 13 <= h <= 17:
        return "NEW_YORK"
    return "ASIA"


# =========================
# SIMPLE SCORING (FROM PHASE 11)
# =========================
def score(price):
    s = 50

    if price and price % 2 == 0:
        s += 20

    if session() in ["LONDON", "NEW_YORK"]:
        s += 20

    return s


# =========================
# CLASSIFY SIGNAL
# =========================
def classify(score_value):

    if score_value >= 80:
        return "A+"
    elif score_value >= 60:
        return "B"
    else:
        return "NO_TRADE"


# =========================
# LOGGING ENGINE (PHASE 12 CORE)
# =========================
def log_trade(signal_type, score_value):

    trade_log.append({
        "time": time.time(),
        "session": session(),
        "signal": signal_type,
        "score": score_value
    })


# =========================
# ANALYTICS ENGINE
# =========================
def analytics():

    if not trade_log:
        return "NO DATA"

    total = len(trade_log)

    a_plus = len([t for t in trade_log if t["signal"] == "A+"])
    b = len([t for t in trade_log if t["signal"] == "B"])

    return {
        "total_signals": total,
        "a_plus_ratio": round(a_plus / total * 100, 2),
        "b_ratio": round(b / total * 100, 2),
    }


# =========================
# HOME
# =========================
@app.route("/")
def home():
    return "PHASE 12 INTELLIGENCE ACTIVE"


# =========================
# RUN SIGNAL ENGINE
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

    score_value = score(price)
    signal = classify(score_value)

    # prevent duplicates
    if signal == last_signal:
        return "duplicate"

    last_signal = signal
    last_signal_time = now

    # LOG IT
    log_trade(signal, score_value)

    send(
        f"🏦 PHASE 12 SIGNAL\n"
        f"Session: {session()}\n"
        f"Score: {score_value}\n"
        f"Signal: {signal}\n"
        f"Trades Logged: {len(trade_log)}"
    )

    return "sent"


# =========================
# STATS ENDPOINT (NEW)
# =========================
@app.route("/stats")
def stats():
    return analytics()


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send("🧪 PHASE 12 OK")
    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
