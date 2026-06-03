import requests

def check_news_risk():
    API_KEY = os.environ.get("d8g8h6pr01qlgcuhut60d8g8h6pr01qlgcuhut6g")

    url = f"https://finnhub.io/api/v1/news?category=general&token={API_KEY}"
    data = requests.get(url).json()

    risky_keywords = ["CPI", "inflation", "Fed", "interest rate", "NFP"]

    for article in data[:10]:
        headline = article.get("headline", "")

        for word in risky_keywords:
            if word.lower() in headline.lower():
                return "RISKY"

    return "SAFE"
