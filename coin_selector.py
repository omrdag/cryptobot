"""
Coin Selection Engine — Cross-Sectional Momentum Skorlaması
===========================================================
Her döngüde coin evrenini skorlayıp en uygun long/short coinleri seçer.

Felsefe:
  - Tüm coinlerde kör şekilde işlem açma
  - Göreceli olarak en güçlü coinler → long aday
  - Göreceli olarak en zayıf coinler  → short aday
  - Düşük hacimli / manipülatif coinleri ele
  - Tier sistemi: Tier1 her zaman, Tier2 koşullara bağlı

Skor Bileşenleri (toplam 100 puan):
  [25] 7 günlük getiri (momentum kısa vade)
  [20] 30 günlük getiri (momentum orta vade)
  [20] Hacim artışı (kurumsal ilgi)
  [15] Trend uyumu (EMA yapısı)
  [10] Volatilite kalitesi (ATR stabilitesi)
  [10] Funding cezası (pozisyon maliyeti)
  [-]  Spread / likidite cezası (uygulanabilirlik)
"""

import os
import time
import pandas as pd
import numpy as np
import urllib.request
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone


# ── Coin Evreni Tanımı ────────────────────────────────────────────────────────

TIER_1 = [
    "BTC-USDT-SWAP",   # Bitcoin — en likit, ana barikat
    "ETH-USDT-SWAP",   # Ethereum — en derin market
    "SOL-USDT-SWAP",   # Solana — yüksek volatilite, likit
    "BNB-USDT-SWAP",   # BNB — stabil hacim
]

TIER_2 = [
    "AVAX-USDT-SWAP",  # Avalanche
    "LINK-USDT-SWAP",  # Chainlink
    "DOT-USDT-SWAP",   # Polkadot
    "MATIC-USDT-SWAP", # Polygon
    "ADA-USDT-SWAP",   # Cardano
    "ATOM-USDT-SWAP",  # Cosmos
]

# Varsayılan aktif coin evreni (env ile override edilebilir)
DEFAULT_UNIVERSE = TIER_1 + TIER_2[:2]  # BTC+ETH+SOL+BNB+AVAX+LINK

# Konfig
MAX_LONG_COINS  = int(os.getenv("MAX_LONG_COINS",  "3"))
MAX_SHORT_COINS = int(os.getenv("MAX_SHORT_COINS", "3"))
MIN_VOLUME_24H  = float(os.getenv("MIN_VOLUME_24H", "50000000"))  # $50M min günlük hacim
TIER2_REGIME_GATE = os.getenv("TIER2_REGIME_GATE", "TREND_UP,TREND_DOWN")  # Tier2 sadece trend'de


@dataclass
class CoinScore:
    """Tek coin için skor sonucu."""
    inst_id:          str
    symbol:           str
    tier:             int    # 1 veya 2
    long_score:       float  # 0-100 long uygunluğu
    short_score:      float  # 0-100 short uygunluğu
    momentum_7d:      float  # 7 günlük getiri %
    momentum_30d:     float  # 30 günlük getiri %
    volume_score:     float  # Hacim artış skoru
    trend_score:      float  # EMA uyum skoru
    volatility_score: float  # Volatilite kalite skoru
    funding_penalty:  float  # Funding cezası (0=yok, negatif=ceza)
    volume_24h_usd:   float  # 24s hacim USD
    eligible:         bool   # Tüm filtreleri geçti mi
    rejection_reason: str    = ""
    current_price:    float  = 0.0
    timestamp:        str    = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class SelectionResult:
    """Coin seçim sonucu."""
    long_candidates:  List[CoinScore] = field(default_factory=list)
    short_candidates: List[CoinScore] = field(default_factory=list)
    eliminated:       List[CoinScore] = field(default_factory=list)
    all_scores:       List[CoinScore] = field(default_factory=list)
    timestamp:        str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def top_long(self, n: int = None) -> List[CoinScore]:
        n = n or MAX_LONG_COINS
        return self.long_candidates[:n]

    def top_short(self, n: int = None) -> List[CoinScore]:
        n = n or MAX_SHORT_COINS
        return self.short_candidates[:n]


# ── OKX Veri Çekme ───────────────────────────────────────────────────────────

def _okx_get(path: str, timeout: int = 8) -> dict:
    try:
        url = "https://www.okx.com" + path
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/3.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e), "data": []}


