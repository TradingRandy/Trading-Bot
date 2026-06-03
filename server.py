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

price_history = []
swing_highs = []
swing_lows = []


# =========================
# TELEGRAM
# =========================
def send(msg):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Missing Telegram env vars")
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": msg},
            timeout=5
        )
    except Exception as e:
        print("Telegram error:", e)


# =========================
# STRUCTURE UPDATE
# =========================
def update_structure(price):

    price_history.append(price)

    if len(price_history) > 50:
        price_history.pop(0)

    if len(price_history) < 5:
        return

    i = len(price_history) - 3

    # swing high
    if price_history[i] > price_history[i-1] and price_history[i] > price_history[i+1]:
        swing_highs.append(price_history[i])

    # swing low
    if price_history[i] < price_history[i-1] and price_history[i] < price_history[i+1]:
        swing_lows.append(price_history[i])

    if len(swing_highs) > 20:
        swing_highs.pop(0)

    if len(swing_lows) > 20:
        swing_lows.pop(0)


# =========================
# LIQUIDITY DETECTION
# =========================
def liquidity_sweep(price):

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "NO_SWEEP"

    last_high = swing_highs[-1]
    last_low = swing_lows[-1]

    # BUY SIDE LIQUIDITY (stop hunt above highs)
    if price > last_high:
        return "BUY_SIDE_SWEEP"

    # SELL SIDE LIQUIDITY (stop hunt below lows)
    if price < last_low:
        return "SELL_SIDE_SWEEP"

    return "NONE"


# =========================
# MARKET CONTEXT
# =========================
def context_bias():
    if len(price_history) < 10:
        return "NEUTRAL"

    if price_history[-1] > price_history[-5]:
        return "BULLISH"

    if price_history[-1] < price_history[-5]:
        return "BEARISH"

    return "RANGE"


# =========================
# MAIN SIGNAL ENGINE
# =========================
def signal(price):

    update_structure(price)

    sweep = liquidity_sweep(price)
    bias = context_bias()

    score = 50
    direction = "NONE"

    # =========================
    # LIQUIDITY EDGE (CORE)
    # =========================
    if sweep == "BUY_SIDE_SWEEP":
        score += 35
        direction = "SHORT"

    elif sweep == "SELL_SIDE_SWEEP":
        score += 35
        direction = "LONG"

    else:
        score -= 10

    # =========================
    # CONTEXT FILTER
    # =========================
    if bias == "BULLISH" and direction == "LONG":
        score += 15

    if bias == "BEARISH" and direction == "SHORT":
        score += 15

    if bias == "RANGE":
        score -= 10

    # =========================
    # FINAL DECISION
    # =========================
    if score >= 80:
        return f"A+ {direction} (LIQUIDITY SWEEP)", score

    if score >= 65:
        return f"B {direction} (STRUCTURE ENTRY)", score

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
        f"""💧 LIQUIDITY ENGINE

Symbol: {symbol}
TV Signal: {tv_signal}

Price: {price}

Structure: {len(price_history)} candles tracked
Bias: {context_bias()}

Result: {sig}
Score: {score}

Sweep Active: {liquidity_sweep(price)}
"""
    )

    return "ok", 200


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send("🧪 LIQUIDITY ENGINE ONLINE")
    return "ok"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
