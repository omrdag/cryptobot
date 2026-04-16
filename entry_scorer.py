"""
Entry Scorer — Çok Zaman Dilimli Giriş Kalitesi Motoru
========================================================
Mevcut sisteme modüler onay katmanı olarak eklenir.
bot_engine.py'daki place_order çağrısından önce devreye girer.

Çalışma prensibi:
  - Mevcut PullbackLong/Short stratejisi sinyal üretmeye devam eder
  - Bu modül sadece "bu girişi onaylıyor muyuz?" sorusunu yanıtlar
  - approve() → True  → emir gönderilir
  - approve() → False → emir gönderilmez, log üretilir

Skor Bileşenleri (max 16 puan):
  Trend uygunluğu    : 0-3
  Momentum yönü      : 0-3
  Hacim desteği      : 0-2
  Volatilite         : 0-2
  Order book         : 0-2
  Derivatives        : 0-1
  Risk uygunluğu     : 0-3

Railway Variables (opsiyonel, varsayılanlar güvenli):
  SCORER_ENABLED          = true
  SCORER_MIN_LONG_TREND   = 9   (TREND_UP rejiminde)
  SCORER_MIN_SHORT_TREND  = 9   (TREND_DOWN rejiminde)
  SCORER_MIN_SIDEWAYS     = 10
  SCORER_MIN_HIGH_VOL     = 12
  SCORER_ANTI_CHASE_ATR   = 1.5 (son 3 mumda bu ATR katı aşılırsa bekle)
  SCORER_LOG_VERBOSE      = false
"""

import os
import time
import logging
import urllib.request
import json
from typing import Optional, Tuple
from datetime import datetime, timezone

import pandas as pd
import numpy as np

log = logging.getLogger("entry_scorer")

# ── Konfigürasyon ─────────────────────────────────────────────────────────────
SCORER_ENABLED        = os.getenv("SCORER_ENABLED", "true").lower() == "true"
SCORER_LOG_VERBOSE    = os.getenv("SCORER_LOG_VERBOSE", "false").lower() == "true"
SCORER_ANTI_CHASE_ATR = float(os.getenv("SCORER_ANTI_CHASE_ATR", "1.5"))

# Rejime göre minimum skor eşikleri
SCORER_THRESHOLDS = {
    "TREND_UP":        {"long": int(os.getenv("SCORER_MIN_LONG_TREND",  "9")),  "short": int(os.getenv("SCORER_MIN_SHORT_TREND", "12"))},
    "TREND_DOWN":      {"long": int(os.getenv("SCORER_MIN_LONG_TREND",  "12")), "short": int(os.getenv("SCORER_MIN_SHORT_TREND", "9"))},
    "SIDEWAYS":        {"long": int(os.getenv("SCORER_MIN_SIDEWAYS",    "10")), "short": int(os.getenv("SCORER_MIN_SIDEWAYS",    "10"))},
    "HIGH_VOLATILITY": {"long": int(os.getenv("SCORER_MIN_HIGH_VOL",   "12")), "short": int(os.getenv("SCORER_MIN_HIGH_VOL",   "12"))},
    "LOW_LIQUIDITY":   {"long": 99,  "short": 99},   # Hiç işlem açma
    "RANGE":           {"long": int(os.getenv("SCORER_MIN_SIDEWAYS",    "10")), "short": int(os.getenv("SCORER_MIN_SIDEWAYS",    "10"))},
    "RANGING":         {"long": int(os.getenv("SCORER_MIN_SIDEWAYS",    "10")), "short": int(os.getenv("SCORER_MIN_SIDEWAYS",    "10"))},
    "NO_TRADE":        {"long": 99,  "short": 99},
}
SCORER_DEFAULT_THRESHOLD = {"long": 10, "short": 10}

# ── OKX Veri Çekme ────────────────────────────────────────────────────────────

