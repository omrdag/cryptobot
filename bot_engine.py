"""
Bot Engine — Gerçek Sinyal + Emir Motoru
=========================================
mock_api.py tarafından arka plan thread olarak başlatılır.
Her 60 saniyede bir coinleri tarar, sinyal üretir, OKX'e emir gönderir.

GÜNCELLEME — Nisan 2026:
  - RSI Filtresi eklendi: RSI > LONG_RSI_MAX iken long açılmaz
    Railway Variables: LONG_RSI_MAX=72 (varsayılan)
    Log: ⛔ [LONG RSI BLOKE] BTCUSDT — RSI:88.5 > 72
  - Long log'una RSI değeri eklendi: 🟢 BTCUSDT LONG | RSI:65.2 | ...
  - Girişteki RSI pozisyon kaydına eklendi (rsi_at_entry)
"""

import os, time, hmac, hashlib, base64, json, threading, logging
import urllib.request, urllib.parse
from datetime import datetime, timezone
from typing import Dict, Optional
import pandas as pd

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

COINS    = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP", "AVAX-USDT-SWAP"]
COIN_MAP = {c: c.replace("-USDT-SWAP", "USDT") for c in COINS}

SLOT_NOTIONAL = float(os.getenv("SLOT_NOTIONAL", "1000"))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "3"))

# ── YENİ: RSI Aşırı Alım Filtresi ────────────────────────────────────────────
# RSI bu değerin üzerindeyse long açılmaz — tepe alım koruması
# Railway Variables'a LONG_RSI_MAX=72 ekle (varsayılan: 72)
LONG_RSI_MAX = int(os.getenv("LONG_RSI_MAX", "72"))

_bot_opened_positions: set = set()


def _calc_dynamic_slot(balance: float, max_pos: int = None) -> float:
    if max_pos is None:
        max_pos = MAX_POSITIONS
    if balance <= 0:
        return max(50.0, SLOT_NOTIONAL)
    dynamic = (balance * 0.80) / max(1, max_pos)
    return float(max(50.0, min(dynamic, SLOT_NOTIONAL)))


engine_state: Dict = {
    "running":           False,
    "last_scan":         None,
    "signals":           {},
    "open_positions":    {},
    "logs":              [],
    "balance":           0.0,
    "loop_count":        0,
    "grid":              {},
    "balance_floor_hit": False,
    "balance_floor_at":  None,
    "regime":            {},
    "risk_state":        {},
    "daily_pnl":         0.0,
}
_lock = threading.Lock()


def _log(msg: str, level: str = "info"):
    ts   = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    getattr(log, level)(msg)
    print(f"cryptobot: {line}", flush=True)
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
        ts       = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        body_str = json.dumps(body)
        req      = urllib.request.Request(
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
        df = df.iloc[::-1].reset_index(drop=True)
        return df
    except Exception as e:
        _log(f"OHLCV hatası {inst_id}: {e}", "warning")
        return None


def get_balance() -> float:
    if not OKX_KEY:
        return 10000.0
    data = _okx_get("/api/v5/account/balance?ccy=USDT")
    try:
        return float(data["data"][0]["details"][0]["availBal"])
    except:
        return 0.0


def get_open_positions() -> list:
    if not OKX_KEY:
        return []
    data      = _okx_get("/api/v5/account/positions?instType=SWAP")
    positions = []
    for p in data.get("data", []):
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
        pos_side = p.get("posSide", "")

        if pos_side == "long":
            side = "long"
        elif pos_side == "short":
            side = "short"
        else:
            side = "long" if qty > 0 else "short"

        entry = float(p.get("avgPx", 0))
        sym   = COIN_MAP.get(inst_id, inst_id)

        positions.append({
            "instId":   inst_id,
            "side":     side,
            "qty":      abs(qty),
            "entry":    entry,
            "pnl":      float(p.get("upl", 0)),
            "leverage": int(float(p.get("lever", LEVERAGE))),
            "avgPx":    entry,
            "pos":      abs(qty),
        })

        state_key       = sym + ("_short" if side == "short" else "")
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
                            "stop_loss": sl, "take_profit": tp,
                            "entry_price": entry, "side": side,
                            "inst_id": inst_id, "profit_stage": 0,
                            "half_closed": False, "recovered": True,
                        }
                        _log(f"🔄 {sym} ({side}) bot pozisyonu kurtarıldı: giriş=${entry:.4f} SL=${sl:.4f}")
                    except Exception as e:
                        _log(f"⚠️ {sym} pozisyon kayıt hatası: {e}", "warning")
        else:
            _log(f"👤 {sym} manuel pozisyon — dokunulmayacak (giriş:${entry:.4f})")

    return positions


def set_leverage(inst_id: str, lev: int):
    if not OKX_KEY or PAPER_TRADING:
        return
    _okx_post("/api/v5/account/set-leverage", {
        "instId": inst_id, "lever": str(lev), "mgnMode": "cross"
    })


def get_contract_info(inst_id: str) -> dict:
    if not hasattr(get_contract_info, "_cache"):
        get_contract_info._cache = {}
    if inst_id not in get_contract_info._cache:
        info_data = _okx_get(f"/api/v5/public/instruments?instType=SWAP&instId={inst_id}")
        try:
            d = info_data["data"][0]
            get_contract_info._cache[inst_id] = {
                "ct_val":  float(d.get("ctVal",  0.01)),
                "lot_sz":  float(d.get("lotSz",  1)),
                "tick_sz": float(d.get("tickSz", 0.01)),
                "min_sz":  float(d.get("minSz",  1)),
            }
        except:
            get_contract_info._cache[inst_id] = {"ct_val": 0.01, "lot_sz": 1, "tick_sz": 0.01, "min_sz": 1}
    return get_contract_info._cache[inst_id]


def round_price(price: float, tick_sz: float) -> str:
    if tick_sz <= 0:
        return f"{price:.4f}"
    decimals = max(0, -int(f"{tick_sz:e}".split("e")[1]))
    return f"{round(price / tick_sz) * tick_sz:.{decimals}f}"


