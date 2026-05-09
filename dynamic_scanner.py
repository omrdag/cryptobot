"""
Dynamic Coin Scanner
====================
Her döngüde OKX'teki top 20 USDT perpetual coini hacme göre sıralar,
her birine momentum + trend + volatilite puanı verir,
en yüksek skorlu 2 coini döndürür.

Kullanım:
    from dynamic_scanner import get_best_coins
    coins = get_best_coins()  # ["BTC-USDT-SWAP", "SOL-USDT-SWAP"]
"""

import urllib.request, json, time, logging
from typing import List, Dict, Optional
import pandas as pd

log = logging.getLogger("dynamic_scanner")
logging.basicConfig(level=logging.INFO)

# Railway'de görünmesi için print-based log
def _slog(msg: str):
    """Scanner log — Railway stdout'a yazar."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"cryptobot: [{ts}] {msg}", flush=True)
    log.info(msg)

# ── Sabitler ──────────────────────────────────────────────────────────────────
# Bu coinler her zaman taranır (likit, güvenilir)
ALWAYS_SCAN = [
    "BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP",
    "BNB-USDT-SWAP", "XRP-USDT-SWAP", "DOGE-USDT-SWAP",
]

# Bu coinler hariç tutulur (çok düşük likidite veya manipülasyon riski)
BLACKLIST = {
    "SHIB-USDT-SWAP", "PEPE-USDT-SWAP", "FLOKI-USDT-SWAP",
    "BOME-USDT-SWAP", "WIF-USDT-SWAP",
}

# Minimum 24s hacim filtresi (USDT)
MIN_VOLUME_USDT = 50_000_000   # $50M+

# Kaç coin seçilsin
TOP_N = 2

# Cache — aynı döngüde tekrar çekme
_cache: Dict = {"coins": [], "ts": 0, "scores": {}}
CACHE_SECONDS = 55  # 55 saniye geçerli


def _fetch(url: str, timeout: int = 5) -> dict:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/3.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        _slog(f"[SCANNER] ⚠️ fetch hatası: {e}")
        return {}


def get_top_coins_by_volume(limit: int = 30) -> List[str]:
    """OKX'teki en yüksek hacimli USDT perpetual coinleri döndür."""
    data = _fetch("https://www.okx.com/api/v5/market/tickers?instType=SWAP")
    tickers = data.get("data", [])
    if not tickers:
        return ALWAYS_SCAN

    # USDT swap, kara listede değil, min hacim
    filtered = []
    for t in tickers:
        inst = t.get("instId", "")
        if not inst.endswith("-USDT-SWAP"):
            continue
        if inst in BLACKLIST:
            continue
        vol = float(t.get("volCcy24h") or t.get("vol24h") or 0)
        last = float(t.get("last") or 0)
        vol_usdt = vol * last if last > 0 else vol
        if vol_usdt < MIN_VOLUME_USDT:
            continue
        filtered.append((inst, vol_usdt))

    # Hacme göre sırala, en fazla `limit` tane al
    filtered.sort(key=lambda x: x[1], reverse=True)
    result = [x[0] for x in filtered[:limit]]

    # ALWAYS_SCAN coinleri ekle (zaten listede değilse)
    for c in ALWAYS_SCAN:
        if c not in result:
            result.insert(0, c)

    return result[:limit]


def fetch_ohlcv_simple(inst_id: str, bar: str = "15m", limit: int = 60) -> Optional[pd.DataFrame]:
    """Basit OHLCV çekimi."""
    url = f"https://www.okx.com/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
    data = _fetch(url)
    candles = data.get("data", [])
    if len(candles) < 20:
        return None
    try:
        df = pd.DataFrame(candles, columns=["ts","open","high","low","close","vol","volCcy","volCcyQuote","confirm"])
        df = df[["ts","open","high","low","close","vol"]].copy()
        df.columns = ["timestamp","open","high","low","close","volume"]
        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col])
        return df.iloc[::-1].reset_index(drop=True)
    except:
        return None


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    try:
        prev = df["close"].shift(1)
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev).abs(),
            (df["low"]  - prev).abs(),
        ], axis=1).max(axis=1)
        return float(tr.ewm(span=period, adjust=False).mean().iloc[-1])
    except:
        return 0.0


def _rsi(df: pd.DataFrame, period: int = 14) -> float:
    try:
        delta = df["close"].diff()
        gain  = delta.where(delta > 0, 0).ewm(span=period, adjust=False).mean()
        loss  = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)
        return float(100 - (100 / (1 + rs.iloc[-1])))
    except:
        return 50.0