def _okx_public(path: str, timeout: int = 4) -> dict:
    """İmzasız OKX public endpoint."""
    try:
        req = urllib.request.Request(
            "https://www.okx.com" + path,
            headers={"User-Agent": "CryptoBot/3.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        log.debug(f"OKX public hata {path}: {e}")
        return {}


def _fetch_ohlcv(inst_id: str, bar: str, limit: int) -> Optional[pd.DataFrame]:
    """OHLCV mum verisi — entry_scorer bağımsız çeker."""
    try:
        data    = _okx_public(f"/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}")
        candles = data.get("data", [])
        if not candles:
            return None
        df = pd.DataFrame(candles, columns=["ts","open","high","low","close","vol","volCcy","volCcyQuote","confirm"])
        df = df[["ts","open","high","low","close","vol"]].copy()
        df.columns = ["timestamp","open","high","low","close","volume"]
        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col])
        df = df.iloc[::-1].reset_index(drop=True)
        return df
    except Exception as e:
        log.debug(f"OHLCV hata {inst_id} {bar}: {e}")
        return None


def _fetch_orderbook(inst_id: str) -> dict:
    """Order book — ilk 5 seviye."""
    try:
        data = _okx_public(f"/api/v5/market/books?instId={inst_id}&sz=5")
        raw  = data.get("data", [{}])[0]
        bids = [[float(x[0]), float(x[1])] for x in raw.get("bids", [])[:5]]
        asks = [[float(x[0]), float(x[1])] for x in raw.get("asks", [])[:5]]
        return {"bids": bids, "asks": asks}
    except:
        return {"bids": [], "asks": []}


def _fetch_funding(inst_id: str) -> float:
    """Funding rate."""
    try:
        data = _okx_public(f"/api/v5/public/funding-rate?instId={inst_id}")
        return float(data.get("data", [{}])[0].get("fundingRate", 0) or 0)
    except:
        return 0.0


def _fetch_open_interest(inst_id: str) -> float:
    """Open interest (USDT)."""
    try:
        data = _okx_public(f"/api/v5/public/open-interest?instId={inst_id}")
        return float(data.get("data", [{}])[0].get("oiCcy", 0) or 0)
    except:
        return 0.0


# ── Teknik İndikatörler ───────────────────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> float:
    try:
        delta = close.diff()
        gain  = delta.where(delta > 0, 0).ewm(span=period, adjust=False).mean()
        loss  = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)
        return float(100 - (100 / (1 + rs.iloc[-1])))
    except:
        return 50.0


def _macd_histogram(close: pd.Series) -> float:
    try:
        fast   = close.ewm(span=12, adjust=False).mean()
        slow   = close.ewm(span=26, adjust=False).mean()
        macd   = fast - slow
        signal = macd.ewm(span=9, adjust=False).mean()
        return float((macd - signal).iloc[-1])
    except:
        return 0.0


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    try:
        prev = df["close"].shift(1)
        tr   = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev).abs(),
            (df["low"]  - prev).abs(),
        ], axis=1).max(axis=1)
        return float(tr.ewm(span=period, adjust=False).mean().iloc[-1])
    except:
        return 0.0


def _vwap(df: pd.DataFrame) -> float:
    try:
        typical = (df["high"] + df["low"] + df["close"]) / 3
        vwap    = (typical * df["volume"]).cumsum() / df["volume"].cumsum()
        return float(vwap.iloc[-1])
    except:
        return float(df["close"].iloc[-1])


def _stoch_rsi(close: pd.Series, period: int = 14) -> Tuple[float, float]:
    """Stochastic RSI — (k, d)."""
    try:
        delta = close.diff()
        gain  = delta.where(delta > 0, 0).ewm(span=period, adjust=False).mean()
        loss  = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)
        rsi   = 100 - (100 / (1 + rs))
        min_r = rsi.rolling(period).min()
        max_r = rsi.rolling(period).max()
        k     = 100 * (rsi - min_r) / (max_r - min_r + 1e-10)
        d     = k.rolling(3).mean()
        return float(k.iloc[-1]), float(d.iloc[-1])
    except:
        return 50.0, 50.0


