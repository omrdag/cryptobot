"""
Pullback Long Strategy — Temiz Versiyon
Tüm gate'ler bonus puana dönüştürüldü.
Tek engel: veri yetersizliği.
"""
import os
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignalResult:
    should_enter: bool  = False
    score:        int   = 0
    entry_price:  float = 0.0
    stop_loss:    float = 0.0
    take_profit:  float = 0.0
    reason:       str   = ""
    gate_passed:  bool  = False
    indicators:   dict  = field(default_factory=dict)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"]  - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _supertrend_bullish(df: pd.DataFrame, period: int = 10, factor: float = 3.0):
    """Returns (bullish: bool, st_level: float)"""
    try:
        hl2   = (df["high"] + df["low"]) / 2
        atr   = _atr(df, period)
        upper = hl2 + factor * atr
        lower = hl2 - factor * atr

        st  = pd.Series(index=df.index, dtype=float)
        dir = pd.Series(index=df.index, dtype=int)
        st.iloc[0]  = float(lower.iloc[0])
        dir.iloc[0] = 1

        for i in range(1, len(df)):
            c = float(df["close"].iloc[i])
            u = float(upper.iloc[i])
            l = float(lower.iloc[i])
            ps = float(st.iloc[i-1])
            pd_ = int(dir.iloc[i-1])
            if pd_ == 1:
                ns = max(l, ps) if c > ps else u
                nd = 1 if c > ns else -1
            else:
                ns = min(u, ps) if c < ps else l
                nd = -1 if c < ns else 1
            st.iloc[i]  = ns
            dir.iloc[i] = nd

        return dir.iloc[-1] == 1, float(st.iloc[-1])
    except:
        return True, 0.0


def _rsi(df: pd.DataFrame, period: int = 14) -> float:
    try:
        delta = df["close"].diff()
        gain  = delta.where(delta > 0, 0).ewm(span=period, adjust=False).mean()
        loss  = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)
        return float((100 - 100 / (1 + rs)).iloc[-1])
    except:
        return 50.0


def _macd_hist(df: pd.DataFrame) -> tuple:
    try:
        fast = _ema(df["close"], 12)
        slow = _ema(df["close"], 26)
        macd = fast - slow
        sig  = _ema(macd, 9)
        hist = macd - sig
        return float(hist.iloc[-1]), float(hist.iloc[-2])
    except:
        return 0.0, 0.0


def _vwap(df: pd.DataFrame) -> float:
    try:
        typical = (df["high"] + df["low"] + df["close"]) / 3
        return float((typical * df["volume"]).cumsum().iloc[-1] /
                     df["volume"].cumsum().iloc[-1])
    except:
        return float(df["close"].iloc[-1])


class PullbackLongStrategy:

    def __init__(self, min_score: int = 6):
        self.min_score = int(os.getenv("LONG_MIN_SCORE", str(min_score)))

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

        # 1. Supertrend 5m → +2
        st_bull, st_level = _supertrend_bullish(df, 10, 3.0)
        if st_bull:
            score += 2
            reasons.append("✓ ST↑(+2)")
        else:
            reasons.append("✗ ST↓")

        # 2. EMA hizası (9>21>50) → +2
        ema9  = float(_ema(df["close"], 9).iloc[-1])
        ema21 = float(_ema(df["close"], 21).iloc[-1])
        ema50 = float(_ema(df["close"], 50).iloc[-1])
        if ema9 > ema21 > ema50:
            score += 2
            reasons.append("✓ EMA↑↑(+2)")
        elif ema9 > ema21:
            score += 1
            reasons.append("✓ EMA↑(+1)")
        else:
            reasons.append("✗ EMA↓")

        # 3. MACD histogram → +2
        h_now, h_prev = _macd_hist(df)
        if h_now > 0 and h_now > h_prev:
            score += 2
            reasons.append("✓ MACD↑(+2)")
        elif h_now > 0:
            score += 1
            reasons.append("✓ MACD+(+1)")
        else:
            reasons.append("✗ MACD↓")

        # 4. RSI 35-70 ideal bölge → +1
        rsi_val = _rsi(df)
        if 35 <= rsi_val <= 70:
            score += 1
            reasons.append(f"✓ RSI={rsi_val:.0f}(+1)")
        else:
            reasons.append(f"✗ RSI={rsi_val:.0f}")

        # 5. Fiyat EMA21 üzerinde → +1
        if close > ema21:
            score += 1
            reasons.append("✓ P>EMA21(+1)")
        else:
            reasons.append("✗ P<EMA21")

        # 6. VWAP üzerinde → +1
        vwap_val = _vwap(df)
        if close > vwap_val:
            score += 1
            reasons.append("✓ VWAP(+1)")
        else:
            reasons.append("✗ VWAP")

        # 7. 4H trend (opsiyonel bonus) → +1
        if df_1h is not None and len(df_1h) >= 25:
            ema9_1h  = float(_ema(df_1h["close"], 9).iloc[-1])
            ema21_1h = float(_ema(df_1h["close"], 21).iloc[-1])
            if ema9_1h > ema21_1h:
                score += 1
                reasons.append("✓ 1H EMA↑(+1)")

        result.score  = score
        result.reason = " | ".join(reasons)

        # Giriş kararı
        effective_min = self.min_score
        if hour_utc in [1, 2, 3, 4, 5]:
            effective_min += 1

        if score >= effective_min:
            # SL/TP hesapla — 1H ATR tercih et, yoksa 5m ATR × 6
            try:
                if df_1h is not None and len(df_1h) >= 15:
                    atr_val = float(_atr(df_1h, 14).iloc[-1])
                else:
                    atr_val = float(_atr(df, 14).iloc[-1]) * 6.0

                sl_mult = float(os.getenv("SL_ATR_MULT", "2.0"))
                sl = close - atr_val * sl_mult
                tp = close + atr_val * sl_mult * 2.5  # 1:2.5 R/R

                # Minimum SL mesafesi: %0.8
                if (close - sl) / close < 0.008:
                    sl = close * 0.992
                    tp = close * (1 + 0.008 * 2.5)
            except:
                sl = close * 0.97
                tp = close * 1.06

            result.should_enter = True
            result.entry_price  = close
            result.stop_loss    = sl
            result.take_profit  = tp

        result.indicators = {
            "score": score, "close": close,
            "st_bullish": st_bull, "rsi": rsi_val,
            "ema9": ema9, "ema21": ema21,
        }
        return result


# Uyumluluk alias
PullbackLong = PullbackLongStrategy
