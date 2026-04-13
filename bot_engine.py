"""
Bot Engine — Gerçek Sinyal + Emir Motoru
=========================================
mock_api.py tarafından arka plan thread olarak başlatılır.
Her 60 saniyede bir coinleri tarar, sinyal üretir, OKX'e emir gönderir.
"""

import os, time, hmac, hashlib, base64, json, threading, logging
import urllib.request, urllib.parse
from datetime import datetime, timezone
from typing import Dict, Optional
import pandas as pd

# ── Yeni modüller: Rejim + Coin Seçimi + Risk Yönetimi ───────────────────────
try:
    from regime_engine import (
        detect_regime, get_btc_regime, coin_regime_modifier,
        regime_summary, RegimeResult
    )
    from coin_selector import score_coins, format_selection_log, TIER_1
    from risk_manager import get_risk_manager
    from entry_recycler import get_recycler
    _ADVANCED_MODULES = True
except ImportError as _ie:
    _ADVANCED_MODULES = False
    logging.getLogger("bot_engine").warning(f"Gelişmiş modüller yüklenemedi: {_ie}")

log = logging.getLogger("bot_engine")

# ── Config ────────────────────────────────────────────────────────────────────
OKX_KEY        = os.getenv("OKX_API_KEY", "")
OKX_SECRET     = os.getenv("OKX_API_SECRET", "")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")
PAPER_TRADING  = os.getenv("PAPER_TRADING", "true").lower() != "false"
LEVERAGE       = int(os.getenv("LEVERAGE", "10"))
LOOP_SECONDS   = int(os.getenv("LOOP_SECONDS", "60"))

COINS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP", "AVAX-USDT-SWAP"]
COIN_MAP = {c: c.replace("-USDT-SWAP", "USDT") for c in COINS}

# Slot başına notional (USDT) — dinamik hesaplanır
SLOT_NOTIONAL  = float(os.getenv("SLOT_NOTIONAL", "1000"))
MAX_POSITIONS  = int(os.getenv("MAX_POSITIONS", "3"))

# Manuel açılan pozisyonları tanımak için bot'un açtığı coinleri takip et
_bot_opened_positions: set = set()   # Bot'un açtığı inst_id'ler

def _calc_dynamic_slot(balance: float, max_pos: int = None) -> float:
    """
    Serbest bakiyeye göre slot büyüklüğü hesapla.
    Available bakiyenin %80'i / max pozisyon sayısı = slot
    Min $50, Max SLOT_NOTIONAL (Railway'den)
    """
    if max_pos is None:
        max_pos = MAX_POSITIONS
    if balance <= 0:
        return max(50.0, SLOT_NOTIONAL)
    # Serbest bakiyenin %80'ini kullan, MAX_POSITIONS'a böl
    dynamic = (balance * 0.80) / max(1, max_pos)
    # Min $50, Max SLOT_NOTIONAL
    result = float(max(50.0, min(dynamic, SLOT_NOTIONAL)))
    return result

# ── Paylaşılan durum (mock_api ile ortak) ─────────────────────────────────────
engine_state: Dict = {
    "running":            False,
    "last_scan":          None,
    "signals":            {},
    "open_positions":     {},
    "logs":               [],
    "balance":            0.0,
    "loop_count":         0,
    "grid":               {},
    "balance_floor_hit":  False,
    "balance_floor_at":   None,
    "regime":             {},        # Market regime engine sonucu
    "risk_state":         {},        # Risk manager durumu
    "daily_pnl":          0.0,
}
_lock = threading.Lock()


