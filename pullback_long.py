"""
Pullback Long Strategy — Yüksek Olasılıklı Trend-Geri-Çekilme Girişi
======================================================================
Temel Felsefe:
  Trend yönünde hareket etmek ama breakout kovalamamak.
  EMA21 civarına geri çekilen fiyata girmek (daha iyi RR).

Koşullar (10/10 üzeri, min 7 puan):
  [3 puan] Trend hizalama: EMA9 > EMA21 > EMA50, fiyat > EMA50, EMA50 eğimi +
  [2 puan] Pullback giriş zonu: fiyat EMA21 civarında veya hafif altında
  [2 puan] Sağlıklı momentum: RSI 42-62 VE ADX >= 20
  [2 puan] Hacim onayı: hacim 20-bar ortalamasının 1.15x üzerinde
  [1 puan] Volatilite uygunluğu: ATR %0.6-12% arası

Oturum:  20:00–22:00 UTC  (analiz edilmiş en iyi saatler)
RR:      ~1.6× (SL = 2.5×ATR altı, TP = 1.6× risk üstü)
Türü:    Sadece LONG — kısa vadeli swing içinde trend takibi
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
class SignalResult:
    should_enter:      bool
    score:             int
    reason:            str
    entry_price:       Optional[float] = None
    stop_loss:         Optional[float] = None
    take_profit:       Optional[float] = None
    min_hold_minutes:  Optional[int]   = None
    volume_ok:         bool            = True


# ─── Strateji Durumu (per-symbol cooldown + streak ban) ──────────────────────

class StrategyState:
    """
    Sembol bazlı cooldown ve kayıp serisi takibi.
    Not: Genel risk kontrolü hâlâ RiskManager üzerinden yapılır.
    Bu sınıf strateji seviyesinde ek koruma sağlar.
    """
    def __init__(self):
        self.symbol_cooldowns:   Dict[str, float] = {}
        self.symbol_loss_streak: Dict[str, int]   = {}
        self.daily_trade_count:  int               = 0
        self.max_daily_trades:   int               = 12  # günlük sistemik tavan

    def is_symbol_on_cooldown(self, symbol: str) -> bool:
        return time.time() < self.symbol_cooldowns.get(symbol, 0)

    def set_symbol_cooldown(self, symbol: str, minutes: int):
        self.symbol_cooldowns[symbol] = time.time() + minutes * 60
        logger.info(f"[PullbackStrategy] {symbol}: {minutes} dk cooldown başladı")

    def register_trade_result(self, symbol: str, won: bool):
        if won:
            self.symbol_loss_streak[symbol] = 0
        else:
            self.symbol_loss_streak[symbol] = self.symbol_loss_streak.get(symbol, 0) + 1
            streak = self.symbol_loss_streak[symbol]
            if streak >= 3:
                logger.warning(
                    f"[PullbackStrategy] {symbol}: {streak} art arda kayıp "
                    f"→ sembol geçici olarak yasaklandı"
                )

    def should_ban_symbol(self, symbol: str) -> bool:
        return self.symbol_loss_streak.get(symbol, 0) >= 3

    def increment_trade(self):
        self.daily_trade_count += 1

    def reset_daily(self):
        self.daily_trade_count = 0


# ─── Filtreler ─────────────────────────────────────────────────────────────────

def _in_allowed_session(hour_utc: int) -> bool:
    """24 saat aktif — saat kısıtlaması devre dışı (v3)."""
    return True


def _is_trend_up(d: dict) -> bool:
    """
    Trend hizalama kontrolü:
    - EMA9 > EMA21 > EMA50 (tam hiza)
    - Fiyat EMA50 üzerinde (trend desteği)
    - EMA50 eğimi pozitif (trend hâlâ yukarı)
    """
    return (
        d["close"] > d["ema50"] and
        d["ema9"] > d["ema21"] > d["ema50"] and
        d["ema50"] > d["ema50_prev"]
    )


def _is_above_vwap(d: dict) -> bool:
    """
    VWAP filtresi — fiyat VWAP üzerinde olmalı.
    VWAP = günlük hacim ağırlıklı ortalama fiyat.
    Fiyat VWAP üzerindeyse kurumsal alıcılar aktif demektir.
    vwap=0 ise (hesaplanamadıysa) filtreyi geç.
    """
    vwap = d.get("vwap", 0)
    if vwap <= 0:
        return True  # VWAP yoksa filtreyi atla
    return d["close"] > vwap * 0.999  # %0.1 tolerans


def _is_good_session(hour_utc: int) -> bool:
    """
    Piyasa saati filtresi — en yüksek hacim ve trend kalitesi saatleri.
    Araştırma: 08-12 UTC (Avrupa açılış) ve 13-17 UTC (ABD öncesi) en iyi.
    Gece 00-06 UTC düşük hacim → daha fazla sahte sinyal.
    """
    good_hours = list(range(7, 18))   # 07:00-17:59 UTC (Avrupa+ABD örtüşmesi)
    return hour_utc in good_hours


def _is_pullback_entry(d: dict) -> bool:
    """
    EMA21 civarı geri çekilme — genişletilmiş bölge (v2).
    Fiyat EMA21'e ATR'nin 1.2 katı içinde olmalı (önceki: 0.35).
    Veya son mumun dibi EMA21'e dokunmuş olmalı.
    Maksimum uzaklık: EMA21 + ATR×2.0 (önceki: 0.6).
    """
    close    = d["close"]
    low      = d["low"]
    ema21    = d["ema21"]
    atr      = d["atr"]

    distance           = abs(close - ema21)
    touched_zone       = (distance <= atr * 1.2) or (low <= ema21)
    not_too_extended   = close <= ema21 + atr * 2.0

    return touched_zone and not_too_extended


def _is_momentum_healthy(d: dict) -> bool:
    """
    RSI momentum zonu: 36-70 (gevşetilmiş, v2).
    ADX minimum 15 (önceki: 20).
    """
    return 36 <= d["rsi"] <= 70 and d["adx"] >= 15


def _is_volume_confirmed(d: dict) -> bool:
    """Son hacim 20-bar ortalamasının 1.05x üzerinde (hafif eşik — kalite ile denge)."""
    return d["volume"] > d["volume_ma20"] * 1.05


def _is_volatility_acceptable(d: dict) -> bool:
    """
    Çok ölü piyasa da olmasın, fırtına da olmasın.
    ATR %0.4–%15 arası (gevşetilmiş, v2).
    """
    close     = d["close"]
    atr       = d["atr"]
    bb_range  = d["bb_upper"] - d["bb_lower"]

    atr_pct      = atr / close if close > 0 else 0
    bb_width_pct = bb_range / close if close > 0 else 0

    if atr_pct < 0.004:        # Çok düşük volatilite
        return False
    if bb_width_pct > 0.15:    # Aşırı genişleme (önceki: 0.12)
        return False
    return True


# ─── Skor Hesaplama ────────────────────────────────────────────────────────────

def _calculate_signal_score(d: dict, hour_utc: int = 12) -> Tuple[int, list]:
    """
    10 üzerinden puan ver. 7 ve üzeri → işlem aç.

    Dağılım:
      Trend hizalama   = 3 puan (en önemli)
      Pullback zonu    = 2 puan
      Momentum         = 2 puan
      Hacim            = 2 puan
      Volatilite       = 1 puan
      VWAP bonus       = +1 puan (VWAP üzerinde ise)
    Toplam max = 11 puan
    """
    score   = 0
    reasons = []

    if _is_trend_up(d):
        score += 3
        reasons.append(f"✓ Trend hizalı (EMA9>{d['ema21']:.4f}>EMA50, EMA50↑)")
    else:
        reasons.append(
            f"✗ Trend hizasız "
            f"(close={d['close']:.4f} EMA9={d['ema9']:.4f} "
            f"EMA21={d['ema21']:.4f} EMA50={d['ema50']:.4f})"
        )

    if _is_pullback_entry(d):
        score += 2
        reasons.append(
            f"✓ Pullback zonu (fiyat EMA21 civarı, mesafe={abs(d['close']-d['ema21']):.4f})"
        )
    else:
        reasons.append(
            f"✗ Pullback yok (fiyat EMA21'den uzak veya çok üstte)"
        )

    if _is_momentum_healthy(d):
        score += 2
        reasons.append(f"✓ Momentum sağlıklı (RSI={d['rsi']:.1f}, ADX={d['adx']:.1f})")
    else:
        reasons.append(
            f"✗ Momentum sorunlu (RSI={d['rsi']:.1f} [beklenen:36-70], "
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
        reasons.append(f"✗ Volatilite uygun değil (ATR/fiyat sınır dışı)")

    # VWAP bonus — fiyat VWAP üzerindeyse +1 puan
    if _is_above_vwap(d):
        vwap = d.get("vwap", 0)
        if vwap > 0:
            score += 1
            reasons.append(f"✓ VWAP üzerinde (fiyat=${d['close']:.4f} > VWAP=${vwap:.4f})")
        # vwap=0 → sessiz geç (filtre atlandı)
    else:
        vwap = d.get("vwap", 0)
        reasons.append(f"✗ VWAP altında (fiyat=${d['close']:.4f} < VWAP=${vwap:.4f}) — zayıf kurumsal destek")

    # Piyasa saati bilgisi (puan değil, log için)
    if not _is_good_session(hour_utc):
        reasons.append(f"⚠ Düşük hacim saati (UTC {hour_utc}:xx — önerilen 07-17)")

    return score, reasons


# ─── Ana Sinyal Fonksiyonu ─────────────────────────────────────────────────────

def build_long_signal(
    symbol:    str,
    hour_utc:  int,
    d:         dict,
    state:     StrategyState,
    min_score: int  = 7,
    df_5m:     "pd.DataFrame | None" = None,
    df_15m:    "pd.DataFrame | None" = None,
) -> SignalResult:
    """
    Tüm filtrelerden geçen yüksek kalite BUY sinyali üretir.

    Yeni parametreler (MTF):
      df_5m  — 5 dakikalık OHLCV (opsiyonel, trend onayı için)
      df_15m — 15 dakikalık OHLCV (opsiyonel, ana trend için)
    """
    # 1. Günlük limit
    if state.daily_trade_count >= state.max_daily_trades:
        return SignalResult(False, 0, "Günlük işlem limiti doldu")

    # 2. Symbol cooldown
    if state.is_symbol_on_cooldown(symbol):
        return SignalResult(False, 0, f"{symbol} cooldown aktif")

    # 3. Symbol ban (3 art arda kayıp)
    if state.should_ban_symbol(symbol):
        streak = state.symbol_loss_streak.get(symbol, 0)
        return SignalResult(
            False, 0,
            f"{symbol} geçici yasaklı ({streak} art arda kayıp)"
        )

    # 4. Piyasa saati filtresi — düşük hacim saatlerinde min_score artır
    session_ok = _is_good_session(hour_utc)
    effective_min = min_score if session_ok else min_score + 1

    # 5. MTF trend onayı (opsiyonel — df_5m veya df_15m varsa)
    mtf_bonus = 0
    mtf_notes = []
    if df_5m is not None and len(df_5m) >= 55:
        ind5 = _extract_indicators(df_5m)
        if ind5 and _is_trend_up(ind5):
            mtf_bonus += 1
            mtf_notes.append("✓ 5dk trend yukarı")
        elif ind5:
            mtf_notes.append("✗ 5dk trend olumsuz")
    if df_15m is not None and len(df_15m) >= 55:
        ind15 = _extract_indicators(df_15m)
        if ind15 and _is_trend_up(ind15):
            mtf_bonus += 1
            mtf_notes.append("✓ 15dk trend yukarı")
        elif ind15:
            mtf_notes.append("✗ 15dk trend olumsuz")

    # 6. Ana timeframe skor hesapla
    score, reasons = _calculate_signal_score(d, hour_utc=hour_utc)
    score += mtf_bonus
    if mtf_notes:
        reasons.extend(mtf_notes)

    if score < effective_min:
        session_note = f" (gece saati: min {effective_min} gerekli)" if not session_ok else ""
        return SignalResult(
            False, score,
            f"Puan yetersiz ({score}/{effective_min}){session_note}: {' | '.join(reasons)}"
        )

    # 6. SL / TP (ATR tabanlı, ATR×2.5 — daha geniş nefes alanı)
    entry_price = d["close"]
    atr         = d["atr"]
    stop_loss   = entry_price - (atr * 2.5)    # ATR×2.5: küçük geri çekilmelerden etkilenmez
    risk        = entry_price - stop_loss
    take_profit = entry_price + (risk * 1.6)   # RR = 1.6× (daha ulaşılabilir hedef)

    return SignalResult(
        should_enter     = True,
        score            = score,
        reason           = " | ".join(reasons),
        entry_price      = entry_price,
        stop_loss        = stop_loss,
        take_profit      = take_profit,
        min_hold_minutes = 30,
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

def _vwap(df: pd.DataFrame) -> float:
    """Günlük VWAP hesapla (volume weighted average price)."""
    if "volume" not in df.columns:
        return 0.0
    try:
        typical = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (typical * df["volume"]).cumsum() / df["volume"].cumsum()
        return float(vwap.iloc[-1])
    except:
        return 0.0


def _extract_indicators(df: pd.DataFrame) -> Optional[dict]:
    """DataFrame'den strateji için gereken tüm indikatörleri hesapla."""
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

    vwap_val = _vwap(df)

    return {
        "close":       float(close.iloc[-1]),
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
        "vwap":        vwap_val,
    }


