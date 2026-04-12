"""
Market Regime Engine — Kurumsal Seviye Piyasa Rejimi Tespiti
=============================================================
Her bot döngüsünde ilk çalışan modül.
Sinyal değil, rejim bakılır önce.

5 Rejim:
  1. TREND_UP       — Güçlü yukarı trend, long öncelikli
  2. TREND_DOWN     — Güçlü aşağı trend, short öncelikli
  3. RANGE          — Yatay/chop, grid öncelikli
  4. HIGH_VOL       — Aşırı volatilite, pozisyon küçült
  5. NO_TRADE       — Tehlikeli koşullar, işlem açma

Ölçüm:
  - 1H + 4H ADX (trend gücü)
  - EMA9/21/50 hizası (yön)
  - ATR değişim hızı (volatilite kalitesi)
  - BTC dominans proxy (funding volatility)
  - Funding rate aşırılığı
"""

import os
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


# ── Rejim Sabitleri ───────────────────────────────────────────────────────────
ADX_STRONG_TREND   = float(os.getenv("ADX_STRONG_TREND",   "25"))  # Güçlü trend eşiği
ADX_WEAK_TREND     = float(os.getenv("ADX_WEAK_TREND",     "18"))  # Zayıf trend / range sınırı
ATR_SURGE_MULT     = float(os.getenv("ATR_SURGE_MULT",     "2.0")) # ATR artış çarpanı (yüksek vol)
FUNDING_EXTREME    = float(os.getenv("FUNDING_EXTREME",    "0.05"))# %0.05 = aşırı funding
NO_TRADE_ATR_MULT  = float(os.getenv("NO_TRADE_ATR_MULT",  "3.0")) # Bu kadar ATR artışı → no-trade


@dataclass
class RegimeResult:
    """Rejim analiz sonucu."""
    regime:          str            # TREND_UP / TREND_DOWN / RANGE / HIGH_VOL / NO_TRADE
    confidence:      float          # 0.0 - 1.0 güven skoru
    adx_1h:          float = 0.0
    adx_4h:          float = 0.0
    ema_aligned:     bool  = False  # EMA9 > EMA21 > EMA50
    ema_direction:   str   = "flat" # up / down / flat
    atr_normal:      bool  = True   # ATR normal seviyede mi
    atr_ratio:       float = 1.0    # Güncel ATR / 20-bar ortalama ATR
    funding_extreme: bool  = False  # Aşırı funding var mı
    funding_rate:    float = 0.0
    allow_long:      bool  = True
    allow_short:     bool  = True
    allow_grid:      bool  = True
    position_size_mult: float = 1.0 # Risk çarpanı (0.5 = yarı pozisyon)
    reason:          str   = ""
    timestamp:       str   = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ── İndikatör Hesaplamaları ───────────────────────────────────────────────────

def _ema(s: pd.Series, p: int) -> pd.Series:
    return s.ewm(span=p, adjust=False).mean()


def _atr(df: pd.DataFrame, p: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"]  - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=p, adjust=False).mean()


def _adx(df: pd.DataFrame, p: int = 14) -> float:
    """ADX hesapla — trend gücü ölçümü."""
    try:
        if len(df) < p * 2:
            return 0.0
        high, low, close = df["high"], df["low"], df["close"]
        prev_high = high.shift(1)
        prev_low  = low.shift(1)
        prev_close = close.shift(1)

        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)

        dm_plus  = (high - prev_high).clip(lower=0)
        dm_minus = (prev_low - low).clip(lower=0)

        # DM+ > DM- olmayan yerleri sıfırla
        mask = dm_plus >= dm_minus
        dm_plus  = dm_plus.where(mask, 0)
        dm_minus = dm_minus.where(~mask, 0)

        atr_s   = tr.ewm(span=p, adjust=False).mean()
        di_plus  = 100 * dm_plus.ewm(span=p, adjust=False).mean()  / atr_s.replace(0, np.nan)
        di_minus = 100 * dm_minus.ewm(span=p, adjust=False).mean() / atr_s.replace(0, np.nan)

        dx = 100 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, np.nan)
        adx = dx.ewm(span=p, adjust=False).mean()
        return float(adx.iloc[-1]) if not adx.empty else 0.0
    except Exception:
        return 0.0


