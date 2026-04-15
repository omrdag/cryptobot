"""
Merkezi Yapılandırma — Crypto Trading Bot v3
=============================================
Tüm parametreler burada. Modüler ve profesyonel yapı.

GÜNCELLEME — Nisan 2026:
  - PULLBACK_SHORT_ACTIVE_REGIMES: RANGING + MIXED eklendi (short geç kalma sorunu çözüldü)
  - PULLBACK_SHORT_MIN_SCORE_WEAK: 8 → 7 (RANGING'de short eşiği hafifletildi)
  - LONG_MIN_SCORE: 6 (Railway Variables'dan)
  - SHORT_MIN_SCORE: 6 (Railway Variables'dan)

KÂR STRATEJİSİ GÜNCELLEMESİ — Nisan 2026:
  - Zaman bazlı çıkış devre dışı (MAX_BARS_IN_TRADE → 999)
  - Yüzde bazlı kısmi TP devre dışı (PARTIAL_TP1_SIZE → 0)
  - Breakeven yüzde bazlı devre dışı (BREAK_EVEN_ENABLED → False)
  - Sadece USDT bazlı Stage2 sistemi aktif:
      +$3  → SL giriş üzerine çek (zarar engellendi)
      +$5  → SL kâr garantili seviyeye çek
      +$7  → %50 kapat, kalan izle
      +$10 → Kalan %50 tamamen kapat
  - SL (ATR bazlı) + Trailing Stop korundu
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ═══════════════════════════════════════════════════════════════
# BORSA BAĞLANTISI
# ═══════════════════════════════════════════════════════════════
EXCHANGE = os.getenv("EXCHANGE", "okx")
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

# ═══════════════════════════════════════════════════════════════
# GENEL BOT AYARLARI
# ═══════════════════════════════════════════════════════════════
PAPER_TRADING        = os.getenv("PAPER_TRADING", "true").lower() != "false"
INITIAL_BALANCE_USDT = float(os.getenv("INITIAL_BALANCE_USDT", "10000"))
LOOP_INTERVAL_SECONDS = 60

# ═══════════════════════════════════════════════════════════════
# İŞLEM ÇİFTLERİ ve ZAMAN DİLİMİ
# ═══════════════════════════════════════════════════════════════
TRADING_PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
]

KLINE_INTERVAL = "1h"
KLINE_LIMIT    = 300

# ═══════════════════════════════════════════════════════════════
# AKTİF STRATEJİ
# ═══════════════════════════════════════════════════════════════
ACTIVE_STRATEGY = "pullback"

# ═══════════════════════════════════════════════════════════════
# SIGNAL ENGINE — Çok Katmanlı Sinyal Onay Sistemi
# ═══════════════════════════════════════════════════════════════
SIGNAL_MIN_SCORE       = 60.0

EMA_FAST_PERIOD   = 9
EMA_SLOW_PERIOD   = 21
EMA_TREND_PERIOD  = 50

RSI_PERIOD        = 14
RSI_BUY_MAX       = 55.0
RSI_SELL_MIN      = 45.0
RSI_OVERSOLD      = 35.0
RSI_OVERBOUGHT    = 65.0

ATR_PERIOD        = 14
ATR_SL_MULTIPLIER = 2.5
ATR_TP_MULTIPLIER = 4.0

ADX_MIN_THRESHOLD   = 18.0
GATE_MIN_SCORE      = 6
CANDLE_CONFIRM_BARS = 2
VOLUME_MIN_RATIO    = 1.0
MIN_ATR_THRESHOLD   = 0.002

# ═══════════════════════════════════════════════════════════════
# MARKET REGIME FILTER
# ═══════════════════════════════════════════════════════════════
REGIME_ENABLED          = True
REGIME_TREND_ADX        = 22.0
REGIME_HIGH_VOL_RATIO   = 0.04
REGIME_LOW_VOL_RATIO    = 0.005
REGIME_RANGING_BB_WIDTH = 0.025
REGIME_MIN_VOL_RATIO    = 0.35

REGIME_NO_TRADE = ["WEAK_LIQUIDITY"]
REGIME_REDUCE   = ["HIGH_VOLATILITY"]

# ═══════════════════════════════════════════════════════════════
# EMA CROSSOVER STRATEJİSİ (Eski mod)
# ═══════════════════════════════════════════════════════════════
MAX_HOLDING_CANDLES = 6
MIN_VOLUME_FACTOR   = 0.3

# ═══════════════════════════════════════════════════════════════
# KLASİK STRATEJİ AYARLARI
# ═══════════════════════════════════════════════════════════════
MA_SHORT_PERIOD = 9
MA_LONG_PERIOD  = 21

MACD_FAST_PERIOD   = 12
MACD_SLOW_PERIOD   = 26
MACD_SIGNAL_PERIOD = 9

BB_PERIOD  = 20
BB_STD_DEV = 2.0

COMBINED_STRATEGIES = ["ma_crossover", "macd", "rsi"]
COMBINED_MIN_VOTES  = 2

# ═══════════════════════════════════════════════════════════════
# KALDIRAÇ
# ═══════════════════════════════════════════════════════════════
LEVERAGE = int(os.getenv("LEVERAGE", "10"))
LEVERAGE = 10

# ═══════════════════════════════════════════════════════════════
# POZİSYON BOYUTLANDIRMA
# ═══════════════════════════════════════════════════════════════
POSITION_SIZING_MODE = "atr"
RISK_PER_TRADE_PCT   = 0.01
TRADE_AMOUNT_PCT     = 0.10

TRADE_AMOUNT      = 100.0
TRADE_AMOUNT_TYPE = "auto"

STOP_LOSS_PCT   = 0.02
TAKE_PROFIT_PCT = 0.04

# ═══════════════════════════════════════════════════════════════
# POZİSYON ROTASYONU
# ═══════════════════════════════════════════════════════════════
ROTATION_MIN_SCORE = 78

# ═══════════════════════════════════════════════════════════════
# SMART EXIT — SADECE STAGE2 USDT BAZLI SİSTEM AKTİF
# ═══════════════════════════════════════════════════════════════
#
# Kâr alma akışı:
#   Giriş → SL (ATR bazlı) koruma
#   +$3   → SL giriş üzerine çek (zarar engellendi)
#   +$5   → SL kâr garantili seviyeye çek
#   +$7   → %50 pozisyon kapat, kalan izle
#   +$10  → Kalan %50 tamamen kapat
#   Trailing Stop → Zirve - %0.2 düşünce kapat
#
# Devre dışı bırakılanlar:
#   - Zaman bazlı çıkış (MAX_BARS → 999)
#   - Yüzde bazlı kısmi TP (PARTIAL_TP1_SIZE → 0)
#   - Breakeven yüzde (BREAK_EVEN_ENABLED → False)
# ──────────────────────────────────────────────────────────────

# Breakeven — DEVRE DIŞI (Stage2 +$3'de hallediyor)
BREAKEVEN_TRIGGER_PCT     = 999.0   # ✅ Devre dışı: 0.8 → 999
BREAKEVEN_OFFSET_PCT      = 0.1

# Yüzde bazlı kısmi TP — DEVRE DIŞI
PARTIAL_TP1_PCT           = 1.2
PARTIAL_TP1_SIZE          = 0       # ✅ Devre dışı: 100 → 0
PARTIAL_TP2_PCT           = 2.8
PARTIAL_TP2_SIZE          = 0
RUNNER_POSITION_PCT       = 0

# Trailing Stop — KORUNDU
TRAILING_STOP_ENABLED     = True
TRAILING_STOP_PCT         = 0.002   # %0.2 — zirve - %0.2 → kapat
BREAK_EVEN_ENABLED        = False   # ✅ Devre dışı: Stage2 hallediyor
BREAK_EVEN_PCT            = 0.012

# Zaman bazlı çıkış — DEVRE DIŞI
MAX_BARS_IN_TRADE         = 999     # ✅ Devre dışı: 6 → 999
MIN_PROFIT_AFTER_4_BARS   = 0.0     # ✅ Devre dışı: 0.8 → 0.0

# Smart Time Exit — DEVRE DIŞI
SMART_EXIT_BASE_MAX_BARS      = 999  # ✅ Devre dışı: 8 → 999
SMART_EXIT_LARGE_LOT_MAX_BARS = 999  # ✅ Devre dışı: 10 → 999
SMART_EXIT_TP1_EXTENSION      = 0    # ✅ Devre dışı: 3 → 0
SMART_EXIT_BE_EXTENSION       = 0    # ✅ Devre dışı: 2 → 0
SMART_EXIT_TREND_MAX_BARS     = 999  # ✅ Devre dışı: 12 → 999
SMART_EXIT_ADX_STRONG_MIN     = 25
SMART_EXIT_DELAY_BARS         = 0    # ✅ Devre dışı: 2 → 0
SMART_EXIT_DELAY_LOSS_TOL     = 0.003

# ═══════════════════════════════════════════════════════════════
# PAPER TRADING — GERÇEKÇİ SİMÜLASYON
# ═══════════════════════════════════════════════════════════════
FEE_RATE          = 0.001
SLIPPAGE_PCT      = 0.0005
PARTIAL_FILL_PROB = 0.0

# ═══════════════════════════════════════════════════════════════
# POZİSYON BOYUTLANDIRMA — RİSK BAZLI SİSTEM (v3)
# ═══════════════════════════════════════════════════════════════
POSITION_MIN_USDT      = 75.0
MIN_ECONOMIC_NOTIONAL  = 100.0
POSITION_DEFAULT_USDT  = 100.0
POSITION_STRONG_USDT   = 125.0
POSITION_MAX_USDT      = 150.0

POSITION_NOTIONAL_BY_QUALITY = {
    "A": 125.0,
    "B": 100.0,
    "C":  75.0,
}

SIGNAL_QUALITY_MULTIPLIER = {
    "A": 1.25,
    "B": 1.00,
    "C": 0.75,
}

POSITION_TARGET_MOMENTUM   = (75.0,  100.0)
POSITION_TARGET_REVERSAL   = (100.0, 125.0)
POSITION_TARGET_DIVERGENCE = (100.0, 100.0)
POSITION_TARGET_PULLBACK   = (75.0,  150.0)

# ═══════════════════════════════════════════════════════════════
# RİSK YÖNETİMİ
# ═══════════════════════════════════════════════════════════════
MAX_OPEN_POSITIONS      = 5
DAILY_MAX_LOSS_PCT      = 0.05
MAX_TOTAL_OPEN_RISK_PCT = 0.02
MAX_CONSECUTIVE_LOSS    = 5
MAX_SYMBOL_EXPOSURE     = 0.30
MAX_DRAWDOWN_PCT        = 0.15
DRAWDOWN_WARN_PCT       = 0.08
DEFENSE_LOSS_COUNT      = 3
DEFENSE_SIZE_FACTOR     = 0.5
KILL_SWITCH             = False

SYMBOL_MAX_CONSEC_LOSS      = 2
SYMBOL_COOLDOWN_HOURS       = 4.0
MAX_DAILY_TRADES_PER_SYMBOL = 2

TRADING_HOURS_UTC     = list(range(24))
TRADING_HOURS_ENABLED = False

# ═══════════════════════════════════════════════════════════════
# MARKET SCANNER / COIN SELECTION
# ═══════════════════════════════════════════════════════════════
SCANNER_ENABLED        = True
SCANNER_INTERVAL_LOOPS = 20
SCANNER_MIN_VOLUME_24H = 5_000_000
SCANNER_MAX_SPREAD_PCT = 0.5
SCANNER_MIN_SCORE      = 50.0
SCANNER_SHORTLIST_SIZE = 12
SCANNER_MAX_CANDIDATES = 60
SCANNER_OHLCV_LIMIT    = 200

SCANNER_TIER1 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]

SCANNER_TIER2 = [
    "LINKUSDT", "AVAXUSDT", "ADAUSDT", "DOGEUSDT", "SUIUSDT",
    "ONDOUSDT", "FETUSDT", "PYTHUSDT", "TAOUSDT",
    "DOTUSDT", "MATICUSDT", "LTCUSDT", "ATOMUSDT", "UNIUSDT",
    "AAVEUSDT", "INJUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
    "STXUSDT", "SEIUSDT", "TIAUSDT", "NEARUSDT", "TRXUSDT",
]

# ═══════════════════════════════════════════════════════════════
# MOMENTUM SCANNER / MOMENTUM COIN SELECTION
# ═══════════════════════════════════════════════════════════════
MOMENTUM_SCANNER_ENABLED  = True
MOMENTUM_SCANNER_INTERVAL = 25
MOMENTUM_MIN_VOLUME_24H   = 10_000_000
MOMENTUM_MAX_SPREAD_PCT   = 0.30
MOMENTUM_MIN_SCORE        = 55.0
MOMENTUM_SHORTLIST_SIZE   = 10
MOMENTUM_MAX_CANDIDATES   = 40
MOMENTUM_OHLCV_LIMIT_1H   = 150
MOMENTUM_OHLCV_LIMIT_15M  = 100
MOMENTUM_OHLCV_LIMIT_5M   = 60

# ═══════════════════════════════════════════════════════════════
# KALİTE AĞIRLIKLI 5 SLOT STRATEJİSİ
# ═══════════════════════════════════════════════════════════════
USE_QUALITY_WEIGHTED_SLOT_STRATEGY = True

SLOT_TOTAL_BALANCE_USDT = 1000.0
SLOT_RESERVE_USDT       = 100.0

SLOT_CONFIG = [
    {"id": 1, "notional": 1000, "quality_min": "B",  "regime_min": "any"},
    {"id": 2, "notional": 1000, "quality_min": "B",  "regime_min": "any"},
    {"id": 3, "notional": 1000, "quality_min": "B",  "regime_min": "any"},
    {"id": 4, "notional": 1000, "quality_min": "B+", "regime_min": "any"},
    {"id": 5, "notional": 1000, "quality_min": "B+", "regime_min": "any"},
]

SLOT_REGIME_MAX_ACTIVE = {
    "WEAK_LIQUIDITY":  2,
    "HIGH_VOLATILITY": 2,
    "UNKNOWN":         2,
    "RANGING":         3,
    "TRENDING_DOWN":   2,
    "MIXED":           3,
    "TRENDING_UP":     4,
    "BULL":            4,
    "BULL_TREND":      5,
    "BULL_MOMENTUM":   4,
    "STRONG":          4,
    "BEAR_TREND":      3,
}
SLOT_REGIME_MAX_DEFAULT = 3

SLOT_WEAK_LIQUIDITY_MIN_QUALITY = "B"

SLOT_QUALITY_RANK = {
    "C":  1,
    "B":  2,
    "B+": 3,
    "A":  4,
    "A+": 5,
}

SLOT_QUALITY_GATE_THRESHOLDS = {
    "A+": 10,
    "A":   9,
    "B":   8,
    "C":   7,
}
SLOT_QUALITY_BPLUS_SCORE_MIN = 80

SLOT_QUALITY_SCORE_THRESHOLDS = {
    "A+": 90,
    "A":  85,
    "B+": 80,
    "B":  75,
    "C":  65,
}

SLOT_ENTRY_MIN_SCORE = 70

# ═══════════════════════════════════════════════════════════════
# PULLBACK SHORT STRATEJİSİ
# ═══════════════════════════════════════════════════════════════
USE_PULLBACK_SHORT_STRATEGY = True

# ✅ DEĞİŞTİRİLDİ: RANGING ve MIXED eklendi
# Önceki: ["BEAR_TREND", "TRENDING_DOWN"]
PULLBACK_SHORT_ACTIVE_REGIMES = ["BEAR_TREND", "TRENDING_DOWN", "RANGING", "MIXED"]

PULLBACK_SHORT_MIN_SCORE   = 6
PULLBACK_SHORT_MIN_QUALITY = "B"

# ═══════════════════════════════════════════════════════════════
# UZUN/KISA REJİM + YÖN FİLTRELERİ (PATCH-5)
# ═══════════════════════════════════════════════════════════════
LONG_BLOCKED_REGIMES      = ["BEAR_TREND", "TRENDING_DOWN"]
LONG_WEAK_REGIMES         = ["RANGING", "WEAK_LIQUIDITY"]
LONG_WEAK_MIN_SCORE_BONUS = 1

SHORT_WEAK_REGIMES = ["RANGING", "MIXED"]

# ✅ DEĞİŞTİRİLDİ: 8 → 7
PULLBACK_SHORT_MIN_SCORE_WEAK = 7

DIRECTION_FLIP_COOLDOWN_SEC = 1800

# ═══════════════════════════════════════════════════════════════
# AŞAMA 2 KÂR ALMA MODU (STAGE2) — TEK AKTİF KÂR SİSTEMİ
# ═══════════════════════════════════════════════════════════════
#
#   Giriş → Bekle
#   +$3   → SL giriş üzerine çek   (zarar engellendi)
#   +$5   → SL kâr garantili       (kâr garantilendi)
#   +$7   → %50 kapat, kalan izle
#   +$10  → Kalan %50 tamamen kapat
#
# NOT: PROFIT_LOCK_1=3, PROFIT_LOCK_2=5, PROFIT_HALF=7, PROFIT_FULL=10
#      Railway Variables'da tanımlı — bot_engine.py oradan okuyor.
# ──────────────────────────────────────────────────────────────
STAGE2_PROFIT_MODE   = True    # Ana switch — kesinlikle True

STAGE2_USDT_TRIGGER  = 7.0    # +$7 → %50 kısmi kapatma
STAGE2_PARTIAL_SIZE  = 0.50   # %50 kapatılır

STAGE2_RUNNER_QUALITY_MIN  = "A"
STAGE2_RUNNER_TP2_PCT      = 0.05
STAGE2_RUNNER_TRAILING_PCT = 0.015

# ═══════════════════════════════════════════════════════════════
# BACKTEST AYARLARI
# ═══════════════════════════════════════════════════════════════
BACKTEST_INITIAL_BALANCE = 10_000
BACKTEST_FEE_RATE        = 0.001
BACKTEST_SLIPPAGE        = 0.0005
BACKTEST_MIN_TRADES      = 20
WALK_FORWARD_SPLITS      = 5

# ═══════════════════════════════════════════════════════════════
# GÜVENLİ CANLI TEST MODU
# ═══════════════════════════════════════════════════════════════
LIVE_TEST_MODE = False

if LIVE_TEST_MODE:
    MAX_OPEN_POSITIONS = 1
    SLOT_CONFIG = [
        {"id": 1, "notional": 75, "quality_min": "B", "regime_min": "any"},
    ]

# ═══════════════════════════════════════════════════════════════
# FORCE MAX SLOT TEST MODE
# ═══════════════════════════════════════════════════════════════
FORCE_MAX_SLOT_TEST_MODE = False

# ═══════════════════════════════════════════════════════════════
# LARGE LOT MODE — Risk/Ödül Bazlı Büyük Lot Sistemi
# ═══════════════════════════════════════════════════════════════
LARGE_LOT_MODE_ENABLED     = True
LARGE_LOT_MIN_QUALITY      = "A"
LARGE_LOT_PREFER_QUALITY   = "A"
WEAK_VOLUME_MIN_QUALITY    = "B"
WEAK_VOLUME_BP_SECOND_CHANCE = True
WEAK_VOLUME_PENDING_TTL_SEC  = 900
LARGE_LOT_STOP_PCT          = 0.0125
LARGE_LOT_TP_PCT            = 0.05
LARGE_LOT_RISK_USDT         = 5.0
LARGE_LOT_MIN_PROFIT_USDT   = 20.0
LARGE_LOT_MIN_NOTIONAL      = 2000.0
LARGE_LOT_STANDARD_NOTIONAL = 2500.0

LARGE_LOT_BPLUS_TP1_PCT      = 0.012
LARGE_LOT_BPLUS_TP1_SIZE     = 0.40
LARGE_LOT_BPLUS_TP2_PCT      = 0.030
LARGE_LOT_BPLUS_TP2_SIZE     = 0.60
LARGE_LOT_BPLUS_TRAILING_PCT = 0.008

LARGE_LOT_AA_TP1_PCT         = 0.012
LARGE_LOT_AA_TP1_SIZE        = 0.40
LARGE_LOT_AA_TP2_PCT         = 0.030
LARGE_LOT_AA_TP2_SIZE        = 0.60
LARGE_LOT_AA_TRAILING_PCT    = 0.008

# ═══════════════════════════════════════════════════════════════
# PATCH-1: Time-Exit Hard Cap — DEVRE DIŞI
# ═══════════════════════════════════════════════════════════════
SMART_EXIT_SMALL_LOT_ABS_MAX_BARS = 999  # ✅ Devre dışı: 120 → 999
SMART_EXIT_LARGE_LOT_ABS_MAX_BARS = 999  # ✅ Devre dışı: 160 → 999

# ═══════════════════════════════════════════════════════════════
# PATCH-2: Large Lot Rejim Filtresi
# ═══════════════════════════════════════════════════════════════
LARGE_LOT_ALLOWED_REGIMES = [
    "TRENDING_UP",
    "STRONG_UP",
    "BULL_TREND",
    "TRENDING",
    "BREAKOUT_UP",
    "RANGING",
]

LARGE_LOT_RANGING_MIN_QUALITY = "A+"

# ═══════════════════════════════════════════════════════════════
# PATCH-3: Ekonomik Filled Notional Filtresi
# ═══════════════════════════════════════════════════════════════
MIN_ECONOMIC_FILLED_NOTIONAL = 750.0

# ═══════════════════════════════════════════════════════════════
# PATCH-4: Aynı Coin Yeniden Giriş Soğuma Süresi
# ═══════════════════════════════════════════════════════════════
SAME_COIN_REENTRY_COOLDOWN_SEC = 900
