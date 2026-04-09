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
        "posSide": pos_side,
        "ordType": "market",
        "sz":      str(int(qty_contract)),
    }

    result = _okx_post("/api/v5/trade/order", body)
    ok = result.get("code") == "0"
    if not ok:
        _log(f"❌ Emir reddedildi: {inst_id} → {result.get('msg','?')}", "error")
        return False

    order_id = result.get("data", [{}])[0].get("ordId", "")
    _log(f"✅ {side.upper()} {inst_id} {int(qty_contract)} kontrat | ordId={order_id}")

    # ── 2. SL algo emri (tüm pozisyon) ───────────────────────────────────────
    if sl_price > 0:
        sl_side  = "sell" if pos_side == "long" else "buy"
        sl_body  = {
            "instId":     inst_id,
            "tdMode":     "cross",
            "side":       sl_side,
            "posSide":    pos_side,
            "ordType":    "conditional",
            "sz":         str(int(qty_contract)),
            "slTriggerPx": round_price(sl_price, tick_sz),
            "slOrdPx":     "-1",   # market fiyatı
            "slTriggerPxType": "mark",
        }
        sl_result = _okx_post("/api/v5/trade/order-algo", sl_body)
        if sl_result.get("code") == "0":
            _log(f"🛡️ SL ayarlandı: ${sl_price:.4f}")
        else:
            _log(f"⚠️ SL ayarlanamadı: {sl_result.get('msg','?')}", "warning")

    # ── 3. TP1 — %50 kısmi kâr alma ──────────────────────────────────────────
    if tp1_price > 0:
        tp1_qty  = max(1, int(qty_contract * 0.50))  # %50
        tp1_side = "sell" if pos_side == "long" else "buy"
        tp1_body = {
            "instId":     inst_id,
            "tdMode":     "cross",
            "side":       tp1_side,
            "posSide":    pos_side,
            "ordType":    "conditional",
            "sz":         str(tp1_qty),
            "tpTriggerPx": round_price(tp1_price, tick_sz),
            "tpOrdPx":     "-1",
            "tpTriggerPxType": "mark",
        }
        tp1_result = _okx_post("/api/v5/trade/order-algo", tp1_body)
        if tp1_result.get("code") == "0":
            _log(f"🎯 TP1 ayarlandı: ${tp1_price:.4f} (%50 kapat)")
        else:
            _log(f"⚠️ TP1 ayarlanamadı: {tp1_result.get('msg','?')}", "warning")

    # ── 4. TP2 — kalan %50 tam çıkış ─────────────────────────────────────────
    if tp2_price > 0:
        tp2_qty  = int(qty_contract) - (max(1, int(qty_contract * 0.50)))
        if tp2_qty > 0:
            tp2_side = "sell" if pos_side == "long" else "buy"
            tp2_body = {
                "instId":     inst_id,
                "tdMode":     "cross",
                "side":       tp2_side,
                "posSide":    pos_side,
                "ordType":    "conditional",
                "sz":         str(tp2_qty),
                "tpTriggerPx": round_price(tp2_price, tick_sz),
                "tpOrdPx":     "-1",
                "tpTriggerPxType": "mark",
            }
            tp2_result = _okx_post("/api/v5/trade/order-algo", tp2_body)
            if tp2_result.get("code") == "0":
                _log(f"🎯 TP2 ayarlandı: ${tp2_price:.4f} (kalan kapat)")
            else:
                _log(f"⚠️ TP2 ayarlanamadı: {tp2_result.get('msg','?')}", "warning")

    return True


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
    MTF: 1dk (ana) + 5dk (trend onayı) + 15dk (ana trend)
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

        # Ana timeframe: 1dk
        df = fetch_ohlcv(inst_id, bar="1m", limit=100)
        if df is None or len(df) < 55:
            _log(f"{sym}: yetersiz 1dk veri ({len(df) if df is not None else 0} bar)")
            continue

        # MTF: 5dk ve 15dk
        df_5m  = fetch_ohlcv(inst_id, bar="5m",  limit=80)
        df_15m = fetch_ohlcv(inst_id, bar="15m", limit=80)

        hour_utc = datetime.now(timezone.utc).hour

        # Long sinyal (MTF ile)
        long_res = long_strat.generate(
            df, symbol=sym, hour_utc=hour_utc,
            df_5m=df_5m, df_15m=df_15m
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

# ── Funding Rate Arbitrage ────────────────────────────────────────────────────
# Sadece BTC ve ETH — en likit, en düşük spread
FUNDING_COINS   = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
FUNDING_NOTIONAL = float(os.getenv("FUNDING_NOTIONAL", "1000"))  # USDT

# Eşikler
FUNDING_ENTRY_THRESHOLD  = float(os.getenv("FUNDING_ENTRY_PCT", "0.03"))   # %0.03 — giriş eşiği
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

            # 5. Funding Rate Arbitrage (her 5 döngüde bir — ~5 dk)
            if loop_num % 5 == 0:
                try:
                    run_funding_arbitrage(positions, db=db, trade_ids=_trade_ids)
                except Exception as _fe:
                    _log(f"[FUNDING] Döngü hatası: {_fe}", "warning")

            # 6. Emir gönder
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
                    sl    = sig["long"]["sl"] or price * (1 - 0.012)
                    tp    = sig["long"]["tp"] or price * (1 + 0.018)
                    # Kısmi TP sistemi
                    risk  = price - sl
                    tp1   = price + risk * 1.0   # 1R kâr → TP1 (%50 kapat)
                    tp2   = price + risk * 2.0   # 2R kâr → TP2 (kalan kapat)
                    _log(f"🟢 {sym} LONG | Puan:{sig['long']['score']}/10 | Giriş:${price:.4f} SL:${sl:.4f} TP1:${tp1:.4f} TP2:${tp2:.4f}")
                    ok = place_order(inst_id, "buy", SLOT_NOTIONAL, price,
                                     sl_price=sl, tp1_price=tp1, tp2_price=tp2)
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
                        if db:
                            tid = db.open_trade(sym, "long", price, sl, tp, SLOT_NOTIONAL,
                                                sig["long"]["score"], "Pullback Long",
                                                "paper" if PAPER_TRADING else "live")
                            if tid:
                                _trade_ids[sym] = tid

                # Short sinyali (yalnızca long yoksa)
                elif sig["short"]["enter"] and sig["short"]["entry"]:
                    price = sig["short"]["entry"]
                    sl    = sig["short"]["sl"] or price * (1 + 0.012)
                    tp    = sig["short"]["tp"] or price * (1 - 0.018)
                    risk  = sl - price
                    tp1   = price - risk * 1.0   # 1R kâr → TP1
                    tp2   = price - risk * 2.0   # 2R kâr → TP2
                    _log(f"🔴 {sym} SHORT | Puan:{sig['short']['score']}/10 | Giriş:${price:.4f} SL:${sl:.4f} TP1:${tp1:.4f} TP2:${tp2:.4f}")
                    ok = place_order(inst_id, "sell", SLOT_NOTIONAL, price,
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
                        open_count += 1
                        if db:
                            tid = db.open_trade(sym, "short", price, sl, tp, SLOT_NOTIONAL,
                                                sig["short"]["score"], "Pullback Short",
                                                "paper" if PAPER_TRADING else "live")
                            if tid:
                                _trade_ids[sym] = tid

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
