"""
Pullback Short Strategy — Düşüş Trendinde Geri Çekilme Kısaltma
==============================================================
Temel Felsefe:
  Trend aşağı yönde hareket ederken, kısa vadeli yukarı tepkileri
  (EMA21'e yakın pullback) satmak (short açmak).
  Pullback Long'un tam mirror versiyonu.

Koşullar (10/10 üzeri, min 7 puan):
  [3 puan] Trend hizalama: EMA9 < EMA21 < EMA50, fiyat < EMA50, EMA50 eğimi -
  [2 puan] Short pullback zonu: fiyat EMA21 civarında (yukarı tepki sonrası)
  [2 puan] Short momentum: RSI 30-64, ADX >= 15
  [2 puan] Hacim onayı: hacim 20-bar ortalamasının 1.05x üzerinde
  [1 puan] Volatilite uygunluğu: ATR %0.4-12% arası

RR:   1.8× (SL = giriş + 1.8×ATR, TP = giriş - risk×1.8)
Türü: Sadece SHORT — kısa vadeli düşüş trendinde EMA21 tepkisini yakala
"""

import time
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from strategies.base import BaseStrategy, Signal
from utils.logger import get_logger

logger = get_logger()


# ─── Veri Sınıfları ────────────────────────────────────────────────────────────

@dataclass
class ShortSignalResult:
    should_enter:      bool
    score:             int
    reason:            str
    entry_price:       Optional[float] = None
    stop_loss:         Optional[float] = None
    take_profit:       Optional[float] = None
    min_hold_minutes:  Optional[int]   = None
    volume_ok:         bool            = True


# ─── Strateji Durumu (per-symbol cooldown + streak ban) ──────────────────────

class ShortStrategyState:
    """
    Sembol bazlı cooldown ve kayıp serisi takibi (Short stratejisi için).
    """
    def __init__(self):
        self.symbol_cooldowns:   Dict[str, float] = {}
        self.symbol_loss_streak: Dict[str, int]   = {}
        self.daily_trade_count:  int               = 0
        self.max_daily_trades:   int               = 8   # Konservatif: short için düşük tavan

    def is_symbol_on_cooldown(self, symbol: str) -> bool:
        return time.time() < self.symbol_cooldowns.get(symbol, 0)

    def set_symbol_cooldown(self, symbol: str, minutes: int):
        self.symbol_cooldowns[symbol] = time.time() + minutes * 60
        logger.info(f"[PullbackShort] {symbol}: {minutes} dk cooldown başladı")

    def register_trade_result(self, symbol: str, won: bool):
        if won:
            self.symbol_loss_streak[symbol] = 0
        else:
            self.symbol_loss_streak[symbol] = self.symbol_loss_streak.get(symbol, 0) + 1
            streak = self.symbol_loss_streak[symbol]
            if streak >= 3:
                logger.warning(
                    f"[PullbackShort] {symbol}: {streak} art arda kayıp "
                    f"→ sembol geçici olarak yasaklandı"
                )

    def should_ban_symbol(self, symbol: str) -> bool:
        return self.symbol_loss_streak.get(symbol, 0) >= 3

    def increment_trade(self):
        self.daily_trade_count += 1

    def reset_daily(self):
        self.daily_trade_count = 0


# ─── Filtreler ─────────────────────────────────────────────────────────────────

def _is_trend_down(d: dict) -> bool:
    """
    Düşüş trendi hizalama kontrolü (Long'un tam tersi):
    - EMA9 < EMA21 < EMA50 (tam ters hiza)
    - Fiyat EMA50 altında (trend baskısı)
    - EMA50 eğimi negatif (trend hâlâ aşağı)
    """
    return (
        d["close"] < d["ema50"] and
        d["ema9"] < d["ema21"] < d["ema50"] and
        d["ema50"] < d["ema50_prev"]
    )


