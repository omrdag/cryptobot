"""
Merkezi Yapılandırma — Crypto Trading Bot v3
=============================================
Tüm parametreler burada. Modüler ve profesyonel yapı.

GÜNCELLEME — Nisan 2026:
  - PULLBACK_SHORT_ACTIVE_REGIMES: RANGING + MIXED eklendi (short geç kalma sorunu çözüldü)
  - PULLBACK_SHORT_MIN_SCORE_WEAK: 8 → 7 (RANGING'de short eşiği hafifletildi)
  - LONG_MIN_SCORE: 6 (Railway Variables'dan)
  - SHORT_MIN_SCORE: 6 (Railway Variables'dan)
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
KLINE_LIMIT    = 300     # Daha fazla veri → daha iyi indikatörler (min 205 bar gerekir)

# ═══════════════════════════════════════════════════════════════
# AKTİF STRATEJİ
# ═══════════════════════════════════════════════════════════════
# "pullback"      → Trend-Geri-Çekilme (önerilen v3) EMA21 pullback + ADX + Hacim
# "signal_engine" → Çok katmanlı onay sistemi (v2)
# "ema_crossover" → Sadece EMA (eski mod)
ACTIVE_STRATEGY = "pullback"

# ═══════════════════════════════════════════════════════════════
# SIGNAL ENGINE — Çok Katmanlı Sinyal Onay Sistemi
# ═══════════════════════════════════════════════════════════════
SIGNAL_MIN_SCORE       = 60.0   # 10-üzeri gate puanı 6/10 gerekli → normalize ~60

# EMA
EMA_FAST_PERIOD   = 9
EMA_SLOW_PERIOD   = 21
EMA_TREND_PERIOD  = 50

# RSI
RSI_PERIOD        = 14
RSI_BUY_MAX       = 55.0    # v2: BUY için RSI maksimumu düşürüldü (55 üzeri → reddedilir)
RSI_SELL_MIN      = 45.0    # v2: SELL için RSI minimumu yükseltildi
RSI_OVERSOLD      = 35.0
RSI_OVERBOUGHT    = 65.0

# ATR
ATR_PERIOD        = 14
ATR_SL_MULTIPLIER = 2.5   # Geniş stop loss — 1H sinyal için nefes alanı
ATR_TP_MULTIPLIER = 4.0   # v2: TP uzatıldı → RR = 1.6x (2.5SL : 4.0TP)

# v2: ADX minimum eşiği — trend olmadan BUY/SELL engellenir
ADX_MIN_THRESHOLD = 18.0

# v2: Kapı sistemi minimum puan (10 üzerinden)
GATE_MIN_SCORE    = 6

# Mum onayı
CANDLE_CONFIRM_BARS = 2

# Hacim onayı
VOLUME_MIN_RATIO  = 1.0     # v2: 0.8 → 1.0 (ortalama hacmin altında giriş yok)

# Minimum ATR/fiyat
MIN_ATR_THRESHOLD = 0.002   # v2: 0.001 → 0.002 (volatilite kalitesi için)

# ═══════════════════════════════════════════════════════════════
# MARKET REGIME FILTER
# ═══════════════════════════════════════════════════════════════
REGIME_ENABLED          = True
REGIME_TREND_ADX        = 22.0   # ADX > 22 → trend var
REGIME_HIGH_VOL_RATIO   = 0.04   # ATR/fiyat > 4% → yüksek volatilite
REGIME_LOW_VOL_RATIO    = 0.005  # ATR/fiyat < 0.5% → düşük volatilite
REGIME_RANGING_BB_WIDTH = 0.025  # BB genişliği < 2.5% → ranging
REGIME_MIN_VOL_RATIO    = 0.35   # Son hacim < ortalama × 0.35 → zayıf likidite

# Strateji-Rejim uyumu:
# - "signal_engine" → trending + ranging'de çalışır
# - "ema_crossover" → sadece trending'de
# - Weak Liquidity → hiçbir strateji çalışmaz
REGIME_NO_TRADE = ["WEAK_LIQUIDITY"]      # Bu rejimlerde işlem yok
REGIME_REDUCE   = ["HIGH_VOLATILITY"]     # Bu rejimlerde %50 pozisyon

# ═══════════════════════════════════════════════════════════════
# EMA CROSSOVER STRATEJİSİ (Eski mod)
# ═══════════════════════════════════════════════════════════════
MAX_HOLDING_CANDLES = 6   # 6 × 1h = 6 saat
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
POSITION_SIZING_MODE = "atr"   # "atr" veya "fixed"
RISK_PER_TRADE_PCT   = 0.01   # %1 risk per trade
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
# SMART EXIT — Kısmi TP + Breakeven + Trailing + Zaman Bazlı
# ═══════════════════════════════════════════════════════════════
BREAKEVEN_TRIGGER_PCT     = 0.8
BREAKEVEN_OFFSET_PCT      = 0.1

PARTIAL_TP1_PCT           = 1.2
PARTIAL_TP1_SIZE          = 100
PARTIAL_TP2_PCT           = 2.8
PARTIAL_TP2_SIZE          = 0
RUNNER_POSITION_PCT       = 0

TRAILING_STOP_ENABLED     = True
TRAILING_STOP_PCT         = 0.01
BREAK_EVEN_ENABLED        = True
BREAK_EVEN_PCT            = 0.012

MAX_BARS_IN_TRADE         = 6
MIN_PROFIT_AFTER_4_BARS   = 0.8

SMART_EXIT_BASE_MAX_BARS      = 8
SMART_EXIT_LARGE_LOT_MAX_BARS = 10
SMART_EXIT_TP1_EXTENSION      = 3
SMART_EXIT_BE_EXTENSION       = 2
SMART_EXIT_TREND_MAX_BARS     = 12
SMART_EXIT_ADX_STRONG_MIN     = 25
SMART_EXIT_DELAY_BARS         = 2
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
MAX_OPEN_POSITIONS     = 5
DAILY_MAX_LOSS_PCT     = 0.05
MAX_TOTAL_OPEN_RISK_PCT= 0.02
MAX_CONSECUTIVE_LOSS   = 5
MAX_SYMBOL_EXPOSURE    = 0.30
MAX_DRAWDOWN_PCT       = 0.15
DRAWDOWN_WARN_PCT      = 0.08
DEFENSE_LOSS_COUNT     = 3
DEFENSE_SIZE_FACTOR    = 0.5
KILL_SWITCH            = False

SYMBOL_MAX_CONSEC_LOSS = 2
SYMBOL_COOLDOWN_HOURS  = 4.0

MAX_DAILY_TRADES_PER_SYMBOL = 2

TRADING_HOURS_UTC      = list(range(24))
TRADING_HOURS_ENABLED  = False

# ═══════════════════════════════════════════════════════════════
# MARKET SCANNER / COIN SELECTION
# ═══════════════════════════════════════════════════════════════
SCANNER_ENABLED          = True
SCANNER_INTERVAL_LOOPS   = 20
SCANNER_MIN_VOLUME_24H   = 5_000_000
SCANNER_MAX_SPREAD_PCT   = 0.5
SCANNER_MIN_SCORE        = 50.0
SCANNER_SHORTLIST_SIZE   = 12
SCANNER_MAX_CANDIDATES   = 60
SCANNER_OHLCV_LIMIT      = 200

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
MOMENTUM_SCANNER_ENABLED    = True
MOMENTUM_SCANNER_INTERVAL   = 25
MOMENTUM_MIN_VOLUME_24H     = 10_000_000
MOMENTUM_MAX_SPREAD_PCT     = 0.30
MOMENTUM_MIN_SCORE          = 55.0
MOMENTUM_SHORTLIST_SIZE     = 10
MOMENTUM_MAX_CANDIDATES     = 40
MOMENTUM_OHLCV_LIMIT_1H     = 150
MOMENTUM_OHLCV_LIMIT_15M    = 100
MOMENTUM_OHLCV_LIMIT_5M     = 60

# ═══════════════════════════════════════════════════════════════
# KALİTE AĞIRLIKLI 5 SLOT STRATEJİSİ
# ═══════════════════════════════════════════════════════════════
USE_QUALITY_WEIGHTED_SLOT_STRATEGY = True

SLOT_TOTAL_BALANCE_USDT  = 1000.0
SLOT_RESERVE_USDT        = 100.0

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
# Sebep: Piyasa dönüş yaparken RANGING rejiminde short sinyalleri
#        yakalanabilsin — geç kalma sorunu çözüldü
PULLBACK_SHORT_ACTIVE_REGIMES = ["BEAR_TREND", "TRENDING_DOWN", "RANGING", "MIXED"]

PULLBACK_SHORT_MIN_SCORE = 6

PULLBACK_SHORT_MIN_QUALITY = "B"

# ═══════════════════════════════════════════════════════════════
# UZUN/KISA REJİM + YÖN FİLTRELERİ (PATCH-5)
# ═══════════════════════════════════════════════════════════════
LONG_BLOCKED_REGIMES          = ["BEAR_TREND", "TRENDING_DOWN"]
LONG_WEAK_REGIMES             = ["RANGING", "WEAK_LIQUIDITY"]
LONG_WEAK_MIN_SCORE_BONUS     = 1

SHORT_WEAK_REGIMES            = ["RANGING", "MIXED"]

# ✅ DEĞİŞTİRİLDİ: 8 → 7
# Önceki: 8
# Sebep: RANGING rejimi artık short için aktif — eşik biraz gevşetildi
#        Hala 7/10 minimum kalite koruyor (3/10 gibi zayıf sinyaller engelleniyor)
PULLBACK_SHORT_MIN_SCORE_WEAK = 7

DIRECTION_FLIP_COOLDOWN_SEC   = 1800

# ═══════════════════════════════════════════════════════════════
# AŞAMA 2 KÂR ALMA MODU (STAGE2)
# ═══════════════════════════════════════════════════════════════
STAGE2_PROFIT_MODE          = True

STAGE2_USDT_TRIGGER         = 10.0
STAGE2_PARTIAL_SIZE         = 0.50

STAGE2_RUNNER_QUALITY_MIN   = "A"
STAGE2_RUNNER_TP2_PCT       = 0.05
STAGE2_RUNNER_TRAILING_PCT  = 0.015

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
LARGE_LOT_MODE_ENABLED      = True
LARGE_LOT_MIN_QUALITY       = "A"
LARGE_LOT_PREFER_QUALITY    = "A"
WEAK_VOLUME_MIN_QUALITY       = "B"
WEAK_VOLUME_BP_SECOND_CHANCE  = True
WEAK_VOLUME_PENDING_TTL_SEC   = 900
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
# PATCH-1: Time-Exit Hard Cap
# ═══════════════════════════════════════════════════════════════
SMART_EXIT_SMALL_LOT_ABS_MAX_BARS = 120
SMART_EXIT_LARGE_LOT_ABS_MAX_BARS = 160

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
