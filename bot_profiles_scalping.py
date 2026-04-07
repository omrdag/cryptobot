"""
Bot Profilleri — Her Stratejinin Özel Çıkış Ayarları
=====================================================
Her bot kendi risk/TP/trailing parametrelerine sahip.
Pozisyon açıldığında bu profil devreye girer.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class BotProfile:
    name:                    str
    timeframe:               str
    leverage:                int
    order_size_usdt:         float
    stop_loss_pct:           float    # Kesir: 0.018 = %1.8
    breakeven_trigger_pct:   float    # Kesir: 0.010 = %1.0
    breakeven_offset_pct:    float    # Kesir: 0.001 = %0.1
    partial_tp1_pct:         float    # Kesir: 0.015 = %1.5
    partial_tp1_size:        float    # Kesir: 0.40  = %40
    partial_tp2_pct:         float    # Kesir: 0.023 = %2.3
    partial_tp2_size:        float    # Kesir: 0.30  = %30
    runner_pct:              float    # Kesir: 0.30  = %30
    trailing_stop_pct:       float    # Kesir: 0.009 = %0.9
    min_profit_bar:          int      # Kaçıncı mumda kontrol
    min_profit_pct:          float    # Kesir: 0.007 = %0.7
    max_bars:                int
    max_open_positions:      int
    max_daily_loss_pct:      float    # Kesir: 0.06 = %6
    max_consecutive_losses:  int

    def apply_to_position(self, pos) -> None:
        """Profil ayarlarını açık pozisyona uygula."""
        pos.trailing_stop_pct = self.trailing_stop_pct
        pos.break_even_pct    = self.breakeven_trigger_pct
        pos.tp1_pct           = self.partial_tp1_pct
        pos.tp1_size_pct      = self.partial_tp1_size
        pos.tp2_pct           = self.partial_tp2_pct
        pos.tp2_size_pct      = self.partial_tp2_size
        pos.min_profit_pct    = self.min_profit_pct
        pos.min_profit_bar    = self.min_profit_bar
        pos.max_bars          = self.max_bars


# ─── Profil Tanımları ────────────────────────────────────────────────────────

MOMENTUM_PROFILE = BotProfile(
    name                  = "MomentumBot",
    timeframe             = "1h",
    leverage              = 5,
    order_size_usdt       = 100,
    stop_loss_pct         = 0.018,   # %1.8
    breakeven_trigger_pct = 0.010,   # %1.0
    breakeven_offset_pct  = 0.001,   # %0.1
    partial_tp1_pct       = 0.015,   # %1.5
    partial_tp1_size      = 0.40,    # %40
    partial_tp2_pct       = 0.023,   # %2.3
    partial_tp2_size      = 0.30,    # %30
    runner_pct            = 0.30,    # %30
    trailing_stop_pct     = 0.009,   # %0.9
    min_profit_bar        = 4,
    min_profit_pct        = 0.007,   # %0.7
    max_bars              = 6,
    max_open_positions    = 3,
    max_daily_loss_pct    = 0.06,    # %6
    max_consecutive_losses = 3,
)

REVERSAL_PROFILE = BotProfile(
    name                  = "ReversalBot",
    timeframe             = "1h",
    leverage              = 4,
    order_size_usdt       = 100,
    stop_loss_pct         = 0.016,   # %1.6
    breakeven_trigger_pct = 0.008,   # %0.8
    breakeven_offset_pct  = 0.001,   # %0.1
    partial_tp1_pct       = 0.012,   # %1.2
    partial_tp1_size      = 0.45,    # %45
    partial_tp2_pct       = 0.019,   # %1.9
    partial_tp2_size      = 0.35,    # %35
    runner_pct            = 0.20,    # %20
    trailing_stop_pct     = 0.007,   # %0.7
    min_profit_bar        = 3,       # Daha erken kontrol
    min_profit_pct        = 0.005,   # %0.5
    max_bars              = 5,
    max_open_positions    = 3,
    max_daily_loss_pct    = 0.05,    # %5
    max_consecutive_losses = 3,
)

DIVERGENCE_PROFILE = BotProfile(
    name                  = "DivergenceBot",
    timeframe             = "1h",
    leverage              = 4,
    order_size_usdt       = 100,
    stop_loss_pct         = 0.017,   # %1.7
    breakeven_trigger_pct = 0.009,   # %0.9
    breakeven_offset_pct  = 0.001,   # %0.1
    partial_tp1_pct       = 0.014,   # %1.4
    partial_tp1_size      = 0.40,    # %40
    partial_tp2_pct       = 0.021,   # %2.1
    partial_tp2_size      = 0.30,    # %30
    runner_pct            = 0.30,    # %30
    trailing_stop_pct     = 0.008,   # %0.8
    min_profit_bar        = 4,
    min_profit_pct        = 0.006,   # %0.6
    max_bars              = 6,
    max_open_positions    = 3,
    max_daily_loss_pct    = 0.05,    # %5
    max_consecutive_losses = 3,
)

PULLBACK_LONG_PROFILE = BotProfile(
    name                  = "Pullback Long",
    timeframe             = "1m",        # Bot ~2-3 dakikada bir döngü yapar
    leverage              = 10,
    order_size_usdt       = 175,
    stop_loss_pct         = 0.025,       # %2.5 — hard SL güvenlik ağı (ATR×2.5 ile uyumlu)
    breakeven_trigger_pct = 0.012,       # %1.2 — BE: 2×ATR hareketi görmeden SL kilitlenmiyor
    breakeven_offset_pct  = 0.001,       # %0.1
    partial_tp1_pct       = 0.015,       # %1.5 — TP1: 1×ATR'lik gerçek kazanç
    partial_tp1_size      = 0.50,        # %50 — yarısını kilitle, runner devam
    partial_tp2_pct       = 0.025,       # %2.5 — TP2: tam kâr hedefi
    partial_tp2_size      = 0.50,        # %50 — kalan tüm pozisyonu kapat
    runner_pct            = 0.00,        # %0 — TP2 sonrası pozisyon tamamen kapanır
    trailing_stop_pct     = 0.010,       # %1.0 — BE sonrası daha geniş takip (gürültüyü filtreler)
    min_profit_bar        = 8,           # 8 iterasyon ≈ 20 dk sonra kontrol
    min_profit_pct        = -0.9,        # Zararda zaman çıkışı yok — SL kapatsın
    max_bars              = 24,          # 24 iterasyon ≈ 60 dk max (daha fazla zaman)
    max_open_positions    = 5,
    max_daily_loss_pct    = 0.06,        # %6
    max_consecutive_losses = 5,
)

PULLBACK_SHORT_PROFILE = BotProfile(
    name                  = "Pullback Short",
    timeframe             = "1m",        # Bot ~2-3 dakikada bir döngü yapar
    leverage              = 10,
    order_size_usdt       = 175,
    stop_loss_pct         = 0.025,       # %2.5 — hard SL güvenlik ağı (ATR×2.5 ile uyumlu)
    breakeven_trigger_pct = 0.012,       # %1.2 — BE: 2×ATR hareketi görmeden SL kilitlenmiyor
    breakeven_offset_pct  = 0.001,       # %0.1
    partial_tp1_pct       = 0.015,       # %1.5 — TP1: 1×ATR'lik gerçek kazanç
    partial_tp1_size      = 0.50,        # %50 — yarısını kilitle, runner devam
    partial_tp2_pct       = 0.025,       # %2.5 — TP2: tam kâr hedefi
    partial_tp2_size      = 0.50,        # %50 — kalan tüm pozisyonu kapat
    runner_pct            = 0.00,        # %0 — TP2 sonrası pozisyon tamamen kapanır
    trailing_stop_pct     = 0.010,       # %1.0 — BE sonrası daha geniş takip (gürültüyü filtreler)
    min_profit_bar        = 48,          # 48 iterasyon ≈ 2 saat sonra kontrol
    min_profit_pct        = -0.9,        # Zararda zaman çıkışı yok — SL kapatsın
    max_bars              = 96,          # 96 iterasyon ≈ 4 saat max
    max_open_positions    = 5,
    max_daily_loss_pct    = 0.06,        # %6
    max_consecutive_losses = 5,
)

# ─── Lookup Tablosu ───────────────────────────────────────────────────────────

BOT_PROFILES: Dict[str, BotProfile] = {
    "MomentumBot":    MOMENTUM_PROFILE,
    "ReversalBot":    REVERSAL_PROFILE,
    "DivergenceBot":  DIVERGENCE_PROFILE,
    "Pullback Long":  PULLBACK_LONG_PROFILE,
    "Pullback Short": PULLBACK_SHORT_PROFILE,
    "Scalping Long":  SCALPING_LONG_PROFILE,
    "Scalping Short": SCALPING_SHORT_PROFILE,
}

# Sinyal Engine tek-bot modu için varsayılan profil
DEFAULT_PROFILE = MOMENTUM_PROFILE


def get_profile(bot_name: Optional[str]) -> BotProfile:
    """Bot adına göre profil döndür; bulunamazsa varsayılanı kullan."""
    if not bot_name:
        return DEFAULT_PROFILE
    return BOT_PROFILES.get(bot_name, DEFAULT_PROFILE)


def all_profiles() -> list:
    """Tüm profillerin listesini döndür."""
    return list(BOT_PROFILES.values())


# ─── Scalping Profili (YENİ) ──────────────────────────────────────────────────
# 1m timeframe, dar SL/TP, hızlı çıkış, large lot kapalı
# Hedef: %55+ win rate, RR 1.5x, günde 10-20 işlem

SCALPING_LONG_PROFILE = BotProfile(
    name                  = "Scalping Long",
    timeframe             = "1m",
    leverage              = 10,
    order_size_usdt       = 100,          # Küçük pozisyon — scalping'de büyük lot yok
    stop_loss_pct         = 0.003,        # %0.3 — dar SL (scalping şart)
    breakeven_trigger_pct = 0.002,        # %0.2 — çok erken BE kilitle
    breakeven_offset_pct  = 0.0005,       # %0.05 küçük offset
    partial_tp1_pct       = 0.003,        # %0.3 → TP1: erken %50 kapat
    partial_tp1_size      = 0.50,         # %50 — yarısını kilitle
    partial_tp2_pct       = 0.005,        # %0.5 → TP2: kalan %50
    partial_tp2_size      = 0.50,         # %50 — tamamen kapat
    runner_pct            = 0.00,         # %0 — runner yok, hızlı çıkış
    trailing_stop_pct     = 0.002,        # %0.2 — sıkı trailing
    min_profit_bar        = 3,            # 3 dakika sonra kontrol
    min_profit_pct        = -0.9,         # Zararda zaman çıkışı yok — SL kapatsın
    max_bars              = 10,           # 10 dakika max
    max_open_positions    = 3,            # Max 3 pozisyon
    max_daily_loss_pct    = 0.04,         # %4 günlük max kayıp (scalping'de sıkı)
    max_consecutive_losses = 4,
)

SCALPING_SHORT_PROFILE = BotProfile(
    name                  = "Scalping Short",
    timeframe             = "1m",
    leverage              = 10,
    order_size_usdt       = 100,
    stop_loss_pct         = 0.003,        # %0.3
    breakeven_trigger_pct = 0.002,        # %0.2
    breakeven_offset_pct  = 0.0005,
    partial_tp1_pct       = 0.003,        # %0.3
    partial_tp1_size      = 0.50,
    partial_tp2_pct       = 0.005,        # %0.5
    partial_tp2_size      = 0.50,
    runner_pct            = 0.00,
    trailing_stop_pct     = 0.002,        # %0.2
    min_profit_bar        = 3,
    min_profit_pct        = -0.9,
    max_bars              = 10,           # 10 dakika max
    max_open_positions    = 3,
    max_daily_loss_pct    = 0.04,
    max_consecutive_losses = 4,
)