def place_order(inst_id: str, side: str, notional: float, price: float,
                sl_price: float = 0.0, tp1_price: float = 0.0, tp2_price: float = 0.0) -> bool:
    if PAPER_TRADING:
        _log(f"[PAPER] {side.upper()} {inst_id} notional=${notional:.0f} @ ${price:.4f} | SL=${sl_price:.4f} TP1=${tp1_price:.4f} TP2=${tp2_price:.4f}")
        return True
    if not OKX_KEY:
        _log("API anahtarı yok, emir gönderilemedi", "error")
        return False

    info         = get_contract_info(inst_id)
    ct_val       = info["ct_val"]
    tick_sz      = info["tick_sz"]
    qty_coin     = notional / price
    qty_contract = max(info["min_sz"], round(qty_coin / ct_val))
    pos_side     = "long" if side == "buy" else "short"

    result = _okx_post("/api/v5/trade/order", {
        "instId": inst_id, "tdMode": "cross", "side": side,
        "posSide": pos_side, "ordType": "market", "sz": str(int(qty_contract)),
    })
    ok = result.get("code") == "0"
    if not ok:
        err = result.get("data", [{}])[0].get("sMsg") or result.get("msg", "?")
        _log(f"❌ Emir reddedildi: {inst_id} → {err} (code:{result.get('code')})", "error")
        return False

    order_id = result.get("data", [{}])[0].get("ordId", "")
    _log(f"✅ {side.upper()} {inst_id} {int(qty_contract)} kontrat | ordId={order_id}")

    if sl_price > 0:
        sl_side  = "sell" if pos_side == "long" else "buy"
        sl_result = _okx_post("/api/v5/trade/order-algo", {
            "instId": inst_id, "tdMode": "cross", "side": sl_side,
            "posSide": pos_side, "ordType": "conditional",
            "sz": str(int(qty_contract)),
            "slTriggerPx": round_price(sl_price, tick_sz),
            "slOrdPx": "-1", "slTriggerPxType": "mark",
        })
        if sl_result.get("code") == "0":
            _log(f"🛡️ SL ayarlandı: ${sl_price:.4f}")
        else:
            _log(f"⚠️ SL ayarlanamadı: {sl_result.get('msg','?')}", "warning")

    TRAIL_ACTIVATION_PCT = float(os.getenv("TRAIL_ACTIVATION_PCT", "0.003"))
    TRAIL_CALLBACK_PCT   = float(os.getenv("TRAIL_CALLBACK_PCT",   "0.002"))
    trail_active_px = price * (1 + TRAIL_ACTIVATION_PCT) if pos_side == "long" else price * (1 - TRAIL_ACTIVATION_PCT)
    trail_side      = "sell" if pos_side == "long" else "buy"

    trail_result = _okx_post("/api/v5/trade/order-algo", {
        "instId": inst_id, "tdMode": "cross", "side": trail_side,
        "posSide": pos_side, "ordType": "move_order_stop",
        "sz": str(int(qty_contract)),
        "activePx": round_price(trail_active_px, tick_sz),
        "callbackRatio": str(TRAIL_CALLBACK_PCT),
    })
    if trail_result.get("code") == "0":
        _log(f"🎯 Trailing Stop: aktif=${trail_active_px:.4f} | geri=%{TRAIL_CALLBACK_PCT*100:.1f}")
    else:
        _log(f"⚠️ Trailing Stop ayarlanamadı: {trail_result.get('msg','?')}", "warning")
        if tp1_price > 0:
            tp1_qty  = max(1, int(qty_contract * 0.50))
            tp1_side = "sell" if pos_side == "long" else "buy"
            _okx_post("/api/v5/trade/order-algo", {
                "instId": inst_id, "tdMode": "cross", "side": tp1_side,
                "posSide": pos_side, "ordType": "conditional", "sz": str(tp1_qty),
                "tpTriggerPx": round_price(tp1_price, tick_sz),
                "tpOrdPx": "-1", "tpTriggerPxType": "mark",
            })
        if tp2_price > 0:
            tp2_qty = int(qty_contract) - max(1, int(qty_contract * 0.50))
            if tp2_qty > 0:
                tp2_side = "sell" if pos_side == "long" else "buy"
                _okx_post("/api/v5/trade/order-algo", {
                    "instId": inst_id, "tdMode": "cross", "side": tp2_side,
                    "posSide": pos_side, "ordType": "conditional", "sz": str(tp2_qty),
                    "tpTriggerPx": round_price(tp2_price, tick_sz),
                    "tpOrdPx": "-1", "tpTriggerPxType": "mark",
                })
    return True


def close_position(inst_id: str, side: str, qty: float):
    if PAPER_TRADING:
        _log(f"[PAPER] KAPAT {inst_id} {side} qty={qty:.4f}")
        return True
    if not OKX_KEY:
        return False

    close_side = "sell" if side == "long" else "buy"
    info_data  = _okx_get(f"/api/v5/public/instruments?instType=SWAP&instId={inst_id}")
    try:
        ct_val = float(info_data["data"][0]["ctVal"])
    except:
        ct_val = 0.01

    pos_data = _okx_get(f"/api/v5/account/positions?instId={inst_id}")
    try:
        sz = pos_data["data"][0]["pos"]
    except:
        sz = str(round(qty / ct_val))

    result = _okx_post("/api/v5/trade/order", {
        "instId": inst_id, "tdMode": "cross", "side": close_side,
        "posSide": side, "ordType": "market", "sz": str(abs(int(float(sz)))),
    })
    ok = result.get("code") == "0"
    if ok:
        _log(f"✅ Pozisyon kapatıldı: {inst_id} {side}")
    else:
        _log(f"❌ Kapatma başarısız: {inst_id} → {result.get('msg','?')}", "error")
    return ok


# ── RSI Hesaplama Yardımcısı ──────────────────────────────────────────────────

def _calc_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """Son mum RSI'ını hesapla."""
    try:
        close = df["close"]
        delta = close.diff()
        gain  = delta.where(delta > 0, 0).ewm(span=period, adjust=False).mean()
        loss  = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
        rs    = gain / loss.replace(0, 1e-10)
        return float(100 - (100 / (1 + rs.iloc[-1])))
    except:
        return 50.0


# ── Sinyal Motoru ─────────────────────────────────────────────────────────────

