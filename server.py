import time
import os
import requests
from flask import Flask, request

app = Flask(__name__)

# =========================
# STATE
# =========================
history = []
price_history = []

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
# NEWS (REAL FINNHUB)
# =========================
def news_risk():
    api_key = os.environ.get("NEWS_API_KEY")

    if not api_key:
        return "SAFE"

    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
        data = requests.get(url, timeout=5).json()

        risky_words = [
            "CPI", "inflation", "Fed",
            "interest rate", "NFP",
            "unemployment", "rate hike"
        ]

        for article in data[:15]:
            headline = article.get("headline", "")
            if any(w.lower() in headline.lower() for w in risky_words):
                return "RISKY"

        return "SAFE"

    except:
        return "SAFE"


# =========================
# PRICE SOURCE (TRADINGVIEW)
# =========================
def update_price(price):
    price_history.append(price)
    if len(price_history) > 50:
        price_history.pop(0)


# =========================
# VOLATILITY (REAL RANGE BASED)
# =========================
def volatility(price):

    if len(price_history) < 10:
        return "NORMAL"

    high = max(price_history[-10:])
    low = min(price_history[-10:])

    rng = high - low

    if rng > price * 0.005:
        return "HIGH"

    if rng < price * 0.002:
        return "LOW"

    return "NORMAL"


# =========================
# STRUCTURE BIAS
# =========================
def bias():

    if len(price_history) < 10:
        return "NEUTRAL"

    if price_history[-1] > price_history[-5]:
        return "BULLISH"

    if price_history[-1] < price_history[-5]:
        return "BEARISH"

    return "RANGE"


# =========================
# LIQUIDITY LOGIC (SIMPLE BUT REAL)
# =========================
def liquidity_signal(price):

    if len(price_history) < 5:
        return "NONE"

    last_high = max(price_history[-5:])
    last_low = min(price_history[-5:])

    if price > last_high:
        return "BUY_SIDE_SWEEP"

    if price < last_low:
        return "SELL_SIDE_SWEEP"

    return "NONE"


# =========================
# SIGNAL ENGINE
# =========================
def signal(price):

    update_price(price)

    score = 50
    direction = None

    sweep = liquidity_signal(price)
    b = bias()
    vol = volatility(price)

    # liquidity logic
    if sweep == "BUY_SIDE_SWEEP":
        score += 35
        direction = "SHORT"

    elif sweep == "SELL_SIDE_SWEEP":
        score += 35
        direction = "LONG"

    else:
        score -= 10

    # bias confirmation
    if b == "BULLISH" and direction == "LONG":
        score += 15

    if b == "BEARISH" and direction == "SHORT":
        score += 15

    if b == "RANGE":
        score -= 10

    # volatility filter
    if vol == "HIGH":
        score -= 5

    # news filter
    if news_risk() == "RISKY":
        return "BLOCKED (NEWS)", score

    # final decision
    if score >= 80:
        return f"A+ {direction} (PRO)", score

    if score >= 65:
        return f"B {direction}", score

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

    price = float(data.get("price", 0))
    symbol = data.get("symbol", "XAUUSD")
    tv_signal = data.get("signal", "TV")

    now = time.time()

    if now - last_signal_time < COOLDOWN:
        return "cooldown"

    sig, score = signal(price)

    if sig == last_signal:
        return "duplicate"

    last_signal = sig
    last_signal_time = now

    send(f"""
🏦 REAL DATA ENGINE

Symbol: {symbol}
TV Signal: {tv_signal}

Price: {price}

Signal: {sig}
Score: {score}

Bias: {bias()}
Volatility: {volatility(price)}
Liquidity: {liquidity_signal(price)}
News: {news_risk()}
""")

    return "ok", 200


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send("🧪 SYSTEM ONLINE")
    return "ok"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