def _higher_high_lower_low(df: pd.DataFrame, lookback: int = 5) -> dict:
    """Son N mumda HH/HL veya LH/LL yapısı."""
    try:
        highs = df["high"].iloc[-lookback:].values
        lows  = df["low"].iloc[-lookback:].values
        hh = bool(highs[-1] > highs[-2] and highs[-2] > highs[-3]) if len(highs) >= 3 else False
        hl = bool(lows[-1]  > lows[-2]  and lows[-2]  > lows[-3])  if len(lows)  >= 3 else False
        lh = bool(highs[-1] < highs[-2] and highs[-2] < highs[-3]) if len(highs) >= 3 else False
        ll = bool(lows[-1]  < lows[-2]  and lows[-2]  < lows[-3])  if len(lows)  >= 3 else False
        return {"hh": hh, "hl": hl, "lh": lh, "ll": ll}
    except:
        return {"hh": False, "hl": False, "lh": False, "ll": False}


def _body_strength(df: pd.DataFrame, n: int = 3) -> float:
    """Son N mumun ortalama gövde gücü — pozitif = alıcı, negatif = satıcı."""
    try:
        last = df.iloc[-n:]
        bodies = (last["close"] - last["open"]) / (last["high"] - last["low"] + 1e-10)
        return float(bodies.mean())
    except:
        return 0.0


def _relative_volume(df: pd.DataFrame, n: int = 20) -> float:
    """Son mum hacmi / n mum ortalaması."""
    try:
        avg = df["volume"].iloc[-n-1:-1].mean()
        cur = df["volume"].iloc[-1]
        return float(cur / avg) if avg > 0 else 1.0
    except:
        return 1.0


def _volume_trend(df: pd.DataFrame, n: int = 5) -> dict:
    """Son N mumda yükseliş vs düşüş hacmi."""
    try:
        last     = df.iloc[-n:]
        up_vol   = last[last["close"] >= last["open"]]["volume"].sum()
        down_vol = last[last["close"] <  last["open"]]["volume"].sum()
        total    = up_vol + down_vol + 1e-10
        return {"up_ratio": float(up_vol / total), "down_ratio": float(down_vol / total)}
    except:
        return {"up_ratio": 0.5, "down_ratio": 0.5}


def _spread_pct(ob: dict) -> float:
    """Bid/ask spread yüzdesi."""
    try:
        best_bid = ob["bids"][0][0] if ob["bids"] else 0
        best_ask = ob["asks"][0][0] if ob["asks"] else 0
        mid      = (best_bid + best_ask) / 2
        return float((best_ask - best_bid) / mid * 100) if mid > 0 else 999.0
    except:
        return 999.0


def _ob_imbalance(ob: dict) -> float:
    """
    Order book imbalance.
    > 0 → bid ağır (alıcı baskısı)
    < 0 → ask ağır (satıcı baskısı)
    """
    try:
        bid_vol = sum(x[1] for x in ob["bids"])
        ask_vol = sum(x[1] for x in ob["asks"])
        total   = bid_vol + ask_vol + 1e-10
        return float((bid_vol - ask_vol) / total)
    except:
        return 0.0


def _anti_chase(df: pd.DataFrame, atr_val: float, side: str, mult: float = 1.5) -> bool:
    """
    Son 3 mumda aşırı hızlı hareket var mı?
    True → chase riski var, girme
    """
    try:
        if atr_val <= 0:
            return False
        last3      = df.iloc[-3:]
        total_move = abs(float(last3["close"].iloc[-1]) - float(last3["open"].iloc[0]))
        if total_move > atr_val * mult:
            if side == "long" and float(last3["close"].iloc[-1]) > float(last3["open"].iloc[0]):
                return True   # Yukarı chase
            if side == "short" and float(last3["close"].iloc[-1]) < float(last3["open"].iloc[0]):
                return True   # Aşağı chase
        return False
    except:
        return False


def _breakout_mode(df: pd.DataFrame, atr_val: float, rel_vol: float, ob: dict, side: str) -> bool:
    """
    Breakout koşulları — chase filtresi bypass edilir.
    """
    try:
        vol_ok    = rel_vol >= 1.5
        spread_ok = _spread_pct(ob) < 0.1
        last      = df.iloc[-1]
        body_pct  = abs(float(last["close"]) - float(last["open"])) / (float(last["high"]) - float(last["low"]) + 1e-10)
        body_ok   = body_pct > 0.6   # Net kapanış
        ob_imb    = _ob_imbalance(ob)
        ob_ok     = (ob_imb > 0.1 if side == "long" else ob_imb < -0.1)
        return vol_ok and spread_ok and body_ok and ob_ok
    except:
        return False