def get_ticker_24h(inst_id: str) -> dict:
    """24s ticker verisi — fiyat, hacim, değişim."""
    data = _okx_get(f"/api/v5/market/ticker?instId={inst_id}")
    if data.get("data"):
        t = data["data"][0]
        return {
            "last":       float(t.get("last", 0)),
            "vol24h":     float(t.get("vol24h", 0)),      # coin bazlı
            "volCcy24h":  float(t.get("volCcy24h", 0)),   # USDT bazlı
            "chg24h_pct": float(t.get("chgUtc0", 0)),
            "high24h":    float(t.get("high24h", 0)),
            "low24h":     float(t.get("low24h", 0)),
        }
    return {}


def get_candles(inst_id: str, bar: str = "1D", limit: int = 35) -> pd.DataFrame:
    """OHLCV mum verisi."""
    data = _okx_get(f"/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}")
    if not data.get("data"):
        return pd.DataFrame()
    cols = ["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"]
    try:
        df = pd.DataFrame(data["data"], columns=cols[:len(data["data"][0])])
        df = df[df["confirm"] == "1"] if "confirm" in df.columns else df
        for c in ["open", "high", "low", "close", "vol"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.sort_values("ts").reset_index(drop=True)
        return df
    except Exception:
        return pd.DataFrame()


def get_funding_rate(inst_id: str) -> float:
    """Anlık funding rate."""
    data = _okx_get(f"/api/v5/public/funding-rate?instId={inst_id}")
    if data.get("data"):
        return float(data["data"][0].get("fundingRate", 0))
    return 0.0


# ── Skor Hesaplama ────────────────────────────────────────────────────────────

def _momentum_score(df_daily: pd.DataFrame) -> Tuple[float, float]:
    """
    7 ve 30 günlük momentum hesapla.
    Returns: (mom_7d_pct, mom_30d_pct)
    """
    try:
        if len(df_daily) < 8:
            return 0.0, 0.0
        close = df_daily["close"].values
        mom_7  = (close[-1] / close[-8]  - 1) * 100 if len(close) >= 8  else 0.0
        mom_30 = (close[-1] / close[-31] - 1) * 100 if len(close) >= 31 else 0.0
        return float(mom_7), float(mom_30)
    except Exception:
        return 0.0, 0.0


def _volume_trend_score(df_daily: pd.DataFrame) -> float:
    """
    Son 7 günlük ortalama hacim / 30 günlük ortalama hacim.
    > 1.2 = hacim artıyor (kurumsal ilgi) → yüksek skor
    < 0.8 = hacim azalıyor → düşük skor
    """
    try:
        if len(df_daily) < 31 or "vol" not in df_daily.columns:
            return 50.0
        vol = df_daily["vol"].values
        avg_7  = np.mean(vol[-7:])
        avg_30 = np.mean(vol[-30:])
        ratio  = avg_7 / avg_30 if avg_30 > 0 else 1.0
        # 0.5x - 2.0x arasını 0-100'e dönüştür
        score = (ratio - 0.5) / (2.0 - 0.5) * 100
        return float(np.clip(score, 0, 100))
    except Exception:
        return 50.0


def _ema_trend_score(df_daily: pd.DataFrame) -> float:
    """
    EMA9/21/50 hizalaması skoru.
    Tam yukarı hizalı = 100, tam aşağı = 0, karışık = 50
    """
    try:
        if len(df_daily) < 55:
            return 50.0
        close = df_daily["close"]
        ema9  = float(close.ewm(span=9,  adjust=False).mean().iloc[-1])
        ema21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
        ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
        cur   = float(close.iloc[-1])

        if ema9 > ema21 > ema50 and cur > ema50:
            return 90.0  # Güçlü yukarı
        elif ema9 > ema21 and cur > ema21:
            return 70.0  # Orta yukarı
        elif ema9 < ema21 < ema50 and cur < ema50:
            return 10.0  # Güçlü aşağı
        elif ema9 < ema21 and cur < ema21:
            return 30.0  # Orta aşağı
        else:
            return 50.0  # Karışık
    except Exception:
        return 50.0


def _volatility_quality_score(df_daily: pd.DataFrame) -> float:
    """
    Volatilite kalitesi: düşük ama tutarlı ATR iyi, aşırı yüksek kötü.
    Hedef: ATR/fiyat %1-8 arası ideal.
    """
    try:
        if len(df_daily) < 15:
            return 50.0
        close = df_daily["close"]
        high  = df_daily["high"]
        low   = df_daily["low"]
        prev  = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev).abs(),
            (low  - prev).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.ewm(span=14, adjust=False).mean().iloc[-1])
        cur = float(close.iloc[-1])
        atr_pct = atr / cur * 100 if cur > 0 else 0

        if 1.0 <= atr_pct <= 5.0:
            return 90.0   # İdeal aralık
        elif 0.5 <= atr_pct < 1.0 or 5.0 < atr_pct <= 8.0:
            return 65.0   # Kabul edilebilir
        elif atr_pct < 0.5:
            return 30.0   # Çok düşük vol — fırsat yok
        else:
            return 20.0   # Çok yüksek — riskli
    except Exception:
        return 50.0


