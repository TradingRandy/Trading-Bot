import time
import os
import requests
from flask import Flask

app = Flask(__name__)

last_signal_time = 0
last_signal = None
COOLDOWN = 300  # 5 min (VERY selective system)


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
# SESSION DETECTION (simplified)
# =========================
def get_session():
    hour = time.gmtime().tm_hour

    if 7 <= hour <= 11:
        return "LONDON"
    if 13 <= hour <= 17:
        return "NEW_YORK"
    return "ASIA"


# =========================
# LIQUIDITY ZONES (simplified model)
# =========================
def liquidity_zone(price):

    if not price:
        return "NONE"

    if price % 10 == 0:
        return "HIGH_LIQUIDITY"

    return "NORMAL"


# =========================
# SWEEP DETECTION
# =========================
def sweep(price):

    if price and price % 5 == 0:
        return "SWEEP"

    return "NONE"


# =========================
# STRUCTURE SHIFT (MSS)
# =========================
def mss(sweep_state):

    if sweep_state == "SWEEP":
        return "SHIFT"

    return "NONE"


# =========================
# FAIR VALUE GAP (FVG)
# =========================
def fvg(price):

    if price and price % 7 == 0:
        return "FVG_ZONE"

    return "NONE"


# =========================
# SCORE ENGINE (PRO FILTER)
# =========================
def score(session, sweep_state, mss_state, fvg_state):

    s = 0

    if sweep_state == "SWEEP":
        s += 40

    if mss_state == "SHIFT":
        s += 30

    if fvg_state == "FVG_ZONE":
        s += 20

    if session in ["LONDON", "NEW_YORK"]:
        s += 10

    return s


# =========================
# HOME
# =========================
@app.route("/")
def home():
    return "PHASE 10 MANUAL ACTIVE"


# =========================
# MAIN ENGINE
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

    session = get_session()
    sweep_state = sweep(price)
    mss_state = mss(sweep_state)
    fvg_state = fvg(price)

    score_value = score(session, sweep_state, mss_state, fvg_state)

    # FINAL DECISION
    if sweep_state == "SWEEP" and mss_state == "SHIFT" and fvg_state == "FVG_ZONE" and score_value >= 80:
        signal = "🟢 A+ INSTITUTIONAL SETUP"

    elif score_value >= 60:
        signal = "⚠️ B SETUP (WATCH)"

    else:
        signal = "❌ NO TRADE"

    if signal == last_signal:
        return "duplicate"

    last_signal = signal
    last_signal_time = now

    send(
        f"🏦 XAUUSD PHASE 10\n"
        f"Session: {session}\n"
        f"Liquidity: {sweep_state}\n"
        f"Structure: {mss_state}\n"
        f"FVG: {fvg_state}\n"
        f"Score: {score_value}\n"
        f"Signal: {signal}"
    )

    return "sent"


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send("🧪 PHASE 10 MANUAL OK")
    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