# ── Skor Hesaplama ────────────────────────────────────────────────────────────

class ScoreResult:
    def __init__(self):
        self.total         = 0
        self.trend         = 0   # 0-3
        self.momentum      = 0   # 0-3
        self.volume        = 0   # 0-2
        self.volatility    = 0   # 0-2
        self.orderbook     = 0   # 0-2
        self.derivatives   = 0   # 0-1
        self.risk          = 0   # 0-3
        self.entry_mode    = "no_trade"
        self.reject_reason = ""
        self.details       = {}

    def compute_total(self):
        self.total = (self.trend + self.momentum + self.volume +
                      self.volatility + self.orderbook + self.derivatives + self.risk)
        return self.total


def _score_trend(df_1h: Optional[pd.DataFrame], df_15m: Optional[pd.DataFrame],
                 df_5m: Optional[pd.DataFrame], side: str) -> Tuple[int, dict]:
    """Trend skoru 0-3."""
    score   = 0
    details = {}

    if df_5m is None or len(df_5m) < 21:
        return 1, {"trend": "veri_yok"}

    close_5m  = df_5m["close"]
    ema9_5m   = float(_ema(close_5m, 9).iloc[-1])
    ema20_5m  = float(_ema(close_5m, 20).iloc[-1])
    ema50_5m  = float(_ema(close_5m, 50).iloc[-1]) if len(df_5m) >= 51 else ema20_5m
    vwap_5m   = _vwap(df_5m)
    cur_5m    = float(close_5m.iloc[-1])
    struct_5m = _higher_high_lower_low(df_5m)

    details.update({
        "ema9_5m":  round(ema9_5m,  4),
        "ema20_5m": round(ema20_5m, 4),
        "ema50_5m": round(ema50_5m, 4),
        "vwap_5m":  round(vwap_5m,  4),
        "cur_5m":   round(cur_5m,   4),
    })

    if side == "long":
        # EMA hizalaması
        if ema9_5m > ema20_5m:
            score += 1
        # VWAP üstünde
        if cur_5m > vwap_5m:
            score += 1
        # HH/HL yapısı
        if struct_5m["hh"] or struct_5m["hl"]:
            score += 1
    else:
        if ema9_5m < ema20_5m:
            score += 1
        if cur_5m < vwap_5m:
            score += 1
        if struct_5m["lh"] or struct_5m["ll"]:
            score += 1

    # 1H onayı (varsa +bonus, ama üst sınır 3)
    if df_1h is not None and len(df_1h) >= 21:
        close_1h = df_1h["close"]
        ema20_1h = float(_ema(close_1h, 20).iloc[-1])
        cur_1h   = float(close_1h.iloc[-1])
        details["ema20_1h"] = round(ema20_1h, 4)
        if side == "long" and cur_1h < ema20_1h * 0.97:
            score = max(0, score - 1)   # 1H aşağı baskısı
        elif side == "short" and cur_1h > ema20_1h * 1.03:
            score = max(0, score - 1)

    return min(3, score), details


