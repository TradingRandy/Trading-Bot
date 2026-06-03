import time
import os
import requests
from flask import Flask, request

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
# VOLATILITY
# =========================
def volatility(price):
    if price % 2 == 0:
        return "LOW"
    if price % 3 == 0:
        return "HIGH"
    return "NORMAL"


# =========================
# RISK
# =========================
def risk_check(price):
    if volatility(price) == "HIGH":
        return False
    return True


# =========================
# SIGNAL ENGINE (DEIN SYSTEM)
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
# LOG
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
# HOME
# =========================
@app.route("/")
def home():
    return "TRADING ENGINE ONLINE"


# =========================
# TRADINGVIEW WEBHOOK (WICHTIG!)
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    global last_signal_time, last_signal

    data = request.json

    if not data:
        return "no data", 400

    symbol = data.get("symbol", "XAUUSD")
    price = float(data.get("price", 0))

    now = time.time()

    if now - last_signal_time < COOLDOWN:
        return "cooldown"

    sig, score = signal(price)

    if sig == last_signal:
        return "duplicate"

    last_signal = sig
    last_signal_time = now

    log(price, sig, score)

    send(
        f"""📊 TRADINGVIEW ALERT

Symbol: {symbol}
Price: {price}

Engine Signal: {sig}
Score: {score}

Session: {session()}
"""
    )

    return "ok", 200


# =========================
# MANUAL TEST
# =========================
@app.route("/test")
def test():
    send("🧪 BOT OK")
    return "sent"


# =========================
# OPTIONAL MANUAL RUN
# =========================
@app.route("/run")
def run():
    price = get_price()

    if not price:
        return "no data"

    sig, score = signal(price)
    log(price, sig, score)

    send(f"MANUAL RUN: {sig} | {score}")

    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
