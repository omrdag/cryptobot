"""
Market Regime Filter
====================
Piyasanın hangi modda olduğunu tespit eder ve stratejilerin
hangi rejimde aktif olacağını belirler.

Rejimler:
  TRENDING_UP    → Güçlü yükselen trend
  TRENDING_DOWN  → Güçlü düşen trend
  RANGING        → Yatay / sıkışma
  HIGH_VOLATILITY → Çok oynak piyasa
  WEAK_LIQUIDITY  → Düşük hacim / likidite sorunu
  UNKNOWN         → Yeterli veri yok

Kullanım:
    regime_filter = MarketRegimeFilter()
    regime = regime_filter.detect(df)
    if regime.is_trending:
        # trend stratejisi çalışsın
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional
from utils.logger import get_logger

logger = get_logger()


class Regime:
    TRENDING_UP     = "TRENDING_UP"
    TRENDING_DOWN   = "TRENDING_DOWN"
    RANGING         = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    WEAK_LIQUIDITY  = "WEAK_LIQUIDITY"
    UNKNOWN         = "UNKNOWN"


@dataclass
class RegimeResult:
    regime:           str
    trend_strength:   float   # 0-100 (ADX-like)
    volatility_ratio: float   # ATR / price ratio
    volume_ratio:     float   # son hacim / ortalama hacim
    bb_width_pct:     float   # Bollinger Band genişliği %
    price_vs_ema200:  float   # Fiyat - EMA200 / EMA200 (%)
    confidence:       float   # 0-100 rejim güveni
    details:          str     = ""

    @property
    def is_trending(self) -> bool:
        return self.regime in (Regime.TRENDING_UP, Regime.TRENDING_DOWN)

    @property
    def is_ranging(self) -> bool:
        return self.regime == Regime.RANGING

    @property
    def is_tradeable(self) -> bool:
        return self.regime not in (Regime.WEAK_LIQUIDITY, Regime.UNKNOWN)

    @property
    def is_high_vol(self) -> bool:
        return self.regime == Regime.HIGH_VOLATILITY


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


def _adx_approx(df: pd.DataFrame, period: int = 14) -> float:
    """
    Approximate ADX using directional movement.
    Returns 0-100 trend strength score.
    """
    if len(df) < period + 5:
        return 0.0

    high  = df["high"]
    low   = df["low"]
    close = df["close"]

    dm_plus  = (high - high.shift(1)).clip(lower=0)
    dm_minus = (low.shift(1) - low).clip(lower=0)

    # Resolve when both are positive
    mask = (dm_plus > 0) & (dm_minus > 0)
    dm_plus_clean  = dm_plus.where(dm_plus > dm_minus, 0)
    dm_minus_clean = dm_minus.where(dm_minus > dm_plus, 0)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr_s  = tr.ewm(span=period, adjust=False).mean()
    di_plus  = (dm_plus_clean.ewm(span=period, adjust=False).mean()  / atr_s * 100).fillna(0)
    di_minus = (dm_minus_clean.ewm(span=period, adjust=False).mean() / atr_s * 100).fillna(0)

    dx = (abs(di_plus - di_minus) / (di_plus + di_minus + 1e-9) * 100).fillna(0)
    adx = dx.ewm(span=period, adjust=False).mean()

    return float(adx.iloc[-1])


class MarketRegimeFilter:
    """
    Piyasa rejimini tespit eder.
    Her strateji kendi için uygun rejimleri belirtir.
    """

    def __init__(
        self,
        # ADX thresholds
        trend_strong_adx:    float = 22.0,   # Scalping: 22 ADX yeterli
        trend_very_strong:   float = 40.0,   # ADX > 40 → very strong trend
        # ATR / price thresholds
        high_vol_threshold:  float = 0.025,  # Scalping: %2.5 üstü yüksek volatilite
        low_vol_threshold:   float = 0.005,  # ATR/price < 0.5% → low volatility
        # Bollinger Band width for ranging detection
        ranging_bb_width:    float = 0.025,  # Scalping: daha dar BB = ranging
        # Volume thresholds
        min_volume_ratio:    float = 0.6,    # Scalping: hacim minimum %60 olmalı
        # EMA for trend direction
        fast_ema:            int   = 20,
        slow_ema:            int   = 50,
        trend_ema:           int   = 200,
    ):
        self.trend_strong_adx   = trend_strong_adx
        self.trend_very_strong  = trend_very_strong
        self.high_vol_threshold = high_vol_threshold
        self.low_vol_threshold  = low_vol_threshold
        self.ranging_bb_width   = ranging_bb_width
        self.min_volume_ratio   = min_volume_ratio
        self.fast_ema           = fast_ema
        self.slow_ema           = slow_ema
        self.trend_ema          = trend_ema

    def detect(self, df: pd.DataFrame) -> RegimeResult:
        """
        DataFrame'den piyasa rejimini tespit et.
        Returns: RegimeResult
        """
        min_bars = max(self.trend_ema, 50) + 5
        if df is None or len(df) < min_bars:
            return RegimeResult(
                regime=Regime.UNKNOWN, trend_strength=0, volatility_ratio=0,
                volume_ratio=0, bb_width_pct=0, price_vs_ema200=0,
                confidence=0, details="Yetersiz veri"
            )

        close  = df["close"]
        price  = float(close.iloc[-1])

        # ── İndikatörler ──────────────────────────────────────────────────────
        atr_val  = float(_atr(df, 14).iloc[-1])
        ema_fast = float(_ema(close, self.fast_ema).iloc[-1])
        ema_slow = float(_ema(close, self.slow_ema).iloc[-1])
        ema_200  = float(_ema(close, self.trend_ema).iloc[-1])

        # ADX (trend gücü)
        adx = _adx_approx(df, 14)

        # ATR / Price ratio (volatilite)
        vol_ratio = atr_val / price if price > 0 else 0

        # Bollinger Band genişliği (ranging tespiti)
        bb_mid = float(close.rolling(20).mean().iloc[-1])
        bb_std = float(close.rolling(20).std().iloc[-1])
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_width = (bb_upper - bb_lower) / bb_mid if bb_mid > 0 else 0

        # Volume ratio
        if "volume" in df.columns:
            last_vol = float(df["volume"].iloc[-1])
            avg_vol  = float(df["volume"].tail(50).mean())
            vol_ratio_v = last_vol / avg_vol if avg_vol > 0 else 1.0
        else:
            vol_ratio_v = 1.0

        # Price vs EMA200
        price_vs_200 = (price - ema_200) / ema_200 * 100 if ema_200 > 0 else 0

        # ── Rejim Tespiti ─────────────────────────────────────────────────────
        details_list = []

        # 1. Zayıf likidite
        if vol_ratio_v < self.min_volume_ratio:
            return RegimeResult(
                regime=Regime.WEAK_LIQUIDITY,
                trend_strength=adx,
                volatility_ratio=vol_ratio,
                volume_ratio=vol_ratio_v,
                bb_width_pct=bb_width * 100,
                price_vs_ema200=price_vs_200,
                confidence=85,
                details=f"Hacim düşük ({vol_ratio_v:.2f}x ortalama)"
            )

        # 2. Yüksek volatilite (işlem edilebilir ama riskli)
        if vol_ratio > self.high_vol_threshold:
            details_list.append(f"Yüksek volatilite (ATR/fiyat={vol_ratio:.3f})")
            # Trend de varsa TRENDING olarak devam et, yoksa HIGH_VOLATILITY
            if adx < self.trend_strong_adx:
                return RegimeResult(
                    regime=Regime.HIGH_VOLATILITY,
                    trend_strength=adx, volatility_ratio=vol_ratio,
                    volume_ratio=vol_ratio_v, bb_width_pct=bb_width * 100,
                    price_vs_ema200=price_vs_200, confidence=80,
                    details="; ".join(details_list)
                )

        # 3. Güçlü trend mi?
        if adx >= self.trend_strong_adx:
            uptrend   = ema_fast > ema_slow and price > ema_200
            downtrend = ema_fast < ema_slow and price < ema_200

            if uptrend:
                confidence = min(100, 50 + adx)
                return RegimeResult(
                    regime=Regime.TRENDING_UP,
                    trend_strength=adx, volatility_ratio=vol_ratio,
                    volume_ratio=vol_ratio_v, bb_width_pct=bb_width * 100,
                    price_vs_ema200=price_vs_200, confidence=confidence,
                    details=f"ADX={adx:.1f} | EMA{self.fast_ema}>{self.slow_ema} | Fiyat>EMA{self.trend_ema}"
                )
            elif downtrend:
                confidence = min(100, 50 + adx)
                return RegimeResult(
                    regime=Regime.TRENDING_DOWN,
                    trend_strength=adx, volatility_ratio=vol_ratio,
                    volume_ratio=vol_ratio_v, bb_width_pct=bb_width * 100,
                    price_vs_ema200=price_vs_200, confidence=confidence,
                    details=f"ADX={adx:.1f} | EMA{self.fast_ema}<{self.slow_ema} | Fiyat<EMA{self.trend_ema}"
                )

        # 4. Ranging (BB dar + ADX zayıf)
        if bb_width < self.ranging_bb_width and adx < self.trend_strong_adx:
            return RegimeResult(
                regime=Regime.RANGING,
                trend_strength=adx, volatility_ratio=vol_ratio,
                volume_ratio=vol_ratio_v, bb_width_pct=bb_width * 100,
                price_vs_ema200=price_vs_200, confidence=70,
                details=f"BB genişliği={bb_width*100:.2f}% | ADX={adx:.1f}"
            )

        # 5. Belirsiz / Zayıf trend — v2: RANGING olarak işaretle
        # Eski kod: sadece fiyat > EMA200'e bakarak TRENDING_UP sayıyordu.
        # Bu, signal_scorer'ın yanlışlıkla TRENDING_DOWN bloğunu atlamasına yol açıyordu.
        # Düzeltme: ADX < trend_strong_adx ise RANGING dön (daha güvenli).
        return RegimeResult(
            regime=Regime.RANGING,
            trend_strength=adx, volatility_ratio=vol_ratio,
            volume_ratio=vol_ratio_v, bb_width_pct=bb_width * 100,
            price_vs_ema200=price_vs_200, confidence=35,
            details=f"Belirsiz rejim — ADX zayıf ({adx:.1f}) | RANGING olarak işaretlendi"
        )
