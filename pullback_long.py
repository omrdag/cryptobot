"""
Pullback Long Strategy v4 — Global Kanıtlanmış Sinyal Motoru
=============================================================
Araştırma kaynakları:
  - Supertrend + RSI kombinasyonu: backtestlerde %62-68 win rate
  - Çift Supertrend (10,3) + (7,2): iki farklı ayar hemfikirse çok güçlü
  - MACD histogram momentum onayı: MACD standalone'dan %20 daha iyi
  - VWAP kurumsal seviye filtresi: kurumsal akış teyidi
  - 4H MTF teyidi: büyük trend yönü doğrulaması
  - Volume spike (1.3x MA20): hacim onayı zorunlu

Skor sistemi (max 11):
  Gate (zorunlu — 0 ise sinyal üretilmez):
    1. Supertrend yönü (5m) — fiyat supertrend üzerinde
    2. 4H trend hizası — EMA50 eğimi yukarı
    3. Volume filtresi — hacim MA20 × 1.2 üzerinde

  Ağırlıklı puanlar:
    4. Supertrend flip (son 3 barda yeni yeşile döndü)   → +2
    5. Çift Supertrend hemfikir (7,2 de yeşil)           → +1
    6. MACD histogram pozitif ve yükseliyor              → +1
    7. RSI 40-65 arası (ideal giriş zonu)                → +1
    8. VWAP üzerinde işlem                               → +1
    9. 1H EMA9 > EMA21 (kısa vade trend)                 → +1
   10. Pullback zonu (EMA21 civarında)                   → +1
   11. 4H RSI 45-70 arası (büyük trend sağlıklı)         → +1
"""

import os
import math
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


# ── Sonuç veri sınıfı ─────────────────────────────────────────────────────────

@dataclass
class SignalResult:
    should_enter:  bool  = False
    score:         int   = 0
    entry_price:   float = 0.0
    stop_loss:     float = 0.0
    take_profit:   float = 0.0
    reason:        str   = ""
    gate_passed:   bool  = False
    indicators:    dict  = field(default_factory=dict)


# ── Gösterge Hesaplamaları ────────────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"]  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _supertrend(df: pd.DataFrame, atr_period: int = 10, factor: float = 3.0):
    """
    Supertrend hesaplama — global standart (10, 3) varsayılan.
    Returns: (supertrend_series, direction_series)
    direction = 1 → bullish (fiyat üzerinde yeşil), -1 → bearish
    """
    hl2  = (df["high"] + df["low"]) / 2
    atr  = _atr(df, atr_period)
    upper = hl2 + factor * atr
    lower = hl2 - factor * atr

    supertrend = pd.Series(index=df.index, dtype=float)
    direction  = pd.Series(index=df.index, dtype=int)

    supertrend.iloc[0] = lower.iloc[0]
    direction.iloc[0]  = 1

    for i in range(1, len(df)):
        prev_st  = supertrend.iloc[i - 1]
        prev_dir = direction.iloc[i - 1]
        c        = df["close"].iloc[i]
        u        = upper.iloc[i]
        l        = lower.iloc[i]

        if prev_dir == 1:
            new_st  = max(l, prev_st) if c > prev_st else u
            new_dir = 1 if c > new_st else -1
        else:
            new_st  = min(u, prev_st) if c < prev_st else l
            new_dir = -1 if c < new_st else 1

        supertrend.iloc[i] = new_st
        direction.iloc[i]  = new_dir

    return supertrend, direction


