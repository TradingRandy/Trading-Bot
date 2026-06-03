import time
import os
import requests
from flask import Flask

app = Flask(__name__)

# =========================
# MEMORY (TRADES)
# =========================
trades = []

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
# PRICE (SIMULATED SOURCE)
# =========================
def get_price():
    try:
        url = "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcv&h&e=json"
        data = requests.get(url, timeout=5).json()
        return float(data["symbols"][0]["close"])
    except:
        return None


# =========================
# SIMPLE RESULT SIMULATION
# =========================
def simulate_outcome(price):
    # simplified forward assumption (placeholder for real backtest engine)
    return "WIN" if price % 2 == 0 else "LOSS"


# =========================
# BACKTEST LOGIC
# =========================
def evaluate_trade(price, signal):

    outcome = simulate_outcome(price)

    trades.append({
        "time": time.time(),
        "price": price,
        "signal": signal,
        "outcome": outcome
    })

    return outcome


# =========================
# METRICS ENGINE
# =========================
def metrics():

    if not trades:
        return {"status": "NO DATA"}

    wins = len([t for t in trades if t["outcome"] == "WIN"])
    losses = len([t for t in trades if t["outcome"] == "LOSS"])

    winrate = wins / len(trades) * 100

    avg = {
        "winrate": round(winrate, 2),
        "total_trades": len(trades),
        "wins": wins,
        "losses": losses
    }

    return avg


# =========================
# SIGNAL ENGINE
# =========================
def generate_signal(price):

    if price % 2 == 0 and price % 3 != 0:
        return "A+"
    elif price % 3 == 0:
        return "B"
    else:
        return "NO TRADE"


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return "PHASE 14 FUND SYSTEM ACTIVE"


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

    signal = generate_signal(price)
    outcome = evaluate_trade(price, signal)

    if signal == last_signal:
        return "duplicate"

    last_signal = signal
    last_signal_time = now

    send(
        f"🏦 PHASE 14 FUND SYSTEM\n"
        f"Signal: {signal}\n"
        f"Outcome (sim): {outcome}\n"
        f"Trades: {len(trades)}"
    )

    return "sent"


@app.route("/stats")
def stats():
    return metrics()


@app.route("/test")
def test():
    send("🧪 PHASE 14 OK")
    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
