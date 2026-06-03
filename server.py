import time
import os
import requests
from flask import Flask, request

app = Flask(__name__)

# =========================
# STATE (HEDGE FUND DASHBOARD CORE)
# =========================
price_history = []
trade_log = []

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
    except:
        pass


# =========================
# PRICE FEED (TRADINGVIEW)
# =========================
def update_price(price):
    price_history.append(price)
    if len(price_history) > 200:
        price_history.pop(0)


# =========================
# NEWS ENGINE (REAL)
# =========================
def news_risk():
    api_key = os.environ.get("NEWS_API_KEY")
    if not api_key:
        return 0

    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
        data = requests.get(url, timeout=5).json()

        high = ["CPI", "Fed", "NFP", "interest rate"]
        med = ["inflation", "GDP", "unemployment"]

        score = 0

        for n in data[:20]:
            h = n.get("headline", "").lower()

            for w in high:
                if w.lower() in h:
                    score += 3

            for w in med:
                if w.lower() in h:
                    score += 1

        return score

    except:
        return 0


# =========================
# VOLATILITY ENGINE
# =========================
def volatility():
    if len(price_history) < 10:
        return 1

    high = max(price_history[-10:])
    low = min(price_history[-10:])
    avg = sum(price_history[-10:]) / 10

    rng = (high - low) / avg

    if rng > 0.006:
        return 3
    if rng < 0.0015:
        return 2
    return 0


# =========================
# STRUCTURE (BOS SIMPLIFIED)
# =========================
def structure():
    if len(price_history) < 6:
        return "NEUTRAL"

    if price_history[-1] > price_history[-5]:
        return "BULLISH"

    if price_history[-1] < price_history[-5]:
        return "BEARISH"

    return "RANGE"


# =========================
# LIQUIDITY MODEL
# =========================
def liquidity(price):
    if len(price_history) < 5:
        return "NONE"

    high = max(price_history[-5:])
    low = min(price_history[-5:])

    if price > high:
        return "BUY_SIDE_SWEEP"

    if price < low:
        return "SELL_SIDE_SWEEP"

    return "NONE"


# =========================
# PERFORMANCE DASHBOARD (HEDGE FUND STYLE)
# =========================
def stats():

    if not trade_log:
        return {
            "trades": 0,
            "winrate": 0,
            "avg_score": 0
        }

    wins = len([t for t in trade_log if "A+" in t["signal"]])
    total = len(trade_log)
    avg_score = sum([t["score"] for t in trade_log]) / total

    return {
        "trades": total,
        "winrate": round((wins / total) * 100, 2),
        "avg_score": round(avg_score, 2)
    }


# =========================
# SIGNAL ENGINE (HEDGE FUND STYLE)
# =========================
def signal(price):

    update_price(price)

    score = 50
    direction = None

    sweep = liquidity(price)
    struct = structure()
    vol = volatility()
    news = news_risk()

    # =====================
    # LIQUIDITY
    # =====================
    if sweep == "BUY_SIDE_SWEEP":
        score += 35
        direction = "SHORT"

    elif sweep == "SELL_SIDE_SWEEP":
        score += 35
        direction = "LONG"

    else:
        score -= 10

    # =====================
    # STRUCTURE
    # =====================
    if struct == "BULLISH" and direction == "LONG":
        score += 20

    if struct == "BEARISH" and direction == "SHORT":
        score += 20

    if struct == "RANGE":
        score -= 5

    # =====================
    # NEWS FILTER
    # =====================
    if news >= 6:
        return "BLOCKED (NEWS)", score

    if news >= 3:
        score -= 15

    # =====================
    # VOLATILITY FILTER
    # =====================
    if vol == 3:
        return "BLOCKED (VOL)", score

    if vol == 2:
        score -= 10

    # =====================
    # FINAL DECISION
    # =====================
    if score >= 85:
        return f"A+ SMART MONEY {direction}", score

    if score >= 70:
        return f"B SETUP {direction}", score

    return "NO TRADE", score


# =========================
# DASHBOARD HOME
# =========================
@app.route("/")
def home():
    return "HEDGE FUND DASHBOARD ACTIVE"


# =========================
# TRADINGVIEW WEBHOOK
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
    timestamp = data.get("time", "N/A")

    now = time.time()

    if now - last_signal_time < COOLDOWN:
        return "cooldown"

    sig, score = signal(price)

    if sig == last_signal:
        return "duplicate"

    last_signal = sig
    last_signal_time = now

    trade_log.append({
        "time": now,
        "price": price,
        "signal": sig,
        "score": score
    })

    send(f"""
📊 HEDGE FUND DASHBOARD SIGNAL

Symbol: {symbol}
TV: {tv_signal}
Price: {price}
Time: {timestamp}

Signal: {sig}
Score: {score}

Structure: {structure()}
Liquidity: {liquidity(price)}
Volatility: {volatility()}
News Risk: {news_risk()}

📈 Stats:
Trades: {stats()['trades']}
Winrate: {stats()['winrate']}%
Avg Score: {stats()['avg_score']}
""")

    return "ok", 200


# =========================
# STATS API
# =========================
@app.route("/stats")
def get_stats():
    return stats()


# =========================
# TEST
# =========================
@app.route("/test")
def test():
    send("🧪 DASHBOARD ONLINE")
    return "ok"


# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
