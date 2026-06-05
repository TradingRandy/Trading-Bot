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
MIN_SCORE   = 75     # Kein Signal unter 75%
COOLDOWN    = 300    # 5 Minuten zwischen Signalen
MAX_HISTORY = 300    # Preishistorie (brauchen mehr für MTF)
JOURNAL_FILE = "trade_journal.json"
 
# Trading Sessions (UTC)
LONDON_OPEN  = 7    # 07:00 UTC
LONDON_CLOSE = 16   # 16:00 UTC
NY_OPEN      = 13   # 13:00 UTC
NY_CLOSE     = 21   # 21:00 UTC
 
# =========================
# STATE
# =========================
price_history    = []   # 1m Kerzen
price_history_5m = []   # 5m Kerzen (für MTF)
trade_log        = []
open_trades      = []   # Offene Trades die noch SL/TP nicht erreicht haben
last_signal_time = 0
last_signal      = None
news_cache       = None   # Gecachte News
news_cache_time  = 0      # Zeitstempel des letzten News-Fetches
NEWS_CACHE_TTL   = 600    # News alle 10 Minuten updaten
 
 
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
            json.dump(trade_log[-500:], f)
    except:
        pass
 
load_journal()
 
 
# =========================
# HISTORISCHE DATEN LADEN (Yahoo Finance)
# =========================
def load_historical_prices():
    """Lädt 1m und 5m Kerzen von Yahoo Finance beim Start."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
 
        # 1m Daten (letzter Tag)
        url1 = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d"
        resp1 = requests.get(url1, headers=headers, timeout=10).json()
        closes1 = (
            resp1.get("chart", {})
                 .get("result", [{}])[0]
                 .get("indicators", {})
                 .get("quote", [{}])[0]
                 .get("close", [])
        )
        closes1 = [float(p) for p in closes1 if p is not None]
        for p in closes1[-300:]:
            price_history.append(p)
 
        # 5m Daten (letzte 5 Tage)
        url5 = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=5m&range=5d"
        resp5 = requests.get(url5, headers=headers, timeout=10).json()
        closes5 = (
            resp5.get("chart", {})
                 .get("result", [{}])[0]
                 .get("indicators", {})
                 .get("quote", [{}])[0]
                 .get("close", [])
        )
        closes5 = [float(p) for p in closes5 if p is not None]
        for p in closes5[-300:]:
            price_history_5m.append(p)
 
        print(f"[HISTORY] ✅ 1m: {len(price_history)} | 5m: {len(price_history_5m)} Punkte geladen")
 
    except Exception as e:
        print(f"[HISTORY] Fehler: {e}")
 
load_historical_prices()
 
 
# =========================
# TELEGRAM
# =========================
def send_telegram(msg):
    token   = os.environ.get("TELEGRAM_TOKEN")
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
 
    # 5m Kerze: jede 5. 1m-Kerze aggregieren
    if len(price_history) % 5 == 0:
        last5 = price_history[-5:]
        close5 = last5[-1]
        price_history_5m.append(close5)
        if len(price_history_5m) > MAX_HISTORY:
            price_history_5m.pop(0)
 
 
# =========================
# EMA BERECHNUNG
# =========================
def calc_ema(prices, period):
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 4)
 
def get_ema_signal(history=None):
    if history is None:
        history = price_history
    if len(history) < 52:
        return {"status": "INSUFFICIENT_DATA", "ema20": None, "ema50": None, "cross": "NONE"}
 
    ema20 = calc_ema(history, 20)
    ema50 = calc_ema(history, 50)
    price = history[-1]
 
    cross = "NONE"
    if len(history) >= 55:
        old20 = calc_ema(history[:-3], 20)
        old50 = calc_ema(history[:-3], 50)
        if old20 and old50:
            if old20 <= old50 and ema20 > ema50:
                cross = "BULLISH_CROSS"
            elif old20 >= old50 and ema20 < ema50:
                cross = "BEARISH_CROSS"
 
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
# RSI (14)
# =========================
def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = prices[-i] - prices[-i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs  = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)
 
def get_rsi_signal():
    rsi = calc_rsi(price_history, 14)
    if rsi is None:
        return {"rsi": None, "status": "INSUFFICIENT_DATA"}
 
    if rsi < 30:
        status = "OVERSOLD"       # Bullisch
    elif rsi > 70:
        status = "OVERBOUGHT"     # Bärisch
    elif rsi < 45:
        status = "BEARISH_ZONE"
    elif rsi > 55:
        status = "BULLISH_ZONE"
    else:
        status = "NEUTRAL"
 
    return {"rsi": rsi, "status": status}
 
 
# =========================
# MACD (12/26/9)
# =========================
def get_macd_signal():
    if len(price_history) < 35:
        return {"status": "INSUFFICIENT_DATA", "macd": None, "signal": None, "histogram": None}
 
    ema12 = calc_ema(price_history, 12)
    ema26 = calc_ema(price_history, 26)
    if not ema12 or not ema26:
        return {"status": "INSUFFICIENT_DATA", "macd": None, "signal": None, "histogram": None}
 
    macd_line = round(ema12 - ema26, 4)
 
    # Signal Line = EMA9 der letzten MACD-Werte
    macd_values = []
    for i in range(9, 0, -1):
        e12 = calc_ema(price_history[:-i] if i > 0 else price_history, 12)
        e26 = calc_ema(price_history[:-i] if i > 0 else price_history, 26)
        if e12 and e26:
            macd_values.append(e12 - e26)
 
    signal_line = round(sum(macd_values) / len(macd_values), 4) if macd_values else 0
    histogram   = round(macd_line - signal_line, 4)
 
    # Kreuzung erkennen
    if macd_line > signal_line and histogram > 0:
        status = "BULLISH"
    elif macd_line < signal_line and histogram < 0:
        status = "BEARISH"
    else:
        status = "NEUTRAL"
 
    # Momentum stärker?
    momentum = "INCREASING" if len(macd_values) >= 2 and abs(histogram) > abs(macd_values[-2] - signal_line) else "DECREASING"
 
    return {
        "status": status,
        "macd": macd_line,
        "signal_line": signal_line,
        "histogram": histogram,
        "momentum": momentum
    }
 
 
# =========================
# MULTI-TIMEFRAME (5m Bestätigung)
# =========================
def get_mtf_signal():
    if len(price_history_5m) < 52:
        return {"status": "INSUFFICIENT_DATA", "ema_5m": None}
 
    ema_5m = get_ema_signal(price_history_5m)
    rsi_5m_val = calc_rsi(price_history_5m, 14)
 
    return {
        "status": ema_5m["status"],
        "ema20_5m": ema_5m["ema20"],
        "ema50_5m": ema_5m["ema50"],
        "rsi_5m": rsi_5m_val,
        "cross_5m": ema_5m["cross"]
    }
 
 
# =========================
# MARKTSTRUKTUR
# =========================
def get_structure():
    if len(price_history) < 10:
        return "NEUTRAL"
    recent = price_history[-10:]
    highs = [recent[i] for i in range(1, len(recent)-1)
             if recent[i] > recent[i-1] and recent[i] > recent[i+1]]
    lows  = [recent[i] for i in range(1, len(recent)-1)
             if recent[i] < recent[i-1] and recent[i] < recent[i+1]]
    if len(highs) >= 2 and highs[-1] > highs[-2]:
        return "BULLISH"
    if len(lows) >= 2 and lows[-1] < lows[-2]:
        return "BEARISH"
    return "RANGE"
 
 
# =========================
# LIQUIDITÄT (Smart Money)
# =========================
def get_liquidity(price):
    if len(price_history) < 20:
        return "NONE"
    recent = price_history[-20:]
    high = max(recent[:-1])
    low  = min(recent[:-1])
    if price > high * 1.0005:
        return "BUY_SIDE_SWEEP"
    if price < low * 0.9995:
        return "SELL_SIDE_SWEEP"
    return "NONE"
 
 
# =========================
# VOLATILITÄT (ATR)
# =========================
def get_volatility():
    if len(price_history) < 14:
        return {"level": "NORMAL", "atr_pct": 0}
    ranges = [abs(price_history[-i] - price_history[-i-1]) for i in range(1, 14)]
    atr     = sum(ranges) / len(ranges)
    atr_pct = (atr / price_history[-1]) * 100
    level   = "HIGH" if atr_pct > 0.5 else ("LOW" if atr_pct < 0.1 else "NORMAL")
    return {"level": level, "atr_pct": round(atr_pct, 4)}
 
 
# =========================
# NEWS SENTIMENT (Finnhub)
# =========================
def get_news_sentiment():
    global news_cache, news_cache_time
 
    # Cache prüfen — nur alle 10 Minuten neu laden
    if news_cache and (time.time() - news_cache_time) < NEWS_CACHE_TTL:
        return news_cache
 
    api_key = os.environ.get("NEWS_API_KEY")
    if not api_key:
        return {"bull_score": 0, "bear_score": 0, "net": 0, "risk": "UNKNOWN", "headlines": []}
    try:
        url  = f"https://finnhub.io/api/v1/news?category=general&token={api_key}"
        data = requests.get(url, timeout=10).json()
 
        bullish_words  = ["rate cut", "fed dovish", "safe haven", "gold rally",
                          "gold climbs", "gold rises", "gold jumps", "gold gains",
                          "inflation", "dollar weak", "dollar slips", "dollar falls",
                          "risk off", "uncertainty", "recession", "geopolitic",
                          "war", "crisis", "ceasefire", "conflict", "attack",
                          "middle east", "iran", "hezbollah", "hostilities",
                          "yields fall", "bond yields fall", "haven demand",
                          "rate cut", "easing", "stimulus"]
        bearish_words  = ["rate hike", "fed hawkish", "dollar strong", "dollar rises",
                          "risk on", "gold slips", "gold falls", "gold drops",
                          "gold sell", "taper", "yields rise", "strong economy",
                          "peace deal", "iran deal", "ceasefire deal", "war ends",
                          "higher rates", "rate increase"]
        high_impact    = ["CPI", "NFP", "Fed", "interest rate", "FOMC", "Powell",
                          "GDP", "unemployment", "payroll", "BOJ", "ECB", "RBI",
                          "rate decision", "inflation data", "jobs report"]
 
        bull_score = bear_score = high_impact_count = 0
        relevant_headlines = []
 
        for n in data[:30]:
            headline    = n.get("headline", "").lower()
            original    = n.get("headline", "")
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
 
        risk = "HIGH" if high_impact_count >= 3 else ("MEDIUM" if high_impact_count >= 1 else "LOW")
 
        result = {
            "bull_score": bull_score,
            "bear_score": bear_score,
            "net": bull_score - bear_score,
            "risk": risk,
            "high_impact": high_impact_count,
            "headlines": relevant_headlines
        }
        # Cache speichern
        news_cache      = result
        news_cache_time = time.time()
        print(f"[NEWS] ✅ bull:{bull_score} bear:{bear_score} risk:{risk} headlines:{len(relevant_headlines)}")
        return result
    except Exception as e:
        print(f"[NEWS] Fehler: {e}")
        # Alten Cache zurückgeben falls vorhanden
        if news_cache:
            return news_cache
        return {"bull_score": 0, "bear_score": 0, "net": 0, "risk": "UNKNOWN", "headlines": []}
 
 
 
# =========================
# SESSION FILTER
# =========================
def get_session_status():
    """Prüft ob gerade London oder NY Session aktiv ist."""
    hour = datetime.utcnow().hour
 
    london_active = LONDON_OPEN <= hour < LONDON_CLOSE
    ny_active     = NY_OPEN <= hour < NY_CLOSE
    overlap       = NY_OPEN <= hour < LONDON_CLOSE  # 13:00-16:00 UTC = bestes Fenster
 
    if overlap:
        session = "OVERLAP (London+NY) 🔥"
    elif london_active:
        session = "LONDON 🇬🇧"
    elif ny_active:
        session = "NEW YORK 🇺🇸"
    else:
        session = "CLOSED 😴"
 
    active = london_active or ny_active
 
    return {
        "active":  active,
        "session": session,
        "hour_utc": hour,
        "overlap": overlap
    }
 
 
# =========================
# SCORE ENGINE (0–100%)
# =========================
def calculate_score(price, tv_signal=""):
    """
    Score-Breakdown:
    EMA 20/50:        0–25 Punkte
    RSI:              0–20 Punkte
    MACD:             0–20 Punkte
    Marktstruktur:    0–15 Punkte
    Liquidität/Sweep: 0–15 Punkte
    News Sentiment:   0–10 Punkte
    Volatilität:      0–10 Punkte
    Multi-Timeframe:  0–10 Punkte
    Max: 125 → normiert auf 100%
    """
    update_price(price)
 
    ema   = get_ema_signal()
    rsi   = get_rsi_signal()
    macd  = get_macd_signal()
    mtf   = get_mtf_signal()
    struct = get_structure()
    sweep  = get_liquidity(price)
    vol    = get_volatility()
    news   = get_news_sentiment()
 
    breakdown = {}
    total     = 0
    direction = None
 
    # --- EMA 20/50 (25 Punkte) ---
    ema_pts = 0
    if ema["status"] == "BULLISH":
        ema_pts = 25
        direction = "LONG"
    elif ema["status"] == "BEARISH":
        ema_pts = 25
        direction = "SHORT"
    elif ema["status"] == "NEUTRAL":
        ema_pts = 8
    if ema["cross"] == "BULLISH_CROSS":
        ema_pts = min(25, ema_pts + 5)
        direction = "LONG"
    elif ema["cross"] == "BEARISH_CROSS":
        ema_pts = min(25, ema_pts + 5)
        direction = "SHORT"
    breakdown["EMA"] = ema_pts
    total += ema_pts
 
    # --- RSI (20 Punkte) ---
    rsi_pts = 0
    if rsi["status"] != "INSUFFICIENT_DATA":
        if rsi["status"] == "OVERSOLD":
            rsi_pts = 20
            if not direction:
                direction = "LONG"
        elif rsi["status"] == "OVERBOUGHT":
            rsi_pts = 20
            if not direction:
                direction = "SHORT"
        elif rsi["status"] == "BULLISH_ZONE" and direction == "LONG":
            rsi_pts = 12
        elif rsi["status"] == "BEARISH_ZONE" and direction == "SHORT":
            rsi_pts = 12
        elif rsi["status"] == "NEUTRAL":
            rsi_pts = 5
        # Gegenläufig = Abzug
        if rsi["status"] == "OVERBOUGHT" and direction == "LONG":
            rsi_pts = -10
        elif rsi["status"] == "OVERSOLD" and direction == "SHORT":
            rsi_pts = -10
    breakdown["RSI"] = rsi_pts
    total += rsi_pts
 
    # --- MACD (20 Punkte) ---
    macd_pts = 0
    if macd["status"] != "INSUFFICIENT_DATA":
        if macd["status"] == "BULLISH" and direction == "LONG":
            macd_pts = 20
        elif macd["status"] == "BEARISH" and direction == "SHORT":
            macd_pts = 20
        elif macd["status"] == "NEUTRAL":
            macd_pts = 5
        elif macd["status"] == "BULLISH" and direction == "SHORT":
            macd_pts = -5   # Gegenläufig
        elif macd["status"] == "BEARISH" and direction == "LONG":
            macd_pts = -5
        # Momentum Bonus
        if macd.get("momentum") == "INCREASING" and macd_pts > 0:
            macd_pts = min(20, macd_pts + 3)
    breakdown["MACD"] = macd_pts
    total += macd_pts
 
    # --- MARKTSTRUKTUR (15 Punkte) ---
    struct_pts = 0
    if struct == "BULLISH" and direction == "LONG":
        struct_pts = 15
    elif struct == "BEARISH" and direction == "SHORT":
        struct_pts = 15
    elif struct == "RANGE":
        struct_pts = 3
    breakdown["Struktur"] = struct_pts
    total += struct_pts
 
    # --- LIQUIDITÄT / SWEEP (15 Punkte) ---
    sweep_pts = 0
    if sweep == "BUY_SIDE_SWEEP" and direction == "SHORT":
        sweep_pts = 15
    elif sweep == "SELL_SIDE_SWEEP" and direction == "LONG":
        sweep_pts = 15
    elif sweep != "NONE":
        sweep_pts = 7
    breakdown["Liquiditaet"] = sweep_pts
    total += sweep_pts
 
    # --- NEWS SENTIMENT (10 Punkte) ---
    news_pts = 0
    if news["risk"] == "HIGH":
        news_pts = -10
    elif news["risk"] == "MEDIUM":
        news_pts = -5
    else:
        if news.get("net", 0) > 0 and direction == "LONG":
            news_pts = 10
        elif news.get("net", 0) < 0 and direction == "SHORT":
            news_pts = 10
        else:
            news_pts = 3
    breakdown["News"] = news_pts
    total += news_pts
 
    # --- VOLATILITÄT (10 Punkte) ---
    vol_pts = 0
    if vol["level"] == "NORMAL":
        vol_pts = 10
    elif vol["level"] == "LOW":
        vol_pts = 4
    elif vol["level"] == "HIGH":
        vol_pts = -5
    breakdown["Volatilitaet"] = vol_pts
    total += vol_pts
 
    # --- MULTI-TIMEFRAME 5m (10 Punkte) ---
    mtf_pts = 0
    if mtf["status"] != "INSUFFICIENT_DATA":
        if mtf["status"] == "BULLISH" and direction == "LONG":
            mtf_pts = 10
        elif mtf["status"] == "BEARISH" and direction == "SHORT":
            mtf_pts = 10
        elif mtf["status"] == mtf["status"]:  # Gegenläufig
            if (mtf["status"] == "BULLISH" and direction == "SHORT") or \
               (mtf["status"] == "BEARISH" and direction == "LONG"):
                mtf_pts = -8
    breakdown["MTF_5m"] = mtf_pts
    total += mtf_pts
 
    # Normierung auf 0–100
    score_pct = max(0, min(100, round((total / 125) * 100)))
 
    return {
        "score": score_pct,
        "direction": direction,
        "breakdown": breakdown,
        "ema": ema,
        "rsi": rsi,
        "macd": macd,
        "mtf": mtf,
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
    sl_mult = 1.5
    tp_mult = 2.5
    if direction == "LONG":
        sl = round(price - atr_abs * sl_mult, 2)
        tp = round(price + atr_abs * tp_mult, 2)
    else:
        sl = round(price + atr_abs * sl_mult, 2)
        tp = round(price - atr_abs * tp_mult, 2)
    rrr = round(abs(tp - price) / abs(sl - price), 2)
    return {"sl": sl, "tp": tp, "rrr": rrr}
 
 
# =========================
# STATISTIKEN
# =========================
def get_stats():
    if not trade_log:
        return {"trades": 0, "avg_score": "N/A", "longs": 0, "shorts": 0, "blocked": 0}
    valid   = [t for t in trade_log if t.get("direction") in ["LONG", "SHORT"]]
    blocked = [t for t in trade_log if t.get("direction") not in ["LONG", "SHORT"]]
    longs   = [t for t in valid if t.get("direction") == "LONG"]
    shorts  = [t for t in valid if t.get("direction") == "SHORT"]
    scores  = [t.get("score", 0) for t in valid]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0
    wl = get_win_loss_stats() if trade_log else {}
    return {
        "trades":       len(valid),
        "avg_score":    avg_score,
        "longs":        len(longs),
        "shorts":       len(shorts),
        "blocked":      len(blocked),
        "open_trades":  len(open_trades),
        "winrate":      wl.get("winrate", "N/A"),
        "total_pnl":    wl.get("total_pnl", 0),
        "closed_trades": wl.get("closed_trades", 0)
    }
 
 
# =========================
# TELEGRAM NACHRICHT
# =========================
def build_telegram_message(result, price, symbol, timestamp, sl_tp):
    score     = result["score"]
    direction = result["direction"]
    bd        = result["breakdown"]
    ema       = result["ema"]
    rsi       = result["rsi"]
    macd      = result["macd"]
    mtf       = result["mtf"]
    news      = result["news"]
 
    session = get_session_status()
    grade = "🏆 A+" if score >= 90 else ("✅ A" if score >= 80 else "⚠️ B")
    direction_emoji = "📈 LONG" if direction == "LONG" else "📉 SHORT"
    filled = int(score / 10)
    bar    = "█" * filled + "░" * (10 - filled)
 
    # RSI Anzeige
    rsi_val = rsi.get("rsi", "N/A")
    rsi_status = rsi.get("status", "N/A")
 
    # MACD Anzeige
    macd_val  = macd.get("macd", "N/A")
    macd_status = macd.get("status", "N/A")
    macd_mom  = macd.get("momentum", "N/A")
 
    # MTF Anzeige
    mtf_status = mtf.get("status", "N/A")
    mtf_rsi    = mtf.get("rsi_5m", "N/A")
 
    msg = f"""