def _funding_penalty(funding_rate: float) -> float:
    """
    Funding cezası hesapla.
    Yüksek pozitif funding → long maliyetli → ceza
    Yüksek negatif funding → short maliyetli → ceza
    Returns: 0 (ceza yok) ile -30 (max ceza) arasında
    """
    abs_rate = abs(funding_rate) * 100  # Yüzdeye çevir
    if abs_rate < 0.01:
        return 0.0         # Normal funding, ceza yok
    elif abs_rate < 0.03:
        return -5.0        # Hafif ceza
    elif abs_rate < 0.05:
        return -15.0       # Orta ceza
    else:
        return -30.0       # Ağır ceza (aşırı funding)


def _compute_long_short_scores(
    mom_7d:     float,
    mom_30d:    float,
    vol_score:  float,
    trend_score: float,
    vol_quality: float,
    funding_rate: float,
) -> Tuple[float, float]:
    """
    Long ve Short skorlarını hesapla (0-100).
    """
    funding_pen = _funding_penalty(funding_rate)

    # Long skoru: momentum yukarıysa yüksek
    long_score = (
        _normalize_momentum(mom_7d,  -30, 30)  * 0.25 +   # 7g momentum
        _normalize_momentum(mom_30d, -50, 50)  * 0.20 +   # 30g momentum
        vol_score                               * 0.20 +   # Hacim artışı
        trend_score                             * 0.15 +   # EMA uyumu
        vol_quality                             * 0.10 +   # Volatilite kalitesi
        50                                      * 0.10     # Base
    )
    # Pozitif funding → long maliyetli
    if funding_rate > 0:
        long_score += funding_pen

    # Short skoru: momentum aşağıysa yüksek
    short_score = (
        _normalize_momentum(-mom_7d,  -30, 30) * 0.25 +   # Ters momentum
        _normalize_momentum(-mom_30d, -50, 50) * 0.20 +
        vol_score                               * 0.20 +
        (100 - trend_score)                     * 0.15 +   # Ters EMA
        vol_quality                             * 0.10 +
        50                                      * 0.10
    )
    # Negatif funding → short maliyetli
    if funding_rate < 0:
        short_score += funding_pen

    return float(np.clip(long_score, 0, 100)), float(np.clip(short_score, 0, 100))


def _normalize_momentum(mom: float, low: float, high: float) -> float:
    """Momentum değerini 0-100 arasına normalize et."""
    return float(np.clip((mom - low) / (high - low) * 100, 0, 100))


# ── Ana Seçim Fonksiyonu ──────────────────────────────────────────────────────

