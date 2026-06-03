import time
import os
import requests
from flask import Flask, request

app = Flask(__name__)

# =========================
# STATE
# =========================
price_history = []

swing_highs = []
swing_lows = []

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
# STRUCTURE ENGINE
# =========================
def update_structure(price):

    price_history.append(price)

    if len(price_history) > 100:
        price_history.pop(0)

    if len(price_history) < 5:
        return

    i = len(price_history) - 3

    if price_history[i] > price_history[i-1] and price_history[i] > price_history[i+1]:
        swing_highs.append(price_history[i])

    if price_history[i] < price_history[i-1] and price_history[i] < price_history[i+1]:
        swing_lows.append(price_history[i])

    if len(swing_highs) > 20:
        swing_highs.pop(0)

    if len(swing_lows) > 20:
        swing_lows.pop(0)


# =========================
# LIQUIDITY SWEEP
# =========================
def liquidity_sweep(price):

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "NO_SWEEP"

    last_high = swing_highs[-1]
    last_low = swing_lows[-1]

    if price > last_high:
        return "BUY_SIDE_SWEEP"

    if price < last_low:
        return "SELL_SIDE_SWEEP"

    return "NONE"


# =========================
# MARKET STRUCTURE STATE
# =========================
def structure_state():

    if len(price_history) < 10:
        return "NEUTRAL"

    hh = price_history[-1] > price_history[-5]
    ll = price_history[-1] < price_history[-5]

    if hh:
        return "BULLISH"
    if ll:
        return "BEARISH"

    return "RANGE"


# =========================
# DISPLACEMENT (REAL MOVE FILTER)
# =========================
def displacement(price):

    if len(price_history) < 5:
        return False

    return abs(price_history[-1] - price_history[-5]) > (price_history[-5] * 0.002)


# =========================
# SIGNAL ENGINE (INSTITUTIONAL LOGIC)
# =========================
def signal(price):

    update_structure(price)

    sweep = liquidity_sweep(price)
    bias = structure_state()
    impulse = displacement(price)

    score = 50
    direction = None

    # =========================
    # LIQUIDITY EDGE
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
    # STRUCTURE CONFIRMATION
    # =========================
    if bias == "BULLISH" and direction == "LONG":
        score += 15

    if bias == "BEARISH" and direction == "SHORT":
        score += 15

    if bias == "RANGE":
        score -= 10

    # =========================
    # DISPLACEMENT CONFIRMATION
    # =========================
    if impulse:
        score += 10

    # =========================
    # FINAL DECISION
    # =========================
    if score >= 80:
        return f"A+ {direction} (INSTITUTIONAL)", score

    if score >= 65:
        return f"B {direction}", score

    return "NO TRADE", score


# =========================
# WEBHOOK
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    global last_signal_time, last_signal

    data = request.get_json(silent=True)
    if not data:
        return "no data", 400

    price = float(data.get("price", 0))
    symbol = data.get("symbol", "XAUUSD")

    now = time.time()

    if now - last_signal_time < COOLDOWN:
        return "cooldown"

    sig, score = signal(price)

    if sig == last_signal:
        return "duplicate"

    last_signal = sig
    last_signal_time = now

    send(f"""🏦 INSTITUTIONAL PRO ENGINE

Symbol: {symbol}

Signal: {sig}
Score: {score}

Structure: {structure_state()}
Sweep: {liquidity_sweep(price)}
Displacement: {displacement(price)}

Price: {price}
""")

    return "ok", 200


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send("🧪 INSTITUTIONAL ENGINE LIVE")
    return "ok"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