🥇 <b>XAUUSD SIGNAL — {grade}</b>
 
{direction_emoji} | Score: <b>{score}%</b>
[{bar}]
 
💰 <b>Preis:</b> {price}
⏱ <b>Zeit:</b> {timestamp}
🕐 <b>Session:</b> {session['session']}
 
🎯 <b>Trade-Parameter</b>
  Stop-Loss:   {sl_tp['sl']}
  Take-Profit: {sl_tp['tp']}
  RRR:         1:{sl_tp['rrr']}
 
📊 <b>Score-Breakdown</b>
  EMA 20/50:   {bd.get('EMA', 0)}/25
  RSI:         {bd.get('RSI', 0)}/20
  MACD:        {bd.get('MACD', 0)}/20
  Struktur:    {bd.get('Struktur', 0)}/15
  Liquidität:  {bd.get('Liquiditaet', 0)}/15
  News:        {bd.get('News', 0)}/10
  Volatilität: {bd.get('Volatilitaet', 0)}/10
  MTF (5m):    {bd.get('MTF_5m', 0)}/10
 
📈 <b>Indikatoren (1m)</b>
  EMA 20:  {ema.get('ema20', 'N/A')}
  EMA 50:  {ema.get('ema50', 'N/A')}
  EMA Cross: {ema.get('cross', 'NONE')}
  RSI 14:  {rsi_val} → {rsi_status}
  MACD:    {macd_val} → {macd_status} ({macd_mom})
 
