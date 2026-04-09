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

# Slot başına notional (USDT)
SLOT_NOTIONAL  = float(os.getenv("SLOT_NOTIONAL", "1000"))
MAX_POSITIONS  = int(os.getenv("MAX_POSITIONS", "3"))

# ── Paylaşılan durum (mock_api ile ortak) ─────────────────────────────────────
engine_state: Dict = {
    "running":       False,
    "last_scan":     None,
    "signals":       {},     # symbol → son sinyal detayı
    "open_positions": {},    # symbol → pozisyon detayı
    "logs":          [],     # son 50 log satırı
    "balance":       0.0,
    "loop_count":    0,
}
_lock = threading.Lock()


def _log(msg: str, level: str = "info"):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    getattr(log, level)(msg)
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
        with urllib.request.urlopen(req, timeout=8) as r:
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
        with urllib.request.urlopen(req, timeout=8) as r:
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
        with urllib.request.urlopen(req, timeout=8) as r:
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
    """OKX'teki açık pozisyonlar."""
    if not OKX_KEY:
        return []
    data = _okx_get("/api/v5/account/positions?instType=SWAP")
    positions = []
    for p in data.get("data", []):
        qty = float(p.get("pos", 0))
        if qty == 0:
            continue
        positions.append({
            "instId":   p.get("instId", ""),
            "side":     "long" if qty > 0 else "short",
            "qty":      abs(qty),
            "entry":    float(p.get("avgPx", 0)),
            "pnl":      float(p.get("upl", 0)),
            "leverage": int(float(p.get("lever", LEVERAGE))),
        })
    return positions


def set_leverage(inst_id: str, lev: int):
    """Kaldıraç ayarla."""
    if not OKX_KEY or PAPER_TRADING:
        return
    _okx_post("/api/v5/account/set-leverage", {
        "instId": inst_id, "lever": str(lev), "mgnMode": "cross"
    })


def place_order(inst_id: str, side: str, notional: float, price: float) -> bool:
    """
    Market emri gönder.
    side: "buy" (long aç) veya "sell" (short aç)
    """
    if PAPER_TRADING:
        _log(f"[PAPER] {side.upper()} {inst_id} notional=${notional:.0f} @ ${price:.4f}")
        return True

    if not OKX_KEY:
        _log("API anahtarı yok, emir gönderilemedi", "error")
        return False

    # Kontrat büyüklüğünü al
    info_data = _okx_get(f"/api/v5/public/instruments?instType=SWAP&instId={inst_id}")
    try:
        ct_val = float(info_data["data"][0]["ctVal"])  # 1 kontrat = kaç coin
    except:
        ct_val = 0.01  # BTC varsayılan

    qty_coin     = notional / price          # Coin miktarı
    qty_contract = qty_coin / ct_val        # Kontrat sayısı
    qty_contract = max(1, round(qty_contract))  # Minimum 1 kontrat

    pos_side = "long" if side == "buy" else "short"

    body = {
        "instId":  inst_id,
        "tdMode":  "cross",
        "side":    side,
        "posSide": pos_side,
        "ordType": "market",
        "sz":      str(qty_contract),
    }

    result = _okx_post("/api/v5/trade/order", body)
    ok = result.get("code") == "0"
    if ok:
        _log(f"✅ Emir onaylandı: {side.upper()} {inst_id} {qty_contract} kontrat")
    else:
        _log(f"❌ Emir reddedildi: {inst_id} → {result.get('msg','?')}", "error")
    return ok