# ─── BaseStrategy Wrapper ──────────────────────────────────────────────────────

class PullbackLongStrategy(BaseStrategy):
    """
    Trend-Geri-Çekilme uzun stratejisi.
    EMA21 civarında geri çekilen, trend hizalı ve hacim onaylı girişler.

    Saat filtresi bu strateji içinde uygulanır (20-22 UTC).
    Symbol ban/cooldown StrategyState üzerinden yönetilir.
    Genel risk kontrolü (daily loss, drawdown) RiskManager'da kalır.
    """

    def __init__(self, min_score: int = 6):
        super().__init__(name="Pullback Long")
        self.min_score = min_score
        self.state     = StrategyState()

        # Son üretilen tam sinyal (SL/TP için main.py'den erişilir)
        self.last_result: Optional[SignalResult] = None

        # Son değerlendirmenin detaylı koşul verisi (dashboard için)
        self.last_conditions: Optional[dict] = None

    def generate_signal(self, df: pd.DataFrame) -> str:
        """BaseStrategy uyumluluğu için — tam sonuç için generate() kullan."""
        result = self.generate(df)
        return Signal.BUY if result.should_enter else Signal.HOLD

    def generate(
        self,
        df:       pd.DataFrame,
        symbol:   str            = "UNKNOWN",
        hour_utc: Optional[int]  = None,
        df_5m:    "pd.DataFrame | None" = None,
        df_15m:   "pd.DataFrame | None" = None,
    ) -> SignalResult:
        """
        Tam sinyal üretimi.
        df      — 1dk OHLCV (ana timeframe)
        df_5m   — 5dk OHLCV (MTF trend onayı, opsiyonel)
        df_15m  — 15dk OHLCV (MTF ana trend, opsiyonel)
        """
        from datetime import datetime, timezone
        if hour_utc is None:
            hour_utc = datetime.now(timezone.utc).hour

        indicators = _extract_indicators(df)
        if indicators is None:
            self.last_result = SignalResult(False, 0, "Yetersiz veri (min 55 bar)")
            self.last_conditions = None
            return self.last_result

        result = build_long_signal(
            symbol    = symbol,
            hour_utc  = hour_utc,
            d         = indicators,
            state     = self.state,
            min_score = self.min_score,
            df_5m     = df_5m,
            df_15m    = df_15m,
        )
        self.last_result = result

        # Dashboard için per-koşul detay verisi
        d = indicators
        atr_pct = (d["atr"] / d["close"] * 100) if d.get("close", 0) > 0 else 0
        pullback_dist = abs(d["close"] - d["ema21"])
        vwap = d.get("vwap", 0)
        self.last_conditions = {
            "price":     round(d["close"], 6),
            "ema9":      round(d["ema9"], 6),
            "ema21":     round(d["ema21"], 6),
            "ema50":     round(d["ema50"], 6),
            "vwap":      round(vwap, 4) if vwap > 0 else 0,
            "rsi":       round(d["rsi"], 1),
            "adx":       round(d["adx"], 1),
            "atr_pct":   round(atr_pct, 3),
            "vol_ratio": round(d["volume"] / d["volume_ma20"], 2) if d.get("volume_ma20", 0) > 0 else 0,
            "pullback_dist_pct": round(pullback_dist / d["close"] * 100, 2) if d.get("close", 0) > 0 else 0,
            "session_ok": _is_good_session(hour_utc),
            "conditions": {
                "trend":      {"ok": _is_trend_up(d),              "weight": 3, "label": "Trend Hizası",   "detail": f"EMA9>{d['ema9']:.4f} > EMA21>{d['ema21']:.4f} > EMA50>{d['ema50']:.4f}"},
                "pullback":   {"ok": _is_pullback_entry(d),        "weight": 2, "label": "Pullback Zonu",  "detail": f"Mesafe: %{round(pullback_dist / d['close'] * 100, 2) if d['close'] > 0 else 0:.2f}"},
                "momentum":   {"ok": _is_momentum_healthy(d),      "weight": 2, "label": "Momentum",      "detail": f"RSI:{d['rsi']:.1f} ADX:{d['adx']:.1f}"},
                "volume":     {"ok": _is_volume_confirmed(d),      "weight": 2, "label": "Hacim Onayı",   "detail": f"Vol/Ort: x{round(d['volume'] / d['volume_ma20'], 2) if d.get('volume_ma20', 0) > 0 else 0:.2f}"},
                "volatility": {"ok": _is_volatility_acceptable(d), "weight": 1, "label": "Volatilite",    "detail": f"ATR%:{atr_pct:.2f}"},
                "vwap":       {"ok": _is_above_vwap(d),            "weight": 1, "label": "VWAP",          "detail": f"Fiyat/VWAP: ${d['close']:.4f} / ${vwap:.4f}" if vwap > 0 else "VWAP yok"},
                "session":    {"ok": _is_good_session(hour_utc),   "weight": 0, "label": "Piyasa Saati",  "detail": f"UTC {hour_utc}:xx {'✓ aktif saat' if _is_good_session(hour_utc) else '⚠ düşük hacim'}"},
            },
            "score":      result.score,
            "min_score":  self.min_score,
            "should_enter": result.should_enter,
            "blocked_reason": result.reason if not result.should_enter else None,
            "hour_utc":   hour_utc,
            "cooldown":   self.state.is_symbol_on_cooldown(symbol),
        }

        if result.should_enter:
            logger.info(
                f"✅ [{self.name}] {symbol} BUY | "
                f"Puan:{result.score}/11 | "
                f"Giriş:{result.entry_price:.4f} | "
                f"SL:{result.stop_loss:.4f} | TP:{result.take_profit:.4f} | "
                f"VWAP={'✓' if _is_above_vwap(d) else '✗'} | "
                f"Saat={'✓' if _is_good_session(hour_utc) else '⚠'} | "
                f"{result.reason[:100]}"
            )
        else:
            logger.debug(
                f"[{self.name}] {symbol} HOLD | "
                f"Puan:{result.score}/11 | {result.reason[:80]}"
            )

        return result

    def on_trade_closed(self, symbol: str, pnl: float):
        """İşlem kapandığında strateji durumunu güncelle."""
        won = pnl > 0
        self.state.register_trade_result(symbol, won)
        if not won:
            streak = self.state.symbol_loss_streak.get(symbol, 0)
            if streak >= 2:
                cooldown_min = streak * 60   # 2 kayıp=120dk, 3 kayıp=180dk cooldown
                self.state.set_symbol_cooldown(symbol, cooldown_min)

    def get_last_sl_tp(self) -> Tuple[Optional[float], Optional[float]]:
        """Son sinyalin SL/TP değerlerini döndür (main.py entegrasyonu için)."""
        if self.last_result and self.last_result.should_enter:
            return self.last_result.stop_loss, self.last_result.take_profit
        return None, None

    def get_last_indicators(self, df: pd.DataFrame) -> Optional[dict]:
        """Mevcut indikatör değerlerini döndür (debug için)."""
        return _extract_indicators(df)