def _ema_structure(df: pd.DataFrame) -> tuple:
    """
    EMA9/21/50 yapısını analiz et.
    Returns: (aligned_up, aligned_down, direction)
    """
    try:
        if len(df) < 55:
            return False, False, "flat"
        close = df["close"]
        ema9  = float(_ema(close, 9).iloc[-1])
        ema21 = float(_ema(close, 21).iloc[-1])
        ema50 = float(_ema(close, 50).iloc[-1])
        cur   = float(close.iloc[-1])

        aligned_up   = ema9 > ema21 > ema50 and cur > ema50
        aligned_down = ema9 < ema21 < ema50 and cur < ema50

        # EMA50 eğimi
        ema50_now  = float(_ema(close, 50).iloc[-1])
        ema50_prev = float(_ema(close, 50).iloc[-5]) if len(df) >= 55 else ema50_now
        slope = (ema50_now - ema50_prev) / ema50_prev * 100 if ema50_prev > 0 else 0

        if slope > 0.05:
            direction = "up"
        elif slope < -0.05:
            direction = "down"
        else:
            direction = "flat"

        return aligned_up, aligned_down, direction
    except Exception:
        return False, False, "flat"


def _atr_ratio(df: pd.DataFrame) -> float:
    """
    Güncel ATR / 20-bar ortalama ATR.
    > 2.0 = volatilite patlaması
    """
    try:
        if len(df) < 30:
            return 1.0
        atr_series = _atr(df, 14)
        current    = float(atr_series.iloc[-1])
        avg_20     = float(atr_series.iloc[-20:].mean())
        return current / avg_20 if avg_20 > 0 else 1.0
    except Exception:
        return 1.0


# ── Ana Rejim Tespiti ─────────────────────────────────────────────────────────

