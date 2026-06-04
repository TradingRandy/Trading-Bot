import time
import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime
 
app = Flask(__name__)
 
# =========================
# CONFIG
# =========================
MIN_SCORE = 75          # Kein Signal unter 75%
COOLDOWN = 300          # 5 Minuten zwischen Signalen
MAX_HISTORY = 200       # Preishistorie
JOURNAL_FILE = "trade_journal.json"
 
# =========================
# STATE
# =========================
price_history = []
trade_log = []
last_signal_time = 0
last_signal = None
 
 
# =========================
# TRADE JOURNAL (Persistent)
# =========================
def load_journal():
    global trade_log
    try:
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, "r") as f:
                trade_log = json.load(f)
    except:
        trade_log = []
 
def save_journal():
    try:
        with open(JOURNAL_FILE, "w") as f:
            json.dump(trade_log[-500:], f)  # Max 500 Trades speichern
    except:
        pass
 
load_journal()
 
 
# =========================
# HISTORISCHE DATEN LADEN (Yahoo Finance)
# =========================
def load_historical_prices():
    """Lädt die letzten 200 5-Minuten-Kerzen von Yahoo Finance beim Start."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10).json()
 
        closes = (
            resp.get("chart", {})
                .get("result", [{}])[0]
                .get("indicators", {})
                .get("quote", [{}])[0]
                .get("close", [])
        )
 
        # None-Werte rausfiltern
        closes = [float(p) for p in closes if p is not None]
 
        if len(closes) >= 52:
            for price in closes[-200:]:
                price_history.append(price)
            print(f"[HISTORY] ✅ {len(closes)} Preispunkte geladen → EMA sofort bereit")
        else:
            print(f"[HISTORY] Nur {len(closes)} Punkte → warte auf Live-Preise")
 
    except Exception as e:
        print(f"[HISTORY] Fehler: {e}")
 
load_historical_prices()
 
 
# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[TELEGRAM] Env vars fehlen")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=5
        )
    except Exception as e:
        print(f"[TELEGRAM] Fehler: {e}")
 
 
# =========================
# PREIS UPDATE
# =========================
def update_price(price):
    price_history.append(float(price))
    if len(price_history) > MAX_HISTORY:
        price_history.pop(0)
 
 
# =========================
# EMA BERECHNUNG
# =========================
def calc_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period  # SMA als Startwert
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 4)
 
def get_ema_signal():
    """
    Gibt EMA-Status zurück:
    - Richtung: BULLISH / BEARISH / NEUTRAL
    - Abstand EMA20 zu EMA50
    - Kreuzung erkannt?
    """
    if len(price_history) < 52:
        return {"status": "INSUFFICIENT_DATA", "ema20": None, "ema50": None, "cross": None}
 
    ema20 = calc_ema(price_history, 20)
    ema50 = calc_ema(price_history, 50)
    price = price_history[-1]
 
    # Kreuzungs-Erkennung (letzte 3 Kerzen)
    cross = "NONE"
    if len(price_history) >= 55:
        old_ema20 = calc_ema(price_history[:-3], 20)
        old_ema50 = calc_ema(price_history[:-3], 50)
        if old_ema20 and old_ema50:
            if old_ema20 <= old_ema50 and ema20 > ema50:
                cross = "BULLISH_CROSS"   # Golden Cross
            elif old_ema20 >= old_ema50 and ema20 < ema50:
                cross = "BEARISH_CROSS"   # Death Cross
 
    if ema20 > ema50 and price > ema20:
        status = "BULLISH"
    elif ema20 < ema50 and price < ema20:
        status = "BEARISH"
    else:
        status = "NEUTRAL"
 
    return {
        "status": status,
        "ema20": ema20,
        "ema50": ema50,
        "cross": cross,
        "price_vs_ema20": round(price - ema20, 2) if ema20 else None
    }
 
 
# =========================
# STRUKTUR (Market Structure)
# =========================
def get_structure():
    if len(price_history) < 10:
        return "NEUTRAL"
    recent = price_history[-10:]
    highs = [recent[i] for i in range(1, len(recent)-1) if recent[i] > recent[i-1] and recent[i] > recent[i+1]]
    lows  = [recent[i] for i in range(1, len(recent)-1) if recent[i] < recent[i-1] and recent[i] < recent[i+1]]
 
    if len(highs) >= 2 and highs[-1] > highs[-2]:
        return "BULLISH"   # Higher Highs
    if len(lows) >= 2 and lows[-1] < lows[-2]:
        return "BEARISH"   # Lower Lows
    return "RANGE"
 
 
# =========================
# LIQUIDITÄT (Smart Money)
# =========================
def get_liquidity(price):
    if len(price_history) < 20:
        return "NONE"
    recent = price_history[-20:]
    high = max(recent[:-1])   # Bisheriges High (ohne aktuelle Kerze)
    low  = min(recent[:-1])   # Bisheriges Low
 
    if price > high * 1.0005:   # 0.05% über High → Sweep
        return "BUY_SIDE_SWEEP"
    if price < low * 0.9995:    # 0.05% unter Low → Sweep
        return "SELL_SIDE_SWEEP"
    return "NONE"
 
 
# =========================
# VOLATILITÄT (ATR-Style)
# =========================
def get_volatility():
    if len(price_history) < 14:
        return {"level": "NORMAL", "atr_pct": 0}
 
    ranges = []
    for i in range(1, 14):
        r = abs(price_history[-i] - price_history[-i-1])
        ranges.append(r)
    atr = sum(ranges) / len(ranges)
    atr_pct = (atr / price_history[-1]) * 100
 
    if atr_pct > 0.5:
        level = "HIGH"
    elif atr_pct < 0.1:
        level = "LOW"
    else:
        level = "NORMAL"
 
    return {"level": level, "atr_pct": round(atr_pct, 4)}
 
 
# =========================
# NEWS SENTIMENT (Finnhub)
# =========================
def get_news_sentiment():
    api_key = os.environ.get("NEWS_API_KEY")
    if not api_key:
        return {"score": 0, "risk": "UNKNOWN", "headlines": []}
 
    try:
        # Gold-relevante News
        url = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
        data = requests.get(url, timeout=6).json()
 
        bullish_words = ["rate cut", "fed dovish", "safe haven", "gold rally",
                         "inflation", "dollar weak", "risk off", "uncertainty",
                         "recession", "geopolitic", "war", "crisis"]
 
        bearish_words = ["rate hike", "fed hawkish", "dollar strong", "risk on",
                         "gold sell", "taper", "yields rise", "strong economy"]
 
        high_impact = ["CPI", "NFP", "Fed", "interest rate", "FOMC", "Powell",
                       "GDP", "unemployment", "payroll"]
 
        bull_score = 0
        bear_score = 0
        high_impact_count = 0
        relevant_headlines = []
 
        for n in data[:30]:
            headline = n.get("headline", "").lower()
            original  = n.get("headline", "")
 
            is_relevant = False
 
            for w in bullish_words:
                if w in headline:
                    bull_score += 1
                    is_relevant = True
 
            for w in bearish_words:
                if w in headline:
                    bear_score += 1
                    is_relevant = True
 
            for w in high_impact:
                if w.lower() in headline:
                    high_impact_count += 1
                    is_relevant = True
 
            if is_relevant and len(relevant_headlines) < 3:
                relevant_headlines.append(original[:80])
 
        net = bull_score - bear_score
 
        # Risiko-Assessment
        if high_impact_count >= 3:
            risk = "HIGH"        # News-Event aktiv → vorsichtig
        elif high_impact_count >= 1:
            risk = "MEDIUM"
        else:
            risk = "LOW"
 
        return {
            "bull_score": bull_score,
            "bear_score": bear_score,
            "net": net,
            "risk": risk,
            "high_impact": high_impact_count,
            "headlines": relevant_headlines
        }
 
    except Exception as e:
        print(f"[NEWS] Fehler: {e}")
        return {"score": 0, "risk": "UNKNOWN", "headlines": []}
 
 
# =========================
# SCORE ENGINE (0–100%)
# =========================
def calculate_score(price, tv_signal=""):
    """
    Transparenter Score mit klarem Breakdown:
    - EMA Alignment:      0–30 Punkte
    - Marktstruktur:      0–20 Punkte
    - Liquidität/Sweep:   0–25 Punkte
    - News Sentiment:     0–15 Punkte  (kann auch abziehen)
    - Volatilität:        0–10 Punkte  (Strafe bei extremer Vol)
    - TV Signal Bonus:    0–10 Punkte
 
    Max: 110 → normiert auf 100%
    """
 
    update_price(price)
 
    ema     = get_ema_signal()
    struct  = get_structure()
    sweep   = get_liquidity(price)
    vol     = get_volatility()
    news    = get_news_sentiment()
 
    score_breakdown = {}
    total = 0
    direction = None
 
    # --- EMA ALIGNMENT (30 Punkte) ---
    ema_pts = 0
    if ema["status"] == "BULLISH":
        ema_pts = 30
        direction = "LONG"
    elif ema["status"] == "BEARISH":
        ema_pts = 30
        direction = "SHORT"
    elif ema["status"] == "NEUTRAL":
        ema_pts = 10
    # Cross gibt Bonus
    if ema["cross"] == "BULLISH_CROSS":
        ema_pts = min(30, ema_pts + 5)
        direction = "LONG"
    elif ema["cross"] == "BEARISH_CROSS":
        ema_pts = min(30, ema_pts + 5)
        direction = "SHORT"
 
    score_breakdown["EMA"] = ema_pts
    total += ema_pts
 
    # --- MARKTSTRUKTUR (20 Punkte) ---
    struct_pts = 0
    if struct == "BULLISH" and direction == "LONG":
        struct_pts = 20
    elif struct == "BEARISH" and direction == "SHORT":
        struct_pts = 20
    elif struct == "RANGE":
        struct_pts = 5   # Range = weniger interessant
 
    score_breakdown["Struktur"] = struct_pts
    total += struct_pts
 
    # --- LIQUIDITÄT / SWEEP (25 Punkte) ---
    sweep_pts = 0
    if sweep == "BUY_SIDE_SWEEP" and direction == "SHORT":
        sweep_pts = 25   # Perfect: Sweep + Short = Smart Money Short
    elif sweep == "SELL_SIDE_SWEEP" and direction == "LONG":
        sweep_pts = 25   # Perfect: Sweep + Long = Smart Money Long
    elif sweep != "NONE":
        sweep_pts = 10   # Sweep vorhanden aber Richtung unklar
 
    score_breakdown["Liquiditaet"] = sweep_pts
    total += sweep_pts
 
    # --- NEWS SENTIMENT (15 Punkte, kann negativ sein) ---
    news_pts = 0
    if news["risk"] == "HIGH":
        news_pts = -15   # High-Impact Event → Risiko rauf, Score runter
    elif news["risk"] == "MEDIUM":
        news_pts = -5
    else:
        # Sentiment passt zur Richtung?
        if news.get("net", 0) > 0 and direction == "LONG":
            news_pts = 15
        elif news.get("net", 0) < 0 and direction == "SHORT":
            news_pts = 15
        elif news.get("net", 0) == 0:
            news_pts = 5   # neutral
 
    score_breakdown["News"] = news_pts
    total += news_pts
 
    # --- VOLATILITÄT (10 Punkte) ---
    vol_pts = 0
    if vol["level"] == "NORMAL":
        vol_pts = 10
    elif vol["level"] == "LOW":
        vol_pts = 5    # Zu wenig Bewegung = weniger Potenzial
    elif vol["level"] == "HIGH":
        vol_pts = -5   # Zu viel = gefährlich
 
    score_breakdown["Volatilitaet"] = vol_pts
    total += vol_pts
 
    # --- TRADINGVIEW SIGNAL BONUS (10 Punkte) ---
    tv_pts = 0
    tv_signal_lower = tv_signal.lower()
    if direction == "LONG" and ("buy" in tv_signal_lower or "long" in tv_signal_lower):
        tv_pts = 10
    elif direction == "SHORT" and ("sell" in tv_signal_lower or "short" in tv_signal_lower):
        tv_pts = 10
 
    score_breakdown["TradingView"] = tv_pts
    total += tv_pts
 
    # Normierung auf 0–100 (Max theoretisch 110)
    score_pct = max(0, min(100, round((total / 110) * 100)))
 
    return {
        "score": score_pct,
        "direction": direction,
        "breakdown": score_breakdown,
        "ema": ema,
        "structure": struct,
        "sweep": sweep,
        "volatility": vol,
        "news": news,
        "raw_total": total
    }
 
 
# =========================
# STOP LOSS & TAKE PROFIT
# =========================
def calc_sl_tp(price, direction, vol):
    atr_pct = vol.get("atr_pct", 0.2)
    atr_abs = price * (atr_pct / 100)
 
    sl_multiplier = 1.5   # SL = 1.5x ATR
    tp_multiplier = 2.5   # TP = 2.5x ATR → RRR 1:1.67
 
    if direction == "LONG":
        sl = round(price - atr_abs * sl_multiplier, 2)
        tp = round(price + atr_abs * tp_multiplier, 2)
    else:
        sl = round(price + atr_abs * sl_multiplier, 2)
        tp = round(price - atr_abs * tp_multiplier, 2)
 
    rrr = round(abs(tp - price) / abs(sl - price), 2)
    return {"sl": sl, "tp": tp, "rrr": rrr}
 
 
# =========================
# STATISTIKEN
# =========================
def get_stats():
    if not trade_log:
        return {"trades": 0, "winrate": "N/A", "avg_score": "N/A",
                "longs": 0, "shorts": 0, "blocked": 0}
 
    valid = [t for t in trade_log if t.get("direction") in ["LONG", "SHORT"]]
    blocked = [t for t in trade_log if t.get("direction") not in ["LONG", "SHORT"]]
    longs  = [t for t in valid if t.get("direction") == "LONG"]
    shorts = [t for t in valid if t.get("direction") == "SHORT"]
 
    scores = [t.get("score", 0) for t in valid]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
 
    return {
        "trades": len(valid),
        "avg_score": avg_score,
        "longs": len(longs),
        "shorts": len(shorts),
        "blocked": len(blocked)
    }
 
 
# =========================
# TELEGRAM NACHRICHT BAUEN
# =========================
def build_telegram_message(result, price, symbol, timestamp, sl_tp):
    score = result["score"]
    direction = result["direction"]
    bd = result["breakdown"]
    ema = result["ema"]
    news = result["news"]
 
    # Emoji je nach Score
    if score >= 90:
        grade = "🏆 A+"
    elif score >= 80:
        grade = "✅ A"
    else:
        grade = "⚠️ B"
 
    direction_emoji = "📈 LONG" if direction == "LONG" else "📉 SHORT"
 
    # Score-Balken
    filled = int(score / 10)
    bar = "█" * filled + "░" * (10 - filled)
 
    msg = f"""
