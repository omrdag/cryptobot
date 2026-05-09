"""
Pullback Short Strategy — Temiz Versiyon
pullback_long.py mirror — SHORT yönü
"""
import os
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from pullback_long import (
    SignalResult, _ema, _atr, _rsi, _macd_hist, _vwap,
    _supertrend_bullish, PullbackLongStrategy
)


class PullbackShortStrategy:

    def __init__(self, min_score: int = 6):
        self.min_score = int(os.getenv("LONG_MIN_SCORE", str(min_score)))

    def generate(
        self,
        df:       pd.DataFrame,
        symbol:   str = "",
        hour_utc: int = 12,
        df_1h:    Optional[pd.DataFrame] = None,
        df_4h:    Optional[pd.DataFrame] = None,
    ) -> SignalResult:

        result = SignalResult()

        if not int(os.getenv("PULLBACK_SHORT_ACTIVE", "0")):
            result.reason = "Short devre dışı"
            return result

        if df is None or len(df) < 30:
            result.reason = "Yetersiz veri"
            return result

        close = float(df["close"].iloc[-1])
        if close <= 0:
            result.reason = "Geçersiz fiyat"
            return result

        result.gate_passed = True
        score   = 0
        reasons = []

        # 1. Supertrend bearish → +2
        st_bull, st_level = _supertrend_bullish(df, 10, 3.0)
        if not st_bull:
            score += 2
            reasons.append("✓ ST↓(+2)")
        else:
            reasons.append("✗ ST↑")

        # 2. EMA hizası (9<21<50) → +2
        ema9  = float(_ema(df["close"], 9).iloc[-1])
        ema21 = float(_ema(df["close"], 21).iloc[-1])
        ema50 = float(_ema(df["close"], 50).iloc[-1])
        if ema9 < ema21 < ema50:
            score += 2
            reasons.append("✓ EMA↓↓(+2)")
        elif ema9 < ema21:
            score += 1
            reasons.append("✓ EMA↓(+1)")
        else:
            reasons.append("✗ EMA↑")

        # 3. MACD histogram negatif ve düşüyor → +2
        h_now, h_prev = _macd_hist(df)
        if h_now < 0 and h_now < h_prev:
            score += 2
            reasons.append("✓ MACD↓(+2)")
        elif h_now < 0:
            score += 1
            reasons.append("✓ MACD-(+1)")
        else:
            reasons.append("✗ MACD↑")

        # 4. RSI 30-65 → +1
        rsi_val = _rsi(df)
        if 30 <= rsi_val <= 65:
            score += 1
            reasons.append(f"✓ RSI={rsi_val:.0f}(+1)")
        else:
            reasons.append(f"✗ RSI={rsi_val:.0f}")

        # 5. Fiyat EMA21 altında → +1
        if close < ema21:
            score += 1
            reasons.append("✓ P<EMA21(+1)")
        else:
            reasons.append("✗ P>EMA21")

        # 6. VWAP altında → +1
        vwap_val = _vwap(df)
        if close < vwap_val:
            score += 1
            reasons.append("✓ VWAP(+1)")
        else:
            reasons.append("✗ VWAP")

        result.score  = score
        result.reason = " | ".join(reasons)

        effective_min = self.min_score
        if hour_utc in [1, 2, 3, 4, 5]:
            effective_min += 1

        if score >= effective_min:
            try:
                atr_val = float(_atr(df, 14).iloc[-1])
                sl = close + atr_val * 2.0
                tp = close - atr_val * 4.0
                if tp <= 0:
                    sl = close * 1.03
                    tp = close * 0.94
            except:
                sl = close * 1.03
                tp = close * 0.94

            result.should_enter = True
            result.entry_price  = close
            result.stop_loss    = sl
            result.take_profit  = tp

        result.indicators = {
            "score": score, "close": close,
            "st_bearish": not st_bull, "rsi": rsi_val,
        }
        return result


PullbackShort = PullbackShortStrategy