def close_position(inst_id: str, side: str, qty: float):
    """Pozisyonu kapat."""
    if PAPER_TRADING:
        _log(f"[PAPER] KAPAT {inst_id} {side} qty={qty:.4f}")
        return True
    if not OKX_KEY:
        return False

    close_side = "sell" if side == "long" else "buy"
    pos_side   = side  # "long" veya "short"

    info_data = _okx_get(f"/api/v5/public/instruments?instType=SWAP&instId={inst_id}")
    try:
        ct_val = float(info_data["data"][0]["ctVal"])
    except:
        ct_val = 0.01

    # OKX'teki gerçek kontrat sayısını al
    pos_data = _okx_get(f"/api/v5/account/positions?instId={inst_id}")
    try:
        sz = pos_data["data"][0]["pos"]
    except:
        sz = str(round(qty / ct_val))

    body = {
        "instId":  inst_id,
        "tdMode":  "cross",
        "side":    close_side,
        "posSide": pos_side,
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
    Döndürür: {symbol: signal_info}
    """
    from pullback_long  import PullbackLongStrategy
    from pullback_short import PullbackShortStrategy

    long_strat  = PullbackLongStrategy(min_score=7)
    short_strat = PullbackShortStrategy(min_score=7)

    open_syms = {p["instId"] for p in positions}
    signals   = {}

    for inst_id in COINS:
        sym = COIN_MAP[inst_id]
        df  = fetch_ohlcv(inst_id, bar="1m", limit=100)
        if df is None or len(df) < 55:
            _log(f"{sym}: yetersiz veri ({len(df) if df is not None else 0} bar)")
            continue

        hour_utc = datetime.now(timezone.utc).hour

        # Long sinyal
        long_res = long_strat.generate(df, symbol=sym, hour_utc=hour_utc)
        # Short sinyal (yalnızca düşüş rejiminde — basit kontrol)
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
            status = f"BUY ({long_res.score}/10)"
        elif short_res.should_enter:
            status = f"SHORT ({short_res.score}/10)"
        else:
            status = f"HOLD (L:{long_res.score} S:{short_res.score})"
        _log(f"{sym}: {status}")

    return signals


def check_exits(positions: list, signals: dict):
    """SL/TP kontrolü — basit fiyat bazlı çıkış."""
    for pos in positions:
        inst_id = pos["instId"]
        sym     = COIN_MAP.get(inst_id, inst_id)
        sig     = signals.get(sym, {})
        if not sig:
            continue

        current_price_data = _okx_get(f"/api/v5/market/ticker?instId={inst_id}")
        try:
            price = float(current_price_data["data"][0]["last"])
        except:
            continue

        entry  = pos["entry"]
        side   = pos["side"]

        # SL/TP değerlerini engine_state'den al (açılışta kaydedildi)
        pos_detail = engine_state["open_positions"].get(sym, {})
        sl = pos_detail.get("stop_loss", 0)
        tp = pos_detail.get("take_profit", 0)

        if sl <= 0 or tp <= 0:
            continue

        should_close = False
        reason = ""
        if side == "long":
            if price <= sl:
                should_close, reason = True, f"SL tetiklendi (${price:.4f} <= ${sl:.4f})"
            elif price >= tp:
                should_close, reason = True, f"TP tetiklendi (${price:.4f} >= ${tp:.4f})"
        elif side == "short":
            if price >= sl:
                should_close, reason = True, f"SL tetiklendi (${price:.4f} >= ${sl:.4f})"
            elif price <= tp:
                should_close, reason = True, f"TP tetiklendi (${price:.4f} <= ${tp:.4f})"

        if should_close:
            _log(f"🔴 {sym} KAPAT — {reason}")
            close_position(inst_id, side, pos["qty"])
            with _lock:
                engine_state["open_positions"].pop(sym, None)


# ── Ana Döngü ─────────────────────────────────────────────────────────────────

def bot_loop():
    """Ana bot döngüsü — her LOOP_SECONDS saniyede çalışır."""
    _log(f"Bot motoru başlatıldı | Paper={PAPER_TRADING} | Kaldıraç={LEVERAGE}x | Coinler={list(COIN_MAP.values())}")

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

            # 5. Emir gönder
            open_count = len(positions)
            for sym, sig in signals.items():
                if open_count >= MAX_POSITIONS:
                    break
                if sig["in_position"]:
                    continue

                inst_id = sig["inst_id"]

                # Long sinyali
                if sig["long"]["enter"] and sig["long"]["entry"]:
                    price = sig["long"]["entry"]
                    sl    = sig["long"]["sl"]
                    tp    = sig["long"]["tp"]
                    _log(f"🟢 {sym} LONG aç | Puan:{sig['long']['score']}/10 | Giriş:${price:.4f} SL:${sl:.4f} TP:${tp:.4f}")
                    ok = place_order(inst_id, "buy", SLOT_NOTIONAL, price)
                    if ok:
                        with _lock:
                            engine_state["open_positions"][sym] = {
                                "symbol": sym, "side": "long",
                                "entry_price": price, "stop_loss": sl,
                                "take_profit": tp, "notional": SLOT_NOTIONAL,
                                "opened_at": datetime.now(timezone.utc).isoformat(),
                                "score": sig["long"]["score"],
                            }
                        open_count += 1

                # Short sinyali (yalnızca long yoksa)
                elif sig["short"]["enter"] and sig["short"]["entry"]:
                    price = sig["short"]["entry"]
                    sl    = sig["short"]["sl"]
                    tp    = sig["short"]["tp"]
                    _log(f"🔴 {sym} SHORT aç | Puan:{sig['short']['score']}/10 | Giriş:${price:.4f} SL:${sl:.4f} TP:${tp:.4f}")
                    ok = place_order(inst_id, "sell", SLOT_NOTIONAL, price)
                    if ok:
                        with _lock:
                            engine_state["open_positions"][sym] = {
                                "symbol": sym, "side": "short",
                                "entry_price": price, "stop_loss": sl,
                                "take_profit": tp, "notional": SLOT_NOTIONAL,
                                "opened_at": datetime.now(timezone.utc).isoformat(),
                                "score": sig["short"]["score"],
                            }
                        open_count += 1

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