🥇 <b>XAUUSD SIGNAL — {grade}</b>
 
{direction_emoji} | Score: <b>{score}%</b>
[{bar}]
 
💰 <b>Preis:</b> {price}
⏱ <b>Zeit:</b> {timestamp}
 
🎯 <b>Trade-Parameter</b>
  Stop-Loss:   {sl_tp['sl']}
  Take-Profit: {sl_tp['tp']}
  RRR:         1:{sl_tp['rrr']}
 
📊 <b>Score-Breakdown</b>
  EMA 20/50:   {bd.get('EMA', 0)}/30
  Struktur:    {bd.get('Struktur', 0)}/20
  Liquidität:  {bd.get('Liquiditaet', 0)}/25
  News:        {bd.get('News', 0)}/15
  Volatilität: {bd.get('Volatilitaet', 0)}/10
  TradingView: {bd.get('TradingView', 0)}/10
 
📈 <b>Marktanalyse</b>
  EMA 20:    {ema.get('ema20', 'N/A')}
  EMA 50:    {ema.get('ema50', 'N/A')}
  EMA Cross: {ema.get('cross', 'NONE')}
  Struktur:  {result['structure']}
  Sweep:     {result['sweep']}
  Vol-Level: {result['volatility']['level']}
 
📰 <b>News</b>
  Risiko: {news.get('risk', 'N/A')}
  Bull/Bear: {news.get('bull_score', 0)}/{news.get('bear_score', 0)}"""
 
    if news.get("headlines"):
        msg += f"\n  Top: {news['headlines'][0][:60]}"
 
    stats = get_stats()
    msg += f"""
 