def score_coins(
    universe: List[str] = None,
    regime:   str       = "RANGE",
    max_long: int       = None,
    max_short: int      = None,
) -> SelectionResult:
    """
    Coin evrenini skorla ve en iyi long/short adayları seç.

    Args:
        universe:  Coin listesi (inst_id formatında)
        regime:    Mevcut piyasa rejimi (TREND_UP/DOWN/RANGE/HIGH_VOL/NO_TRADE)
        max_long:  Max long aday sayısı
        max_short: Max short aday sayısı

    Returns:
        SelectionResult
    """
    universe  = universe  or DEFAULT_UNIVERSE
    max_long  = max_long  or MAX_LONG_COINS
    max_short = max_short or MAX_SHORT_COINS

    scores     = []
    eliminated = []

    for inst_id in universe:
        sym = inst_id.replace("-USDT-SWAP", "USDT")

        # Tier belirleme
        tier = 1 if inst_id in TIER_1 else 2

        # Tier 2 için rejim kapısı
        if tier == 2:
            allowed_regimes = TIER2_REGIME_GATE.split(",")
            if regime not in allowed_regimes:
                eliminated.append(CoinScore(
                    inst_id=inst_id, symbol=sym, tier=tier,
                    long_score=0, short_score=0,
                    momentum_7d=0, momentum_30d=0,
                    volume_score=0, trend_score=0,
                    volatility_score=0, funding_penalty=0,
                    volume_24h_usd=0, eligible=False,
                    rejection_reason=f"Tier2 — rejim {regime} izin vermiyor",
                ))
                continue

        # Ticker verisi
        ticker = get_ticker_24h(inst_id)
        if not ticker:
            eliminated.append(CoinScore(
                inst_id=inst_id, symbol=sym, tier=tier,
                long_score=0, short_score=0,
                momentum_7d=0, momentum_30d=0,
                volume_score=0, trend_score=0,
                volatility_score=0, funding_penalty=0,
                volume_24h_usd=0, eligible=False,
                rejection_reason="Ticker verisi alınamadı",
            ))
            continue

        # Min hacim filtresi
        vol_usd = ticker.get("volCcy24h", 0) or ticker.get("vol24h", 0) * ticker.get("last", 0)
        if vol_usd < MIN_VOLUME_24H:
            eliminated.append(CoinScore(
                inst_id=inst_id, symbol=sym, tier=tier,
                long_score=0, short_score=0,
                momentum_7d=0, momentum_30d=0,
                volume_score=0, trend_score=0,
                volatility_score=0, funding_penalty=0,
                volume_24h_usd=vol_usd, eligible=False,
                rejection_reason=f"Düşük hacim: ${vol_usd/1e6:.1f}M < ${MIN_VOLUME_24H/1e6:.0f}M",
            ))
            continue

        # Günlük mum verisi
        df_daily = get_candles(inst_id, bar="1D", limit=35)
        if len(df_daily) < 10:
            eliminated.append(CoinScore(
                inst_id=inst_id, symbol=sym, tier=tier,
                long_score=0, short_score=0,
                momentum_7d=0, momentum_30d=0,
                volume_score=0, trend_score=0,
                volatility_score=0, funding_penalty=0,
                volume_24h_usd=vol_usd, eligible=False,
                rejection_reason="Yetersiz günlük veri",
            ))
            continue

        # Funding rate
        funding_rate = get_funding_rate(inst_id)

        # Skor bileşenleri
        mom_7d, mom_30d = _momentum_score(df_daily)
        vol_score       = _volume_trend_score(df_daily)
        trend_score     = _ema_trend_score(df_daily)
        vol_quality     = _volatility_quality_score(df_daily)
        fund_pen        = _funding_penalty(funding_rate)

        long_score, short_score = _compute_long_short_scores(
            mom_7d, mom_30d, vol_score, trend_score, vol_quality, funding_rate
        )

        # NO_TRADE rejiminde tüm skorlar sıfır
        if regime == "NO_TRADE":
            long_score = short_score = 0.0

        scores.append(CoinScore(
            inst_id          = inst_id,
            symbol           = sym,
            tier             = tier,
            long_score       = long_score,
            short_score      = short_score,
            momentum_7d      = mom_7d,
            momentum_30d     = mom_30d,
            volume_score     = vol_score,
            trend_score      = trend_score,
            volatility_score = vol_quality,
            funding_penalty  = fund_pen,
            volume_24h_usd   = vol_usd,
            eligible         = True,
            current_price    = ticker.get("last", 0),
        ))

        # OKX rate limit koruma
        time.sleep(0.1)

    # Sıralama
    long_sorted  = sorted(scores, key=lambda x: x.long_score,  reverse=True)
    short_sorted = sorted(scores, key=lambda x: x.short_score, reverse=True)

    return SelectionResult(
        long_candidates  = long_sorted[:max_long],
        short_candidates = short_sorted[:max_short],
        eliminated       = eliminated,
        all_scores       = scores,
    )


def get_selected_coins(
    regime: str = "RANGE",
) -> Dict[str, List[str]]:
    """
    Seçilen coinleri dict olarak döndür.
    Returns: {"long": [...inst_ids], "short": [...inst_ids]}
    """
    result = score_coins(regime=regime)
    return {
        "long":  [c.inst_id for c in result.top_long()],
        "short": [c.inst_id for c in result.top_short()],
    }


def format_selection_log(result: SelectionResult) -> str:
    """Loglama için özet."""
    lines = ["[COIN SELECTOR]"]
    lines.append(f"  Long adaylar ({len(result.long_candidates)}):")
    for c in result.long_candidates:
        lines.append(
            f"    {c.symbol}: long={c.long_score:.0f} | "
            f"mom7={c.momentum_7d:+.1f}% | mom30={c.momentum_30d:+.1f}% | "
            f"vol=${c.volume_24h_usd/1e6:.0f}M"
        )
    lines.append(f"  Short adaylar ({len(result.short_candidates)}):")
    for c in result.short_candidates:
        lines.append(
            f"    {c.symbol}: short={c.short_score:.0f} | "
            f"mom7={c.momentum_7d:+.1f}% | vol=${c.volume_24h_usd/1e6:.0f}M"
        )
    if result.eliminated:
        lines.append(f"  Elenen ({len(result.eliminated)}): " +
                     ", ".join(f"{c.symbol}({c.rejection_reason})" for c in result.eliminated))
    return "\n".join(lines)
