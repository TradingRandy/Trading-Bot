import time
import os
import requests
from flask import Flask

app = Flask(__name__)

# =========================
# ANTI SPAM SYSTEM
# =========================
last_message_time = {}
last_run_time = 0
COOLDOWN_SECONDS = 30


# =========================
# TELEGRAM (SAFE)
# =========================
def send_telegram(message):
    global last_message_time

    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Missing env vars")
        return

    now = time.time()

    # prevent duplicate messages
    if message in last_message_time:
        if now - last_message_time[message] < 10:
            print("BLOCKED DUPLICATE:", message)
            return

    last_message_time[message] = now

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        requests.post(url, data={
            "chat_id": chat_id,
            "text": message
        }, timeout=5)
    except Exception as e:
        print("Telegram error:", e)


# =========================
# MARKET DATA (SAFE FALLBACK)
# =========================
def get_price():
    try:
        url = "https://stooq.com/q/l/?s=xauusd&f=sd2t2ohlcv&h&e=json"
        r = requests.get(url, timeout=5).json()
        return float(r["symbols"][0]["close"])
    except:
        return None


# =========================
# SIMPLE MARKET CHECK
# =========================
def market_ok(price):
    if not price:
        return False

    # simple volatility filter
    if price <= 0:
        return False

    return True


# =========================
# SCORE ENGINE (SIMPLE PHASE BASE)
# =========================
def get_score(price):
    score = 50

    if price > 2000:
        score += 20

    return score


# =========================
# HEALTH CHECK (IMPORTANT)
# =========================
@app.route("/")
def health():
    return "OK - Bot Alive"


# =========================
# MAIN TRADING ROUTE (MANUAL / CONTROLLED)
# =========================
@app.route("/run")
def run():
    global last_run_time

    now = time.time()

    # cooldown protection (VERY IMPORTANT)
    if now - last_run_time < COOLDOWN_SECONDS:
        return "cooldown active"

    last_run_time = now

    price = get_price()

    if not market_ok(price):
        send_telegram("❌ NO DATA")
        return "no data"

    score = get_score(price)

    if score >= 80:
        send_telegram(f"🟢 STRONG TRADE | Score {score}")
    elif score >= 50:
        send_telegram(f"⚠️ WEAK TRADE | Score {score}")
    else:
        send_telegram(f"❌ NO TRADE | Score {score}")

    return "done"


# =========================
# TEST ROUTE
# =========================
@app.route("/test")
def test():
    send_telegram("🧪 TEST OK")
    return "sent"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