def score_coin(inst_id: str) -> Dict:
    """
    Bir coini 10 üzerinden puanla.
    Yüksek puan = güçlü trend + iyi momentum + düşük aşırı alım.
    """
    df = fetch_ohlcv_simple(inst_id, bar="15m", limit=80)
    if df is None or len(df) < 30:
        return {"inst_id": inst_id, "score": 0, "reason": "veri yok"}

    score = 0
    notes = []
    close = float(df["close"].iloc[-1])

    # 1. Supertrend yönü (15m) ─ +2 puan
    try:
        hl2 = (df["high"] + df["low"]) / 2
        atr_s = _atr(df, 10)
        upper = hl2 + 3.0 * atr_s
        lower = hl2 - 3.0 * atr_s
        st = lower.iloc[-1]  # basit yaklaşım
        if close > st:
            score += 2
            notes.append("ST↑")
        else:
            notes.append("ST↓")
    except:
        pass

    # 2. EMA trend hizası (9>21>50) ─ +2 puan
    ema9  = float(_ema(df["close"], 9).iloc[-1])
    ema21 = float(_ema(df["close"], 21).iloc[-1])
    ema50 = float(_ema(df["close"], 50).iloc[-1])
    if ema9 > ema21 > ema50:
        score += 2
        notes.append("EMA↑↑")
    elif ema9 > ema21:
        score += 1
        notes.append("EMA↑")
    else:
        notes.append("EMA↓")

    # 3. MACD histogram pozitif ve artıyor ─ +2 puan
    try:
        macd_line   = _ema(df["close"], 12) - _ema(df["close"], 26)
        signal_line = _ema(macd_line, 9)
        hist        = macd_line - signal_line
        h_now  = float(hist.iloc[-1])
        h_prev = float(hist.iloc[-2])
        if h_now > 0 and h_now > h_prev:
            score += 2
            notes.append("MACD↑")
        elif h_now > 0:
            score += 1
            notes.append("MACD+")
        else:
            notes.append("MACD↓")
    except:
        pass

    # 4. RSI ideal bölge 40-65 ─ +2 puan
    rsi_val = _rsi(df)
    if 40 <= rsi_val <= 65:
        score += 2
        notes.append(f"RSI={rsi_val:.0f}✓")
    elif 35 <= rsi_val < 40 or 65 < rsi_val <= 72:
        score += 1
        notes.append(f"RSI={rsi_val:.0f}~")
    else:
        notes.append(f"RSI={rsi_val:.0f}✗")

    # 5. Hacim spike (son bar > MA20 × 1.3) ─ +1 puan
    if len(df) >= 21:
        vol_ma = float(df["volume"].rolling(20).mean().iloc[-1])
        vol_now = float(df["volume"].iloc[-1])
        if vol_now > vol_ma * 1.3:
            score += 1
            notes.append("VOL↑")

    # 6. Fiyat EMA21 üzerinde (trend desteği) ─ +1 puan
    if close > ema21:
        score += 1
        notes.append("P>EMA21")

    return {
        "inst_id": inst_id,
        "score":   score,
        "max":     10,
        "close":   close,
        "rsi":     round(rsi_val, 1),
        "ema9":    round(ema9, 4),
        "ema21":   round(ema21, 4),
        "reason":  " | ".join(notes),
    }


def get_best_coins(top_n: int = TOP_N, min_score: int = 4) -> List[str]:
    """
    OKX'teki en iyi N coini döndür.
    Cache geçerliyse tekrar taramaz.
    """
    now = time.time()
    if now - _cache["ts"] < CACHE_SECONDS and _cache["coins"]:
        return _cache["coins"]

    log.info("[SCANNER] Coin taraması başlatılıyor...")

    # Top coinleri hacme göre al
    candidates = get_top_coins_by_volume(limit=20)
    _slog(f"[SCANNER] {len(candidates)} aday coin taranıyor...")

    # Her birini puanla
    scored = []
    for inst_id in candidates:
        try:
            result = score_coin(inst_id)
            scored.append(result)
            _slog(f"[SCANNER] {inst_id.replace('-USDT-SWAP','')}: {result['score']}/{result['max']} — {result['reason']}")
            time.sleep(0.1)  # rate limit
        except Exception as e:
            _slog(f"[SCANNER] ⚠️ {inst_id} hata: {e}")

    # Min skor filtresi + sırala
    qualified = [s for s in scored if s["score"] >= min_score]
    qualified.sort(key=lambda x: x["score"], reverse=True)

    # En iyi N'i seç
    best = [s["inst_id"] for s in qualified[:top_n]]

    # Hiç qualify olmadıysa fallback
    if not best:
        _slog("[SCANNER] ⚠️ Qualify olan coin yok → BTC+SOL fallback")
        best = ["BTC-USDT-SWAP", "SOL-USDT-SWAP"]

    _slog(f"[SCANNER] ✅ Seçilen coinler: {[c.replace('-USDT-SWAP','') for c in best]}")
    _slog(f"[SCANNER] 🏆 Top 5: {[(s['inst_id'].replace('-USDT-SWAP',''), s['score']) for s in qualified[:5]]}")

    # Cache güncelle
    _cache["coins"] = best
    _cache["ts"]    = now
    _cache["scores"] = {s["inst_id"]: s for s in scored}

    return best


def get_scanner_scores() -> Dict:
    """Dashboard için en son tarama sonuçlarını döndür."""
    return _cache.get("scores", {})


def get_last_scan_time() -> float:
    return _cache.get("ts", 0)
