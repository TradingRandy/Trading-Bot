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

# store price history for EMA + structure
prices = []


# =========================
# TELEGRAM
# =========================
def send(msg):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Missing Telegram env vars")
        return

    requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": msg},
        timeout=5
    )


# =========================
# EMA CALCULATION (REAL)
# =========================
def ema(values, period):
    if len(values) < period:
        return None

    k = 2 / (period + 1)
    ema_val = sum(values[:period]) / period  # SMA seed

    for price in values[period:]:
        ema_val = price * k + ema_val * (1 - k)

    return ema_val


# =========================
# MARKET STRUCTURE
# =========================
def market_structure(prices):
    if len(prices) < 5:
        return "NO_STRUCTURE"

    highs = prices[-5:]
    trend_up = all(highs[i] >= highs[i-1] for i in range(1, len(highs)))
    trend_down = all(highs[i] <= highs[i-1] for i in range(1, len(highs)))

    if trend_up:
        return "UPTREND"
    if trend_down:
        return "DOWNTREND"
    return "RANGE"


# =========================
# SIGNAL ENGINE (PRO LOGIC)
# =========================
def signal(price):

    prices.append(price)

    ema9 = ema(prices, 9)
    ema21 = ema(prices, 21)
    structure = market_structure(prices)

    if not ema9 or not ema21:
        return "NO DATA", 0

    score = 50

    # EMA crossover logic
    if ema9 > ema21:
        score += 25
        direction = "LONG"
    else:
        score -= 25
        direction = "SHORT"

    # Market structure filter
    if structure == "UPTREND" and direction == "LONG":
        score += 20
    if structure == "DOWNTREND" and direction == "SHORT":
        score += 20

    # Range penalty
    if structure == "RANGE":
        score -= 20

    if score >= 80:
        return "A+ SETUP", score
    if score >= 65:
        return "B SETUP", score

    return "NO TRADE", score


# =========================
# WEBHOOK (TRADINGVIEW)
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    global last_signal_time, last_signal

    data = request.get_json(silent=True)

    if not data:
        return "no data", 400

    symbol = data.get("symbol", "XAUUSD")
    price = float(data.get("price", 0))
    tv_signal = data.get("signal", "TV")

    now = time.time()

    if now - last_signal_time < COOLDOWN:
        return "cooldown"

    sig, score = signal(price)

    if sig == last_signal:
        return "duplicate"

    last_signal = sig
    last_signal_time = now

    send(
        f"""📊 PRO EMA ENGINE

Symbol: {symbol}
TV Signal: {tv_signal}

Price: {price}
EMA9/EMA21 ACTIVE
Structure: {market_structure(prices)}

Result: {sig}
Score: {score}

COOLDOWN: ON
"""
    )

    return "ok", 200


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send("🧪 EMA ENGINE ONLINE")
    return "ok"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