def _score_momentum(df_5m: Optional[pd.DataFrame], df_1m: Optional[pd.DataFrame],
                    side: str) -> Tuple[int, dict]:
    """Momentum skoru 0-3."""
    score   = 0
    details = {}

    if df_5m is None or len(df_5m) < 27:
        return 1, {"momentum": "veri_yok"}

    rsi_val  = _rsi(df_5m["close"])
    macd_h   = _macd_histogram(df_5m["close"])
    body_str = _body_strength(df_5m, n=3)
    stoch_k, stoch_d = _stoch_rsi(df_5m["close"])

    details.update({
        "rsi":     round(rsi_val, 1),
        "macd_h":  round(macd_h, 6),
        "body":    round(body_str, 3),
        "stoch_k": round(stoch_k, 1),
        "stoch_d": round(stoch_d, 1),
    })

    if side == "long":
        # RSI 40-68 ve yukarı
        if 40 <= rsi_val <= 68:
            score += 1
        # MACD histogram pozitif veya yukarı dönüyor
        if macd_h > 0 or (df_5m["close"].iloc[-1] > df_5m["close"].iloc[-3]):
            score += 1
        # Gövde gücü pozitif ve stoch_k < 80
        if body_str > 0.1 and stoch_k < 80:
            score += 1
    else:
        if 32 <= rsi_val <= 60:
            score += 1
        if macd_h < 0 or (df_5m["close"].iloc[-1] < df_5m["close"].iloc[-3]):
            score += 1
        if body_str < -0.1 and stoch_k > 20:
            score += 1

    # 1m mikro onay (varsa)
    if df_1m is not None and len(df_1m) >= 14:
        rsi_1m = _rsi(df_1m["close"])
        details["rsi_1m"] = round(rsi_1m, 1)
        if side == "long" and rsi_1m > 45:
            score = min(3, score + 0)   # Zaten hesaplandı
        elif side == "short" and rsi_1m < 55:
            score = min(3, score + 0)

    return min(3, score), details


def _score_volume(df_5m: Optional[pd.DataFrame], side: str) -> Tuple[int, dict]:
    """Hacim skoru 0-2."""
    score   = 0
    details = {}

    if df_5m is None or len(df_5m) < 21:
        return 1, {"volume": "veri_yok"}

    rel_vol  = _relative_volume(df_5m)
    vol_tr   = _volume_trend(df_5m, n=5)

    details.update({
        "rel_vol":    round(rel_vol, 2),
        "up_ratio":   round(vol_tr["up_ratio"],   2),
        "down_ratio": round(vol_tr["down_ratio"], 2),
    })

    # Ortalama üstü hacim
    if rel_vol >= 1.0:
        score += 1

    if side == "long" and vol_tr["up_ratio"] > 0.55:
        score += 1
    elif side == "short" and vol_tr["down_ratio"] > 0.55:
        score += 1

    return min(2, score), details


def _score_volatility(df_5m: Optional[pd.DataFrame], atr_val: float) -> Tuple[int, dict]:
    """Volatilite skoru 0-2."""
    score   = 0
    details = {}

    if df_5m is None or len(df_5m) < 15:
        return 1, {"volatility": "veri_yok"}

    cur      = float(df_5m["close"].iloc[-1])
    atr_pct  = (atr_val / cur * 100) if cur > 0 else 0

    details["atr_pct"] = round(atr_pct, 3)

    # İdeal volatilite: %0.1 - %3.0
    if 0.1 <= atr_pct <= 3.0:
        score += 2
    elif 0.05 <= atr_pct < 0.1 or 3.0 < atr_pct <= 5.0:
        score += 1
    # < 0.05 veya > 5.0 → 0 puan

    return min(2, score), details


def _score_orderbook(ob: dict, side: str) -> Tuple[int, dict]:
    """Order book skoru 0-2."""
    score   = 0
    details = {}

    spread  = _spread_pct(ob)
    imb     = _ob_imbalance(ob)

    details.update({
        "spread_pct": round(spread, 4),
        "ob_imb":     round(imb, 3),
    })

    # Spread < 0.1% → normal
    if spread < 0.1:
        score += 1
    elif spread >= 0.5:
        return 0, details   # Çok geniş spread → skor 0

    # Order book imbalance
    if side == "long"  and imb >  0.05:
        score += 1
    elif side == "short" and imb < -0.05:
        score += 1

    return min(2, score), details


def _score_derivatives(inst_id: str, side: str) -> Tuple[int, dict]:
    """Derivatives skoru 0-1."""
    score   = 0
    details = {}

    try:
        funding = _fetch_funding(inst_id)
        details["funding"] = round(funding * 100, 4)

        if side == "long":
            # Negatif veya düşük funding → long avantajlı
            if funding <= 0.0001:
                score += 1
        else:
            # Pozitif veya yüksek funding → short avantajlı
            if funding >= -0.0001:
                score += 1
    except:
        score = 0

    return min(1, score), details


