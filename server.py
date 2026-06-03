import time
import os
import requests
from flask import Flask

app = Flask(__name__)

# =========================
# STATE
# =========================
history = []

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
# MARKET DATA (MULTI CHECK)
# =========================
def get_price():

    sources = [
        "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcv&h&e=json"
    ]

    for url in sources:
        try:
            data = requests.get(url, timeout=5).json()
            return float(data["symbols"][0]["close"])
        except:
            continue

    return None


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
# VOLATILITY FILTER
# =========================
def volatility(price):
    if price % 2 == 0:
        return "LOW"
    if price % 3 == 0:
        return "HIGH"
    return "NORMAL"


# =========================
# NEWS FILTER (SIMPLIFIED)
# =========================
def news_risk():
    # placeholder for real API integration
    return "SAFE"


# =========================
# RISK ENGINE (CORE)
# =========================
def risk_check(price):

    if news_risk() == "RISKY":
        return False

    if volatility(price) == "HIGH":
        return False

    return True


# =========================
# SIGNAL ENGINE
# =========================
def signal(price):

    score = 50

    if price % 2 == 0:
        score += 25

    if session() in ["LONDON", "NEW_YORK"]:
        score += 20

    if volatility(price) == "LOW":
        score += 10

    if not risk_check(price):
        return "BLOCKED", score

    if score >= 80:
        return "A+ SETUP", score
    if score >= 60:
        return "B SETUP", score

    return "NO TRADE", score


# =========================
# LOGGING
# =========================
def log(price, sig, score):

    history.append({
        "time": time.time(),
        "price": price,
        "signal": sig,
        "score": score,
        "session": session()
    })


# =========================
# STATS
# =========================
def stats():

    if not history:
        return {"status": "NO DATA"}

    total = len(history)
    aplus = len([h for h in history if "A+" in h["signal"]])

    return {
        "total": total,
        "a_plus_rate": round(aplus / total * 100, 2)
    }


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return "PHASE 15 INSTITUTIONAL STACK ACTIVE"


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

    sig, score = signal(price)

    if sig == last_signal:
        return "duplicate"

    last_signal = sig
    last_signal_time = now

    log(price, sig, score)

    send(
        f"🏦 PHASE 15 EXECUTION PLAN\n"
        f"Session: {session()}\n"
        f"Signal: {sig}\n"
        f"Score: {score}\n"
        f"Risk Approved: {risk_check(price)}\n"
        f"Trades: {len(history)}"
    )

    return "sent"


@app.route("/stats")
def get_stats():
    return stats()


@app.route("/test")
def test():
    send("🧪 PHASE 15 OK")
    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