📋 <b>Session-Stats</b>
  Trades: {stats['trades']} | Ø Score: {stats['avg_score']}%
  Longs: {stats['longs']} | Shorts: {stats['shorts']}
"""
    return msg
 
 
# =========================
# ROUTES
# =========================
@app.route("/status")
def status_route():
    bars = len(price_history)
    ema_ready = bars >= 52
    return jsonify({
        "price_bars": bars,
        "ema_ready": ema_ready,
        "ema_status": "✅ Bereit" if ema_ready else f"⏳ Warte auf {52 - bars} weitere Preispunkte",
        "min_score": f"{MIN_SCORE}%",
        "stats": get_stats()
    })
 
 
@app.route("/")
def home():
    stats = get_stats()
    return jsonify({
        "status": "XAUUSD BOT AKTIV",
        "min_score": f"{MIN_SCORE}%",
        "stats": stats,
        "price_bars": len(price_history)
    })
 
 
@app.route("/webhook", methods=["POST"])
def webhook():
    global last_signal_time, last_signal
 
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Keine Daten"}), 400
 
    price     = float(data.get("price", 0))
    symbol    = data.get("symbol", "XAUUSD")
    tv_signal = data.get("signal", "")
    timestamp = data.get("time", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
 
    if price <= 0:
        return jsonify({"error": "Ungültiger Preis"}), 400
 
    # Cooldown check
    now = time.time()
    if now - last_signal_time < COOLDOWN:
        remaining = int(COOLDOWN - (now - last_signal_time))
        return jsonify({"status": "cooldown", "remaining_seconds": remaining})
 
    # Score berechnen
    result = calculate_score(price, tv_signal)
    score  = result["score"]
    direction = result["direction"]
 
    # Trade loggen (auch blockierte)
    trade_entry = {
        "time": datetime.utcnow().isoformat(),
        "price": price,
        "score": score,
        "direction": direction,
        "breakdown": result["breakdown"]
    }
    trade_log.append(trade_entry)
    save_journal()
 
    # Score-Filter
    if score < MIN_SCORE:
        return jsonify({"status": "blocked", "score": score, "min": MIN_SCORE})
 
    # Duplikat-Check
    if direction == last_signal:
        return jsonify({"status": "duplicate_signal"})
 
    # SL/TP berechnen
    sl_tp = calc_sl_tp(price, direction, result["volatility"])
 
    # Telegram senden
    msg = build_telegram_message(result, price, symbol, timestamp, sl_tp)
    send_telegram(msg)
 
    last_signal = direction
    last_signal_time = now
 
    return jsonify({
        "status": "signal_sent",
        "direction": direction,
        "score": score,
        "sl": sl_tp["sl"],
        "tp": sl_tp["tp"],
        "rrr": sl_tp["rrr"]
    })
 
 
@app.route("/stats")
def stats_route():
    return jsonify(get_stats())
 
 
@app.route("/journal")
def journal_route():
    return jsonify(trade_log[-50:])   # Letzte 50 Trades
 
 
@app.route("/analysis")
def analysis_route():
    """Manuelle Analyse ohne Trade auszulösen"""
    price = float(request.args.get("price", 0))
    if price <= 0:
        return jsonify({"error": "?price=XXXX angeben"}), 400
    result = calculate_score(price)
    return jsonify(result)
 
 
@app.route("/test")
def test_route():
    send_telegram("🧪 <b>XAUUSD BOT ONLINE</b>\nAlle Systeme aktiv ✅")
    return jsonify({"status": "Telegram-Testnachricht gesendet"})
 
 
# =========================
# START
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"[BOT] XAUUSD Bot startet auf Port {port}")
    app.run(host="0.0.0.0", port=port)