🔭 <b>Multi-Timeframe (5m)</b>
  Trend:   {mtf_status}
  RSI 5m:  {mtf_rsi}
 
📰 <b>News</b>
  Risiko:    {news.get('risk', 'N/A')}
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
# AUTO WIN/LOSS TRACKING
# =========================
def check_open_trades(current_price):
    """
    Prüft bei jedem neuen Preis ob offene Trades
    ihren SL oder TP erreicht haben.
    """
    global open_trades
 
    closed = []
    still_open = []
 
    for trade in open_trades:
        direction = trade["direction"]
        sl        = trade["sl"]
        tp        = trade["tp"]
        entry     = trade["entry_price"]
        result    = None
 
        if direction == "LONG":
            if current_price >= tp:
                result = "WIN"
            elif current_price <= sl:
                result = "LOSS"
        elif direction == "SHORT":
            if current_price <= tp:
                result = "WIN"
            elif current_price >= sl:
                result = "LOSS"
 
        if result:
            pnl = abs(tp - entry) if result == "WIN" else -abs(sl - entry)
            trade["result"]      = result
            trade["close_price"] = current_price
            trade["close_time"]  = datetime.utcnow().isoformat()
            trade["pnl"]         = round(pnl, 2)
            closed.append(trade)
 
            # Telegram Benachrichtigung
            emoji = "✅" if result == "WIN" else "❌"
            send_telegram(
                f"{emoji} <b>TRADE GESCHLOSSEN — {result}</b>\n\n"
                f"Richtung:    {direction}\n"
                f"Entry:       {entry}\n"
                f"Close:       {current_price}\n"
                f"PnL (Punkte): {'+' if pnl > 0 else ''}{pnl}\n\n"
                f"Score war:   {trade.get('score', 'N/A')}%\n"
                f"Session:     {trade.get('session', 'N/A')}\n"
                f"Eröffnet:    {trade.get('open_time', 'N/A')}"
            )
 
            # Im Journal aktualisieren
            for t in trade_log:
                if t.get("time") == trade.get("open_time"):
                    t["result"]      = result
                    t["close_price"] = current_price
                    t["pnl"]         = round(pnl, 2)
            save_journal()
        else:
            still_open.append(trade)
 
    open_trades = still_open
 
    if closed:
        print(f"[TRACKING] {len(closed)} Trade(s) geschlossen")
 
 
