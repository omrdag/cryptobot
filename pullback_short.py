"""
Pullback Short Strategy v4 — Global Kanıtlanmış Sinyal Motoru
==============================================================
pullback_long.py'nin ayna versiyonu — SHORT yönü için.

Gate koşulları:
  1. Supertrend bearish (fiyat ST altında)
  2. 4H EMA50 aşağı eğimli
  3. Volume spike (1.2x MA20)

Bonus puanlar (max 8):
  4. ST yeni kırmızıya döndü (flip)    → +2
  5. Çift ST hemfikir bearish          → +1
  6. MACD histogram negatif ve düşüyor → +1
  7. RSI 35-60 arası                   → +1
  8. VWAP altında                      → +1
  9. 1H EMA9 < EMA21                   → +1
 10. 4H RSI 30-55 arası               → +1
"""

import os
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

# pullback_long'dan hesaplama fonksiyonlarını al
from pullback_long import (
    _ema, _atr, _supertrend, _macd, _rsi, _vwap, SignalResult
)


class PullbackShortStrategy:

    def __init__(self, min_score: int = 7):
        self.min_score = int(os.getenv("LONG_MIN_SCORE", str(min_score)))

    def _gate_supertrend_bearish(self, df: pd.DataFrame) -> tuple[bool, float]:
        st, direction = _supertrend(df, atr_period=10, factor=3.0)
        if len(direction) < 3:
            return False, 0.0
        bearish  = direction.iloc[-1] == -1
        st_level = float(st.iloc[-1])
        return bearish, st_level

    def _gate_4h_trend_down(self, df_4h: Optional[pd.DataFrame]) -> bool:
        if df_4h is None or len(df_4h) < 55:
            return True
        ema50 = _ema(df_4h["close"], 50)
        return float(ema50.iloc[-1]) < float(ema50.iloc[-3])

    def _gate_volume(self, df: pd.DataFrame) -> bool:
        if len(df) < 22:
            return True
        vol_ma20 = df["volume"].rolling(20).mean().iloc[-1]
        return df["volume"].iloc[-1] > vol_ma20 * 1.2

    def _score_supertrend_flip(self, df: pd.DataFrame) -> int:
        try:
            _, direction = _supertrend(df, atr_period=10, factor=3.0)
            if len(direction) < 5:
                return 0
            if direction.iloc[-1] == -1 and any(direction.iloc[-4:-1] == 1):
                return 2
            return 0
        except:
            return 0

    def _score_dual_supertrend(self, df: pd.DataFrame) -> int:
        try:
            _, dir_slow = _supertrend(df, atr_period=10, factor=3.0)
            _, dir_fast = _supertrend(df, atr_period=7,  factor=2.0)
            if dir_slow.iloc[-1] == -1 and dir_fast.iloc[-1] == -1:
                return 1
            return 0
        except:
            return 0

    def _score_macd(self, df: pd.DataFrame) -> int:
        try:
            _, _, hist = _macd(df)
            if len(hist) < 4:
                return 0
            h_now  = float(hist.iloc[-1])
            h_prev = float(hist.iloc[-2])
            if h_now < 0 and h_now < h_prev:  # negatif ve düşüyor
                return 1
            return 0
        except:
            return 0

    def _score_rsi(self, df: pd.DataFrame) -> int:
        try:
            rsi_val = float(_rsi(df).iloc[-1])
            if 35 <= rsi_val <= 60:
                return 1
            return 0
        except:
            return 0

    def _score_vwap(self, df: pd.DataFrame) -> int:
        try:
            vwap_val = float(_vwap(df).iloc[-1])
            close    = float(df["close"].iloc[-1])
            return 1 if close < vwap_val else 0
        except:
            return 0

    def _score_ema_trend(self, df_1h: Optional[pd.DataFrame]) -> int:
        if df_1h is None or len(df_1h) < 25:
            return 0
        try:
            ema9  = float(_ema(df_1h["close"], 9).iloc[-1])
            ema21 = float(_ema(df_1h["close"], 21).iloc[-1])
            return 1 if ema9 < ema21 else 0
        except:
            return 0

    def _score_4h_rsi(self, df_4h: Optional[pd.DataFrame]) -> int:
        if df_4h is None or len(df_4h) < 16:
            return 0
        try:
            rsi_4h = float(_rsi(df_4h).iloc[-1])
            return 1 if 30 <= rsi_4h <= 55 else 0
        except:
            return 0

    def _calc_sl_tp(self, df: pd.DataFrame, df_1h: Optional[pd.DataFrame],
                    entry: float, st_level: float) -> tuple[float, float]:
        try:
            if df_1h is not None and len(df_1h) >= 15:
                atr_1h = float(_atr(df_1h, 14).iloc[-1])
            else:
                atr_1h = float(_atr(df, 14).iloc[-1]) * 3

            sl_mult = float(os.getenv("SL_ATR_MULT", "1.5"))
            sl_from_st  = st_level * 1.002
            sl_from_atr = entry + atr_1h * sl_mult
            sl  = min(sl_from_st, sl_from_atr)  # daha aşağıdaki

            risk = sl - entry
            if risk <= 0:
                risk = entry * 0.015
                sl   = entry + risk

            tp_mult = float(os.getenv("TP2_R_MULT", "1.0"))
            tp = entry - risk * tp_mult * 2

            return sl, tp
        except:
            sl = entry * (1 + 0.015)
            tp = entry * (1 - 0.03)
            return sl, tp

    def generate(
        self,
        df:       pd.DataFrame,
        symbol:   str = "",
        hour_utc: int = 12,
        df_1h:    Optional[pd.DataFrame] = None,
        df_4h:    Optional[pd.DataFrame] = None,
    ) -> SignalResult:

        result = SignalResult()

        if df is None or len(df) < 55:
            result.reason = "Yetersiz veri"
            return result

        close = float(df["close"].iloc[-1])

        st_bearish, st_level = self._gate_supertrend_bearish(df)
        if not st_bearish:
            result.reason = f"✗ Gate: Supertrend bullish (ST ${st_level:.4f})"
            return result

        trend_4h_ok = self._gate_4h_trend_down(df_4h)
        if not trend_4h_ok:
            result.reason = "✗ Gate: 4H EMA50 yukarı eğimli (büyük trend bullish)"
            return result

        vol_ok = self._gate_volume(df)
        if not vol_ok:
            result.reason = "✗ Gate: Hacim zayıf"
            return result

        result.gate_passed = True

        score   = 0
        reasons = []

        s_flip = self._score_supertrend_flip(df)
        score += s_flip
        reasons.append("✓ ST flip (yeni kırmızı +2)" if s_flip == 2 else "✗ ST flip yok")

        s_dual = self._score_dual_supertrend(df)
        score += s_dual
        reasons.append("✓ Çift ST hemfikir" if s_dual else "✗ Çift ST çakışmıyor")

        s_macd = self._score_macd(df)
        score += s_macd
        reasons.append("✓ MACD histogram ↓" if s_macd else "✗ MACD short zayıf")

        s_rsi = self._score_rsi(df)
        score += s_rsi
        try:
            rsi_val = float(_rsi(df).iloc[-1])
            reasons.append(f"{'✓' if s_rsi else '✗'} RSI={rsi_val:.1f} (ideal:35-60)")
        except:
            reasons.append("✗ RSI hesaplanamadı")

        s_vwap = self._score_vwap(df)
        score += s_vwap
        reasons.append("✓ VWAP altında" if s_vwap else "✗ VWAP üzerinde")

        s_ema = self._score_ema_trend(df_1h)
        score += s_ema
        reasons.append("✓ 1H EMA9<EMA21" if s_ema else "✗ 1H EMA trend yok")

        s_4h_rsi = self._score_4h_rsi(df_4h)
        score += s_4h_rsi
        reasons.append("✓ 4H RSI bearish zonu" if s_4h_rsi else "✗ 4H RSI dışında")

        result.score = score

        effective_min = self.min_score
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
            "supertrend_bearish":  True,
            "supertrend_flip":     s_flip == 2,
            "dual_supertrend":     s_dual == 1,
            "macd_negative":       s_macd == 1,
            "rsi_zone":            s_rsi == 1,
            "vwap_below":          s_vwap == 1,
            "ema_trend":           s_ema == 1,
            "4h_rsi_ok":           s_4h_rsi == 1,
            "score":               score,
        }

        return result


PullbackShort = PullbackShortStrategy