def detect_regime(
    df_1h:        pd.DataFrame,
    df_4h:        Optional[pd.DataFrame] = None,
    funding_rate: float = 0.0,
) -> RegimeResult:
    """
    Ana rejim tespiti.

    Args:
        df_1h:        1 saatlik OHLCV (min 60 bar)
        df_4h:        4 saatlik OHLCV (opsiyonel, üst trend teyidi)
        funding_rate: Anlık funding rate (örn: 0.0001 = %0.01)

    Returns:
        RegimeResult
    """
    reasons = []

    # ── 1H analiz ────────────────────────────────────────────────────────────
    adx_1h = _adx(df_1h, 14)
    aligned_up_1h, aligned_down_1h, direction_1h = _ema_structure(df_1h)
    atr_ratio_1h = _atr_ratio(df_1h)

    # ── 4H analiz (varsa) ─────────────────────────────────────────────────────
    adx_4h = 0.0
    aligned_up_4h   = False
    aligned_down_4h = False
    if df_4h is not None and len(df_4h) >= 55:
        adx_4h = _adx(df_4h, 14)
        aligned_up_4h, aligned_down_4h, _ = _ema_structure(df_4h)

    # ── Funding aşırılığı ─────────────────────────────────────────────────────
    funding_extreme = abs(funding_rate) >= FUNDING_EXTREME / 100
    if funding_extreme:
        reasons.append(f"⚠ Aşırı funding rate: %{funding_rate*100:.3f}")

    # ── NO-TRADE: Aşırı volatilite patlaması ──────────────────────────────────
    if atr_ratio_1h >= NO_TRADE_ATR_MULT:
        reasons.append(f"🚫 ATR patlaması: {atr_ratio_1h:.1f}x normal ({NO_TRADE_ATR_MULT}x eşik)")
        return RegimeResult(
            regime             = "NO_TRADE",
            confidence         = min(1.0, atr_ratio_1h / NO_TRADE_ATR_MULT),
            adx_1h             = adx_1h,
            adx_4h             = adx_4h,
            ema_aligned        = False,
            ema_direction      = direction_1h,
            atr_normal         = False,
            atr_ratio          = atr_ratio_1h,
            funding_extreme    = funding_extreme,
            funding_rate       = funding_rate,
            allow_long         = False,
            allow_short        = False,
            allow_grid         = False,
            position_size_mult = 0.0,
            reason             = " | ".join(reasons),
        )

    # ── HIGH_VOL: Yüksek ama yönetilebilir volatilite ─────────────────────────
    if atr_ratio_1h >= ATR_SURGE_MULT:
        reasons.append(f"⚠ Yüksek volatilite: {atr_ratio_1h:.1f}x normal")
        # High vol'da işlem açılabilir ama pozisyon %50 küçültülür
        # Trend varsa devam et ama dikkatli ol
        if adx_1h >= ADX_STRONG_TREND and aligned_up_1h:
            regime = "TREND_UP"
            mult = 0.5
        elif adx_1h >= ADX_STRONG_TREND and aligned_down_1h:
            regime = "TREND_DOWN"
            mult = 0.5
        else:
            regime = "HIGH_VOL"
            mult = 0.3
        reasons.append(f"ADX_1H={adx_1h:.1f} | Pozisyon x{mult}")
        return RegimeResult(
            regime             = regime,
            confidence         = 0.6,
            adx_1h             = adx_1h,
            adx_4h             = adx_4h,
            ema_aligned        = aligned_up_1h or aligned_down_1h,
            ema_direction      = direction_1h,
            atr_normal         = False,
            atr_ratio          = atr_ratio_1h,
            funding_extreme    = funding_extreme,
            funding_rate       = funding_rate,
            allow_long         = regime == "TREND_UP",
            allow_short        = regime == "TREND_DOWN",
            allow_grid         = True,
            position_size_mult = mult,
            reason             = " | ".join(reasons),
        )

    # ── TREND_UP ──────────────────────────────────────────────────────────────
    if adx_1h >= ADX_STRONG_TREND and aligned_up_1h:
        confidence = min(1.0, adx_1h / 50)
        # 4H teyidi varsa güven artar
        if aligned_up_4h:
            confidence = min(1.0, confidence + 0.2)
            reasons.append(f"✓ 4H trend de yukarı")
        # Aşırı pozitif funding → long'da dikkatli ol
        if funding_rate > FUNDING_EXTREME / 100:
            reasons.append(f"⚠ Pozitif funding ({funding_rate*100:.3f}%) — long maliyetli")
            mult = 0.8
        else:
            mult = 1.0
        reasons.append(f"✓ TREND_UP | ADX_1H={adx_1h:.1f} | EMA hizalı yukarı")
        return RegimeResult(
            regime             = "TREND_UP",
            confidence         = confidence,
            adx_1h             = adx_1h,
            adx_4h             = adx_4h,
            ema_aligned        = True,
            ema_direction      = "up",
            atr_normal         = True,
            atr_ratio          = atr_ratio_1h,
            funding_extreme    = funding_extreme,
            funding_rate       = funding_rate,
            allow_long         = True,
            allow_short        = False,   # Trend yukarıyken short açma
            allow_grid         = True,
            position_size_mult = mult,
            reason             = " | ".join(reasons),
        )

    # ── TREND_DOWN ────────────────────────────────────────────────────────────
    if adx_1h >= ADX_STRONG_TREND and aligned_down_1h:
        confidence = min(1.0, adx_1h / 50)
        if aligned_down_4h:
            confidence = min(1.0, confidence + 0.2)
            reasons.append(f"✓ 4H trend de aşağı")
        # Aşırı negatif funding → short'ta dikkatli ol
        if funding_rate < -FUNDING_EXTREME / 100:
            reasons.append(f"⚠ Negatif funding ({funding_rate*100:.3f}%) — short maliyetli")
            mult = 0.8
        else:
            mult = 1.0
        reasons.append(f"✓ TREND_DOWN | ADX_1H={adx_1h:.1f} | EMA hizalı aşağı")
        return RegimeResult(
            regime             = "TREND_DOWN",
            confidence         = confidence,
            adx_1h             = adx_1h,
            adx_4h             = adx_4h,
            ema_aligned        = True,
            ema_direction      = "down",
            atr_normal         = True,
            atr_ratio          = atr_ratio_1h,
            funding_extreme    = funding_extreme,
            funding_rate       = funding_rate,
            allow_long         = False,   # Trend aşağıyken long açma
            allow_short        = True,
            allow_grid         = True,
            position_size_mult = mult,
            reason             = " | ".join(reasons),
        )

    # ── RANGE: Zayıf trend / yatay ────────────────────────────────────────────
    # ADX < 25 veya EMA hizasız
    confidence = max(0.3, 1.0 - adx_1h / ADX_STRONG_TREND)
    reasons.append(
        f"RANGE | ADX_1H={adx_1h:.1f} (<{ADX_STRONG_TREND}) | "
        f"EMA={'hizalı' if (aligned_up_1h or aligned_down_1h) else 'karışık'}"
    )

    # Range'de hem long hem short açılabilir ama daha küçük
    # ADX 18-25 arası → zayıf trend, yarım güçle
    if adx_1h >= ADX_WEAK_TREND:
        allow_long  = direction_1h == "up"
        allow_short = direction_1h == "down"
        mult = 0.7
        reasons.append(f"Zayıf trend ({direction_1h}), x{mult} pozisyon")
    else:
        # ADX < 18 → tam range, sadece grid
        allow_long  = False
        allow_short = False
        mult = 0.0
        reasons.append(f"Tam range/chop (ADX<{ADX_WEAK_TREND}), sadece Grid")

    return RegimeResult(
        regime             = "RANGE",
        confidence         = confidence,
        adx_1h             = adx_1h,
        adx_4h             = adx_4h,
        ema_aligned        = aligned_up_1h or aligned_down_1h,
        ema_direction      = direction_1h,
        atr_normal         = True,
        atr_ratio          = atr_ratio_1h,
        funding_extreme    = funding_extreme,
        funding_rate       = funding_rate,
        allow_long         = allow_long,
        allow_short        = allow_short,
        allow_grid         = True,
        position_size_mult = mult,
        reason             = " | ".join(reasons),
    )