def _score_risk(open_positions_count: int, max_positions: int,
                daily_pnl: float, max_daily_loss: float,
                side: str, existing_sides: list) -> Tuple[int, dict]:
    """Risk skoru 0-3."""
    score   = 3   # Başlangıçta tam puan, sorun varsa düş
    details = {}

    # Pozisyon doluluk oranı
    fill_ratio = open_positions_count / max(1, max_positions)
    details["fill_ratio"] = round(fill_ratio, 2)

    if fill_ratio >= 0.8:
        score -= 1   # Slotlar dolmak üzere
    if fill_ratio >= 1.0:
        return 0, details   # Tamamen dolu

    # Günlük zarar
    if max_daily_loss > 0 and daily_pnl < -max_daily_loss * 0.8:
        score -= 1
        details["daily_loss_warning"] = True

    # Korelasyon — aynı yönde çok pozisyon
    same_side_count = existing_sides.count(side)
    details["same_side"] = same_side_count
    if same_side_count >= 3:
        score -= 1

    return max(0, min(3, score)), details


# ── Ana Onay Fonksiyonu ───────────────────────────────────────────────────────

def approve(
    inst_id:             str,
    side:                str,   # "long" veya "short"
    df_5m:               Optional[pd.DataFrame],
    regime:              str    = "RANGE",
    open_positions_count: int   = 0,
    max_positions:       int    = 5,
    daily_pnl:           float  = 0.0,
    max_daily_loss:      float  = 50.0,
    existing_sides:      list   = None,
    df_1h:               Optional[pd.DataFrame] = None,
    df_1m:               Optional[pd.DataFrame] = None,
    df_15m:              Optional[pd.DataFrame] = None,
) -> Tuple[bool, ScoreResult]:
    """
    Giriş onay kararı.

    Returns:
        (True, result)  → emir gönderilebilir
        (False, result) → emir gönderilmez
    """
    result = ScoreResult()

    if not SCORER_ENABLED:
        result.entry_mode = "scorer_disabled"
        return True, result

    if existing_sides is None:
        existing_sides = []

    # LOW_LIQUIDITY → kesinlikle açma
    if regime in ("LOW_LIQUIDITY", "NO_TRADE"):
        result.reject_reason = f"regime={regime}"
        result.entry_mode    = "no_trade"
        return False, result

    # Veri yetersizse geç (sistemi bloke etme)
    if df_5m is None or len(df_5m) < 20:
        result.entry_mode    = "no_data_fallback"
        result.reject_reason = "yetersiz_5m_veri"
        return True, result   # Veri yoksa mevcut sisteme bırak

    # ── Veri toplama ─────────────────────────────────────────────────────────
    atr_val = _atr(df_5m)
    ob      = _fetch_orderbook(inst_id)
    rel_vol = _relative_volume(df_5m)

    # ── Anti-chase filtresi ───────────────────────────────────────────────────
    is_chase = _anti_chase(df_5m, atr_val, side, mult=SCORER_ANTI_CHASE_ATR)
    is_break = _breakout_mode(df_5m, atr_val, rel_vol, ob, side)

    if is_chase and not is_break:
        result.reject_reason = f"anti_chase (atr_mult={SCORER_ANTI_CHASE_ATR})"
        result.entry_mode    = "no_trade"
        _emit_log(inst_id, side, result, regime, ob, rel_vol, df_5m)
        return False, result

    # ── Spread kontrolü ───────────────────────────────────────────────────────
    spread = _spread_pct(ob)
    if spread >= 0.5:
        result.reject_reason = f"spread_yüksek ({spread:.3f}%)"
        result.entry_mode    = "no_trade"
        _emit_log(inst_id, side, result, regime, ob, rel_vol, df_5m)
        return False, result

    # ── Skor hesaplama ────────────────────────────────────────────────────────
    s_trend, d_trend = _score_trend(df_1h, df_15m, df_5m, side)
    s_mom,   d_mom   = _score_momentum(df_5m, df_1m, side)
    s_vol,   d_vol   = _score_volume(df_5m, side)
    s_vola,  d_vola  = _score_volatility(df_5m, atr_val)
    s_ob,    d_ob    = _score_orderbook(ob, side)
    s_deriv, d_deriv = _score_derivatives(inst_id, side)
    s_risk,  d_risk  = _score_risk(
        open_positions_count, max_positions,
        daily_pnl, max_daily_loss,
        side, existing_sides
    )

    result.trend       = s_trend
    result.momentum    = s_mom
    result.volume      = s_vol
    result.volatility  = s_vola
    result.orderbook   = s_ob
    result.derivatives = s_deriv
    result.risk        = s_risk
    result.details.update({**d_trend, **d_mom, **d_vol, **d_vola, **d_ob, **d_deriv, **d_risk})
    result.compute_total()

    # ── Entry mode ────────────────────────────────────────────────────────────
    if is_break:
        result.entry_mode = "breakout"
    elif s_trend >= 2 and s_mom >= 2:
        result.entry_mode = "continuation"
    else:
        result.entry_mode = "pullback"

    # ── Eşik kontrolü ────────────────────────────────────────────────────────
    thresholds = SCORER_THRESHOLDS.get(regime, SCORER_DEFAULT_THRESHOLD)
    min_score  = thresholds.get(side, 10)

    # Breakout modunda eşiği 1 düşür
    if is_break:
        min_score = max(7, min_score - 1)

    approved = result.total >= min_score
    if not approved:
        result.reject_reason = f"skor_düşük ({result.total}/{min_score})"

    _emit_log(inst_id, side, result, regime, ob, rel_vol, df_5m, min_score, approved)
    return approved, result