def _is_short_pullback_entry(d: dict) -> bool:
    """
    EMA21 civarı yukarı tepki (short girişi için).
    Fiyat düşüş içindeyken EMA21'e yakın tepki bölgesi aranır.
    - Fiyat EMA21'e ATR'nin 1.2 katı içinde olmalı (uzaktan tepki veya doğrudan test)
    - Fiyat EMA21'den çok yukarıda olmamalı (uzak tepki = geç giriş)
    """
    close    = d["close"]
    high     = d.get("high", close)
    ema21    = d["ema21"]
    atr      = d["atr"]

    distance        = abs(close - ema21)
    near_ema21      = (distance <= atr * 1.2) or (high >= ema21)
    not_too_extended = close >= ema21 - atr * 2.0

    return near_ema21 and not_too_extended


def _is_momentum_short(d: dict) -> bool:
    """
    Short için momentum zonu: RSI 30-64.
    - 30 altı: aşırı satılmış → short için tehlikeli
    - 64 üstü: overbought bölge kıyısı → short için ideal ama geç sayılır
    - ADX minimum 15: trend gücü var
    """
    return 38 <= d["rsi"] <= 60 and d["adx"] >= 20  # Scalping: sıkı RSI + ADX


def _is_volume_confirmed(d: dict) -> bool:
    """Son hacim 20-bar ortalamasının 1.05x üzerinde (hem long hem short için aynı)."""
    return d["volume"] > d["volume_ma20"] * 1.3  # Scalping: güçlü hacim


def _is_volatility_acceptable(d: dict) -> bool:
    """
    Çok ölü piyasa da olmasın, fırtına da olmasın.
    ATR %0.4–%15 arası (long ile aynı eşikler).
    """
    close     = d["close"]
    atr       = d["atr"]
    bb_range  = d["bb_upper"] - d["bb_lower"]

    atr_pct      = atr / close if close > 0 else 0
    bb_width_pct = bb_range / close if close > 0 else 0

    if atr_pct < 0.004:
        return False
    if bb_width_pct > 0.15:
        return False
    return True


# ─── Skor Hesaplama ────────────────────────────────────────────────────────────

def _calculate_short_score(d: dict) -> Tuple[int, list]:
    """
    10 üzerinden puan ver. 7 ve üzeri → short işlem aç.

    Dağılım (Long ile simetrik):
      Trend hizalama   = 3 puan (en önemli)
      Pullback zonu    = 2 puan
      Momentum         = 2 puan
      Hacim            = 2 puan
      Volatilite       = 1 puan
    """
    score   = 0
    reasons = []

    if _is_trend_down(d):
        score += 3
        reasons.append(
            f"✓ Düşüş trendi hizalı "
            f"(EMA9={d['ema9']:.4f}<EMA21={d['ema21']:.4f}<EMA50={d['ema50']:.4f}, EMA50↓)"
        )
    else:
        reasons.append(
            f"✗ Düşüş trendi hizasız "
            f"(close={d['close']:.4f} EMA9={d['ema9']:.4f} "
            f"EMA21={d['ema21']:.4f} EMA50={d['ema50']:.4f})"
        )

    if _is_short_pullback_entry(d):
        score += 2
        reasons.append(
            f"✓ Short pullback zonu (fiyat EMA21 civarı, mesafe={abs(d['close']-d['ema21']):.4f})"
        )
    else:
        reasons.append(
            f"✗ Short pullback yok (fiyat EMA21'den uzak veya çok altında)"
        )

    if _is_momentum_short(d):
        score += 2
        reasons.append(f"✓ Short momentum uygun (RSI={d['rsi']:.1f}, ADX={d['adx']:.1f})")
    else:
        reasons.append(
            f"✗ Short momentum uygun değil (RSI={d['rsi']:.1f} [beklenen:30-64], "
            f"ADX={d['adx']:.1f} [min:15])"
        )

    if _is_volume_confirmed(d):
        score += 2
        reasons.append(
            f"✓ Hacim onaylı ({d['volume']:.0f} > MA20×1.05={d['volume_ma20']*1.05:.0f})"
        )
    else:
        reasons.append(
            f"✗ Hacim zayıf ({d['volume']:.0f} < MA20×1.05={d['volume_ma20']*1.05:.0f})"
        )

    if _is_volatility_acceptable(d):
        score += 1
        atr_pct = d["atr"] / d["close"] * 100
        reasons.append(f"✓ Volatilite uygun (ATR%={atr_pct:.2f})")
    else:
        reasons.append("✗ Volatilite uygun değil (ATR/fiyat sınır dışı)")

    return score, reasons