def run_signals(positions: list) -> dict:
    from pullback_long  import PullbackLongStrategy
    from pullback_short import PullbackShortStrategy

    long_strat  = PullbackLongStrategy(min_score=LONG_MIN_SCORE)
    short_strat = PullbackShortStrategy(min_score=LONG_MIN_SCORE)

    open_syms = {p["instId"] for p in positions if p["instId"] in _bot_opened_positions}
    signals   = {}

    for inst_id in COINS:
        sym = COIN_MAP[inst_id]

        df = fetch_ohlcv(inst_id, bar="5m", limit=100)
        if df is None or len(df) < 55:
            _log(f"{sym}: yetersiz veri ({len(df) if df is not None else 0} bar)")
            continue

        df_1h    = fetch_ohlcv(inst_id, bar="1H", limit=60)
        hour_utc = datetime.now(timezone.utc).hour

        long_res  = long_strat.generate(df, symbol=sym, hour_utc=hour_utc,
                                        df_5m=None, df_15m=None, df_1h=df_1h)
        short_res = short_strat.generate(df, symbol=sym, hour_utc=hour_utc)

        # ── RSI hesapla — emir gönderme filtresi için ─────────────────────────
        rsi_val = _calc_rsi(df)

        signals[sym] = {
            "inst_id":     inst_id,
            "rsi":         round(rsi_val, 1),
            "long":  {
                "score":  long_res.score,
                "enter":  long_res.should_enter,
                "sl":     long_res.stop_loss,
                "tp":     long_res.take_profit,
                "entry":  long_res.entry_price,
                "reason": long_res.reason[:100],
                "rsi":    round(rsi_val, 1),
            },
            "short": {
                "score":  short_res.score,
                "enter":  short_res.should_enter,
                "sl":     short_res.stop_loss,
                "tp":     short_res.take_profit,
                "entry":  short_res.entry_price,
                "reason": short_res.reason[:100],
            },
            "in_position": inst_id in open_syms,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        }

        if long_res.should_enter:
            status = f"BUY ({long_res.score}/11)"
        elif short_res.should_enter:
            status = f"SHORT ({short_res.score}/10)"
        else:
            status = f"HOLD (L:{long_res.score} S:{short_res.score})"
        _log(f"{sym}: {status} | enter={long_res.should_enter}")

    return signals