def get_win_loss_stats():
    """Berechnet echte Winrate aus abgeschlossenen Trades."""
    closed = [t for t in trade_log if t.get("result") in ["WIN", "LOSS"]]
    if not closed:
        return {"closed_trades": 0, "wins": 0, "losses": 0, "winrate": "N/A", "total_pnl": 0}
 
    wins   = [t for t in closed if t["result"] == "WIN"]
    losses = [t for t in closed if t["result"] == "LOSS"]
    total_pnl = round(sum(t.get("pnl", 0) for t in closed), 2)
    winrate   = round(len(wins) / len(closed) * 100, 1)
 
    return {
        "closed_trades": len(closed),
        "wins":          len(wins),
        "losses":        len(losses),
        "winrate":       f"{winrate}%",
        "total_pnl":     total_pnl,
        "avg_win":       round(sum(t.get("pnl",0) for t in wins)   / len(wins),   2) if wins   else 0,
        "avg_loss":      round(sum(t.get("pnl",0) for t in losses) / len(losses), 2) if losses else 0
    }
 
 
# =========================
# STARTUP NEWS PRELOAD
# =========================
print("[STARTUP] Lade News beim Start...")
_startup_news = get_news_sentiment()
print(f"[STARTUP] News: bull={_startup_news.get('bull_score',0)} bear={_startup_news.get('bear_score',0)} risk={_startup_news.get('risk','?')}")
 