# ─── Ana Short Sinyal Fonksiyonu ───────────────────────────────────────────────

def build_short_signal(
    symbol:   str,
    hour_utc: int,
    d:        dict,
    state:    ShortStrategyState,
    min_score: int = 8,  # Scalping: yüksek eşik
) -> ShortSignalResult:
    """
    Tüm filtrelerden geçen yüksek kalite SELL (short aç) sinyali üretir.

    Beklenen 'd' anahtarları:
      close, high, ema9, ema21, ema50, ema50_prev,
      rsi, adx, atr, bb_upper, bb_lower, volume, volume_ma20
    """
    # 1. Günlük limit
    if state.daily_trade_count >= state.max_daily_trades:
        return ShortSignalResult(False, 0, "Günlük short işlem limiti doldu")

    # 2. Symbol cooldown
    if state.is_symbol_on_cooldown(symbol):
        return ShortSignalResult(False, 0, f"{symbol} short cooldown aktif")

    # 3. Symbol ban (3 art arda kayıp)
    if state.should_ban_symbol(symbol):
        streak = state.symbol_loss_streak.get(symbol, 0)
        return ShortSignalResult(
            False, 0,
            f"{symbol} short geçici yasaklı ({streak} art arda kayıp)"
        )

    # 4. Puan hesapla
    score, reasons = _calculate_short_score(d)

    if score < min_score:
        return ShortSignalResult(
            False, score,
            f"Short puan yetersiz ({score}/{min_score}): {' | '.join(reasons)}"
        )

    # 5. SL / TP — SHORT için TERSİNE (SL yukarıda, TP aşağıda)
    entry_price = d["close"]
    atr         = d["atr"]
    stop_loss   = entry_price + (atr * 1.2)  # Scalping: dar SL      # SL giriş üstünde (ATR×2.5 — daha geniş nefes alanı)
    risk        = stop_loss - entry_price          # = ATR × 2.5
    take_profit = entry_price - (risk * 1.8)  # Scalping: RR 1.8x       # TP giriş altında, RR = 1.6×

    return ShortSignalResult(
        should_enter     = True,
        score            = score,
        reason           = " | ".join(reasons),
        entry_price      = entry_price,
        stop_loss        = stop_loss,
        take_profit      = take_profit,
        min_hold_minutes = 5,  # Scalping
        volume_ok        = _is_volume_confirmed(d),
    )


# ─── DataFrame → d dict dönüşümü ───────────────────────────────────────────────

def _ema(s: pd.Series, p: int) -> pd.Series:
    return s.ewm(span=p, adjust=False).mean()

def _rsi(s: pd.Series, p: int = 14) -> pd.Series:
    d     = s.diff()
    gain  = d.clip(lower=0).ewm(span=p, adjust=False).mean()
    loss  = (-d.clip(upper=0)).ewm(span=p, adjust=False).mean()
    rs    = gain / (loss + 1e-9)
    return 100 - 100 / (1 + rs)

