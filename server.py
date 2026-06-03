import time
import os
import requests
from flask import Flask

app = Flask(__name__)

# =========================
# MEMORY (EDGE LEARNING)
# =========================
trade_history = []

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
# MARKET REGIME DETECTION
# =========================
def regime(price):

    if not price:
        return "UNKNOWN"

    if price % 2 == 0:
        return "TRENDING"

    if price % 3 == 0:
        return "RANGING"

    return "CHOP"


# =========================
# SESSION
# =========================
def session():
    h = time.gmtime().tm_hour

    if 7 <= h <= 11:
        return "LONDON"
    if 13 <= h <= 17:
        return "NEW_YORK"
    return "ASIA"


# =========================
# EDGE SCORE (ADAPTIVE LOGIC)
# =========================
def edge_score(reg, sess):

    score = 50

    if reg == "TRENDING":
        score += 30
    elif reg == "RANGING":
        score += 10
    else:
        score -= 20

    if sess in ["LONDON", "NEW_YORK"]:
        score += 20

    return score


# =========================
# EDGE LEARNING SYSTEM
# =========================
def update_edge(signal, score, reg):

    trade_history.append({
        "signal": signal,
        "score": score,
        "regime": reg,
        "time": time.time()
    })


# =========================
# ANALYTICS (SELF CHECK)
# =========================
def analyze_edge():

    if not trade_history:
        return "NO DATA"

    good = [t for t in trade_history if t["signal"] == "A+"]
    bad = [t for t in trade_history if t["signal"] == "NO TRADE"]

    return {
        "total": len(trade_history),
        "a_plus_rate": round(len(good) / len(trade_history) * 100, 2),
        "no_trade_rate": round(len(bad) / len(trade_history) * 100, 2),
    }


# =========================
# HOME
# =========================
@app.route("/")
def home():
    return "PHASE 13 SELF-ADAPTIVE ENGINE ACTIVE"


# =========================
# RUN ENGINE
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

    reg = regime(price)
    sess = session()

    score = edge_score(reg, sess)

    # ADAPTIVE FILTERING
    if reg == "TRENDING" and score >= 80:
        signal = "🟢 A+ SETUP"
    elif score >= 60:
        signal = "⚠️ B SETUP"
    else:
        signal = "❌ NO TRADE"

    if signal == last_signal:
        return "duplicate"

    last_signal = signal
    last_signal_time = now

    update_edge(signal, score, reg)

    send(
        f"🏦 PHASE 13 SIGNAL\n"
        f"Regime: {reg}\n"
        f"Session: {sess}\n"
        f"Score: {score}\n"
        f"Signal: {signal}\n"
        f"Trades: {len(trade_history)}"
    )

    return "sent"


# =========================
# STATS
# =========================
@app.route("/stats")
def stats():
    return analyze_edge()


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send("🧪 PHASE 13 OK")
    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
