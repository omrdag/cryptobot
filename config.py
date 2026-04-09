"""
Merkezi Yapılandırma — Crypto Trading Bot v3
=============================================
Tüm parametreler burada. Modüler ve profesyonel yapı.
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
LEVERAGE = int(os.getenv("LEVERAGE", "10"))   # 1=kaldıraçsız, 3=3x, 5=5x, 10=10x vb.
# LEVERAGE OVERRIDE: Ortam değişkeni 5x olarak ayarlıydı; OKX hesabı ve notional
# hesaplamaları 10x için yapılandırılmıştır. Tutarlılık için burada açıkça 10 yapıyoruz.
# LEVERAGE ortam değişkenini güncelledikten sonra bu satırı kaldırabilirsiniz.
LEVERAGE = 10

# ═══════════════════════════════════════════════════════════════
# POZİSYON BOYUTLANDIRMA
# ═══════════════════════════════════════════════════════════════
POSITION_SIZING_MODE = "atr"   # "atr" veya "fixed"
RISK_PER_TRADE_PCT   = 0.01   # %1 risk per trade
TRADE_AMOUNT_PCT     = 0.10

# UI'dan okunur (DB → config, load_mode_from_db):
#   "auto"    → bakiye / maks_pozisyon (en mantıklı seçenek)
#   "fixed"   → sabit USDT miktarı
#   "percent" → bakiyenin yüzdesi
TRADE_AMOUNT      = 100.0   # Sabit mod (USDT) veya oran (%)
TRADE_AMOUNT_TYPE = "auto"  # Varsayılan: otomatik bölüştürme

STOP_LOSS_PCT   = 0.02
TAKE_PROFIT_PCT = 0.04

# ═══════════════════════════════════════════════════════════════
# POZİSYON ROTASYONU
# ═══════════════════════════════════════════════════════════════
# Sinyal skoru bu eşiği geçerse en zayıf pozisyon kapatılıp yer açılır
ROTATION_MIN_SCORE = 78

# ═══════════════════════════════════════════════════════════════
# SMART EXIT — Kısmi TP + Breakeven + Trailing + Zaman Bazlı
# ═══════════════════════════════════════════════════════════════
# Breakeven: +BREAKEVEN_TRIGGER_PCT kârda SL giriş fiyatına çekilir
BREAKEVEN_TRIGGER_PCT     = 0.8    # %+0.8 kâr → SL breakeven'e taşı (agresif: daha erken)
BREAKEVEN_OFFSET_PCT      = 0.1    # Breakeven + %0.1 küçük pozitif offset

# Kısmi TP: TP1'de pozisyonun TAMAMI kapatılır (runner yok — hızlı kâr yakalama modu)
PARTIAL_TP1_PCT           = 1.2    # %+1.2 → TP1 tetikle ve tamamını kapat
PARTIAL_TP1_SIZE          = 100    # Pozisyonun %100'ünü kapat (tam çıkış)
PARTIAL_TP2_PCT           = 2.8    # (TP1=100 olduğu için artık tetiklenmez)
PARTIAL_TP2_SIZE          = 0      # Devre dışı
RUNNER_POSITION_PCT       = 0      # Runner yok — hızlı kâr modu

# Trailing Stop: Runner (%40) için
TRAILING_STOP_ENABLED     = True
TRAILING_STOP_PCT         = 0.01   # %1.0 trailing stop (runner için)
BREAK_EVEN_ENABLED        = True
BREAK_EVEN_PCT            = 0.012  # Breakeven trigger (0.012 = %1.2)

# Zaman bazlı çıkış kuralları
MAX_BARS_IN_TRADE         = 6      # Maksimum 6 mum (6 × 1h = 6 saat)
MIN_PROFIT_AFTER_4_BARS   = 0.8    # 4. mumdan sonra %0.8 kâr yoksa kapat

# ── Akıllı Zaman Bazlı Çıkış (Smart Time Exit) ──────────────────────────────
# Pullback Long strateji için dinamik max bar sistemi.
# Bot kötü işlemleri hâlâ erken kapatır; iyi işlemlere daha fazla zaman tanır.
SMART_EXIT_BASE_MAX_BARS      = 8    # Küçük lot: profil max_bars yerine geçer (8 mum)
SMART_EXIT_LARGE_LOT_MAX_BARS = 10   # Large lot: daha büyük pozisyon = daha fazla süre
SMART_EXIT_TP1_EXTENSION      = 3    # TP1 tetiklendikten sonra +3 mum ek süre
SMART_EXIT_BE_EXTENSION       = 2    # Sadece BE tetiklendiyse (TP1 yoksa) +2 mum
SMART_EXIT_TREND_MAX_BARS     = 12   # Güçlü trend varsa maksimum uzatılacak mum sayısı
SMART_EXIT_ADX_STRONG_MIN     = 25   # ADX bu eşiğin üzerindeyse "güçlü trend" sayılır
SMART_EXIT_DELAY_BARS         = 2    # Hafif pozitif/BE yakını pozisyon için ekstra izin verilen mum sayısı
SMART_EXIT_DELAY_LOSS_TOL     = 0.003  # Bu eşiğin üstündeyse (%-0.3) seçici gecikmede pozisyon tutulur

# ═══════════════════════════════════════════════════════════════
# PAPER TRADING — GERÇEKÇİ SİMÜLASYON
# ═══════════════════════════════════════════════════════════════
FEE_RATE          = 0.001    # %0.1 komisyon
SLIPPAGE_PCT      = 0.0005   # %0.05 slippage
PARTIAL_FILL_PROB = 0.0

# ═══════════════════════════════════════════════════════════════
# POZİSYON BOYUTLANDIRMA — RİSK BAZLI SİSTEM (v3)
# ═══════════════════════════════════════════════════════════════
# İşlem başı maks risk: bakiyenin %1'i (1000 USDT hesapta = 10 USDT)
# Pozisyon notional = risk / SL% — ardından min/max ile sınırlandır
POSITION_MIN_USDT      = 75.0    # Minimum işlem büyüklüğü — C kalite sinyali (USDT notional)
MIN_ECONOMIC_NOTIONAL  = 100.0   # Ekonomik verimlilik eşiği: hesaplanan notional bu değerin altındaysa işlem açılmaz
POSITION_DEFAULT_USDT  = 100.0   # Varsayılan işlem büyüklüğü — B kalite sinyali
POSITION_STRONG_USDT   = 125.0   # Güçlü sinyal — A kalite
POSITION_MAX_USDT      = 150.0   # Hard cap — maksimum notional

# Sinyal kalitesi → hedef notional (USDT) — TAM miktarlar
# Risk hesabı bu değerleri üst sınır olarak kullanır; risk < hedef ise risk kullanılır
POSITION_NOTIONAL_BY_QUALITY = {
    "A": 125.0,   # Güçlü sinyal: gate≥9 veya score≥85
    "B": 100.0,   # Normal sinyal: gate≥8 veya score≥75
    "C":  75.0,   # Zayıf sinyal:  gate=7 veya score≥65
}

# Sinyal kalitesi → çarpan (POSITION_DEFAULT_USDT bazında)
SIGNAL_QUALITY_MULTIPLIER = {
    "A": 1.25,   # 100 × 1.25 = 125 USDT
    "B": 1.00,   # 100 × 1.00 = 100 USDT
    "C": 0.75,   # 100 × 0.75 =  75 USDT
}

# Strateji türüne göre hedef notional aralıkları (referans — sizer tarafından kullanılmaz)
POSITION_TARGET_MOMENTUM   = (75.0,  100.0)
POSITION_TARGET_REVERSAL   = (100.0, 125.0)
POSITION_TARGET_DIVERGENCE = (100.0, 100.0)
POSITION_TARGET_PULLBACK   = (75.0,  150.0)

# ═══════════════════════════════════════════════════════════════
# RİSK YÖNETİMİ
# ═══════════════════════════════════════════════════════════════
MAX_OPEN_POSITIONS     = 5
DAILY_MAX_LOSS_PCT     = 0.05    # %5 günlük max zarar → kill switch
MAX_TOTAL_OPEN_RISK_PCT= 0.02    # Toplam açık pozisyon riski maks %2 bakiye
MAX_CONSECUTIVE_LOSS   = 5       # Art arda bu kadar kayıp → durdur
MAX_SYMBOL_EXPOSURE    = 0.30
MAX_DRAWDOWN_PCT       = 0.15    # %15 drawdown → tam durdur
DRAWDOWN_WARN_PCT      = 0.08    # %8 drawdown → pozisyon küçült
DEFENSE_LOSS_COUNT     = 3       # Bu kadar art arda kayıptan sonra savunma modu
DEFENSE_SIZE_FACTOR    = 0.5     # Savunma modunda pozisyon × 0.5
KILL_SWITCH            = False

# ── Sembol Bazlı Cooldown ─────────────────────────────────────────────────
# Aynı sembolde N art arda kayıptan sonra sembolü X saat bloke eder
SYMBOL_MAX_CONSEC_LOSS = 2       # Kaç art arda kayıptan sonra sembol bloke?
SYMBOL_COOLDOWN_HOURS  = 4.0     # v2: 2 → 4 saat (daha uzun cooldown)

# v2: Günlük sembol başına maksimum işlem sayısı (aşırı işlem koruması)
MAX_DAILY_TRADES_PER_SYMBOL = 2  # Aynı sembolde günde max 2 işlem

# ── Saat Bazlı İşlem Filtresi (UTC) ──────────────────────────────────────
# v3: Tüm saatler açık (24/7) — kullanıcı talebi
TRADING_HOURS_UTC      = list(range(24))  # 0-23 arası tüm saatler
TRADING_HOURS_ENABLED  = False   # v3: Devre dışı → 24 saat aktif

# ═══════════════════════════════════════════════════════════════
# MARKET SCANNER / COIN SELECTION
# ═══════════════════════════════════════════════════════════════
SCANNER_ENABLED          = True          # False → eski sabit liste davranışı
SCANNER_INTERVAL_LOOPS   = 20           # Her 20 döngüde bir yeniden tara (~20 dak)
SCANNER_MIN_VOLUME_24H   = 5_000_000    # Min. 24h hacim ($)
SCANNER_MAX_SPREAD_PCT   = 0.5          # Max. bid/ask spread (%)
SCANNER_MIN_SCORE        = 50.0         # Bu skorun altındaki coinler elenir
SCANNER_SHORTLIST_SIZE   = 12           # Shortlist'e alınacak max coin sayısı
SCANNER_MAX_CANDIDATES   = 60           # Ön filtre sonrası max aday sayısı
SCANNER_OHLCV_LIMIT      = 200          # Her coin için çekilecek mum sayısı

# Tier 1 — yüksek likidite, tam pozisyon boyutu
SCANNER_TIER1 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]

# Tier 2 — orta likidite, normal işlem
SCANNER_TIER2 = [
    "LINKUSDT", "AVAXUSDT", "ADAUSDT", "DOGEUSDT", "SUIUSDT",
    "ONDOUSDT", "FETUSDT", "PYTHUSDT", "TAOUSDT",
    "DOTUSDT", "MATICUSDT", "LTCUSDT", "ATOMUSDT", "UNIUSDT",
    "AAVEUSDT", "INJUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
    "STXUSDT", "SEIUSDT", "TIAUSDT", "NEARUSDT", "TRXUSDT",
]

# Tier 3 — riskli, küçük boyut veya yasak (Tier2/3 dışı tüm coinler)

# ═══════════════════════════════════════════════════════════════
# MOMENTUM SCANNER / MOMENTUM COIN SELECTION
# ═══════════════════════════════════════════════════════════════
MOMENTUM_SCANNER_ENABLED    = True          # Momentum tarayıcısını aktifleştir
MOMENTUM_SCANNER_INTERVAL   = 25            # Her N döngüde bir tara (~25 dak)
MOMENTUM_MIN_VOLUME_24H     = 10_000_000    # Min. 24h hacim ($) — genel'den daha sıkı
MOMENTUM_MAX_SPREAD_PCT     = 0.30          # Max. spread (%)
MOMENTUM_MIN_SCORE          = 55.0          # Min. momentum skor eşiği
MOMENTUM_SHORTLIST_SIZE     = 10            # Shortlist'e alınacak max coin sayısı
MOMENTUM_MAX_CANDIDATES     = 40            # Ön filtre sonrası max aday
MOMENTUM_OHLCV_LIMIT_1H     = 150           # 1H mum sayısı
MOMENTUM_OHLCV_LIMIT_15M    = 100           # 15M mum sayısı
MOMENTUM_OHLCV_LIMIT_5M     = 60            # 5M mum sayısı

# ═══════════════════════════════════════════════════════════════
# KALİTE AĞIRLIKLI 5 SLOT STRATEJİSİ
# ═══════════════════════════════════════════════════════════════
# Feature flag: False → eski sistem (A/B/C → 75/100/125 USDT)
#               True  → yeni 5-slot motoru aktif
USE_QUALITY_WEIGHTED_SLOT_STRATEGY = True

# Toplam bakiye / rezerv
SLOT_TOTAL_BALANCE_USDT  = 1000.0   # Hedef bakiye (gerçek bakiye okunur)
SLOT_RESERVE_USDT        = 100.0    # Asla kullanılmayacak minimum marjin rezervi ($100)

# 5 slot konfigürasyonu
# quality_min: bu slotu almak için minimum sinyal kalitesi
# regime_min : "any" | "medium" | "strong"
SLOT_CONFIG = [
    {"id": 1, "notional": 1000, "quality_min": "B",  "regime_min": "any"},  # Slot 1: B  — 1000 USDT (~$100 marjin)
    {"id": 2, "notional": 1000, "quality_min": "B",  "regime_min": "any"},  # Slot 2: B  — 1000 USDT (~$100 marjin)
    {"id": 3, "notional": 1000, "quality_min": "B",  "regime_min": "any"},  # Slot 3: B  — 1000 USDT (~$100 marjin)
    {"id": 4, "notional": 1000, "quality_min": "B+", "regime_min": "any"},  # Slot 4: B+ — 1000 USDT (~$100 marjin)
    {"id": 5, "notional": 1000, "quality_min": "B+", "regime_min": "any"},  # Slot 5: B+ — 1000 USDT (~$100 marjin)
]

# Piyasa rejimine göre aynı anda maksimum aktif slot sayısı
# Stage2: güçlü rejimlerde 4-5 slot, zayıf rejimlerde koruyucu üst sınır
SLOT_REGIME_MAX_ACTIVE = {
    "WEAK_LIQUIDITY":  2,    # Zayıf likidite: max 2 slot (koruyucu)
    "HIGH_VOLATILITY": 2,    # Yüksek volatilite: max 2 slot
    "UNKNOWN":         2,
    "RANGING":         3,    # Yatay piyasa: max 3 slot
    "TRENDING_DOWN":   2,    # Düşüş trendi: dikkatli
    "MIXED":           3,    # Karışık: max 3 slot
    "TRENDING_UP":     4,    # Yükseliş: max 4 slot
    "BULL":            4,    # Boğa: max 4 slot
    "BULL_TREND":      5,    # Güçlü boğa: tam 5 slot
    "BULL_MOMENTUM":   4,    # Momentum boğa: max 4 slot
    "STRONG":          4,
    "BEAR_TREND":      3,    # Ayı: short sinyaller için max 3 slot
}
SLOT_REGIME_MAX_DEFAULT = 3   # Tanımlanmamış rejim için varsayılan

# WEAK_LIQUIDITY rejiminde izin verilen minimum kalite seviyesi
# "B+"  → Sadece güçlü sinyaller (daha seçici, daha az işlem)
# "B"   → 8/10 Pullback sinyallere de izin verir (daha fazla işlem, max 1 slot)
SLOT_WEAK_LIQUIDITY_MIN_QUALITY = "B"

# Sinyal kalitesi → slot sıralaması (düşük→yüksek)
# Sinyal bu kalitenin üstündeki veya eşit slotları alabilir
SLOT_QUALITY_RANK = {
    "C":  1,
    "B":  2,
    "B+": 3,
    "A":  4,
    "A+": 5,
}

# Genişletilmiş sinyal kalitesi tespiti (pullback gate skoru bazlı)
# gate=7→C, gate=8→B, gate=8+score≥80→B+, gate=9→A, gate=10→A+
SLOT_QUALITY_GATE_THRESHOLDS = {
    "A+": 10,    # gate=10
    "A":   9,    # gate=9
    "B":   8,    # gate=8
    "C":   7,    # gate=7 (minimum)
}
# B+ için ilave skor koşulu (gate=8 AND score≥80)
SLOT_QUALITY_BPLUS_SCORE_MIN = 80

# Sinyal skoru bazlı kalite (signal_engine için)
# A+: 90+ → 200-250 USDT | A: 85-89 → 150 USDT | B+: 80-84 → 125 USDT
# B:  75-79 → 100 USDT   | C: 70-74 → İzleme listesi (işlem YOK)
# <70: REDDEDİLDİ
SLOT_QUALITY_SCORE_THRESHOLDS = {
    "A+": 90,
    "A":  85,
    "B+": 80,
    "B":  75,
    "C":  65,   # 65-74 = C kalite — işlem açılır (gevşetildi, eski: 70)
}

# Bu skorun altındaki sinyaller için işlem açılmaz (izleme modu)
SLOT_ENTRY_MIN_SCORE = 65   # Gevşetildi: eski=75, şimdi C kalite sinyaller de girer

# ═══════════════════════════════════════════════════════════════
# PULLBACK SHORT STRATEJİSİ
# ═══════════════════════════════════════════════════════════════
# Feature flag: False → Pullback Short devre dışı (varsayılan güvenli)
#               True  → BEAR_TREND rejiminde short fırsatları değerlendirilir
USE_PULLBACK_SHORT_STRATEGY = True

# Short stratejisinin aktif olduğu piyasa rejimleri
# "BEAR_TREND"  → ana hedef: ≥60% coin DOWN trendde
# "MIXED"       → isteğe bağlı, yalnızca yüksek kalite shortlara izin verilir
PULLBACK_SHORT_ACTIVE_REGIMES = ["BEAR_TREND", "RANGING", "MIXED"]  # Daha fazla rejimde short

# Short strateji minimum teknik puan (10 üzerinden)
PULLBACK_SHORT_MIN_SCORE = 6   # Gevşetildi: eski=7, daha fazla short sinyali

# Short için minimum kalite seviyesi (slot sistemi ile entegre)
PULLBACK_SHORT_MIN_QUALITY = "C"   # C ve üstü — gevşetildi (eski: "B")

# ═══════════════════════════════════════════════════════════════
# UZUN/KISA REJİM + YÖN FİLTRELERİ (PATCH-5)
# ═══════════════════════════════════════════════════════════════

# LONG — bu rejimlerde açılmaz (piyasa yönüne karşı)
LONG_BLOCKED_REGIMES          = ["BEAR_TREND", "TRENDING_DOWN"]
# LONG — bu rejimlerde min puan +1 artar (daha seçici)
LONG_WEAK_REGIMES             = ["RANGING", "WEAK_LIQUIDITY"]
LONG_WEAK_MIN_SCORE_BONUS     = 1       # Zayıf rejimde eklenen puan

# SHORT — bu rejimlerde min puan yükseltilir
SHORT_WEAK_REGIMES            = ["RANGING", "MIXED"]
PULLBACK_SHORT_MIN_SCORE_WEAK = 8       # Zayıf rejimde SHORT min puan (normal=6)

# Yön değiştirme engeli: son kapanıştan bu süre içinde karşı yöne giriş yok
DIRECTION_FLIP_COOLDOWN_SEC   = 1800    # 30 dakika

# ═══════════════════════════════════════════════════════════════
# AŞAMA 2 KÂR ALMA MODU (STAGE2)
# ═══════════════════════════════════════════════════════════════
# Ana switch — False yapınca eski % tabanlı TP davranışı geri döner.
STAGE2_PROFIT_MODE          = True

# Mutlak USDT kâr tetikleyici: gerçekleşmemiş PnL bu eşiğe ulaşınca kısmi çıkış.
# % TP1 hangisi önce tetiklenirse o geçerlidir.
STAGE2_USDT_TRIGGER         = 10.0     # +$10 gerçekleşmemiş kâr → kısmi kapatma
STAGE2_PARTIAL_SIZE         = 0.50     # Tetik anında kapatılacak kısım (%50)

# Runner modu — yalnızca yüksek kaliteli sinyallerde aktif.
# A veya üstü kalitede kalan %50 daha geniş TP2 ve trailing ile devam eder.
STAGE2_RUNNER_QUALITY_MIN   = "A"      # "A" veya "A+" kalite için runner
STAGE2_RUNNER_TP2_PCT       = 0.05     # Runner TP2 hedefi: +%5 (standart %2.5'ten geniş)
STAGE2_RUNNER_TRAILING_PCT  = 0.015    # Runner trailing stop: %1.5 (standart %1.0'dan geniş)

# ═══════════════════════════════════════════════════════════════
# BACKTEST AYARLARI
# ═══════════════════════════════════════════════════════════════
BACKTEST_INITIAL_BALANCE = 10_000
BACKTEST_FEE_RATE        = 0.001
BACKTEST_SLIPPAGE        = 0.0005
BACKTEST_MIN_TRADES      = 20     # Güvenilir sonuç için minimum işlem sayısı
WALK_FORWARD_SPLITS      = 5      # Walk-forward blok sayısı

# ═══════════════════════════════════════════════════════════════
# GÜVENLİ CANLI TEST MODU
# ═══════════════════════════════════════════════════════════════
# İlk 1-2 canlı işlem OKX'te doğrulandıktan sonra:
#   1. LIVE_TEST_MODE = False yapın
#   2. API Server'ı yeniden başlatın
# Bu blok devre dışı kalınca: MAX_OPEN_POSITIONS=5, tam SLOT_CONFIG devreye girer.
#
# GERİ ALMA REFERANSI (False yaptığınızda geri dönecek değerler):
#   MAX_OPEN_POSITIONS = 5
#   SLOT_CONFIG[0] notional = 100  (B kalite — min 100 USDT)
#   SLOT_CONFIG[1] notional = 100  (B kalite — min 100 USDT)
#   SLOT_CONFIG[2] notional = 100  (B kalite — min 100 USDT)
#   SLOT_CONFIG[3] notional = 100  (B kalite — min 100 USDT)
#   SLOT_CONFIG[4] notional = 125  (B kalite — bonus 5. slot)
# ───────────────────────────────────────────────────────────────
LIVE_TEST_MODE = False  # Production: tam 5-slot sistemi aktif (MAX_OPEN_POSITIONS=5)
# Geri almak için: LIVE_TEST_MODE = True  → API Server restart yeterli

if LIVE_TEST_MODE:
    # Güvenli test: yalnızca 1 eş zamanlı pozisyon
    MAX_OPEN_POSITIONS = 1

    # Yalnızca Slot 1 aktif — 75 USDT notional (10x = $7.5 margin)
    # Diğer slotlar listede yok → SlotManager otomatik pasif bırakır
    SLOT_CONFIG = [
        {"id": 1, "notional": 75, "quality_min": "B", "regime_min": "any"},
    ]

# ═══════════════════════════════════════════════════════════════
# FORCE MAX SLOT TEST MODE — Slot Notional Maksimum Override
# ═══════════════════════════════════════════════════════════════
# Slot filtreleri (kalite, rejim, reserve) aynen çalışır.
# Slot başarıyla atandıktan SONRA notional'ı SLOT_CONFIG'deki
# en yüksek slot'a yükseltir.
#
# Kullanım amacı: Large Lot / büyük notional akışını LIVE_TEST
# ortamında gerçek para ile test etmek.
#
# Dikkat: LIVE_TEST_MODE=True ile kombinlenince SLOT_CONFIG
#   sadece 1 slot (75 USDT) içerir → max = 75 USDT.
#   Tam büyük notional testleri için LIVE_TEST_MODE=False gerekir.
# ───────────────────────────────────────────────────────────────
FORCE_MAX_SLOT_TEST_MODE = False   # True yapınca max slot notional override aktif

# ═══════════════════════════════════════════════════════════════
# LARGE LOT MODE — Risk/Ödül Bazlı Büyük Lot Sistemi
# ═══════════════════════════════════════════════════════════════
# Sadece güçlü sinyallerde aktif: kalite B+ ve üstü (skor ≥ 80)
#
# Risk Formülü:
#   position_notional = LARGE_LOT_RISK_USDT / LARGE_LOT_STOP_PCT
#                     = 5.0 / 0.0125 = 400 USDT (minimum)
#   expected_profit   = notional × LARGE_LOT_TP_PCT
#                     = 400 × 0.05  = 20 USDT  (eşik)
#                     = 500 × 0.05  = 25 USDT  (A/A+ tercih)
#
# Kalite → Notional:
#   B  (75-79) : Büyük lot KAPAL — standart slot (175 USDT)
#   B+ (80-84) : Büyük lot KAPALI — LARGE_LOT_MIN_QUALITY="A" ile engellendi
#   A  (85-89) : 400 USDT notional  |  SL=%1.25  TP=%5.0  R/R=4:1
#   A+ (90+)   : 500 USDT notional  |  SL=%1.25  TP=%5.0  R/R=4:1
#
# NOT: LIVE_TEST_MODE aktifken bu mod otomatik devre dışı kalır.
#      (LIVE_TEST_MODE'da notional=75 USDT sabit)
# ───────────────────────────────────────────────────────────────
LARGE_LOT_MODE_ENABLED      = True
LARGE_LOT_MIN_QUALITY       = "A"     # Minimum kalite: A  (skor ≥ 85) — B+ large lot riski azaltmak için yükseltildi
LARGE_LOT_PREFER_QUALITY    = "A"     # Bu kalite ve üstü → standart notional kullan
WEAK_VOLUME_MIN_QUALITY       = "B"     # Hacim zayıfken giriş için gereken min kalite (B = skor≥75; gevşetildi — eski: "A"=skor≥85)
WEAK_VOLUME_BP_SECOND_CHANCE  = True   # B+ kalite hacimsizde ilk sinyalde beklemeye alınır, ikincide açılır
WEAK_VOLUME_PENDING_TTL_SEC   = 900    # B+ pending sinyal bu kadar saniye geçerliliğini korur (15 dk = 1-2 scan)
LARGE_LOT_STOP_PCT          = 0.0125  # %1.25 sabit stop-loss
LARGE_LOT_TP_PCT            = 0.05    # %5.00 sabit take-profit
LARGE_LOT_RISK_USDT         = 5.0     # Hedef risk (USDT): notional = risk / stop_pct
LARGE_LOT_MIN_PROFIT_USDT   = 20.0    # Minimum beklenen kâr (USDT) — 400 × 0.05 = 20
LARGE_LOT_MIN_NOTIONAL      = 2000.0  # Minimum large lot notional (slot 1000 → large lot 2000+)
LARGE_LOT_STANDARD_NOTIONAL = 2500.0  # A/A+ kalite için standart large lot notional

# ── Large Lot TP Profili — Birleşik Dengeli Kâr Koruma ──────────────────────
# Tüm kalite seviyeleri (B+/A/A+) için tek profil.
# _large_lot_active=True olduğunda bot_profiles uygulamasının ÜSTÜNE yazar.
# Runtime'da main.py LARGE_LOT_BPLUS_* sabitlerini kullanır (birleşik).
#
# Zincir: BE +%0.5 → TP1 +%0.8 (%50 kapat) → [RUNNER ACTIVE] →
#         TP2 +%1.8 (kalan %50 kapat) | trailing %0.5 runner koruma
#
# ─── Birleşik Profil (B+ / A / A+) — dengeli kâr koruma ────────────────────
LARGE_LOT_BPLUS_TP1_PCT      = 0.008   # %0.8 → 1. kısmi çıkış (erken kâr al)
LARGE_LOT_BPLUS_TP1_SIZE     = 0.50    # %50 kapatılır
LARGE_LOT_BPLUS_TP2_PCT      = 0.018   # %1.8 → 2. kısmi çıkış (runner nihai hedef)
LARGE_LOT_BPLUS_TP2_SIZE     = 0.50    # %50 daha kapatılır → pozisyon tamamen kapanır
# Runner = 1 - 0.50 - 0.50 = %0 → TP2 sonrası tamamen kapanır
LARGE_LOT_BPLUS_TRAILING_PCT = 0.005   # %0.5 trailing stop (sıkı koruma)

# ─── A / A+ — birleşik profil (BPLUS ile aynı) ─────────────────────────────
# Tanımlar korunuyor; runtime main.py yalnızca BPLUS_* kullanır.
LARGE_LOT_AA_TP1_PCT         = 0.008   # %0.8 → 1. kısmi çıkış
LARGE_LOT_AA_TP1_SIZE        = 0.50    # %50 kapatılır
LARGE_LOT_AA_TP2_PCT         = 0.018   # %1.8 → 2. kısmi çıkış
LARGE_LOT_AA_TP2_SIZE        = 0.50    # %50 daha kapatılır → pozisyon tamamen kapanır
# Runner = 1 - 0.50 - 0.50 = %0 → TP2 sonrası tamamen kapanır
LARGE_LOT_AA_TRAILING_PCT    = 0.005   # %0.5 trailing stop

# ═══════════════════════════════════════════════════════════════
# PATCH-1: Time-Exit Hard Cap — Mutlak Üst Bar Sınırı
# ═══════════════════════════════════════════════════════════════
# tp1_extension + be_extension + trend_max_bars kombinasyonu
# bazı işlemleri aşırı uzatabilir. Bu hard cap buna üst sınır koyar.
# TP1/BE/Trend uzatmaları bu cap içinde kalacak.
# ─────────────────────────────────────────────────────────────
SMART_EXIT_SMALL_LOT_ABS_MAX_BARS = 120  # Küçük lot: max 120 iterasyon ≈ 4-5 saat (short için yeterli süre)
SMART_EXIT_LARGE_LOT_ABS_MAX_BARS = 160  # Büyük lot: max 160 iterasyon ≈ 6-7 saat

# ═══════════════════════════════════════════════════════════════
# PATCH-2: Large Lot Rejim Filtresi
# ═══════════════════════════════════════════════════════════════
# Large lot yalnızca güçlü / yükselen rejimlerde aktif olacak.
# RANGING / WEAK_LIQUIDITY / MIXED rejimlerinde normal slot kullanılır.
# ─────────────────────────────────────────────────────────────
LARGE_LOT_ALLOWED_REGIMES = [
    "TRENDING_UP",
    "STRONG_UP",
    "BULL_TREND",
    "TRENDING",
    "BREAKOUT_UP",
    "RANGING",        # RANGING'de large lot aktif — yalnızca A+ kalite için (LARGE_LOT_RANGING_MIN_QUALITY)
]

# RANGING rejiminde large lot için minimum kalite seviyesi.
# Yatay piyasada breakout riski yüksek olduğundan A+ (skor ≥ 90, gate=10) zorunlu tutulur.
# A (skor 85-89) ve altı RANGING'de standart slot kullanır.
LARGE_LOT_RANGING_MIN_QUALITY = "A+"

# ═══════════════════════════════════════════════════════════════
# PATCH-3: Ekonomik Filled Notional Filtresi (Post-Fill)
# ═══════════════════════════════════════════════════════════════
# OKX'te doldurulmuş gerçek notional (qty × fill_price) bu eşiğin
# altındaysa işlem ekonomik sayılmaz → pozisyon hemen kapatılır.
# Mevcut MIN_ECONOMIC_NOTIONAL (sizing/teorik) değerinden AYRI ve
# daha kapsamlı bir filtredir.
# ─────────────────────────────────────────────────────────────
MIN_ECONOMIC_FILLED_NOTIONAL = 900.0   # USDT — gerçek fill notional minimum ($100 marjin × 10x = $1000, %90 tolerans)

# ═══════════════════════════════════════════════════════════════
# PATCH-4: Aynı Coin Yeniden Giriş Soğuma Süresi
# ═══════════════════════════════════════════════════════════════
# Bir pozisyon kapandıktan sonra aynı coin için yeniden giriş
# bu süre kadar ertelenir. Daha önce 300 sn (5 dk) idi.
# ─────────────────────────────────────────────────────────────
SAME_COIN_REENTRY_COOLDOWN_SEC = 600   # 10 dakika (eski: 300 = 5 dk)