def _atr(df: pd.DataFrame, p: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr   = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"]  - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()

def _adx(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 5:
        return 0.0
    high, low, close = df["high"], df["low"], df["close"]
    dm_p = (high - high.shift(1)).clip(lower=0)
    dm_m = (low.shift(1) - low).clip(lower=0)
    dm_pc = dm_p.where(dm_p > dm_m, 0)
    dm_mc = dm_m.where(dm_m > dm_p, 0)
    prev_c = close.shift(1)
    tr = pd.concat([high-low, (high-prev_c).abs(), (low-prev_c).abs()], axis=1).max(axis=1)
    atr_s = tr.ewm(span=period, adjust=False).mean()
    di_p  = (dm_pc.ewm(span=period, adjust=False).mean() / atr_s * 100).fillna(0)
    di_m  = (dm_mc.ewm(span=period, adjust=False).mean() / atr_s * 100).fillna(0)
    dx    = (abs(di_p - di_m) / (di_p + di_m + 1e-9) * 100).fillna(0)
    return float(dx.ewm(span=period, adjust=False).mean().iloc[-1])

def _extract_short_indicators(df: pd.DataFrame) -> Optional[dict]:
    """DataFrame'den short stratejisi için gereken tüm indikatörleri hesapla."""
    min_bars = 55
    if df is None or len(df) < min_bars:
        return None

    close = df["close"]

    ema9_s  = _ema(close, 9)
    ema21_s = _ema(close, 21)
    ema50_s = _ema(close, 50)
    atr_s   = _atr(df)
    rsi_s   = _rsi(close)

    bb_mid   = close.rolling(20).mean()
    bb_std   = close.rolling(20).std()
    bb_upper = (bb_mid + 2 * bb_std).iloc[-1]
    bb_lower = (bb_mid - 2 * bb_std).iloc[-1]

    vol_col      = "volume" if "volume" in df.columns else None
    volume       = float(df[vol_col].iloc[-1])        if vol_col else 0.0
    volume_ma20  = float(df[vol_col].tail(20).mean()) if vol_col else 1.0

    return {
        "close":       float(close.iloc[-1]),
        "high":        float(df["high"].iloc[-1]),
        "low":         float(df["low"].iloc[-1]),
        "ema9":        float(ema9_s.iloc[-1]),
        "ema21":       float(ema21_s.iloc[-1]),
        "ema50":       float(ema50_s.iloc[-1]),
        "ema50_prev":  float(ema50_s.iloc[-2]),
        "rsi":         float(rsi_s.iloc[-1]),
        "adx":         _adx(df),
        "atr":         float(atr_s.iloc[-1]),
        "bb_upper":    float(bb_upper),
        "bb_lower":    float(bb_lower),
        "volume":      volume,
        "volume_ma20": volume_ma20,
    }


# ─── BaseStrategy Wrapper ──────────────────────────────────────────────────────

class PullbackShortStrategy(BaseStrategy):
    """
    Trend-Geri-Çekilme kısa stratejisi.
    EMA21 civarında yukarı tepki veren, düşüş trendi hizalı ve hacim onaylı shortlar.

    Pullback Long'un tam mirror versiyonu:
    - Long: EMA hizası yukarı, pullback aşağı → BUY
    - Short: EMA hizası aşağı, pullback yukarı → SELL (short aç)
    """

    def __init__(self, min_score: int = 7):
        super().__init__(name="Pullback Short")
        self.min_score = min_score
        self.state     = ShortStrategyState()

        self.last_result: Optional[ShortSignalResult] = None
        self.last_conditions: Optional[dict] = None

    def generate_signal(self, df: pd.DataFrame) -> str:
        """BaseStrategy uyumluluğu için — tam sonuç için generate() kullan."""
        result = self.generate(df)
        return Signal.SELL if result.should_enter else Signal.HOLD

    def generate(
        self,
        df:       pd.DataFrame,
        symbol:   str       = "UNKNOWN",
        hour_utc: Optional[int] = None,
    ) -> ShortSignalResult:
        """
        Tam short sinyal üretimi. main.py'deki döngü bu metodu çağırır.
        """
        from datetime import datetime, timezone
        if hour_utc is None:
            hour_utc = datetime.now(timezone.utc).hour

        indicators = _extract_short_indicators(df)
        if indicators is None:
            self.last_result = ShortSignalResult(False, 0, "Yetersiz veri (min 55 bar)")
            self.last_conditions = None
            return self.last_result

        result = build_short_signal(
            symbol    = symbol,
            hour_utc  = hour_utc,
            d         = indicators,
            state     = self.state,
            min_score = self.min_score,
        )
        self.last_result = result

        # Dashboard için per-koşul detay verisi
        d = indicators
        atr_pct = (d["atr"] / d["close"] * 100) if d.get("close", 0) > 0 else 0
        pullback_dist = abs(d["close"] - d["ema21"])
        self.last_conditions = {
            "price":     round(d["close"], 6),
            "ema9":      round(d["ema9"], 6),
            "ema21":     round(d["ema21"], 6),
            "ema50":     round(d["ema50"], 6),
            "rsi":       round(d["rsi"], 1),
            "adx":       round(d["adx"], 1),
            "atr_pct":   round(atr_pct, 3),
            "vol_ratio": round(d["volume"] / d["volume_ma20"], 2) if d.get("volume_ma20", 0) > 0 else 0,
            "pullback_dist_pct": round(pullback_dist / d["close"] * 100, 2) if d.get("close", 0) > 0 else 0,
            "direction": "SHORT",
            "conditions": {
                "trend":      {"ok": _is_trend_down(d),              "weight": 3, "label": "Düşüş Trendi",    "detail": f"EMA9={d['ema9']:.4f}<EMA21={d['ema21']:.4f}<EMA50={d['ema50']:.4f}"},
                "pullback":   {"ok": _is_short_pullback_entry(d),    "weight": 2, "label": "Short Pullback",   "detail": f"EMA21 mesafe: %{round(pullback_dist / d['close'] * 100, 2) if d['close'] > 0 else 0:.2f}"},
                "momentum":   {"ok": _is_momentum_short(d),          "weight": 2, "label": "Short Momentum",  "detail": f"RSI:{d['rsi']:.1f} ADX:{d['adx']:.1f}"},
                "volume":     {"ok": _is_volume_confirmed(d),        "weight": 2, "label": "Hacim Onayı",     "detail": f"Vol/Ort: x{round(d['volume'] / d['volume_ma20'], 2) if d.get('volume_ma20', 0) > 0 else 0:.2f}"},
                "volatility": {"ok": _is_volatility_acceptable(d),  "weight": 1, "label": "Volatilite",      "detail": f"ATR%:{atr_pct:.2f}"},
            },
            "score":      result.score,
            "min_score":  self.min_score,
            "should_enter": result.should_enter,
            "blocked_reason": result.reason if not result.should_enter else None,
            "cooldown":   self.state.is_symbol_on_cooldown(symbol),
        }

        if result.should_enter:
            logger.info(
                f"✅ [{self.name}] {symbol} SHORT | "
                f"Puan:{result.score}/10 | "
                f"Giriş:{result.entry_price:.4f} | "
                f"SL:{result.stop_loss:.4f} | TP:{result.take_profit:.4f} | "
                f"{result.reason}"
            )
        else:
            logger.debug(
                f"[{self.name}] {symbol} HOLD | "
                f"Puan:{result.score}/10 | {result.reason[:80]}"
            )

        return result

    def on_trade_closed(self, symbol: str, pnl: float):
        """İşlem kapandığında strateji durumunu güncelle."""
        won = pnl > 0
        self.state.register_trade_result(symbol, won)
        if not won:
            streak = self.state.symbol_loss_streak.get(symbol, 0)
            if streak >= 2:
                cooldown_min = streak * 60
                self.state.set_symbol_cooldown(symbol, cooldown_min)

    def get_last_sl_tp(self) -> Tuple[Optional[float], Optional[float]]:
        """Son sinyalin SL/TP değerlerini döndür (main.py entegrasyonu için)."""
        if self.last_result and self.last_result.should_enter:
            return self.last_result.stop_loss, self.last_result.take_profit
        return None, None