# =========================
# ROUTES
# =========================
@app.route("/status")
def status_route():
    bars    = len(price_history)
    bars_5m = len(price_history_5m)
    session = get_session_status()
    return jsonify({
        "price_bars_1m": bars,
        "price_bars_5m": bars_5m,
        "ema_ready":     bars >= 52,
        "mtf_ready":     bars_5m >= 52,
        "ema_status":    "✅ Bereit" if bars >= 52 else f"⏳ Warte auf {52 - bars} Punkte",
        "mtf_status":    "✅ Bereit" if bars_5m >= 52 else f"⏳ Warte auf {52 - bars_5m} Punkte",
        "min_score":     f"{MIN_SCORE}%",
        "session":       session,
        "stats":         get_stats()
    })
 
 
@app.route("/")
def home():
    return jsonify({
        "status":     "XAUUSD BOT AKTIV",
        "min_score":  f"{MIN_SCORE}%",
        "stats":      get_stats(),
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
 
    # Session Filter
    session = get_session_status()
    if not session["active"]:
        return jsonify({
            "status":  "outside_session",
            "session": session["session"],
            "message": "Kein Trading ausserhalb London/NY Session"
        })
 
    now = time.time()
    if now - last_signal_time < COOLDOWN:
        remaining = int(COOLDOWN - (now - last_signal_time))
        return jsonify({"status": "cooldown", "remaining_seconds": remaining})
 
    # Offene Trades prüfen bei jedem neuen Preis
    check_open_trades(price)
 
    result    = calculate_score(price, tv_signal)
    score     = result["score"]
    direction = result["direction"]
 
    trade_log.append({
        "time":      datetime.utcnow().isoformat(),
        "price":     price,
        "score":     score,
        "direction": direction,
        "breakdown": result["breakdown"]
    })
    save_journal()
 
    if score < MIN_SCORE:
        return jsonify({"status": "blocked", "score": score, "min": MIN_SCORE})
 
    if direction == last_signal:
        return jsonify({"status": "duplicate_signal"})
 
    sl_tp = calc_sl_tp(price, direction, result["volatility"])
    msg   = build_telegram_message(result, price, symbol, timestamp, sl_tp)
    send_telegram(msg)
 
    last_signal      = direction
    last_signal_time = now
 
    # Trade zu open_trades hinzufügen für automatisches Tracking
    open_trades.append({
        "open_time":    datetime.utcnow().isoformat(),
        "entry_price":  price,
        "direction":    direction,
        "sl":           sl_tp["sl"],
        "tp":           sl_tp["tp"],
        "score":        score,
        "session":      get_session_status()["session"]
    })
 
    return jsonify({
        "status":    "signal_sent",
        "direction": direction,
        "score":     score,
        "sl":        sl_tp["sl"],
        "tp":        sl_tp["tp"],
        "rrr":       sl_tp["rrr"]
    })
 
 
@app.route("/stats")
def stats_route():
    return jsonify(get_stats())
 
 
@app.route("/winrate")
def winrate_route():
    wl = get_win_loss_stats()
    open_list = [{
        "direction":   t["direction"],
        "entry":       t["entry_price"],
        "sl":          t["sl"],
        "tp":          t["tp"],
        "score":       t["score"],
        "open_time":   t["open_time"]
    } for t in open_trades]
    return jsonify({
        "stats":       wl,
        "open_trades": open_list
    })
 
 
@app.route("/journal")
def journal_route():
    return jsonify(trade_log[-50:])
 
 
@app.route("/analysis")
def analysis_route():
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
