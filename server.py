import requests
import os
from flask import Flask

app = Flask(__name__)

def send_telegram(message):
    token = os.environ.get("8701563388:AAFuXphtL24yK-BrxS1SU8MB6tsk63JKMoY")
    chat_id = os.environ.get("5562976664")

    if not token or not chat_id:
        print("Missing env vars")
        return

    url = f"https://api.telegram.org/bot8701563388:AAFuXphtL24yK-BrxS1SU8MB6tsk63JKMoY/sendMessage"

    requests.post(url, data={
        "chat_id": chat_id,
        "text": message
    })

@app.route("/")
def home():
    send_telegram("🧠 Trading Brain ONLINE TEST")
    return "Trading Bot läuft 🔥"