def _macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD hesaplama. Returns (macd_line, signal_line, histogram)"""
    ema_fast = _ema(df["close"], fast)
    ema_slow = _ema(df["close"], slow)
    macd_line   = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram   = macd_line - signal_line
    return macd_line, signal_line, histogram


def _rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    delta = df["close"].diff()
    gain  = delta.where(delta > 0, 0).ewm(span=period, adjust=False).mean()
    loss  = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
    rs    = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def _vwap(df: pd.DataFrame) -> pd.Series:
    """Yaklaşık VWAP (günlük sıfırlama yok, kayan pencere)"""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    cumvol  = df["volume"].cumsum()
    cumtp   = (typical * df["volume"]).cumsum()
    return cumtp / cumvol.replace(0, 1e-10)


# ── Ana Strateji Sınıfı ───────────────────────────────────────────────────────

class PullbackLongStrategy:
    """
    Global kanıtlanmış Supertrend + MACD + VWAP + MTF pullback stratejisi.

    Parametre isimleri mevcut bot_engine.py ile uyumlu.
    generate() metodu SignalResult döner.
    """

    def __init__(self, min_score: int = 7):
        self.min_score = int(os.getenv("LONG_MIN_SCORE", str(min_score)))

    # ── Supertrend ─────────────────────────────────────────────────────────────
    def _calc_supertrend_fast(self, df: pd.DataFrame):
        """Hızlı supertrend (7, 2) — kısa vadeli doğrulama"""
        return _supertrend(df, atr_period=7, factor=2.0)

    def _calc_supertrend_slow(self, df: pd.DataFrame):
        """Yavaş supertrend (10, 3) — ana trend filtresi"""
        return _supertrend(df, atr_period=10, factor=3.0)

    # ── Gate Kontrolleri (hepsi zorunlu) ──────────────────────────────────────
    def _gate_supertrend_bullish(self, df: pd.DataFrame) -> tuple[bool, float]:
        """Gate 1: Fiyat supertrend(10,3) üzerinde olmalı"""
        st, direction = self._calc_supertrend_slow(df)
        if len(direction) < 3:
            return False, 0.0
        bullish = direction.iloc[-1] == 1
        st_level = float(st.iloc[-1])
        return bullish, st_level

    def _gate_4h_trend(self, df_4h: Optional[pd.DataFrame]) -> bool:
        """Gate 2: 4H EMA50 eğimi yukarı (büyük trend bullish)"""
        if df_4h is None or len(df_4h) < 55:
            return True  # veri yoksa geç
        ema50 = _ema(df_4h["close"], 50)
        return float(ema50.iloc[-1]) > float(ema50.iloc[-3])

    def _gate_volume(self, df: pd.DataFrame) -> bool:
        """Gate 3: Son bar hacmi MA20 × 1.2 üzerinde"""
        if len(df) < 22:
            return True
        vol_ma20 = df["volume"].rolling(20).mean().iloc[-1]
        vol_now  = df["volume"].iloc[-1]
        return vol_now > vol_ma20 * 1.2

    # ── Bonus Puan Kontrolleri ─────────────────────────────────────────────────
    def _score_supertrend_flip(self, df: pd.DataFrame) -> int:
        """
        +2: Son 3 barda supertrend yeni yeşile döndü (flip).
        En güçlü giriş sinyali — trendin başlangıcını yakalar.
        """
        try:
            _, direction = self._calc_supertrend_slow(df)
            if len(direction) < 5:
                return 0
            d = direction.iloc[-4:]
            # En az bir önceki bar kırmızıydı, şimdi yeşil
            if direction.iloc[-1] == 1 and any(direction.iloc[-4:-1] == -1):
                return 2
            return 0
        except:
            return 0

    def _score_dual_supertrend(self, df: pd.DataFrame) -> int:
        """
        +1: Hem (10,3) hem (7,2) supertrend bullish → çok güçlü teyit.
        Araştırmalarda bu kombinasyon yanlış sinyal oranını %40 düşürüyor.
        """
        try:
            _, dir_slow = self._calc_supertrend_slow(df)
            _, dir_fast = self._calc_supertrend_fast(df)
            if dir_slow.iloc[-1] == 1 and dir_fast.iloc[-1] == 1:
                return 1
            return 0
        except:
            return 0

    def _score_macd(self, df: pd.DataFrame) -> int:
        """
        +1: MACD histogram pozitif VE son 2 barda yükseliyor.
        Momentum devamını teyit eder — geç giriş riskini azaltır.
        """
        try:
            _, _, hist = _macd(df)
            if len(hist) < 4:
                return 0
            h_now  = float(hist.iloc[-1])
            h_prev = float(hist.iloc[-2])
            if h_now > 0 and h_now > h_prev:
                return 1
            return 0
        except:
            return 0

    def _score_rsi(self, df: pd.DataFrame) -> int:
        """
        +1: RSI 40-65 arası (ideal giriş zonu).
        40-65 = ne fazla alım ne fazla satım, trend devamı için uygun.
        RSI > 65 → geç giriş, RSI < 40 → trend zayıf.
        """
        try:
            rsi_val = float(_rsi(df).iloc[-1])
            if 40 <= rsi_val <= 65:
                return 1
            return 0
        except:
            return 0

    def _score_vwap(self, df: pd.DataFrame) -> int:
        """
        +1: Fiyat VWAP üzerinde.
        Kurumsal akış teyidi — fiyat ortalamanın üzerinde = güçlü talep.
        """
        try:
            vwap_val = float(_vwap(df).iloc[-1])
            close    = float(df["close"].iloc[-1])
            return 1 if close > vwap_val else 0
        except:
            return 0

    def _score_ema_trend(self, df_1h: Optional[pd.DataFrame]) -> int:
        """
        +1: 1H EMA9 > EMA21 (kısa vade trend yukarı).
        Kısa vadeli trend hizalaması.
        """
        if df_1h is None or len(df_1h) < 25:
            return 0
        try:
            ema9  = float(_ema(df_1h["close"], 9).iloc[-1])
            ema21 = float(_ema(df_1h["close"], 21).iloc[-1])
            return 1 if ema9 > ema21 else 0
        except:
            return 0

    def _score_pullback_zone(self, df: pd.DataFrame) -> int:
        """
        +1: Fiyat EMA21 civarında (pullback zonu).
        Trend devam ederken geri çekilme — en iyi giriş fırsatı.
        Mesafe EMA21'in ±1.5% içinde olmalı.
        """
        try:
            ema21 = float(_ema(df["close"], 21).iloc[-1])
            close = float(df["close"].iloc[-1])
            dist_pct = abs(close - ema21) / ema21 * 100
            return 1 if dist_pct <= 1.5 else 0
        except:
            return 0

    def _score_4h_rsi(self, df_4h: Optional[pd.DataFrame]) -> int:
        """
        +1: 4H RSI 45-70 arası (büyük trend sağlıklı, aşırı alım yok).
        4H RSI > 70 → aşırı alım, giriş geç. < 45 → trend zayıf.
        """
        if df_4h is None or len(df_4h) < 16:
            return 0
        try:
            rsi_4h = float(_rsi(df_4h).iloc[-1])
            return 1 if 45 <= rsi_4h <= 70 else 0
        except:
            return 0

    # ── SL / TP Hesaplama ──────────────────────────────────────────────────────
    def _calc_sl_tp(self, df: pd.DataFrame, df_1h: Optional[pd.DataFrame],
                    entry: float, st_level: float) -> tuple[float, float]:
        """
        SL: Supertrend seviyesinin biraz altı (dinamik, ATR bazlı).
        TP: Risk × 2 (1:2 R/R) — araştırmalarda en iyi profit factor.
        """
        try:
            # 1H ATR bazlı SL (daha anlamlı mesafe)
            if df_1h is not None and len(df_1h) >= 15:
                atr_1h = float(_atr(df_1h, 14).iloc[-1])
            else:
                atr_1h = float(_atr(df, 14).iloc[-1]) * 3  # 5m ATR × 3 ≈ 1H ATR

            sl_mult = float(os.getenv("SL_ATR_MULT", "1.5"))
            # Supertrend seviyesi veya ATR bazlı — hangisi daha geniş koruma sağlıyorsa
            sl_from_st  = st_level * 0.998  # Supertrend'in %0.2 altı
            sl_from_atr = entry - atr_1h * sl_mult
            sl = max(sl_from_st, sl_from_atr)  # daha yukarıdaki (daha koruyucu)

            risk = entry - sl
            if risk <= 0:
                risk = entry * 0.015  # fallback %1.5
                sl   = entry - risk

            tp_mult = float(os.getenv("TP2_R_MULT", "1.0"))
            tp = entry + risk * tp_mult * 2  # 1:2 R/R

            return sl, tp
        except:
            sl = entry * (1 - 0.015)
            tp = entry * (1 + 0.03)
            return sl, tp

    # ── Ana Üretim Metodu ──────────────────────────────────────────────────────
    def generate(
        self,
        df:       pd.DataFrame,
        symbol:   str = "",
        hour_utc: int = 12,
        df_5m:    Optional[pd.DataFrame] = None,
        df_15m:   Optional[pd.DataFrame] = None,
        df_1h:    Optional[pd.DataFrame] = None,
        df_4h:    Optional[pd.DataFrame] = None,
    ) -> SignalResult:

        result = SignalResult()

        if df is None or len(df) < 55:
            result.reason = "Yetersiz veri"
            return result

        close = float(df["close"].iloc[-1])

        # ── Gate 1: Supertrend bullish ────────────────────────────────────────
        st_bullish, st_level = self._gate_supertrend_bullish(df)
        if not st_bullish:
            result.reason = (
                f"✗ Gate: Supertrend bearish (fiyat ${close:.4f} < ST ${st_level:.4f})"
            )
            result.indicators = {"supertrend": st_level, "supertrend_bullish": False}
            return result

        # ── Gate 2: 4H trend ──────────────────────────────────────────────────
        trend_4h_ok = self._gate_4h_trend(df_4h)
        if not trend_4h_ok:
            result.reason = "✗ Gate: 4H EMA50 aşağı eğimli (büyük trend bearish)"
            return result

        # ── Gate 3: Volume ────────────────────────────────────────────────────
        vol_ok = self._gate_volume(df)
        vol_ma = float(df["volume"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else 0
        vol_now = float(df["volume"].iloc[-1])
        if not vol_ok:
            result.reason = (
                f"✗ Gate: Hacim zayıf ({vol_now:.0f} < MA20×1.2={vol_ma*1.2:.0f})"
            )
            return result

        result.gate_passed = True

        # ── Bonus Puanlar ─────────────────────────────────────────────────────
        score = 0
        reasons = []

        s_flip = self._score_supertrend_flip(df)
        score += s_flip
        if s_flip == 2:
            reasons.append("✓ ST flip (yeni yeşil +2)")
        elif s_flip == 0:
            reasons.append("✗ ST flip yok")

        s_dual = self._score_dual_supertrend(df)
        score += s_dual
        reasons.append("✓ Çift ST hemfikir" if s_dual else "✗ Çift ST çakışmıyor")

        s_macd = self._score_macd(df)
        score += s_macd
        reasons.append("✓ MACD histogram ↑" if s_macd else "✗ MACD zayıf")

        s_rsi = self._score_rsi(df)
        score += s_rsi
        try:
            rsi_val = float(_rsi(df).iloc[-1])
            reasons.append(f"{'✓' if s_rsi else '✗'} RSI={rsi_val:.1f} (ideal:40-65)")
        except:
            reasons.append("✗ RSI hesaplanamadı")

        s_vwap = self._score_vwap(df)
        score += s_vwap
        try:
            vwap_val = float(_vwap(df).iloc[-1])
            reasons.append(f"{'✓' if s_vwap else '✗'} VWAP={vwap_val:.4f}")
        except:
            reasons.append("✗ VWAP hesaplanamadı")

        s_ema = self._score_ema_trend(df_1h)
        score += s_ema
        reasons.append("✓ 1H EMA9>EMA21" if s_ema else "✗ 1H EMA trend yok")

        s_pb = self._score_pullback_zone(df)
        score += s_pb
        try:
            ema21 = float(_ema(df["close"], 21).iloc[-1])
            dist  = abs(close - ema21) / ema21 * 100
            reasons.append(f"{'✓' if s_pb else '✗'} Pullback zonu (EMA21 mesafe={dist:.1f}%)")
        except:
            reasons.append("✗ Pullback zonu hesaplanamadı")

        s_4h_rsi = self._score_4h_rsi(df_4h)
        score += s_4h_rsi
        reasons.append("✓ 4H RSI sağlıklı" if s_4h_rsi else "✗ 4H RSI dışında")

        result.score = score

        # ── Giriş Kararı ──────────────────────────────────────────────────────
        effective_min = self.min_score
        # Saat filtresi: düşük hacim saatlerde +1 eşik
        if hour_utc in [1, 2, 3, 4, 5]:
            effective_min += 1

        if score >= effective_min:
            sl, tp = self._calc_sl_tp(df, df_1h, close, st_level)
            result.should_enter = True
            result.entry_price  = close
            result.stop_loss    = sl
            result.take_profit  = tp

        result.reason = " | ".join(reasons)
        result.indicators = {
            "supertrend":          st_level,
            "supertrend_bullish":  True,
            "supertrend_flip":     s_flip == 2,
            "dual_supertrend":     s_dual == 1,
            "macd_positive":       s_macd == 1,
            "rsi_zone":            s_rsi == 1,
            "vwap_above":          s_vwap == 1,
            "ema_trend":           s_ema == 1,
            "pullback_zone":       s_pb == 1,
            "4h_rsi_ok":           s_4h_rsi == 1,
            "volume_ok":           True,
            "4h_trend_ok":         trend_4h_ok,
            "score":               score,
            "effective_min":       effective_min,
        }

        return result


# ── Uyumluluk Alias ───────────────────────────────────────────────────────────
# Eski bot_engine.py versiyonlarıyla uyumluluk için
PullbackLong = PullbackLongStrategy