def check_exits(positions: list, signals: dict):
    TRAIL_ACTIVATION_PCT = float(os.getenv("TRAIL_ACTIVATION_PCT", "0.003"))
    TRAIL_CALLBACK_PCT   = float(os.getenv("TRAIL_CALLBACK_PCT",   "0.002"))
    PROFIT_LOCK_1        = float(os.getenv("PROFIT_LOCK_1",  "3.0"))
    PROFIT_LOCK_2        = float(os.getenv("PROFIT_LOCK_2",  "5.0"))
    PROFIT_HALF          = float(os.getenv("PROFIT_HALF",    "7.0"))
    PROFIT_FULL          = float(os.getenv("PROFIT_FULL",   "10.0"))

    for pos in positions:
        inst_id = pos["instId"]
        sym     = COIN_MAP.get(inst_id, inst_id)

        if inst_id not in _bot_opened_positions:
            state_key = sym + ("_short" if pos.get("side") == "short" else "")
            if state_key not in engine_state["open_positions"] and sym not in engine_state["open_positions"]:
                continue

        try:
            price = float(_okx_get(f"/api/v5/market/ticker?instId={inst_id}")["data"][0]["last"])
        except:
            continue

        entry = float(pos.get("avgPx", 0) or pos.get("entry", 0))
        side  = pos.get("side", "long")
        qty   = float(pos.get("pos", 0) or pos.get("qty", 0))

        if entry <= 0 or qty <= 0:
            continue

        pos_detail   = engine_state["open_positions"].get(sym, {})
        sl           = float(pos_detail.get("stop_loss",   0))
        tp           = float(pos_detail.get("take_profit", 0))
        half_closed  = pos_detail.get("half_closed",  False)
        profit_stage = pos_detail.get("profit_stage", 0)

        if sl <= 0 and entry > 0:
            sl_mult = float(os.getenv("SL_ATR_MULT", "1.5"))
            sl_pct  = 0.015 * sl_mult
            sl = entry * (1 - sl_pct) if side == "long" else entry * (1 + sl_pct)
            tp = (entry * (1 + sl_pct * 2) if side == "long" else entry * (1 - sl_pct * 2)) if tp <= 0 else tp
            with _lock:
                d = engine_state["open_positions"].setdefault(sym, {})
                d.update({"stop_loss": sl, "take_profit": tp, "entry_price": entry, "side": side})
            sl = 0

        info     = get_contract_info(inst_id)
        coin_qty = qty * info["ct_val"]
        pnl_usdt = (price - entry) * coin_qty if side == "long" else (entry - price) * coin_qty

        # Kâr basamakları
        if pnl_usdt >= PROFIT_FULL:
            _log(f"💰 {sym} +${pnl_usdt:.2f} — {'TAM' if not half_closed else 'KALAN'} KAPANIŞ (${PROFIT_FULL}+)")
            close_position(inst_id, side, qty)
            if _ADVANCED_MODULES:
                try: get_risk_manager().record_trade_result(pnl_usdt)
                except: pass
            with _lock:
                engine_state["open_positions"].pop(sym, None)
            continue

        elif pnl_usdt >= PROFIT_HALF and not half_closed:
            _log(f"🎯 {sym} +${pnl_usdt:.2f} — %50 KISMİ SATIŞ")
            half_qty   = max(1, int(qty * 0.5))
            close_side = "sell" if side == "long" else "buy"
            if not PAPER_TRADING and OKX_KEY:
                r = _okx_post("/api/v5/trade/order", {
                    "instId": inst_id, "tdMode": "cross", "side": close_side,
                    "posSide": side, "ordType": "market", "sz": str(half_qty),
                })
                _log(f"✅ %50 satış OK" if r.get("code") == "0" else f"⚠️ %50 satış hatası: {r.get('msg','?')}")
            else:
                _log(f"[PAPER] {sym} %50 satış ({half_qty} kontrat @ ${price:.4f})")
            with _lock:
                d = engine_state["open_positions"].get(sym, {})
                d.update({"half_closed": True, "half_close_pnl": pnl_usdt, "profit_stage": 3})
            continue

        elif pnl_usdt >= PROFIT_HALF and half_closed:
            sig      = signals.get(sym, {})
            long_ok  = sig.get("long",  {}).get("score", 0) >= 6 and sig.get("long",  {}).get("enter", False)
            short_ok = sig.get("short", {}).get("score", 0) >= 6 and sig.get("short", {}).get("enter", False)
            trend_ok = long_ok if side == "long" else short_ok
            if not trend_ok and pnl_usdt < pos_detail.get("half_close_pnl", PROFIT_HALF):
                _log(f"⚠️ {sym} Trend zayıfladı, kalan kapatılıyor (${pnl_usdt:.2f})")
                close_position(inst_id, side, qty)
                with _lock:
                    engine_state["open_positions"].pop(sym, None)
                continue

        elif pnl_usdt >= PROFIT_LOCK_2 and profit_stage < 2:
            new_sl = entry * 1.002 if side == "long" else entry * 0.998
            if (side == "long" and new_sl > sl) or (side == "short" and new_sl < sl):
                _log(f"🔒 {sym} +${pnl_usdt:.2f} KAR KORUMA 2: SL → ${new_sl:.4f}")
                with _lock:
                    d = engine_state["open_positions"].get(sym, {})
                    d.update({"stop_loss": new_sl, "profit_stage": 2})
                sl = new_sl

        elif pnl_usdt >= PROFIT_LOCK_1 and profit_stage < 1:
            protect_usdt = PROFIT_LOCK_1 * 0.8
            coin_qty_sl  = qty * get_contract_info(inst_id)["ct_val"]
            price_diff   = protect_usdt / coin_qty_sl if coin_qty_sl > 0 else 0
            new_sl = (entry + price_diff) if side == "long" else (entry - price_diff)
            if (side == "long" and new_sl > sl) or (side == "short" and new_sl < sl):
                _log(f"🔒 {sym} +${pnl_usdt:.2f} KAR KİLİTLEME: SL → ${new_sl:.4f} (${protect_usdt:.1f} USDT korunuyor)")
                with _lock:
                    d = engine_state["open_positions"].get(sym, {})
                    d.update({"stop_loss": new_sl, "profit_stage": 1})
                sl = new_sl

        # Trailing Stop — sadece +$3 sonrası
        if pnl_usdt >= PROFIT_LOCK_1:
            if side == "long" and price >= entry * (1 + TRAIL_ACTIVATION_PCT):
                prev_high = float(pos_detail.get("trail_high", 0))
                new_high  = max(prev_high, price)
                trail_sl  = new_high * (1 - TRAIL_CALLBACK_PCT)
                if trail_sl > sl:
                    _log(f"🔒 {sym} Trailing SL: ${sl:.4f} → ${trail_sl:.4f}")
                    with _lock:
                        d = engine_state["open_positions"].get(sym, {})
                        d.update({"stop_loss": trail_sl, "trail_high": new_high})
                    sl = trail_sl
                else:
                    with _lock:
                        engine_state["open_positions"].get(sym, {})["trail_high"] = new_high

            elif side == "short" and price <= entry * (1 - TRAIL_ACTIVATION_PCT):
                prev_low = float(pos_detail.get("trail_low", float("inf")))
                new_low  = min(prev_low, price)
                trail_sl = new_low * (1 + TRAIL_CALLBACK_PCT)
                if trail_sl < sl:
                    _log(f"🔒 {sym} SHORT Trailing SL: ${sl:.4f} → ${trail_sl:.4f}")
                    with _lock:
                        d = engine_state["open_positions"].get(sym, {})
                        d.update({"stop_loss": trail_sl, "trail_low": new_low})
                    sl = trail_sl
                else:
                    with _lock:
                        engine_state["open_positions"].get(sym, {})["trail_low"] = new_low

        # SL / TP kontrolü
        should_close = False
        reason       = ""
        if side == "long":
            if sl > 0 and price <= sl:
                should_close, reason = True, f"SL tetiklendi (${price:.4f} ≤ ${sl:.4f})"
            elif tp > 0 and price >= tp:
                should_close, reason = True, f"TP tetiklendi (${price:.4f} ≥ ${tp:.4f})"
        else:
            if sl > 0 and price >= sl:
                should_close, reason = True, f"SL tetiklendi (${price:.4f} ≥ ${sl:.4f})"
            elif tp > 0 and price <= tp:
                should_close, reason = True, f"TP tetiklendi (${price:.4f} ≤ ${tp:.4f})"

        if should_close:
            _log(f"🔴 {sym} KAPAT — {reason} | PnL: ${pnl_usdt:.2f}")
            close_position(inst_id, side, qty)
            if _ADVANCED_MODULES:
                try: get_risk_manager().record_trade_result(pnl_usdt)
                except: pass
                try:
                    get_recycler().record_close(
                        symbol=sym, inst_id=inst_id, side=side,
                        entry_price=entry, close_price=price,
                        pnl_usdt=pnl_usdt, close_reason=reason.split(" ")[0],
                    )
                except: pass
            with _lock:
                engine_state["open_positions"].pop(sym, None)


# ── Funding Rate Arbitrage ────────────────────────────────────────────────────

FUNDING_COINS            = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
FUNDING_NOTIONAL         = float(os.getenv("FUNDING_NOTIONAL", "1000"))
FUNDING_ENTRY_THRESHOLD  = float(os.getenv("FUNDING_ENTRY_PCT", "0.01"))
FUNDING_EXIT_THRESHOLD   = float(os.getenv("FUNDING_EXIT_PCT",  "0.01"))
FUNDING_MAX_SL_PCT       = 0.005
FUNDING_LEVERAGE         = 3
_funding_positions: Dict[str, dict] = {}


def get_funding_rate(inst_id: str) -> float:
    try:
        data = _okx_get(f"/api/v5/public/funding-rate?instId={inst_id}")
        return float(data.get("data", [{}])[0].get("fundingRate", 0) or 0)
    except:
        return 0.0


def get_next_funding_time(inst_id: str) -> Optional[int]:
    try:
        data = _okx_get(f"/api/v5/public/funding-rate?instId={inst_id}")
        return int(data.get("data", [{}])[0].get("nextFundingTime", 0) or 0)
    except:
        return None


