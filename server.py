import os
import requests
from flask import Flask

app = Flask(__name__)

# =========================
# TELEGRAM
# =========================
def send_telegram(message):
    token = os.environ.get("8701563388:AAFuXphtL24yK-BrxS1SU8MB6tsk63JKMoY")
    chat_id = os.environ.get("5562976664")

    if not token or not chat_id:
        print("Missing Telegram env vars")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    requests.post(url, data={
        "chat_id": chat_id,
        "text": message
    })

# =========================
# NEWS RISK ENGINE
# =========================
def check_news_risk():
    api_key = os.environ.get("d8g8h6pr01qlgcuhut60d8g8h6pr01qlgcuhut6g")

    if not api_key:
        return "SAFE"

    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
        data = requests.get(url).json()

        risky_keywords = ["CPI", "inflation", "Fed", "interest rate", "NFP"]

        for article in data[:10]:
            headline = article.get("headline", "")

            for word in risky_keywords:
                if word.lower() in headline.lower():
                    return "RISKY"

        return "SAFE"

    except:
        return "SAFE"

# =========================
# MAIN ROUTE
# =========================
@app.route("/")
def home():

    market_state = check_news_risk()

    if market_state == "RISKY":
        send_telegram("⚠️ NEWS RISK ACTIVE – NO TRADE")
    else:
        send_telegram("🧠 Trading Bot ONLINE – Market SAFE")

    return "Trading Bot läuft 🔥"

# =========================
# START SERVER (RENDER)
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