def _log(msg: str, level: str = "info"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    getattr(log, level)(msg)
    print(f"cryptobot: {line}", flush=True)  # Railway stdout
    with _lock:
        engine_state["logs"].append(line)
        if len(engine_state["logs"]) > 50:
            engine_state["logs"].pop(0)


# ── OKX API ───────────────────────────────────────────────────────────────────

def _sign(ts, method, path, body=""):
    msg = ts + method + path + body
    sig = base64.b64encode(
        hmac.new(OKX_SECRET.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "OK-ACCESS-KEY":        OKX_KEY,
        "OK-ACCESS-SIGN":       sig,
        "OK-ACCESS-TIMESTAMP":  ts,
        "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
        "Content-Type":         "application/json",
        "User-Agent":           "CryptoBot/3.0",
    }


def _okx_get(path: str) -> dict:
    try:
        ts  = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        req = urllib.request.Request(
            "https://www.okx.com" + path,
            headers=_sign(ts, "GET", path)
        )
        with urllib.request.urlopen(req, timeout=4) as r:
            return json.loads(r.read())
    except Exception as e:
        _log(f"OKX GET hatası {path}: {e}", "error")
        return {}


def _okx_post(path: str, body: dict) -> dict:
    try:
        ts      = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        body_str = json.dumps(body)
        req     = urllib.request.Request(
            "https://www.okx.com" + path,
            data    = body_str.encode(),
            headers = _sign(ts, "POST", path, body_str),
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=4) as r:
            return json.loads(r.read())
    except Exception as e:
        _log(f"OKX POST hatası {path}: {e}", "error")
        return {}


def fetch_ohlcv(inst_id: str, bar: str = "1m", limit: int = 100) -> Optional[pd.DataFrame]:
    """OKX'ten OHLCV mum verisi çek."""
    path = f"/api/v5/market/candles?instId={inst_id}&bar={bar}&limit={limit}"
    try:
        req = urllib.request.Request(
            "https://www.okx.com" + path,
            headers={"User-Agent": "CryptoBot/3.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read())
        candles = data.get("data", [])
        if not candles:
            return None
        df = pd.DataFrame(candles, columns=["ts","open","high","low","close","vol","volCcy","volCcyQuote","confirm"])
        df = df[["ts","open","high","low","close","vol"]].copy()
        df.columns = ["timestamp","open","high","low","close","volume"]
        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col])
        df = df.iloc[::-1].reset_index(drop=True)  # En eski → en yeni
        return df
    except Exception as e:
        _log(f"OHLCV hatası {inst_id}: {e}", "warning")
        return None


def get_balance() -> float:
    """Serbest USDT bakiyesi."""
    if not OKX_KEY:
        return 10000.0
    data = _okx_get("/api/v5/account/balance?ccy=USDT")
    try:
        return float(data["data"][0]["details"][0]["availBal"])
    except:
        return 0.0


def get_open_positions() -> list:
    """
    OKX'teki açık pozisyonları al.
    Hedge mode'da hem long hem short pos ayrı gelir.
    Deploy sonrası memory sıfırlandığında pozisyonları engine_state'e otomatik kaydet.
    """
    if not OKX_KEY:
        return []
    data = _okx_get("/api/v5/account/positions?instType=SWAP")
    positions = []
    raw_list = data.get("data", [])
    for p in raw_list:
        pos_val   = p.get("pos", "0")
        long_qty  = p.get("longQty", "0")
        short_qty = p.get("shortQty", "0")

        qty = float(pos_val or 0)
        if qty == 0 and float(long_qty or 0) > 0:
            qty = float(long_qty)
        elif qty == 0 and float(short_qty or 0) > 0:
            qty = -float(short_qty)
        if qty == 0:
            continue

        inst_id  = p.get("instId", "")
        pos_side = p.get("posSide", "")  # "long", "short", veya "net"

        if pos_side == "long":
            side = "long"
        elif pos_side == "short":
            side = "short"
        else:
            side = "long" if qty > 0 else "short"

        entry = float(p.get("avgPx", 0))
        sym   = COIN_MAP.get(inst_id, inst_id)

        pos_data = {
            "instId":   inst_id,
            "side":     side,
            "qty":      abs(qty),
            "entry":    entry,
            "pnl":      float(p.get("upl", 0)),
            "leverage": int(float(p.get("lever", LEVERAGE))),
            "avgPx":    entry,
            "pos":      abs(qty),
        }
        positions.append(pos_data)

        # ── engine_state'e otomatik kaydet ───────────────────────────────────
        # Sadece bot'un açtığı pozisyonlar yönetilir
        # Manuel açılan pozisyonlara dokunma
        state_key = sym + ("_short" if side == "short" else "")
        is_bot_position = inst_id in _bot_opened_positions or state_key in engine_state["open_positions"]

        if is_bot_position:
            with _lock:
                if state_key not in engine_state["open_positions"] and entry > 0:
                    try:
                        sl_mult = float(os.getenv("SL_ATR_MULT", "1.5"))
                        sl_pct  = 0.015 * sl_mult
                        if side == "long":
                            sl = entry * (1 - sl_pct)
                            tp = entry * (1 + sl_pct * 2)
                        else:
                            sl = entry * (1 + sl_pct)
                            tp = entry * (1 - sl_pct * 2)
                        engine_state["open_positions"][state_key] = {
                            "stop_loss":    sl,
                            "take_profit":  tp,
                            "entry_price":  entry,
                            "side":         side,
                            "inst_id":      inst_id,
                            "profit_stage": 0,
                            "half_closed":  False,
                            "recovered":    True,
                        }
                        _log(f"🔄 {sym} ({side}) bot pozisyonu kurtarıldı: giriş=${entry:.4f} SL=${sl:.4f}")
                    except Exception as e:
                        _log(f"⚠️ {sym} pozisyon kayıt hatası: {e}", "warning")
        else:
            _log(f"👤 {sym} manuel pozisyon — dokunulmayacak (giriş:${entry:.4f})")

    return positions


def set_leverage(inst_id: str, lev: int):
    """Kaldıraç ayarla."""
    if not OKX_KEY or PAPER_TRADING:
        return
    _okx_post("/api/v5/account/set-leverage", {
        "instId": inst_id, "lever": str(lev), "mgnMode": "cross"
    })


def get_contract_info(inst_id: str) -> dict:
    """Kontrat bilgilerini al ve önbellekte tut."""
    if not hasattr(get_contract_info, "_cache"):
        get_contract_info._cache = {}
    if inst_id not in get_contract_info._cache:
        info_data = _okx_get(f"/api/v5/public/instruments?instType=SWAP&instId={inst_id}")
        try:
            d = info_data["data"][0]
            get_contract_info._cache[inst_id] = {
                "ct_val":   float(d.get("ctVal", 0.01)),
                "lot_sz":   float(d.get("lotSz", 1)),
                "tick_sz":  float(d.get("tickSz", 0.01)),
                "min_sz":   float(d.get("minSz", 1)),
            }
        except:
            get_contract_info._cache[inst_id] = {"ct_val": 0.01, "lot_sz": 1, "tick_sz": 0.01, "min_sz": 1}
    return get_contract_info._cache[inst_id]


def round_price(price: float, tick_sz: float) -> str:
    """Fiyatı OKX tick size'a göre yuvarla."""
    if tick_sz <= 0:
        return f"{price:.4f}"
    decimals = max(0, -int(f"{tick_sz:e}".split("e")[1]))
    return f"{round(price / tick_sz) * tick_sz:.{decimals}f}"


def place_order(inst_id: str, side: str, notional: float, price: float,
                sl_price: float = 0.0, tp1_price: float = 0.0, tp2_price: float = 0.0) -> bool:
    """
    Market emri + OKX'e gerçek SL/TP algo emirleri gönder.
    - SL: hard stop loss (OKX'te anlık tetiklenir)
    - TP1: %50 kısmi kâr alma (breakeven'e geçer)
    - TP2: kalan %50 tam çıkış
    side: "buy" (long aç) veya "sell" (short aç)
    """
    if PAPER_TRADING:
        _log(f"[PAPER] {side.upper()} {inst_id} notional=${notional:.0f} @ ${price:.4f} | SL=${sl_price:.4f} TP1=${tp1_price:.4f} TP2=${tp2_price:.4f}")
        return True

    if not OKX_KEY:
        _log("API anahtarı yok, emir gönderilemedi", "error")
        return False

    info = get_contract_info(inst_id)
    ct_val  = info["ct_val"]
    tick_sz = info["tick_sz"]

    qty_coin     = notional / price
    qty_contract = max(info["min_sz"], round(qty_coin / ct_val))
    pos_side     = "long" if side == "buy" else "short"

    # ── 1. Ana market emri ────────────────────────────────────────────────────
    body = {
        "instId":  inst_id,
        "tdMode":  "cross",
        "side":    side,
        "posSide": pos_side,   # Hedge mode zorunlu
        "ordType": "market",
        "sz":      str(int(qty_contract)),
    }

    result = _okx_post("/api/v5/trade/order", body)
    ok = result.get("code") == "0"
    if not ok:
        err = result.get("data", [{}])[0].get("sMsg") or result.get("msg", "?")
        _log(f"❌ Emir reddedildi: {inst_id} → {err} (code:{result.get('code')})", "error")
        return False

    order_id = result.get("data", [{}])[0].get("ordId", "")
    _log(f"✅ {side.upper()} {inst_id} {int(qty_contract)} kontrat | ordId={order_id}")

    # ── 2. SL algo emri ───────────────────────────────────────────────────────
    if sl_price > 0:
        sl_side = "sell" if pos_side == "long" else "buy"
        sl_body = {
            "instId":          inst_id,
            "tdMode":          "cross",
            "side":            sl_side,
            "posSide":         pos_side,
            "ordType":         "conditional",
            "sz":              str(int(qty_contract)),
            "slTriggerPx":     round_price(sl_price, tick_sz),
            "slOrdPx":         "-1",
            "slTriggerPxType": "mark",
        }
        sl_result = _okx_post("/api/v5/trade/order-algo", sl_body)
        if sl_result.get("code") == "0":
            _log(f"🛡️ SL ayarlandı: ${sl_price:.4f}")
        else:
            _log(f"⚠️ SL ayarlanamadı: {sl_result.get('msg','?')}", "warning")

    # ── 3. Trailing Stop ──────────────────────────────────────────────────────
    TRAIL_ACTIVATION_PCT = float(os.getenv("TRAIL_ACTIVATION_PCT", "0.003"))
    TRAIL_CALLBACK_PCT   = float(os.getenv("TRAIL_CALLBACK_PCT",   "0.002"))

    trail_active_px = price * (1 + TRAIL_ACTIVATION_PCT) if pos_side == "long" else price * (1 - TRAIL_ACTIVATION_PCT)
    trail_side      = "sell" if pos_side == "long" else "buy"

    trail_body = {
        "instId":        inst_id,
        "tdMode":        "cross",
        "side":          trail_side,
        "posSide":       pos_side,
        "ordType":       "move_order_stop",
        "sz":            str(int(qty_contract)),
        "activePx":      round_price(trail_active_px, tick_sz),
        "callbackRatio": str(TRAIL_CALLBACK_PCT),
    }
    trail_result = _okx_post("/api/v5/trade/order-algo", trail_body)
    if trail_result.get("code") == "0":
        _log(f"🎯 Trailing Stop: aktif=${trail_active_px:.4f} | geri=%{TRAIL_CALLBACK_PCT*100:.1f}")
    else:
        _log(f"⚠️ Trailing Stop ayarlanamadı: {trail_result.get('msg','?')}", "warning")
        if tp1_price > 0:
            tp1_qty  = max(1, int(qty_contract * 0.50))
            tp1_side = "sell" if pos_side == "long" else "buy"
            tp1_body = {
                "instId": inst_id, "tdMode": "cross", "side": tp1_side,
                "posSide": pos_side, "ordType": "conditional", "sz": str(tp1_qty),
                "tpTriggerPx": round_price(tp1_price, tick_sz),
                "tpOrdPx": "-1", "tpTriggerPxType": "mark",
            }
            _okx_post("/api/v5/trade/order-algo", tp1_body)
        if tp2_price > 0:
            tp2_qty = int(qty_contract) - max(1, int(qty_contract * 0.50))
            if tp2_qty > 0:
                tp2_side = "sell" if pos_side == "long" else "buy"
                tp2_body = {
                    "instId": inst_id, "tdMode": "cross", "side": tp2_side,
                    "posSide": pos_side, "ordType": "conditional", "sz": str(tp2_qty),
                    "tpTriggerPx": round_price(tp2_price, tick_sz),
                    "tpOrdPx": "-1", "tpTriggerPxType": "mark",
                }
                _okx_post("/api/v5/trade/order-algo", tp2_body)

    return True


def close_position(inst_id: str, side: str, qty: float):
    """Pozisyonu kapat — one-way mode."""
    if PAPER_TRADING:
        _log(f"[PAPER] KAPAT {inst_id} {side} qty={qty:.4f}")
        return True
    if not OKX_KEY:
        return False

    close_side = "sell" if side == "long" else "buy"

    info_data = _okx_get(f"/api/v5/public/instruments?instType=SWAP&instId={inst_id}")
    try:
        ct_val = float(info_data["data"][0]["ctVal"])
    except:
        ct_val = 0.01

    pos_data = _okx_get(f"/api/v5/account/positions?instId={inst_id}")
    try:
        sz = pos_data["data"][0]["pos"]
    except:
        sz = str(round(qty / ct_val))

    body = {
        "instId":  inst_id,
        "tdMode":  "cross",
        "side":    close_side,
        "posSide": side,       # Hedge mode: long pozisyonu kapatmak için "long"
        "ordType": "market",
        "sz":      str(abs(int(float(sz)))),
    }
    result = _okx_post("/api/v5/trade/order", body)
    ok = result.get("code") == "0"
    if ok:
        _log(f"✅ Pozisyon kapatıldı: {inst_id} {side}")
    else:
        _log(f"❌ Kapatma başarısız: {inst_id} → {result.get('msg','?')}", "error")
    return ok


# ── Sinyal Motoru ─────────────────────────────────────────────────────────────

def run_signals(positions: list) -> dict:
    """
    Tüm coinleri tara, sinyal üret.
    MTF: 1dk (ana) + 5dk (trend onayı) + 15dk (ana trend)
    Döndürür: {symbol: signal_info}
    """
    from pullback_long  import PullbackLongStrategy
    from pullback_short import PullbackShortStrategy

    long_strat  = PullbackLongStrategy(min_score=LONG_MIN_SCORE)
    short_strat = PullbackShortStrategy(min_score=LONG_MIN_SCORE)

    open_syms = {p["instId"] for p in positions}
    signals   = {}

    for inst_id in COINS:
        sym = COIN_MAP[inst_id]

        # Ana timeframe: 5dk (1dk yerine — daha az API çağrısı, daha stabil)
        df = fetch_ohlcv(inst_id, bar="5m", limit=100)
        if df is None or len(df) < 55:
            _log(f"{sym}: yetersiz veri ({len(df) if df is not None else 0} bar)")
            continue

        # Sadece 1H — rejim tespiti için yeterli
        df_5m  = None   # Ana timeframe zaten 5m
        df_15m = None   # Kaldırıldı — hız için
        df_1h  = fetch_ohlcv(inst_id, bar="1H", limit=60)

        hour_utc = datetime.now(timezone.utc).hour

        # Long sinyal (MTF + 1H rejim tespiti ile)
        long_res = long_strat.generate(
            df, symbol=sym, hour_utc=hour_utc,
            df_5m=df_5m, df_15m=df_15m, df_1h=df_1h
        )
        # Short sinyal
        short_res = short_strat.generate(df, symbol=sym, hour_utc=hour_utc)

        signals[sym] = {
            "inst_id":    inst_id,
            "long":       {"score": long_res.score,  "enter": long_res.should_enter,
                           "sl": long_res.stop_loss,  "tp": long_res.take_profit,
                           "entry": long_res.entry_price, "reason": long_res.reason[:100]},
            "short":      {"score": short_res.score, "enter": short_res.should_enter,
                           "sl": short_res.stop_loss, "tp": short_res.take_profit,
                           "entry": short_res.entry_price, "reason": short_res.reason[:100]},
            "in_position": inst_id in open_syms,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
        }

        status = ""
        if long_res.should_enter:
            status = f"BUY ({long_res.score}/11)"
        elif short_res.should_enter:
            status = f"SHORT ({short_res.score}/10)"
        else:
            status = f"HOLD (L:{long_res.score} S:{short_res.score})"
        _log(f"{sym}: {status} | enter={long_res.should_enter}")

    return signals


def check_exits(positions: list, signals: dict):
    """
    SL/TP + Trailing Stop + Kademeli Kâr Yönetimi.

    Mevcut mantık korundu, üzerine eklendi:
    ── Kâr Basamakları (USDT bazlı) ──
    +3 USDT → Kâr kilitleme: SL breakeven'e çekilir
    +5 USDT → SL daha yukarı (kâr koruması güçlenir)
    +7 USDT → %50 kısmi satış, kalan %50 trend kontrolüne bırakılır
    +10 USDT → Kalan %50 tamamen kapatılır
    Ters dönüş → Kalan pozisyon +5 USDT korumasından çıkarsa kapatılır
    """
    TRAIL_ACTIVATION_PCT = float(os.getenv("TRAIL_ACTIVATION_PCT", "0.003"))
    TRAIL_CALLBACK_PCT   = float(os.getenv("TRAIL_CALLBACK_PCT",   "0.002"))

    # Kâr basamak seviyeleri (USDT)
    PROFIT_LOCK_1  = float(os.getenv("PROFIT_LOCK_1",  "3.0"))   # SL breakeven'e çek
    PROFIT_LOCK_2  = float(os.getenv("PROFIT_LOCK_2",  "5.0"))   # SL daha yukarı
    PROFIT_HALF    = float(os.getenv("PROFIT_HALF",    "7.0"))   # %50 kısmi sat
    PROFIT_FULL    = float(os.getenv("PROFIT_FULL",   "10.0"))   # Tamamını kapat
    PROFIT_PROTECT = float(os.getenv("PROFIT_PROTECT", "5.0"))   # Ters dönüşte koruma seviyesi

    for pos in positions:
        inst_id = pos["instId"]
        sym     = COIN_MAP.get(inst_id, inst_id)

        # ── Manuel pozisyonlara dokunma ───────────────────────────────────────
        if inst_id not in _bot_opened_positions:
            state_key = sym + ("_short" if pos.get("side") == "short" else "")
            if state_key not in engine_state["open_positions"] and sym not in engine_state["open_positions"]:
                continue  # Bot açmadı, atla

        try:
            price_data = _okx_get(f"/api/v5/market/ticker?instId={inst_id}")
            price = float(price_data["data"][0]["last"])
        except:
            continue

        entry = float(pos.get("avgPx", 0) or pos.get("entry", 0))
        side  = pos.get("side", "long")
        qty   = float(pos.get("pos", 0) or pos.get("qty", 0))

        if entry <= 0 or qty <= 0:
            continue

        pos_detail = engine_state["open_positions"].get(sym, {})
        sl = float(pos_detail.get("stop_loss", 0))
        tp = float(pos_detail.get("take_profit", 0))

        # SL yoksa sadece kaydet ama tetikleme — OKX kendi SL emrini yönetir
        if sl <= 0 and entry > 0:
            sl_mult = float(os.getenv("SL_ATR_MULT", "1.5"))
            sl_pct  = 0.015 * sl_mult
            if side == "long":
                sl = entry * (1 - sl_pct)
                tp = entry * (1 + sl_pct * 2) if tp <= 0 else tp
            else:
                sl = entry * (1 + sl_pct)
                tp = entry * (1 - sl_pct * 2) if tp <= 0 else tp
            with _lock:
                if sym not in engine_state["open_positions"]:
                    engine_state["open_positions"][sym] = {}
                engine_state["open_positions"][sym]["stop_loss"]   = sl
                engine_state["open_positions"][sym]["take_profit"] = tp
                engine_state["open_positions"][sym]["entry_price"] = entry
                engine_state["open_positions"][sym]["side"]        = side
            # SL yeni hesaplandı — bu döngüde SL tetikleme yapma
            # OKX'teki algo emri zaten var, ona güven
            sl = 0   # Sıfırla — aşağıdaki SL kontrolü çalışmasın

        # ── Anlık Kâr Hesapla (USDT) ─────────────────────────────────────────
        info   = get_contract_info(inst_id)
        ct_val = info["ct_val"]
        coin_qty = qty * ct_val  # Kontrat → coin miktarı

        if side == "long":
            pnl_usdt = (price - entry) * coin_qty
        else:
            pnl_usdt = (entry - price) * coin_qty

        # ── YENİ: Kademeli Kâr Yönetimi ─────────────────────────────────────
        # Mevcut trailing stop mantığından ÖNCE çalışır
        # Kısmi satış yapıldıysa tekrar yapma
        half_closed  = pos_detail.get("half_closed", False)
        profit_stage = pos_detail.get("profit_stage", 0)  # Hangi aşamada olduğu

        if pnl_usdt >= PROFIT_FULL and not half_closed:
            # +10 USDT → Tamamını kapat
            _log(f"💰 {sym} +${pnl_usdt:.2f} USDT — TAM KAR REALİZASYONU (${PROFIT_FULL}+ hedef)")
            close_position(inst_id, side, qty)
            if _ADVANCED_MODULES:
                try: get_risk_manager().record_trade_result(pnl_usdt)
                except: pass
            with _lock:
                engine_state["open_positions"].pop(sym, None)
            continue

        elif pnl_usdt >= PROFIT_FULL and half_closed:
            # +10 USDT → Kalan %50'yi kapat
            _log(f"💰 {sym} +${pnl_usdt:.2f} USDT — Kalan pozisyon kapatılıyor (${PROFIT_FULL}+ hedef)")
            close_position(inst_id, side, qty)
            if _ADVANCED_MODULES:
                try: get_risk_manager().record_trade_result(pnl_usdt)
                except: pass
            with _lock:
                engine_state["open_positions"].pop(sym, None)
            continue

        elif pnl_usdt >= PROFIT_HALF and not half_closed:
            # +7 USDT → %50 kısmi sat, kalan izlemeye al
            _log(f"🎯 {sym} +${pnl_usdt:.2f} USDT — %50 KISMİ SATIŞ (${PROFIT_HALF}+ hedef)")
            half_qty = max(1, int(qty * 0.5))
            if not PAPER_TRADING and OKX_KEY:
                close_side = "sell" if side == "long" else "buy"
                half_body  = {
                    "instId":  inst_id, "tdMode": "cross",
                    "side":    close_side,
                    "posSide": side,        # Hedge mode zorunlu
                    "ordType": "market",
                    "sz":      str(half_qty),
                }
                result = _okx_post("/api/v5/trade/order", half_body)
                if result.get("code") == "0":
                    _log(f"✅ {sym} %50 satış yapıldı ({half_qty} kontrat)")
                else:
                    _log(f"⚠️ {sym} %50 satış hatası: {result.get('msg','?')}", "warning")
            else:
                _log(f"[PAPER] {sym} %50 satış ({half_qty} kontrat @ ${price:.4f})")
            with _lock:
                if sym in engine_state["open_positions"]:
                    engine_state["open_positions"][sym]["half_closed"]  = True
                    engine_state["open_positions"][sym]["half_close_pnl"] = pnl_usdt
                    engine_state["open_positions"][sym]["profit_stage"] = 3
            continue

        elif pnl_usdt >= PROFIT_HALF and half_closed:
            # +7 sonrası kalan %50 — trend kontrolü
            sig = signals.get(sym, {})
            trend_ok = False
            if side == "long":
                long_sig = sig.get("long", {})
                trend_ok = long_sig.get("score", 0) >= 6 and long_sig.get("enter", False)
            else:
                short_sig = sig.get("short", {})
                trend_ok = short_sig.get("score", 0) >= 6 and short_sig.get("enter", False)

            # Trend zayıfladıysa ve kâr PROFIT_PROTECT üzerindeyse kapat
            if not trend_ok and pnl_usdt < pos_detail.get("half_close_pnl", PROFIT_HALF):
                _log(f"⚠️ {sym} Trend zayıfladı, kalan pozisyon kapatılıyor (${pnl_usdt:.2f} USDT)")
                close_position(inst_id, side, qty)
                with _lock:
                    engine_state["open_positions"].pop(sym, None)
                continue

        elif pnl_usdt >= PROFIT_LOCK_2 and profit_stage < 2:
            # +5 USDT → SL güçlü kâr korumasına çek (giriş + küçük buffer)
            if side == "long":
                new_sl = entry * 1.002  # Girişin %0.2 üzeri
            else:
                new_sl = entry * 0.998
            if (side == "long" and new_sl > sl) or (side == "short" and new_sl < sl):
                _log(f"🔒 {sym} +${pnl_usdt:.2f} KAR KORUMA 2: SL ${sl:.4f} → ${new_sl:.4f}")
                with _lock:
                    if sym in engine_state["open_positions"]:
                        engine_state["open_positions"][sym]["stop_loss"]    = new_sl
                        engine_state["open_positions"][sym]["profit_stage"] = 2
                sl = new_sl

        elif pnl_usdt >= PROFIT_LOCK_1 and profit_stage < 1:
            # +3 USDT → SL'yi kâr koruma seviyesine çek
            # Breakeven değil — en az $2.5 USDT kâr garantile
            # Fiyat geri dönse bile $2.5 kâr kilitlenir
            info_sl   = get_contract_info(inst_id)
            ct_val_sl = info_sl["ct_val"]
            coin_qty_sl = qty * ct_val_sl
            protect_usdt = PROFIT_LOCK_1 * 0.8   # +$3'ün %80'i = $2.4 kâr koru
            if coin_qty_sl > 0:
                price_diff = protect_usdt / coin_qty_sl
                if side == "long":
                    new_sl = entry + price_diff
                else:
                    new_sl = entry - price_diff
            else:
                new_sl = entry   # Fallback: breakeven

            if (side == "long" and new_sl > sl) or (side == "short" and new_sl < sl):
                _log(f"🔒 {sym} +${pnl_usdt:.2f} KAR KİLİTLEME: SL ${sl:.4f} → ${new_sl:.4f} (${protect_usdt:.1f} USDT kâr korunuyor)")
                with _lock:
                    if sym in engine_state["open_positions"]:
                        engine_state["open_positions"][sym]["stop_loss"]    = new_sl
                        engine_state["open_positions"][sym]["profit_stage"] = 1
                sl = new_sl

        # ── Trailing Stop — Sadece +$3 USDT sonrası aktif ──────────────────
        # Kâr basamaklarına ulaşmadan trailing kapatmasın
        TRAIL_MIN_PROFIT = PROFIT_LOCK_1  # En az +$3 USDT kâr olunca aktif
        trail_profit_ok  = pnl_usdt >= TRAIL_MIN_PROFIT

        if side == "long":
            activation_price = entry * (1 + TRAIL_ACTIVATION_PCT)
            in_profit = price >= activation_price and trail_profit_ok
            if in_profit:
                prev_high = float(pos_detail.get("trail_high", 0))
                new_high  = max(prev_high, price)
                trail_sl  = new_high * (1 - TRAIL_CALLBACK_PCT)
                if trail_sl > sl:
                    _log(f"🔒 {sym} Trailing SL: ${sl:.4f} → ${trail_sl:.4f} (zirve:${new_high:.4f})")
                    with _lock:
                        if sym in engine_state["open_positions"]:
                            engine_state["open_positions"][sym]["stop_loss"]   = trail_sl
                            engine_state["open_positions"][sym]["trail_high"]  = new_high
                    sl = trail_sl
                else:
                    with _lock:
                        if sym in engine_state["open_positions"]:
                            engine_state["open_positions"][sym]["trail_high"] = new_high

        elif side == "short":
            activation_price = entry * (1 - TRAIL_ACTIVATION_PCT)
            in_profit = price <= activation_price and trail_profit_ok
            if in_profit:
                prev_low = float(pos_detail.get("trail_low", float("inf")))
                new_low  = min(prev_low, price)
                trail_sl = new_low * (1 + TRAIL_CALLBACK_PCT)
                if trail_sl < sl:
                    _log(f"🔒 {sym} SHORT Trailing SL: ${sl:.4f} → ${trail_sl:.4f} (dip:${new_low:.4f})")
                    with _lock:
                        if sym in engine_state["open_positions"]:
                            engine_state["open_positions"][sym]["stop_loss"]  = trail_sl
                            engine_state["open_positions"][sym]["trail_low"]  = new_low
                    sl = trail_sl
                else:
                    with _lock:
                        if sym in engine_state["open_positions"]:
                            engine_state["open_positions"][sym]["trail_low"] = new_low

        # ── Mevcut SL / TP Kontrolü (korundu) ────────────────────────────────
        should_close = False
        reason = ""
        if side == "long":
            if price <= sl:
                should_close = True
                reason = f"SL tetiklendi (${price:.4f} ≤ ${sl:.4f})"
            elif tp > 0 and price >= tp:
                should_close = True
                reason = f"TP tetiklendi (${price:.4f} ≥ ${tp:.4f})"
        elif side == "short":
            if price >= sl:
                should_close = True
                reason = f"SL tetiklendi (${price:.4f} ≥ ${sl:.4f})"
            elif tp > 0 and price <= tp:
                should_close = True
                reason = f"TP tetiklendi (${price:.4f} ≤ ${tp:.4f})"

        if should_close:
            _log(f"🔴 {sym} KAPAT — {reason} | PnL: ${pnl_usdt:.2f}")
            close_position(inst_id, side, qty)
            if _ADVANCED_MODULES:
                try: get_risk_manager().record_trade_result(pnl_usdt)
                except: pass
                try:
                    # Entry Recycler'a bildir — cooldown + rescan kuyruğuna al
                    get_recycler().record_close(
                        symbol       = sym,
                        inst_id      = inst_id,
                        side         = side,
                        entry_price  = entry,
                        close_price  = price,
                        pnl_usdt     = pnl_usdt,
                        close_reason = reason.split(" ")[0],
                    )
                except: pass
            with _lock:
                engine_state["open_positions"].pop(sym, None)


# ── Ana Döngü ─────────────────────────────────────────────────────────────────

# ── Funding Rate Arbitrage ────────────────────────────────────────────────────
# Sadece BTC ve ETH — en likit, en düşük spread
FUNDING_COINS   = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
FUNDING_NOTIONAL = float(os.getenv("FUNDING_NOTIONAL", "1000"))  # USDT

# Eşikler
FUNDING_ENTRY_THRESHOLD  = float(os.getenv("FUNDING_ENTRY_PCT", "0.01"))   # %0.01 — giriş eşiği (düşürüldü, daha aktif)
FUNDING_EXIT_THRESHOLD   = float(os.getenv("FUNDING_EXIT_PCT",  "0.01"))   # %0.01 — çıkış eşiği (nötrleşince kapat)
FUNDING_MAX_SL_PCT        = 0.005   # %0.5 — maks zarar (dar SL)
FUNDING_LEVERAGE          = 3       # 3x — düşük kaldıraç (yön riski minimize)

# Aktif funding pozisyonları: {sym → {"side", "entry", "sl", "funding_rate", "opened_at"}}
_funding_positions: Dict[str, dict] = {}


def get_funding_rate(inst_id: str) -> float:
    """OKX'ten anlık funding rate al (kesir olarak, ör. 0.0003 = %0.03)."""
    try:
        data = _okx_get(f"/api/v5/public/funding-rate?instId={inst_id}")
        rate = float(data.get("data", [{}])[0].get("fundingRate", 0) or 0)
        return rate
    except Exception as e:
        _log(f"[FUNDING] {inst_id} rate alınamadı: {e}", "warning")
        return 0.0


def get_next_funding_time(inst_id: str) -> Optional[int]:
    """Bir sonraki funding zamanını ms olarak döndür."""
    try:
        data = _okx_get(f"/api/v5/public/funding-rate?instId={inst_id}")
        ts = int(data.get("data", [{}])[0].get("nextFundingTime", 0) or 0)
        return ts
    except:
        return None


def run_funding_arbitrage(open_positions: list, db=None, trade_ids: dict = None) -> None:
    """
    Funding rate arbitrage döngüsü.

    Strateji:
      - Funding rate > +%0.03 → SHORT aç (long'lar sana ödüyor)
      - Funding rate < -%0.03 → LONG aç (short'lar sana ödüyor)
      - Rate nötre döndüğünde (< %0.01) → pozisyonu kapat
      - SL: %0.5 — küçük zarar kabul et, funding geliri koru

    NOT: Funding her 8 saatte bir ödeniyor. Pozisyon funding anına kadar
    tutulur, sonra kapatılır. Günde 0-3 işlem beklenir.
    """
    if not OKX_KEY and not PAPER_TRADING:
        return

    open_syms = {p["instId"] for p in open_positions}

    for inst_id in FUNDING_COINS:
        sym = COIN_MAP.get(inst_id, inst_id)

        # 1. Funding rate kontrolü
        rate = get_funding_rate(inst_id)
        rate_pct = rate * 100
        next_ts  = get_next_funding_time(inst_id)
        mins_to_funding = ((next_ts - int(time.time() * 1000)) / 60000) if next_ts else 999

        # 2. Mevcut funding pozisyonu var mı?
        fp = _funding_positions.get(sym)

        if fp:
            # Çıkış koşulları kontrolü
            should_exit = False
            exit_reason = ""

            # a. Rate nötrleşti → kapat
            if abs(rate) < FUNDING_EXIT_THRESHOLD / 100:
                should_exit  = True
                exit_reason  = f"Rate nötrleşti (%{rate_pct:.4f})"

            # b. Rate yön değiştirdi → kapat
            if fp["side"] == "short" and rate < 0:
                should_exit  = True
                exit_reason  = f"Rate negatife döndü → short dezavantajlı"
            elif fp["side"] == "long" and rate > 0:
                should_exit  = True
                exit_reason  = f"Rate pozitife döndü → long dezavantajlı"

            if should_exit:
                _log(f"[FUNDING] {sym} kapat — {exit_reason}")
                close_side = "sell" if fp["side"] == "long" else "buy"
                # Canlı modda OKX'e kapatma emri
                if not PAPER_TRADING:
                    close_position(inst_id, fp["side"], fp.get("qty", 0))
                else:
                    _log(f"[PAPER FUNDING] {sym} {fp['side']} kapat")
                _funding_positions.pop(sym, None)
                # DB güncelle
                if db and trade_ids and sym in trade_ids:
                    try:
                        entry_p = fp["entry"]
                        cur_p   = fp.get("current_price", entry_p)
                        pnl     = (cur_p - entry_p) if fp["side"] == "long" else (entry_p - cur_p)
                        pnl    *= fp.get("qty", FUNDING_NOTIONAL / entry_p if entry_p > 0 else 0)
                        db.close_trade(trade_ids.pop(sym, None), sym, cur_p, pnl, 0.0, exit_reason)
                    except Exception as _de:
                        _log(f"[FUNDING] DB kapanış hatası: {_de}", "warning")
            continue  # Bu sembol için açılış kısmına geçme

        # 3. Yeni pozisyon açma koşulları
        # Funding zaten çok yakınsa girme (5 dakika içindeyse geç)
        if mins_to_funding < 5:
            _log(f"[FUNDING] {sym} funding {mins_to_funding:.0f}dk içinde — giriş atlandı (çok geç)")
            continue

        # Funding coin zaten başka pozisyonda mı?
        if inst_id in open_syms:
            _log(f"[FUNDING] {sym} zaten pozisyonda — funding arb atlandı")
            continue

        # Eşik kontrolü
        if abs(rate) < FUNDING_ENTRY_THRESHOLD / 100:
            _log(f"[FUNDING] {sym} rate=%{rate_pct:.4f} — eşik altında (min=%{FUNDING_ENTRY_THRESHOLD:.2f})")
            continue

        # Yön belirle
        if rate > 0:
            arb_side = "sell"   # SHORT — long'lar sana ödüyor
            arb_pos  = "short"
        else:
            arb_side = "buy"    # LONG — short'lar sana ödüyor
            arb_pos  = "long"

        # Anlık fiyat
        price_data = _okx_get(f"/api/v5/market/ticker?instId={inst_id}")
        try:
            price = float(price_data["data"][0]["last"])
        except:
            _log(f"[FUNDING] {sym} fiyat alınamadı", "warning")
            continue

        # SL hesapla — dar (%0.5)
        sl = price * (1 - FUNDING_MAX_SL_PCT) if arb_pos == "long" else price * (1 + FUNDING_MAX_SL_PCT)

        # Beklenen kazanç = notional × rate
        expected_gain = FUNDING_NOTIONAL * abs(rate)
        expected_gain_usdt = round(expected_gain, 4)

        _log(
            f"[FUNDING ARB] {sym} {arb_pos.upper()} | "
            f"Rate=%{rate_pct:.4f} | "
            f"Beklenen kazanç=${expected_gain_usdt:.4f} | "
            f"Funding'e {mins_to_funding:.0f}dk kaldı"
        )

        if PAPER_TRADING:
            _log(f"[PAPER FUNDING] {sym} {arb_pos.upper()} aç @ ${price:.4f} SL=${sl:.4f}")
            ok = True
        else:
            # 3x kaldıraçla aç (funding arb için düşük kaldıraç)
            try:
                _okx_post("/api/v5/account/set-leverage", {
                    "instId": inst_id, "lever": str(FUNDING_LEVERAGE), "mgnMode": "cross"
                })
            except:
                pass
            ok = place_order(
                inst_id, arb_side,
                FUNDING_NOTIONAL, price,
                sl_price=sl,
                tp1_price=0,   # TP yok — rate nötrleşince kapat
                tp2_price=0,
            )

        if ok:
            qty = FUNDING_NOTIONAL / price if price > 0 else 0
            _funding_positions[sym] = {
                "symbol":       sym,
                "side":         arb_pos,
                "entry":        price,
                "sl":           sl,
                "qty":          qty,
                "funding_rate": rate,
                "expected_gain": expected_gain_usdt,
                "opened_at":    datetime.now(timezone.utc).isoformat(),
                "current_price": price,
            }
            # DB kaydet
            if db:
                try:
                    tid = db.open_trade(
                        sym, arb_pos, price, sl, 0.0,
                        FUNDING_NOTIONAL, 0,
                        f"Funding Arb (%{rate_pct:.3f})",
                        "paper" if PAPER_TRADING else "live"
                    )
                    if tid and trade_ids is not None:
                        trade_ids[sym] = tid
                except Exception as _de:
                    _log(f"[FUNDING] DB açılış hatası: {_de}", "warning")

            _log(f"[FUNDING ARB] ✅ {sym} {arb_pos.upper()} açıldı | Rate=%{rate_pct:.4f} | Beklenen kâr=${expected_gain_usdt:.4f}")


PULLBACK_SHORT_ACTIVE = os.getenv("PULLBACK_SHORT_ACTIVE", "true").lower() == "true"
LONG_MIN_SCORE        = int(os.getenv("LONG_MIN_SCORE", "7"))
GOOD_HOURS_UTC        = list(range(0, 24))

# SL/TP çarpanları — Railway Variables ile ayarlanabilir
TP1_R_MULT = float(os.getenv("TP1_R_MULT", "0.5"))  # TP1 = Risk × 0.5 (hızlı kâr)
TP2_R_MULT = float(os.getenv("TP2_R_MULT", "1.0"))  # TP2 = Risk × 1.0 (kalan)  # Her saat açık


def _is_good_trading_hour() -> bool:
    return True  # Kısıtlama yok


# ── Grid Trading Modülü ──────────────────────────────────────────────────────
"""
Grid Trading — Aralık Ticareti
================================
Strateji:
  - ATR bazlı otomatik fiyat aralığı belirle (son 24 saatin ATR'si)
  - Aralığı GRID_LEVELS eşit parçaya böl
  - Her seviyede limit al emri koy
  - Satış → bir üst seviyede limit sat emri koy
  - Fiyat aralıkta sallandıkça sürekli küçük kârlar topla

Avantaj:
  - Yön tahmini gerekmez
  - Pullback stratejisinden tamamen bağımsız slotlar
  - %70-75 win rate (yatay/yüksek volatilite piyasasında)
"""

GRID_COINS         = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
GRID_TOTAL_CAPITAL = float(os.getenv("GRID_CAPITAL", "1000"))   # Toplam grid sermayesi (USDT)
GRID_LEVELS        = int(os.getenv("GRID_LEVELS", "8"))          # Grid seviye sayısı
GRID_LEVERAGE      = int(os.getenv("GRID_LEVERAGE", "3"))        # Düşük kaldıraç (güvenli)
GRID_ATR_MULT      = float(os.getenv("GRID_ATR_MULT", "3.0"))   # ATR çarpanı (aralık genişliği)
GRID_ACTIVE        = os.getenv("GRID_ACTIVE", "true").lower() == "true"

# Grid durumu: {inst_id → {state, levels, orders, last_price, ...}}
_grid_state: Dict[str, dict] = {}  # Her deploy'da sıfırdan başlar


def _calc_atr_14(inst_id: str, bar: str = "1H") -> float:
    """Son 14 mum ATR hesapla — grid aralığını belirlemek için."""
    try:
        df = fetch_ohlcv(inst_id, bar=bar, limit=30)
        if df is None or len(df) < 15:
            return 0.0
        prev  = df["close"].shift(1)
        tr    = pd.concat([
            df["high"] - df["low"],
            (df["high"] - prev).abs(),
            (df["low"]  - prev).abs(),
        ], axis=1).max(axis=1)
        return float(tr.ewm(span=14, adjust=False).mean().iloc[-1])
    except:
        return 0.0


def _place_grid_limit_order(inst_id: str, side: str, price: float,
                             sz: int, pos_side: str) -> Optional[str]:
    """
    Grid limit emir — Hedge mode (posSide zorunlu).
    side: "buy" → pos_side: "long"
    side: "sell" → pos_side: "short"
    """
    if PAPER_TRADING:
        fake_id = f"PAPER-{inst_id}-{side}-{int(price)}"
        _log(f"[PAPER GRID] {side.upper()} {inst_id} {sz}k @ ${price:.4f}")
        return fake_id
    if not OKX_KEY:
        return None
    try:
        info    = get_contract_info(inst_id)
        tick_sz = info["tick_sz"]
        px      = round_price(price, tick_sz)

        body = {
            "instId":  inst_id,
            "tdMode":  "cross",
            "side":    side,
            "posSide": pos_side,   # Hedge mode zorunlu
            "ordType": "limit",
            "px":      px,
            "sz":      str(sz),
        }
        result = _okx_post("/api/v5/trade/order", body)
        if result.get("code") == "0":
            oid = result["data"][0]["ordId"]
            _log(f"[GRID] ✓ {side.upper()} {inst_id} @ ${price:.2f} ({oid[:8]})")
            return oid

        err = result.get("data", [{}])[0].get("sMsg") or result.get("msg", "?")
        _log(f"[GRID] ✗ {inst_id} reddedildi: {err}", "warning")
        return None
    except Exception as e:
        _log(f"[GRID] Hata: {e}", "warning")
        return None


def _cancel_grid_orders(inst_id: str, order_ids: list) -> None:
    """Mevcut grid emirlerini iptal et."""
    if PAPER_TRADING or not OKX_KEY or not order_ids:
        return
    try:
        # Toplu iptal (max 20 adet)
        for i in range(0, len(order_ids), 20):
            batch = [{"instId": inst_id, "ordId": oid}
                     for oid in order_ids[i:i+20] if oid and not oid.startswith("PAPER")]
            if batch:
                _okx_post("/api/v5/trade/cancel-batch-orders", batch)
    except Exception as e:
        _log(f"[GRID] İptal hatası: {e}", "warning")


def _get_grid_filled_orders(inst_id: str, order_ids: list) -> list:
    """Dolmuş grid emirlerini bul."""
    if PAPER_TRADING or not OKX_KEY or not order_ids:
        return []
    filled = []
    try:
        for oid in order_ids:
            if not oid or oid.startswith("PAPER"):
                continue
            data = _okx_get(f"/api/v5/trade/order?instId={inst_id}&ordId={oid}")
            orders = data.get("data", [])
            if orders and orders[0].get("state") == "filled":
                filled.append(orders[0])
    except Exception as e:
        _log(f"[GRID] Emir kontrol hatası: {e}", "warning")
    return filled


def setup_grid(inst_id: str, current_price: float) -> None:
    """
    Grid kur — ATR bazlı otomatik aralık, eşit seviyeler.
    Her coin için $500 sermaye (toplam $1000 / 2 coin).
    """
    capital_per_coin = GRID_TOTAL_CAPITAL / len(GRID_COINS)

    # ATR ile aralık belirle (1 saatlik)
    atr = _calc_atr_14(inst_id, bar="1H")
    if atr <= 0:
        _log(f"[GRID] {inst_id} ATR hesaplanamadı — grid kurulmadı", "warning")
        return

    grid_range  = atr * GRID_ATR_MULT
    lower_price = current_price - grid_range / 2
    upper_price = current_price + grid_range / 2
    step        = grid_range / GRID_LEVELS

    # Kontrat bilgisi
    info               = get_contract_info(inst_id)
    ct_val             = info["ct_val"]
    notional_per_level = capital_per_coin / GRID_LEVELS
    qty_coin           = notional_per_level / current_price
    qty_sz             = max(1, round(qty_coin / ct_val))

    levels = []
    for i in range(GRID_LEVELS):
        lvl_price = lower_price + i * step
        levels.append(round(lvl_price, 2))

    _log(
        f"[GRID] {inst_id} kurulumu | "
        f"Aralık: ${lower_price:.2f} - ${upper_price:.2f} | "
        f"{GRID_LEVELS} seviye | "
        f"Adım: ${step:.2f} | "
        f"ATR: ${atr:.2f} | "
        f"Seviye başı: {qty_sz} kontrat"
    )

    if inst_id in _grid_state:
        old = _grid_state[inst_id]
        _cancel_grid_orders(inst_id, old.get("buy_order_ids", []))
        _cancel_grid_orders(inst_id, old.get("sell_order_ids", []))

    buy_order_ids  = []
    sell_order_ids = []

    # YENİ: Fiyata yakın emir stratejisi
    # Mevcut fiyatın hemen altına en az 2 alış, hemen üstüne en az 2 satış emri koy
    # Böylece fiyat hareket ettiğinde hemen dolar
    CLOSE_DISTANCE = step * 0.3   # Fiyatın çok yakınında emir (adımın %30'u kadar)

    for lvl in levels:
        # Fiyatın altındaki seviyelere alış emri
        if lvl < current_price - CLOSE_DISTANCE:
            oid = _place_grid_limit_order(inst_id, "buy", lvl, qty_sz, "long")
            if oid:
                buy_order_ids.append(oid)
        # Fiyatın üzerindeki seviyelere satış emri
        elif lvl > current_price + CLOSE_DISTANCE:
            oid = _place_grid_limit_order(inst_id, "sell", lvl, qty_sz, "short")
            if oid:
                sell_order_ids.append(oid)

    # YENİ: Fiyata en yakın seviyeye ek emir — boşluk varsa hemen altına bir alış koy
    nearest_buy = current_price - CLOSE_DISTANCE
    oid_near = _place_grid_limit_order(inst_id, "buy", round(nearest_buy, 2), qty_sz, "long")
    if oid_near and oid_near not in buy_order_ids:
        buy_order_ids.insert(0, oid_near)
        _log(f"[GRID] ✓ Yakın alış emri eklendi: ${nearest_buy:.2f}")

    _grid_state[inst_id] = {
        "active":         True,
        "levels":         levels,
        "step":           step,
        "lower":          lower_price,
        "upper":          upper_price,
        "qty_sz":         qty_sz,
        "capital":        capital_per_coin,
        "setup_price":    current_price,
        "buy_order_ids":  buy_order_ids,
        "sell_order_ids": sell_order_ids,
        "filled_buys":    0,
        "filled_sells":   0,
        "total_pnl":      0.0,
        "last_check":     datetime.now(timezone.utc).isoformat(),
    }

    _log(f"[GRID] {inst_id} aktif | {len(buy_order_ids)} alış + {len(sell_order_ids)} satış emri")


def run_grid_trading() -> None:
    """
    Grid yönetim döngüsü — her 5 dakikada çalışır.
    1. Dolmuş emirleri tespit et → karşı taraf emrini koy
    2. Fiyat aralık dışına çıktıysa grid'i yeniden kur
    """
    if not GRID_ACTIVE:
        return

    for inst_id in GRID_COINS:
        sym = COIN_MAP.get(inst_id, inst_id)

        # Anlık fiyat
        try:
            price_data = _okx_get(f"/api/v5/market/ticker?instId={inst_id}")
            current_price = float(price_data["data"][0]["last"])
        except:
            _log(f"[GRID] {sym} fiyat alınamadı", "warning")
            continue

        gs = _grid_state.get(inst_id)

    # Grid hiç kurulmamışsa kur
        if not gs or not gs.get("active"):
            _log(f"[GRID] {sym} ilk kurulum @ ${current_price:.2f}")
            # Kaldıraç ayarla
            if OKX_KEY and not PAPER_TRADING:
                try:
                    _okx_post("/api/v5/account/set-leverage", {
                        "instId": inst_id,
                        "lever":  str(GRID_LEVERAGE),
                        "mgnMode": "cross"
                    })
                except:
                    pass
            setup_grid(inst_id, current_price)
            continue

        # Fiyat aralık dışına çıktıysa grid'i yeniden kur
        margin = gs["step"] * 0.5  # Yarım adım tolerans
        if current_price < gs["lower"] - margin or current_price > gs["upper"] + margin:
            _log(
                f"[GRID] {sym} aralık dışı "
                f"(${current_price:.2f} | aralık: ${gs['lower']:.2f}-${gs['upper']:.2f}) "
                f"— yeniden kuruluyor"
            )
            setup_grid(inst_id, current_price)
            continue

        # Dolmuş emirleri kontrol et
        all_order_ids = gs.get("buy_order_ids", []) + gs.get("sell_order_ids", [])
        filled = _get_grid_filled_orders(inst_id, all_order_ids)

        for order in filled:
            fill_price = float(order.get("avgPx", 0) or 0)
            fill_side  = order.get("side", "buy")
            fill_sz    = int(float(order.get("accFillSz", gs["qty_sz"])))
            pnl        = float(order.get("pnl", 0) or 0)
            fee        = float(order.get("fee", 0) or 0)

            gs["total_pnl"] += pnl + fee

            if fill_side == "buy":
                # Alış doldu → üst seviyede satış koy
                gs["filled_buys"] += 1
                sell_price = fill_price + gs["step"]
                if sell_price <= gs["upper"]:
                    oid = _place_grid_limit_order(inst_id, "sell", sell_price, fill_sz, "short")
                    if oid:
                        gs["sell_order_ids"].append(oid)
                _log(
                    f"[GRID] {sym} ALIŞ doldu @ ${fill_price:.2f} "
                    f"→ SATIŞ @ ${sell_price:.2f} | "
                    f"Toplam kâr: ${gs['total_pnl']:.4f}"
                )
                # Dolmuş emri listeden çıkar
                if order.get("ordId") in gs["buy_order_ids"]:
                    gs["buy_order_ids"].remove(order["ordId"])

            elif fill_side == "sell":
                # Satış doldu → alt seviyede alış koy
                gs["filled_sells"] += 1
                buy_price = fill_price - gs["step"]
                if buy_price >= gs["lower"]:
                    oid = _place_grid_limit_order(inst_id, "buy", buy_price, fill_sz, "long")
                    if oid:
                        gs["buy_order_ids"].append(oid)
                _log(
                    f"[GRID] {sym} SATIŞ doldu @ ${fill_price:.2f} "
                    f"→ ALIŞ @ ${buy_price:.2f} | "
                    f"Toplam kâr: ${gs['total_pnl']:.4f}"
                )
                if order.get("ordId") in gs["sell_order_ids"]:
                    gs["sell_order_ids"].remove(order["ordId"])

        gs["last_check"] = datetime.now(timezone.utc).isoformat()

        _log(
            f"[GRID] {sym} durum | "
            f"Fiyat: ${current_price:.2f} | "
            f"Alış emirleri: {len(gs['buy_order_ids'])} | "
            f"Satış emirleri: {len(gs['sell_order_ids'])} | "
            f"Toplam kâr: ${gs['total_pnl']:.4f}"
        )


BALANCE_FLOOR = float(os.getenv("BALANCE_FLOOR", "0"))  # 0 = devre dışı


def _check_balance_floor(balance: float, positions: list = None) -> bool:
    """Bakiye koruma — $1000 altına düşünce tüm pozisyonları kapat ve dur."""
    if balance <= BALANCE_FLOOR:
        already_hit = engine_state.get("balance_floor_hit", False)

        if not already_hit:
            _log(f"🚨 BAKİYE KORUMA AKTIF — Bakiye ${balance:.2f} ≤ ${BALANCE_FLOOR:.2f}", "error")
            _log(f"🚨 Tüm pozisyonlar kapatılıyor...", "error")

            # Tüm açık pozisyonları market emriyle kapat
            if positions:
                for p in positions:
                    inst_id  = p.get("instId", "")
                    side     = p.get("side", "long")
                    qty      = p.get("qty", 0)
                    close_side = "sell" if side == "long" else "buy"
                    try:
                        if not PAPER_TRADING and OKX_KEY and inst_id and qty > 0:
                            close_position(inst_id, side, qty)
                            _log(f"🔴 {inst_id} {side.upper()} kapatıldı (bakiye koruma)", "error")
                        else:
                            _log(f"[PAPER] {inst_id} {side.upper()} kapatılırdı (bakiye koruma)")
                    except Exception as e:
                        _log(f"❌ {inst_id} kapatılamadı: {e}", "error")

            # Grid emirlerini iptal et
            try:
                for inst_id in GRID_COINS:
                    gs = _grid_state.get(inst_id, {})
                    if gs:
                        _cancel_grid_orders(inst_id, gs.get("buy_order_ids", []))
                        _cancel_grid_orders(inst_id, gs.get("sell_order_ids", []))
                        gs["active"] = False
                        _log(f"[GRID] {inst_id} emirleri iptal edildi (bakiye koruma)")
            except Exception as e:
                _log(f"[GRID] İptal hatası: {e}", "warning")

            with _lock:
                engine_state["balance_floor_hit"] = True
                engine_state["balance_floor_at"]  = datetime.now(timezone.utc).isoformat()
                engine_state["open_positions"]     = {}

        return True

    # Bakiye toparlandıysa korumayı kaldır
    if engine_state.get("balance_floor_hit"):
        _log(f"✅ Bakiye ${balance:.2f} — $1000 üzerine çıktı, sistem devam ediyor")
        with _lock:
            engine_state["balance_floor_hit"] = False
            engine_state["balance_floor_at"]  = None
    return False


def bot_loop():
    """Ana bot döngüsü — her LOOP_SECONDS saniyede çalışır."""
    _log(f"Bot motoru başlatıldı | Paper={PAPER_TRADING} | Kaldıraç={LEVERAGE}x | Coinler={list(COIN_MAP.values())}")

    # DB başlat
    db = None
    try:
        import db_manager as _db
        if _db.init_db():
            db = _db
            _log("PostgreSQL bağlantısı kuruldu")
    except Exception as e:
        _log(f"DB başlatılamadı (devam edilecek): {e}", "warning")

    # trade_id takibi: symbol → db trade id
    _trade_ids: Dict[str, int] = {}

    # Kaldıraç ayarla
    for inst_id in COINS:
        set_leverage(inst_id, LEVERAGE)

    while True:
        try:
            with _lock:
                engine_state["loop_count"] += 1
                loop_num = engine_state["loop_count"]

            _log(f"─── Döngü #{loop_num} ───")

            # 1. Bakiye güncelle
            balance = get_balance()
            with _lock:
                engine_state["balance"] = balance

            # 2. Açık pozisyonları al
            positions = get_open_positions()

            # 2b. Bakiye koruma kontrolü
            if _check_balance_floor(balance, positions):
                _log(f"⏸ Döngü #{loop_num} atlandı — bakiye koruma aktif (${balance:.2f})")
                time.sleep(LOOP_SECONDS)
                continue

            # ── YENİ: Rejim Tespiti ────────────────────────────────────────────
            current_regime     = "RANGE"   # Varsayılan
            current_regime_obj = None
            regime_mult        = 1.0

            if _ADVANCED_MODULES:
                try:
                    # BTC 1H ve 4H verisi çek
                    df_btc_1h = fetch_ohlcv("BTC-USDT-SWAP", bar="1H", limit=80)
                    df_btc_4h = fetch_ohlcv("BTC-USDT-SWAP", bar="4H", limit=60)
                    btc_funding = get_funding_rate("BTC-USDT-SWAP")

                    if df_btc_1h is not None and len(df_btc_1h) >= 30:
                        btc_regime = get_btc_regime(df_btc_1h, df_btc_4h, btc_funding)
                        current_regime     = btc_regime.regime
                        current_regime_obj = btc_regime
                        regime_mult        = btc_regime.position_size_mult
                        _log(f"📊 Rejim: {regime_summary(btc_regime)}")

                        with _lock:
                            engine_state["regime"] = {
                                "name":        btc_regime.regime,
                                "confidence":  btc_regime.confidence,
                                "adx_1h":      btc_regime.adx_1h,
                                "adx_4h":      btc_regime.adx_4h,
                                "allow_long":  btc_regime.allow_long,
                                "allow_short": btc_regime.allow_short,
                                "pos_mult":    btc_regime.position_size_mult,
                                "reason":      btc_regime.reason,
                            }
                except Exception as _re:
                    _log(f"[REGIME] Hata: {_re}", "warning")

            # ── YENİ: Risk Manager Güncelle ───────────────────────────────────
            if _ADVANCED_MODULES:
                try:
                    rm = get_risk_manager()
                    daily_pnl = engine_state.get("daily_pnl", 0.0)
                    rm.update_state(positions, balance, daily_pnl)
                    risk_state = rm.get_state_summary()
                    if risk_state["is_paused"]:
                        _log(f"⏸ Risk Manager: {risk_state['pause_reason']}")
                    with _lock:
                        engine_state["risk_state"] = risk_state
                except Exception as _rme:
                    _log(f"[RISK] Güncelleme hatası: {_rme}", "warning")

            # 3. SL/TP kontrol
            signals_snap = engine_state.get("signals", {})
            if positions and signals_snap:
                check_exits(positions, signals_snap)
                positions = get_open_positions()  # Güncel listeyi al

            # 4. Sinyal üret
            signals = run_signals(positions)
            with _lock:
                engine_state["signals"]    = signals
                engine_state["last_scan"]  = datetime.now(timezone.utc).isoformat()

            # 5. Funding Rate Arbitrage (ilk döngüde + her 5 döngüde bir)
            if loop_num == 1 or loop_num % 5 == 0:
                try:
                    run_funding_arbitrage(positions, db=db, trade_ids=_trade_ids)
                except Exception as _fe:
                    _log(f"[FUNDING] Döngü hatası: {_fe}", "warning")

            # 5b. Grid Trading (ilk döngüde + her 5 döngüde bir)
            if loop_num == 1 or loop_num % 5 == 0:
                try:
                    run_grid_trading()
                    with _lock:
                        engine_state["grid"] = {
                            sym: {
                                "active":       gs.get("active", False),
                                "lower":        round(gs.get("lower", 0), 2),
                                "upper":        round(gs.get("upper", 0), 2),
                                "step":         round(gs.get("step", 0), 2),
                                "levels":       gs.get("levels", []),
                                "filled_buys":  gs.get("filled_buys", 0),
                                "filled_sells": gs.get("filled_sells", 0),
                                "total_pnl":    round(gs.get("total_pnl", 0), 4),
                                "buy_orders":   len(gs.get("buy_order_ids", [])),
                                "sell_orders":  len(gs.get("sell_order_ids", [])),
                            }
                            for sym, gs in _grid_state.items()
                        }
                except Exception as _ge:
                    _log(f"[GRID] Döngü hatası: {_ge}", "warning")

            # 6. Emir gönder
            open_count  = len(positions)
            hour_ok     = _is_good_trading_hour()
            hour_utc    = datetime.now(timezone.utc).hour

            # Mevcut pozisyonları coin ve yön bazında indeksle
            open_longs  = {p["instId"] for p in positions if p.get("side") == "long"}
            open_shorts = {p["instId"] for p in positions if p.get("side") == "short"}

            # Slot bölüşümü: MAX_POSITIONS yarısı LONG, yarısı SHORT
            long_limit  = MAX_POSITIONS // 2 + (MAX_POSITIONS % 2)  # Üst yarı LONG (tek sayıda +1)
            short_limit = MAX_POSITIONS // 2

            long_count  = len(open_longs)
            short_count = len(open_shorts)

            for sym, sig in signals.items():
                if open_count >= MAX_POSITIONS:
                    _log(f"⛔ Max pozisyon doldu ({open_count}/{MAX_POSITIONS}) — yeni işlem açılmıyor")
                    break
                if sig["in_position"]:
                    continue

                inst_id = sig["inst_id"]

                # ── Entry Recycler: Cooldown kontrolü ─────────────────────────
                if _ADVANCED_MODULES:
                    try:
                        recycler = get_recycler()
                        if recycler.is_in_cooldown(sym):
                            _log(f"⏳ {sym} cooldown'da — giriş bekleniyor")
                            continue
                        # Score boost uygula
                        boost = recycler.get_score_boost(sym)
                        if boost > 0:
                            sig["long"]["score"]  = sig["long"]["score"]  + boost
                            sig["short"]["score"] = sig["short"]["score"] + boost
                            _log(f"⚡ {sym} re-entry boost: +{boost} puan")
                    except:
                        pass

                # ── Dinamik LONG_MIN_SCORE (rejime göre) ─────────────────────
                effective_min = LONG_MIN_SCORE
                if current_regime == "TREND_UP":
                    effective_min = max(6, LONG_MIN_SCORE - 2)
                elif current_regime == "TREND_DOWN":
                    effective_min = LONG_MIN_SCORE + 2
                # RANGE → varsayılan LONG_MIN_SCORE

                # ── LONG sinyali ──────────────────────────────────────────────
                if (sig["long"]["enter"] and sig["long"]["entry"]
                        and sig["long"]["score"] >= effective_min
                        and inst_id not in open_longs
                        and inst_id not in open_shorts
                        and long_count < long_limit):

                    # Rejim long'a izin veriyor mu?
                    # NO_TRADE dışında long açılabilir — rejim skora yansıtılır
                    if current_regime == "NO_TRADE":
                        _log(f"⛔ {sym} LONG — NO_TRADE rejimi")
                        continue

                    price = sig["long"]["entry"]
                    sl    = sig["long"]["sl"] or price * (1 - 0.012)
                    tp    = sig["long"]["tp"] or price * (1 + 0.018)
                    risk  = price - sl
                    tp1   = price + risk * TP1_R_MULT
                    tp2   = price + risk * TP2_R_MULT

                    # Sabit slot — Railway SLOT_NOTIONAL değeri
                    notional_to_use = SLOT_NOTIONAL
                    if _ADVANCED_MODULES:
                        try:
                            rm = get_risk_manager()
                            rd = rm.check_trade(
                                inst_id=inst_id, side="long",
                                notional=notional_to_use,
                                entry_price=price, stop_price=sl,
                                regime=current_regime, regime_mult=regime_mult,
                            )
                            if not rd.approved:
                                _log(f"⛔ {sym} LONG risk reddi: {rd.reason}")
                                continue
                            if rd.warnings:
                                for w in rd.warnings:
                                    _log(f"⚠ {sym} LONG: {w}")
                        except Exception as _rme:
                            _log(f"[RISK] Kontrol hatası: {_rme}", "warning")

                    _log(f"🟢 {sym} LONG | Puan:{sig['long']['score']}/11 | Rejim:{current_regime} | Slot:{long_count+1}/{long_limit} | Giriş:${price:.4f} SL:${sl:.4f} TP1:${tp1:.4f}(0.5R) TP2:${tp2:.4f}(1R)")
                    ok = place_order(inst_id, "buy", notional_to_use, price,
                                     sl_price=sl, tp1_price=tp1, tp2_price=tp2)
                    if ok:
                        _bot_opened_positions.add(inst_id)  # Bot açtı olarak işaretle
                        with _lock:
                            engine_state["open_positions"][sym] = {
                                "symbol": sym, "side": "long",
                                "entry_price": price, "stop_loss": sl,
                                "take_profit": tp, "notional": notional_to_use,
                                "opened_at": datetime.now(timezone.utc).isoformat(),
                                "score": sig["long"]["score"],
                            }
                        open_count  += 1
                        long_count  += 1
                        open_longs.add(inst_id)
                        # Recycler'a başarılı giriş bildir — kuyruğu temizle
                        if _ADVANCED_MODULES:
                            try: get_recycler().mark_re_entered(sym, success=True)
                            except: pass
                        if db:
                            tid = db.open_trade(sym, "long", price, sl, tp, SLOT_NOTIONAL,
                                                sig["long"]["score"], "Pullback Long",
                                                "paper" if PAPER_TRADING else "live")
                            if tid:
                                _trade_ids[sym] = tid

                # ── SHORT sinyali ─────────────────────────────────────────────
                elif (PULLBACK_SHORT_ACTIVE
                        and sig["short"]["enter"] and sig["short"]["entry"]
                        and sig["short"]["score"] >= effective_min
                        and inst_id not in open_shorts
                        and inst_id not in open_longs
                        and short_count < short_limit):

                    # Rejim short'a izin veriyor mu?
                    # NO_TRADE dışında short açılabilir
                    if current_regime == "NO_TRADE":
                        _log(f"⛔ {sym} SHORT — NO_TRADE rejimi")
                        continue

                    price = sig["short"]["entry"]
                    sl    = sig["short"]["sl"] or price * (1 + 0.012)
                    tp    = sig["short"]["tp"] or price * (1 - 0.018)
                    risk  = sl - price
                    tp1   = price - risk * TP1_R_MULT
                    tp2   = price - risk * TP2_R_MULT

                    # Risk Manager kontrolü
                    notional_to_use = SLOT_NOTIONAL
                    if _ADVANCED_MODULES:
                        try:
                            rm = get_risk_manager()
                            rd = rm.check_trade(
                                inst_id=inst_id, side="short",
                                notional=SLOT_NOTIONAL,
                                entry_price=price, stop_price=sl,
                                regime=current_regime, regime_mult=regime_mult,
                            )
                            if not rd.approved:
                                _log(f"⛔ {sym} SHORT risk reddi: {rd.reason}")
                                continue
                            if rd.warnings:
                                for w in rd.warnings:
                                    _log(f"⚠ {sym} SHORT: {w}")
                            notional_to_use = rd.position_size if rd.position_size > 0 else SLOT_NOTIONAL
                        except Exception as _rme:
                            _log(f"[RISK] Kontrol hatası: {_rme}", "warning")

                    _log(f"🔴 {sym} SHORT | Puan:{sig['short']['score']}/11 | Rejim:{current_regime} | Slot:{short_count+1}/{short_limit} | Giriş:${price:.4f} SL:${sl:.4f} TP1:${tp1:.4f}(0.5R) TP2:${tp2:.4f}(1R)")
                    ok = place_order(inst_id, "sell", notional_to_use, price,
                                     sl_price=sl, tp1_price=tp1, tp2_price=tp2)
                    if ok:
                        with _lock:
                            engine_state["open_positions"][sym] = {
                                "symbol": sym, "side": "short",
                                "entry_price": price, "stop_loss": sl,
                                "take_profit": tp, "notional": SLOT_NOTIONAL,
                                "opened_at": datetime.now(timezone.utc).isoformat(),
                                "score": sig["short"]["score"],
                            }
                        open_count  += 1
                        short_count += 1
                        open_shorts.add(inst_id)
                        if db:
                            tid = db.open_trade(sym, "short", price, sl, tp, SLOT_NOTIONAL,
                                                sig["short"]["score"], "Pullback Short",
                                                "paper" if PAPER_TRADING else "live")
                            if tid:
                                _trade_ids[sym] = tid

            # ── Entry Recycler: Hazır öğeleri rescan et ───────────────────────
            if _ADVANCED_MODULES:
                try:
                    recycler = get_recycler()
                    ready_items = recycler.get_ready_items()
                    for item in ready_items:
                        sym = item.trade.symbol
                        _log(f"♻️ {sym} rescan — cooldown bitti, skor değerlendiriliyor")
                        item.mark_attempted()
                        # Rescan: mevcut sinyali kontrol et
                        sig = signals.get(sym, {})
                        long_sig  = sig.get("long", {})
                        short_sig = sig.get("short", {})
                        boosted_long  = long_sig.get("score", 0)  + item.score_boost
                        boosted_short = short_sig.get("score", 0) + item.score_boost
                        if boosted_long >= effective_min and long_sig.get("enter"):
                            _log(f"♻️ {sym} re-entry LONG uygun (skor:{boosted_long}) — bir sonraki döngüde açılacak")
                        elif boosted_short >= effective_min and short_sig.get("enter"):
                            _log(f"♻️ {sym} re-entry SHORT uygun (skor:{boosted_short}) — bir sonraki döngüde açılacak")
                        else:
                            _log(f"♻️ {sym} rescan — skor yetersiz, beklemeye devam")
                            recycler.mark_re_entered(sym, success=False)
                    # Recycler durumunu engine_state'e yaz
                    with _lock:
                        engine_state["recycle_state"] = recycler.get_status()
                except Exception as _re:
                    _log(f"[RECYCLE] Hata: {_re}", "warning")

        except Exception as e:
            _log(f"Döngü hatası: {e}", "error")

        time.sleep(LOOP_SECONDS)


def start():
    """Bot motorunu arka plan thread olarak başlat."""
    with _lock:
        engine_state["running"] = True
    t = threading.Thread(target=bot_loop, daemon=True, name="BotEngine")
    t.start()
    _log("Bot motoru thread başlatıldı")
    return t