def run_funding_arbitrage(open_positions: list, db=None, trade_ids: dict = None) -> None:
    if not OKX_KEY and not PAPER_TRADING:
        return
    open_syms = {p["instId"] for p in open_positions}

    for inst_id in FUNDING_COINS:
        sym             = COIN_MAP.get(inst_id, inst_id)
        rate            = get_funding_rate(inst_id)
        rate_pct        = rate * 100
        next_ts         = get_next_funding_time(inst_id)
        mins_to_funding = ((next_ts - int(time.time() * 1000)) / 60000) if next_ts else 999
        fp              = _funding_positions.get(sym)

        if fp:
            should_exit = (abs(rate) < FUNDING_EXIT_THRESHOLD / 100 or
                          (fp["side"] == "short" and rate < 0) or
                          (fp["side"] == "long"  and rate > 0))
            if should_exit:
                _log(f"[FUNDING] {sym} kapat")
                if not PAPER_TRADING:
                    close_position(inst_id, fp["side"], fp.get("qty", 0))
                _funding_positions.pop(sym, None)
            continue

        if mins_to_funding < 5 or inst_id in open_syms:
            _log(f"[FUNDING] {sym} {'funding yakın' if mins_to_funding < 5 else 'zaten pozisyonda'} — funding arb atlandı")
            continue

        if abs(rate) < FUNDING_ENTRY_THRESHOLD / 100:
            continue

        arb_side = "sell" if rate > 0 else "buy"
        arb_pos  = "short" if rate > 0 else "long"

        try:
            price = float(_okx_get(f"/api/v5/market/ticker?instId={inst_id}")["data"][0]["last"])
        except:
            continue

        sl             = price * (1 - FUNDING_MAX_SL_PCT) if arb_pos == "long" else price * (1 + FUNDING_MAX_SL_PCT)
        expected_gain  = round(FUNDING_NOTIONAL * abs(rate), 4)
        _log(f"[FUNDING ARB] {sym} {arb_pos.upper()} | Rate=%{rate_pct:.4f} | Beklenen=${expected_gain:.4f} | {mins_to_funding:.0f}dk kaldı")

        ok = place_order(inst_id, arb_side, FUNDING_NOTIONAL, price, sl_price=sl) if not PAPER_TRADING else True
        if ok:
            _funding_positions[sym] = {
                "symbol": sym, "side": arb_pos, "entry": price, "sl": sl,
                "qty": FUNDING_NOTIONAL / price if price > 0 else 0,
                "funding_rate": rate, "expected_gain": expected_gain,
                "opened_at": datetime.now(timezone.utc).isoformat(), "current_price": price,
            }
            _log(f"[FUNDING ARB] ✅ {sym} {arb_pos.upper()} açıldı")


# ── Diğer sabitler ────────────────────────────────────────────────────────────

PULLBACK_SHORT_ACTIVE = os.getenv("PULLBACK_SHORT_ACTIVE", "true").lower() == "true"
LONG_MIN_SCORE        = int(os.getenv("LONG_MIN_SCORE", "7"))
TP1_R_MULT            = float(os.getenv("TP1_R_MULT", "0.5"))
TP2_R_MULT            = float(os.getenv("TP2_R_MULT", "1.0"))


def _is_good_trading_hour() -> bool:
    return True


# ── Grid Trading ──────────────────────────────────────────────────────────────

GRID_COINS         = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
GRID_TOTAL_CAPITAL = float(os.getenv("GRID_CAPITAL",  "1000"))
GRID_LEVELS        = int(os.getenv("GRID_LEVELS",     "8"))
GRID_LEVERAGE      = int(os.getenv("GRID_LEVERAGE",   "3"))
GRID_ATR_MULT      = float(os.getenv("GRID_ATR_MULT", "3.0"))
GRID_ACTIVE        = os.getenv("GRID_ACTIVE", "true").lower() == "true"
_grid_state: Dict[str, dict] = {}


def _calc_atr_14(inst_id: str, bar: str = "1H") -> float:
    try:
        df   = fetch_ohlcv(inst_id, bar=bar, limit=30)
        if df is None or len(df) < 15:
            return 0.0
        prev = df["close"].shift(1)
        tr   = pd.concat([df["high"] - df["low"],
                          (df["high"] - prev).abs(),
                          (df["low"]  - prev).abs()], axis=1).max(axis=1)
        return float(tr.ewm(span=14, adjust=False).mean().iloc[-1])
    except:
        return 0.0


def _place_grid_limit_order(inst_id, side, price, sz, pos_side):
    if PAPER_TRADING:
        _log(f"[PAPER GRID] {side.upper()} {inst_id} {sz}k @ ${price:.4f}")
        return f"PAPER-{inst_id}-{side}-{int(price)}"
    if not OKX_KEY:
        return None
    try:
        info   = get_contract_info(inst_id)
        result = _okx_post("/api/v5/trade/order", {
            "instId": inst_id, "tdMode": "cross", "side": side,
            "posSide": pos_side, "ordType": "limit",
            "px": round_price(price, info["tick_sz"]), "sz": str(sz),
        })
        if result.get("code") == "0":
            oid = result["data"][0]["ordId"]
            _log(f"[GRID] ✓ {side.upper()} {inst_id} @ ${price:.2f} ({oid[:8]})")
            return oid
        _log(f"[GRID] ✗ {inst_id}: {result.get('msg','?')}", "warning")
        return None
    except Exception as e:
        _log(f"[GRID] Hata: {e}", "warning")
        return None


def _cancel_grid_orders(inst_id, order_ids):
    if PAPER_TRADING or not OKX_KEY or not order_ids:
        return
    try:
        for i in range(0, len(order_ids), 20):
            batch = [{"instId": inst_id, "ordId": oid}
                     for oid in order_ids[i:i+20] if oid and not oid.startswith("PAPER")]
            if batch:
                _okx_post("/api/v5/trade/cancel-batch-orders", batch)
    except Exception as e:
        _log(f"[GRID] İptal hatası: {e}", "warning")