# ── BTC Market Context ────────────────────────────────────────────────────────

def get_btc_regime(
    df_1h_btc: pd.DataFrame,
    df_4h_btc: Optional[pd.DataFrame] = None,
    funding_rate_btc: float = 0.0,
) -> RegimeResult:
    """
    BTC özelinde rejim tespiti.
    BTC rejimi tüm alt coinler için context sağlar.
    """
    return detect_regime(df_1h_btc, df_4h_btc, funding_rate_btc)


def coin_regime_modifier(
    btc_regime: RegimeResult,
    coin_regime: RegimeResult,
) -> RegimeResult:
    """
    Alt coin rejimine BTC context'ini uygula.

    Kurallar:
    - BTC NO_TRADE → tüm altlar NO_TRADE
    - BTC TREND_UP → altlarda long suitability artar
    - BTC TREND_DOWN → altlarda short suitability artar
    - BTC RANGE + Alt TREND → güven azalt
    """
    # BTC tehlikeliyse altlar da tehlikeli
    if btc_regime.regime == "NO_TRADE":
        return RegimeResult(
            regime             = "NO_TRADE",
            confidence         = 0.9,
            adx_1h             = coin_regime.adx_1h,
            adx_4h             = coin_regime.adx_4h,
            allow_long         = False,
            allow_short        = False,
            allow_grid         = False,
            position_size_mult = 0.0,
            reason             = f"BTC NO_TRADE → tüm altlar durduruldu | {coin_regime.reason}",
        )

    # BTC HIGH_VOL → alt pozisyon boyutunu küçült
    if btc_regime.regime == "HIGH_VOL":
        modified = RegimeResult(
            regime             = coin_regime.regime,
            confidence         = coin_regime.confidence * 0.7,
            adx_1h             = coin_regime.adx_1h,
            adx_4h             = coin_regime.adx_4h,
            ema_aligned        = coin_regime.ema_aligned,
            ema_direction      = coin_regime.ema_direction,
            atr_normal         = False,
            atr_ratio          = coin_regime.atr_ratio,
            funding_extreme    = coin_regime.funding_extreme,
            funding_rate       = coin_regime.funding_rate,
            allow_long         = coin_regime.allow_long,
            allow_short        = coin_regime.allow_short,
            allow_grid         = coin_regime.allow_grid,
            position_size_mult = coin_regime.position_size_mult * 0.6,
            reason             = f"BTC HIGH_VOL → pozisyon küçültüldü | {coin_regime.reason}",
        )
        return modified

    # BTC ve alt ters yönde → güven azalt
    if (btc_regime.regime == "TREND_UP" and coin_regime.regime == "TREND_DOWN") or \
       (btc_regime.regime == "TREND_DOWN" and coin_regime.regime == "TREND_UP"):
        modified_reason = f"⚠ BTC/alt yön uyumsuzluğu | {coin_regime.reason}"
        return RegimeResult(
            regime             = "RANGE",  # Uyumsuz → range gibi davran
            confidence         = coin_regime.confidence * 0.5,
            adx_1h             = coin_regime.adx_1h,
            adx_4h             = coin_regime.adx_4h,
            ema_aligned        = False,
            ema_direction      = "flat",
            atr_normal         = coin_regime.atr_normal,
            atr_ratio          = coin_regime.atr_ratio,
            funding_extreme    = coin_regime.funding_extreme,
            funding_rate       = coin_regime.funding_rate,
            allow_long         = False,
            allow_short        = False,
            allow_grid         = True,
            position_size_mult = 0.0,
            reason             = modified_reason,
        )

    # BTC TREND_UP + alt de uyumlu → confidence boost
    if btc_regime.regime == "TREND_UP" and coin_regime.regime == "TREND_UP":
        return RegimeResult(
            regime             = "TREND_UP",
            confidence         = min(1.0, coin_regime.confidence + 0.15),
            adx_1h             = coin_regime.adx_1h,
            adx_4h             = coin_regime.adx_4h,
            ema_aligned        = True,
            ema_direction      = "up",
            atr_normal         = coin_regime.atr_normal,
            atr_ratio          = coin_regime.atr_ratio,
            funding_extreme    = coin_regime.funding_extreme,
            funding_rate       = coin_regime.funding_rate,
            allow_long         = True,
            allow_short        = False,
            allow_grid         = True,
            position_size_mult = min(1.2, coin_regime.position_size_mult + 0.2),
            reason             = f"✓ BTC+Alt uyumlu yukarı | {coin_regime.reason}",
        )

    # Diğer durumlar — coin rejimini olduğu gibi döndür
    return coin_regime


# ── Rejim Özeti ───────────────────────────────────────────────────────────────

def regime_summary(regime: RegimeResult) -> str:
    """Dashboard/log için kısa özet."""
    icons = {
        "TREND_UP":   "📈",
        "TREND_DOWN": "📉",
        "RANGE":      "↔️",
        "HIGH_VOL":   "⚡",
        "NO_TRADE":   "🚫",
    }
    icon = icons.get(regime.regime, "?")
    return (
        f"{icon} {regime.regime} "
        f"(güven:{regime.confidence:.0%} | "
        f"ADX:{regime.adx_1h:.0f} | "
        f"ATR:{regime.atr_ratio:.1f}x | "
        f"pos_mult:{regime.position_size_mult:.1f})"
    )