def _emit_log(inst_id: str, side: str, result: ScoreResult,
              regime: str, ob: dict, rel_vol: float,
              df_5m: pd.DataFrame, min_score: int = 0, approved: bool = False):
    """Standart log satırı."""
    try:
        sym    = inst_id.replace("-USDT-SWAP", "USDT")
        spread = round(_spread_pct(ob), 4)
        rsi    = result.details.get("rsi", "?")
        cur    = float(df_5m["close"].iloc[-1]) if df_5m is not None and len(df_5m) > 0 else 0

        action = "✅ ONAY" if approved else f"⛔ RED ({result.reject_reason})"

        line = (
            f"[SCORER] {sym} {side.upper()} | "
            f"regime={regime} | "
            f"score={result.total}/16 (min={min_score}) | "
            f"T:{result.trend} M:{result.momentum} V:{result.volume} "
            f"Vl:{result.volatility} OB:{result.orderbook} D:{result.derivatives} R:{result.risk} | "
            f"mode={result.entry_mode} | "
            f"RSI={rsi} | spread={spread}% | rel_vol={round(rel_vol,2)} | "
            f"price={round(cur,4)} | {action}"
        )
        print(f"cryptobot: [{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {line}", flush=True)
        log.info(line)
    except Exception as e:
        log.debug(f"Log hatası: {e}")


# ── Veri Önbelleği ────────────────────────────────────────────────────────────
# Bot_engine her döngüde zaten 5m ve 1H çekiyor.
# Burada ek timeframe'ler için hafif önbellek kullanıyoruz.

_cache: dict = {}
_CACHE_TTL   = 55   # saniye


def get_cached_df(inst_id: str, bar: str, limit: int) -> Optional[pd.DataFrame]:
    """TTL bazlı önbellekten veri al, yoksa çek."""
    key = f"{inst_id}_{bar}_{limit}"
    now = time.time()
    if key in _cache:
        ts, df = _cache[key]
        if now - ts < _CACHE_TTL:
            return df
    df = _fetch_ohlcv(inst_id, bar, limit)
    _cache[key] = (now, df)
    return df


def clear_cache():
    """Döngü başında eski önbellek girişlerini temizle."""
    now = time.time()
    stale = [k for k, (ts, _) in _cache.items() if now - ts > _CACHE_TTL * 3]
    for k in stale:
        del _cache[k]