def _get_grid_filled_orders(inst_id, order_ids):
    if PAPER_TRADING or not OKX_KEY or not order_ids:
        return []
    filled = []
    try:
        for oid in order_ids:
            if not oid or oid.startswith("PAPER"):
                continue
            data   = _okx_get(f"/api/v5/trade/order?instId={inst_id}&ordId={oid}")
            orders = data.get("data", [])
            if orders and orders[0].get("state") == "filled":
                filled.append(orders[0])
    except:
        pass
    return filled


def setup_grid(inst_id: str, current_price: float) -> None:
    capital = GRID_TOTAL_CAPITAL / len(GRID_COINS)
    atr     = _calc_atr_14(inst_id, bar="1H")
    if atr <= 0:
        _log(f"[GRID] {inst_id} ATR hesaplanamadı", "warning")
        return

    grid_range  = atr * GRID_ATR_MULT
    lower       = current_price - grid_range / 2
    upper       = current_price + grid_range / 2
    step        = grid_range / GRID_LEVELS
    info        = get_contract_info(inst_id)
    qty_sz      = max(1, round((capital / GRID_LEVELS / current_price) / info["ct_val"]))
    levels      = [round(lower + i * step, 2) for i in range(GRID_LEVELS)]

    _log(f"[GRID] {inst_id} kurulum | ${lower:.2f}-${upper:.2f} | adım:${step:.2f} | ATR:${atr:.2f}")

    if inst_id in _grid_state:
        old = _grid_state[inst_id]
        _cancel_grid_orders(inst_id, old.get("buy_order_ids",  []))
        _cancel_grid_orders(inst_id, old.get("sell_order_ids", []))

    buy_ids, sell_ids = [], []
    CLOSE_DIST = step * 0.3
    for lvl in levels:
        if lvl < current_price - CLOSE_DIST:
            oid = _place_grid_limit_order(inst_id, "buy",  lvl, qty_sz, "long")
            if oid: buy_ids.append(oid)
        elif lvl > current_price + CLOSE_DIST:
            oid = _place_grid_limit_order(inst_id, "sell", lvl, qty_sz, "short")
            if oid: sell_ids.append(oid)

    oid_near = _place_grid_limit_order(inst_id, "buy", round(current_price - CLOSE_DIST, 2), qty_sz, "long")
    if oid_near and oid_near not in buy_ids:
        buy_ids.insert(0, oid_near)

    _grid_state[inst_id] = {
        "active": True, "levels": levels, "step": step,
        "lower": lower, "upper": upper, "qty_sz": qty_sz,
        "capital": capital, "setup_price": current_price,
        "buy_order_ids": buy_ids, "sell_order_ids": sell_ids,
        "filled_buys": 0, "filled_sells": 0, "total_pnl": 0.0,
        "last_check": datetime.now(timezone.utc).isoformat(),
    }
    _log(f"[GRID] {inst_id} aktif | {len(buy_ids)} alış + {len(sell_ids)} satış")


def run_grid_trading() -> None:
    if not GRID_ACTIVE:
        return
    for inst_id in GRID_COINS:
        sym = COIN_MAP.get(inst_id, inst_id)
        try:
            current_price = float(_okx_get(f"/api/v5/market/ticker?instId={inst_id}")["data"][0]["last"])
        except:
            continue

        gs = _grid_state.get(inst_id)
        if not gs or not gs.get("active"):
            if OKX_KEY and not PAPER_TRADING:
                try:
                    _okx_post("/api/v5/account/set-leverage", {
                        "instId": inst_id, "lever": str(GRID_LEVERAGE), "mgnMode": "cross"
                    })
                except: pass
            setup_grid(inst_id, current_price)
            continue

        margin = gs["step"] * 0.5
        if current_price < gs["lower"] - margin or current_price > gs["upper"] + margin:
            _log(f"[GRID] {sym} aralık dışı — yeniden kuruluyor")
            setup_grid(inst_id, current_price)
            continue

        for order in _get_grid_filled_orders(inst_id, gs.get("buy_order_ids", []) + gs.get("sell_order_ids", [])):
            fill_price = float(order.get("avgPx", 0) or 0)
            fill_side  = order.get("side", "buy")
            fill_sz    = int(float(order.get("accFillSz", gs["qty_sz"])))
            gs["total_pnl"] += float(order.get("pnl", 0) or 0) + float(order.get("fee", 0) or 0)

            if fill_side == "buy":
                gs["filled_buys"] += 1
                sell_p = fill_price + gs["step"]
                if sell_p <= gs["upper"]:
                    oid = _place_grid_limit_order(inst_id, "sell", sell_p, fill_sz, "short")
                    if oid: gs["sell_order_ids"].append(oid)
                if order.get("ordId") in gs["buy_order_ids"]:
                    gs["buy_order_ids"].remove(order["ordId"])
            elif fill_side == "sell":
                gs["filled_sells"] += 1
                buy_p = fill_price - gs["step"]
                if buy_p >= gs["lower"]:
                    oid = _place_grid_limit_order(inst_id, "buy", buy_p, fill_sz, "long")
                    if oid: gs["buy_order_ids"].append(oid)
                if order.get("ordId") in gs["sell_order_ids"]:
                    gs["sell_order_ids"].remove(order["ordId"])

        gs["last_check"] = datetime.now(timezone.utc).isoformat()
        _log(f"[GRID] {sym} | ${current_price:.2f} | Alış:{len(gs['buy_order_ids'])} Satış:{len(gs['sell_order_ids'])} | Kâr:${gs['total_pnl']:.4f}")


# ── Bakiye Koruma ─────────────────────────────────────────────────────────────

BALANCE_FLOOR = float(os.getenv("BALANCE_FLOOR", "0"))


def _check_balance_floor(balance: float, positions: list = None) -> bool:
    if balance <= BALANCE_FLOOR:
        if not engine_state.get("balance_floor_hit"):
            _log(f"🚨 BAKİYE KORUMA — ${balance:.2f} ≤ ${BALANCE_FLOOR:.2f}", "error")
            for p in (positions or []):
                try:
                    if not PAPER_TRADING and OKX_KEY:
                        close_position(p.get("instId",""), p.get("side","long"), p.get("qty",0))
                except: pass
            for inst_id in GRID_COINS:
                gs = _grid_state.get(inst_id, {})
                if gs:
                    _cancel_grid_orders(inst_id, gs.get("buy_order_ids",  []))
                    _cancel_grid_orders(inst_id, gs.get("sell_order_ids", []))
                    gs["active"] = False
            with _lock:
                engine_state.update({
                    "balance_floor_hit": True,
                    "balance_floor_at":  datetime.now(timezone.utc).isoformat(),
                    "open_positions":    {},
                })
        return True

    if engine_state.get("balance_floor_hit"):
        _log(f"✅ Bakiye ${balance:.2f} — koruma kaldırıldı")
        with _lock:
            engine_state["balance_floor_hit"] = False
            engine_state["balance_floor_at"]  = None
    return False


# ── Ana Döngü ─────────────────────────────────────────────────────────────────

def bot_loop():
    _log(f"Bot başlatıldı | Paper={PAPER_TRADING} | Kaldıraç={LEVERAGE}x | RSI_MAX={LONG_RSI_MAX}")

    db = None
    try:
        import db_manager as _db
        if _db.init_db():
            db = _db
            _log("PostgreSQL bağlantısı kuruldu")
    except Exception as e:
        _log(f"DB başlatılamadı: {e}", "warning")

    _trade_ids: Dict[str, int] = {}
    for inst_id in COINS:
        set_leverage(inst_id, LEVERAGE)

    while True:
        try:
            with _lock:
                engine_state["loop_count"] += 1
                loop_num = engine_state["loop_count"]

            _log(f"─── Döngü #{loop_num} ───")

            balance = get_balance()
            with _lock:
                engine_state["balance"] = balance

            positions = get_open_positions()

            if _check_balance_floor(balance, positions):
                time.sleep(LOOP_SECONDS)
                continue

            # Rejim tespiti
            current_regime = "RANGE"
            regime_mult    = 1.0
            if _ADVANCED_MODULES:
                try:
                    df_btc_1h   = fetch_ohlcv("BTC-USDT-SWAP", bar="1H", limit=80)
                    df_btc_4h   = fetch_ohlcv("BTC-USDT-SWAP", bar="4H", limit=60)
                    btc_funding = get_funding_rate("BTC-USDT-SWAP")
                    if df_btc_1h is not None and len(df_btc_1h) >= 30:
                        btc_regime     = get_btc_regime(df_btc_1h, df_btc_4h, btc_funding)
                        current_regime = btc_regime.regime
                        regime_mult    = btc_regime.position_size_mult
                        _log(f"📊 Rejim: {regime_summary(btc_regime)}")
                        with _lock:
                            engine_state["regime"] = {
                                "name": btc_regime.regime,
                                "confidence": btc_regime.confidence,
                                "adx_1h": btc_regime.adx_1h,
                                "adx_4h": btc_regime.adx_4h,
                                "allow_long": btc_regime.allow_long,
                                "allow_short": btc_regime.allow_short,
                                "pos_mult": btc_regime.position_size_mult,
                                "reason": btc_regime.reason,
                            }
                except Exception as _re:
                    _log(f"[REGIME] Hata: {_re}", "warning")

            # Risk Manager
            if _ADVANCED_MODULES:
                try:
                    rm         = get_risk_manager()
                    daily_pnl  = engine_state.get("daily_pnl", 0.0)
                    rm.update_state(positions, balance, daily_pnl)
                    risk_state = rm.get_state_summary()
                    if risk_state["is_paused"]:
                        _log(f"⏸ Risk Manager: {risk_state['pause_reason']}")
                    with _lock:
                        engine_state["risk_state"] = risk_state
                except Exception as _rme:
                    _log(f"[RISK] Hata: {_rme}", "warning")

            # SL/TP kontrol
            signals_snap = engine_state.get("signals", {})
            if positions and signals_snap:
                check_exits(positions, signals_snap)
                positions = get_open_positions()

            # Sinyal üret
            signals = run_signals(positions)
            with _lock:
                engine_state["signals"]   = signals
                engine_state["last_scan"] = datetime.now(timezone.utc).isoformat()

            # Funding + Grid (her 5 döngüde)
            if loop_num == 1 or loop_num % 5 == 0:
                try: run_funding_arbitrage(positions, db=db, trade_ids=_trade_ids)
                except Exception as _fe: _log(f"[FUNDING] Hata: {_fe}", "warning")
                try:
                    run_grid_trading()
                    with _lock:
                        engine_state["grid"] = {
                            sym: {
                                "active": gs.get("active", False),
                                "lower":  round(gs.get("lower", 0), 2),
                                "upper":  round(gs.get("upper", 0), 2),
                                "step":   round(gs.get("step",  0), 2),
                                "filled_buys":  gs.get("filled_buys",  0),
                                "filled_sells": gs.get("filled_sells", 0),
                                "total_pnl":    round(gs.get("total_pnl", 0), 4),
                                "buy_orders":   len(gs.get("buy_order_ids",  [])),
                                "sell_orders":  len(gs.get("sell_order_ids", [])),
                            }
                            for sym, gs in _grid_state.items()
                        }
                except Exception as _ge: _log(f"[GRID] Hata: {_ge}", "warning")

            # Emir gönder
            bot_positions = [p for p in positions if p["instId"] in _bot_opened_positions]
            open_count    = len(bot_positions)
            _log(f"[EMIR] bot_pos:{open_count} max:{MAX_POSITIONS} sinyaller:{len(signals)}")

            open_longs  = {p["instId"] for p in bot_positions if p.get("side") == "long"}
            open_shorts = {p["instId"] for p in bot_positions if p.get("side") == "short"}
            long_limit  = MAX_POSITIONS // 2 + (MAX_POSITIONS % 2)
            short_limit = MAX_POSITIONS // 2
            long_count  = len(open_longs)
            short_count = len(open_shorts)

            for sym, sig in signals.items():
                if open_count >= MAX_POSITIONS:
                    _log(f"⛔ Max pozisyon doldu ({open_count}/{MAX_POSITIONS})")
                    break
                if sig["in_position"]:
                    continue

                inst_id = sig["inst_id"]

                # Entry Recycler
                if _ADVANCED_MODULES:
                    try:
                        recycler = get_recycler()
                        if recycler.is_in_cooldown(sym):
                            _log(f"⏳ {sym} cooldown'da")
                            continue
                        boost = recycler.get_score_boost(sym)
                        if boost > 0:
                            sig["long"]["score"]  += boost
                            sig["short"]["score"] += boost
                            _log(f"⚡ {sym} re-entry boost: +{boost}")
                    except: pass

                # Rejime göre dinamik eşik
                effective_min = LONG_MIN_SCORE
                if current_regime == "TREND_UP":
                    effective_min = max(6, LONG_MIN_SCORE - 2)
                elif current_regime == "TREND_DOWN":
                    effective_min = LONG_MIN_SCORE + 2

                rsi_current = sig.get("rsi", 0)

                # ── LONG SİNYALİ ─────────────────────────────────────────────
                if (sig["long"]["enter"] and sig["long"]["entry"]
                        and sig["long"]["score"] >= effective_min
                        and inst_id not in open_longs
                        and inst_id not in open_shorts
                        and long_count < long_limit):

                    # ✅ YENİ: RSI Aşırı Alım Filtresi
                    if rsi_current > LONG_RSI_MAX and rsi_current > 0:
                        _log(f"⛔ [LONG RSI BLOKE] {sym} — RSI:{rsi_current:.1f} > {LONG_RSI_MAX} (aşırı alım, giriş engellendi)")
                        continue

                    if current_regime == "NO_TRADE":
                        _log(f"⛔ {sym} LONG — NO_TRADE rejimi")
                        continue

                    price = sig["long"]["entry"]
                    sl    = sig["long"]["sl"] or price * (1 - 0.012)
                    tp    = sig["long"]["tp"] or price * (1 + 0.018)
                    risk  = price - sl
                    tp1   = price + risk * TP1_R_MULT
                    tp2   = price + risk * TP2_R_MULT

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
                            for w in rd.warnings:
                                _log(f"⚠ {sym} LONG: {w}")
                        except Exception as _rme:
                            _log(f"[RISK] Hata: {_rme}", "warning")

                    # RSI log'a eklendi
                    _log(f"🟢 {sym} LONG | Puan:{sig['long']['score']}/11 | RSI:{rsi_current:.1f} | Rejim:{current_regime} | Slot:{long_count+1}/{long_limit} | Giriş:${price:.4f} SL:${sl:.4f} TP1:${tp1:.4f}(0.5R) TP2:${tp2:.4f}(1R)")
                    ok = place_order(inst_id, "buy", notional_to_use, price,
                                     sl_price=sl, tp1_price=tp1, tp2_price=tp2)
                    if ok:
                        _bot_opened_positions.add(inst_id)
                        with _lock:
                            engine_state["open_positions"][sym] = {
                                "symbol": sym, "side": "long",
                                "entry_price": price, "stop_loss": sl,
                                "take_profit": tp, "notional": notional_to_use,
                                "opened_at": datetime.now(timezone.utc).isoformat(),
                                "score": sig["long"]["score"],
                                "rsi_at_entry": rsi_current,  # ✅ Girişteki RSI kaydedildi
                            }
                        open_count += 1
                        long_count += 1
                        open_longs.add(inst_id)
                        if _ADVANCED_MODULES:
                            try: get_recycler().mark_re_entered(sym, success=True)
                            except: pass
                        if db:
                            tid = db.open_trade(sym, "long", price, sl, tp, SLOT_NOTIONAL,
                                                sig["long"]["score"], "Pullback Long",
                                                "paper" if PAPER_TRADING else "live")
                            if tid: _trade_ids[sym] = tid

                # ── SHORT SİNYALİ ─────────────────────────────────────────────
                elif (PULLBACK_SHORT_ACTIVE
                        and sig["short"]["enter"] and sig["short"]["entry"]
                        and sig["short"]["score"] >= effective_min
                        and inst_id not in open_shorts
                        and inst_id not in open_longs
                        and short_count < short_limit):

                    if current_regime == "NO_TRADE":
                        _log(f"⛔ {sym} SHORT — NO_TRADE rejimi")
                        continue

                    price = sig["short"]["entry"]
                    sl    = sig["short"]["sl"] or price * (1 + 0.012)
                    tp    = sig["short"]["tp"] or price * (1 - 0.018)
                    risk  = sl - price
                    tp1   = price - risk * TP1_R_MULT
                    tp2   = price - risk * TP2_R_MULT

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
                            for w in rd.warnings: _log(f"⚠ {sym} SHORT: {w}")
                            notional_to_use = rd.position_size if rd.position_size > 0 else SLOT_NOTIONAL
                        except Exception as _rme:
                            _log(f"[RISK] Hata: {_rme}", "warning")

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
                            if tid: _trade_ids[sym] = tid

            # Entry Recycler
            if _ADVANCED_MODULES:
                try:
                    recycler    = get_recycler()
                    ready_items = recycler.get_ready_items()
                    for item in ready_items:
                        sym = item.trade.symbol
                        _log(f"♻️ {sym} rescan — cooldown bitti")
                        item.mark_attempted()
                        sig       = signals.get(sym, {})
                        b_long    = sig.get("long",  {}).get("score", 0) + item.score_boost
                        b_short   = sig.get("short", {}).get("score", 0) + item.score_boost
                        if b_long  >= effective_min and sig.get("long",  {}).get("enter"):
                            _log(f"♻️ {sym} re-entry LONG uygun ({b_long}) — sonraki döngüde")
                        elif b_short >= effective_min and sig.get("short", {}).get("enter"):
                            _log(f"♻️ {sym} re-entry SHORT uygun ({b_short}) — sonraki döngüde")
                        else:
                            _log(f"♻️ {sym} skor yetersiz")
                            recycler.mark_re_entered(sym, success=False)
                    with _lock:
                        engine_state["recycle_state"] = recycler.get_status()
                except Exception as _re:
                    _log(f"[RECYCLE] Hata: {_re}", "warning")

        except Exception as e:
            _log(f"Döngü hatası: {e}", "error")

        time.sleep(LOOP_SECONDS)


def start():
    with _lock:
        engine_state["running"] = True
    t = threading.Thread(target=bot_loop, daemon=True, name="BotEngine")
    t.start()
    _log("Bot motoru thread başlatıldı")
    return t
