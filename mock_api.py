from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
import asyncio, json, os, urllib.request, hmac, hashlib, base64, time, threading
from datetime import datetime, timedelta

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

OKX_KEY        = os.getenv("OKX_API_KEY", "")
OKX_SECRET     = os.getenv("OKX_API_SECRET", "")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")
PAPER_TRADING  = os.getenv("PAPER_TRADING", "true").lower() != "false"

ALLOWED_COINS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT"}
OKX_INST = {"BTCUSDT":"BTC-USDT","ETHUSDT":"ETH-USDT","SOLUSDT":"SOL-USDT",
            "BNBUSDT":"BNB-USDT","AVAXUSDT":"AVAX-USDT"}

_prices     = {}
_positions  = []
_stats      = {}
_last_fetch = 0
_lock       = threading.Lock()

# ── Bot Engine başlat ─────────────────────────────────────────────────────────
try:
    import bot_engine
    bot_engine.start()
    _bot_active = True
except Exception as _be:
    import logging
    logging.getLogger("mock_api").warning(f"Bot engine başlatılamadı: {_be}")
    _bot_active = False

# ── OKX Helpers ───────────────────────────────────────────────────────────────
def _okx_sign(ts, method, path, body=""):
    msg = ts + method + path + body
    sig = base64.b64encode(hmac.new(OKX_SECRET.encode(), msg.encode(), hashlib.sha256).digest()).decode()
    return {"OK-ACCESS-KEY": OKX_KEY, "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
            "Content-Type": "application/json", "User-Agent": "CryptoBot/3.0"}

def _okx_get(path):
    try:
        ts  = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        req = urllib.request.Request("https://www.okx.com"+path, headers=_okx_sign(ts,"GET",path))
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def fetch_price(inst_id):
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
        req = urllib.request.Request(url, headers={"User-Agent":"CryptoBot/3.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            d = json.loads(r.read())
            return float(d["data"][0]["last"])
    except:
        return 0.0

def refresh_all():
    global _positions, _stats, _last_fetch
    with _lock:
        for sym, inst in OKX_INST.items():
            p = fetch_price(inst)
            if p > 0: _prices[sym] = p

        if OKX_KEY:
            data = _okx_get("/api/v5/account/positions?instType=SWAP")
            pos_list = []
            for p in data.get("data", []):
                qty = float(p.get("pos", 0))
                if qty == 0: continue
                inst    = p.get("instId","")
                sym     = inst.replace("-USDT-SWAP","USDT").replace("-USDT","USDT")
                side    = "long" if qty > 0 else "short"
                entry   = float(p.get("avgPx", 0))
                current = _prices.get(sym, entry)
                lev     = int(float(p.get("lever", 10)))
                pnl     = float(p.get("upl", 0) or 0)
                margin  = float(p.get("margin", 0) or 0)
                notional= float(p.get("notionalUsd", 0) or 0)
                # PnL % = pnl / margin * 100 (marjin üzerinden gerçek oran)
                # Eğer margin=0 ise notional/leverage ile hesapla
                if margin <= 0 and notional > 0:
                    margin = notional / lev
                pnl_p   = round((pnl / margin * 100) if margin > 0 else 0.0, 2)
                is_manual = sym not in ALLOWED_COINS

                # Bot engine'den SL/TP al
                eng_pos = {}
                if _bot_active:
                    eng_pos = bot_engine.engine_state.get("open_positions", {}).get(sym, {})

                pos_list.append({
                    "id": len(pos_list)+1, "symbol": sym, "side": side,
                    "entry_price":  round(entry, 6 if entry < 1 else 2),
                    "current_price":round(current,6 if current < 1 else 2),
                    "quantity": abs(qty), "leverage": lev,
                    "pnl": round(pnl,2), "pnl_percent": round(pnl_p,2),
                    "stop_loss":   eng_pos.get("stop_loss",  round(entry*(0.975 if side=="long" else 1.025),4)),
                    "take_profit": eng_pos.get("take_profit",round(entry*(1.04  if side=="long" else 0.96), 4)),
                    "notional": round(notional,2),
                    "candles_held": 1, "max_bars": 24, "bars_remaining": 23,
                    "lot_type": "standard",
                    "is_adopted": is_manual,
                    "strategy_name": "Manuel" if is_manual else "Pullback Long v3",
                    "score": eng_pos.get("score", 0),
                    "opened_at": eng_pos.get("opened_at", datetime.now().isoformat()),
                    "distance_to_sl_pct": round(abs(entry*(0.975 if side=="long" else 1.025)-current)/current*100,2),
                    "distance_to_tp_pct": round(abs(entry*(1.04  if side=="long" else 0.96) -current)/current*100,2),
                })
            _positions = pos_list

            bal_data = _okx_get("/api/v5/account/balance?ccy=USDT")
            try:
                avail = float(bal_data["data"][0]["details"][0]["availBal"])
                total = float(bal_data["data"][0]["totalEq"])
            except:
                avail, total = 0.0, 0.0

            total_unr = sum(p["pnl"] for p in _positions)

            # DB'den gerçek istatistikleri al
            db_stats = {}
            try:
                import db_manager
                db_stats = db_manager.get_stats()
            except:
                pass

            _stats = {
                "totalBalance":      round(total, 2),
                "availableBalance":  round(avail, 2),
                "unrealizedPnl":     round(total_unr, 2),
                "totalPnl":          round(total - float(os.getenv("INITIAL_BALANCE_USDT","1000")), 2),
                "dailyPnl":          round(total_unr, 2),
                "winRate":           db_stats.get("winRate", 0.0),
                "profitFactor":      0.0,
                "totalTrades":       db_stats.get("totalTrades", 0),
                "winningTrades":     db_stats.get("winningTrades", 0),
                "losingTrades":      db_stats.get("losingTrades", 0),
                "consecutiveLosses": 0,
                "openPositions":     len(_positions),
            }
        _last_fetch = time.time()

refresh_all()

def bg_refresh():
    while True:
        time.sleep(5)
        try: refresh_all()
        except: pass

threading.Thread(target=bg_refresh, daemon=True).start()

# ── Payload ───────────────────────────────────────────────────────────────────
def build_payload():
    with _lock:
        eng = bot_engine.engine_state if _bot_active else {}
        return {
            "positions":    list(_positions),
            "recentTrades": [],
            "stats":        dict(_stats),
            "botStatus": {
                "running":       eng.get("running", False),
                "mode":          "paper" if PAPER_TRADING else "live",
                "exchange":      "okx",
                "authenticated": bool(OKX_KEY),
                "strategy":      "Pullback Long + Short v3",
                "last_scan":     eng.get("last_scan"),
                "loop_count":    eng.get("loop_count", 0),
                "signals":       eng.get("signals", {}),
                "logs":          eng.get("logs", [])[-10:],
            },
            "timestamp": datetime.now().isoformat()
        }

# ── SSE ───────────────────────────────────────────────────────────────────────
async def sse_generator(request: Request):
    while True:
        if await request.is_disconnected(): break
        yield f"data: {json.dumps(build_payload())}\n\n"
        await asyncio.sleep(3)

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/")
def dashboard():
    html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    try:
        with open(html_file, "r", encoding="utf-8") as f: return HTMLResponse(f.read())
    except: return HTMLResponse("<h1>dashboard.html bulunamadi</h1>", status_code=404)

@app.get("/api/stream")
async def stream(request: Request):
    return StreamingResponse(sse_generator(request), media_type="text/event-stream",
        headers={"Cache-Control":"no-cache","Access-Control-Allow-Origin":"*"})

@app.get("/api/health")
def health():
    eng = bot_engine.engine_state if _bot_active else {}
    return {
        "ok": True, "exchange": "okx", "authenticated": bool(OKX_KEY),
        "paper_trading": PAPER_TRADING,
        "bot_running": eng.get("running", False),
        "loop_count":  eng.get("loop_count", 0),
        "last_scan":   eng.get("last_scan"),
        "open_positions": len(_positions),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/positions")
def get_positions():
    with _lock: return JSONResponse(list(_positions))

@app.get("/api/signals")
def get_signals():
    if not _bot_active: return JSONResponse({})
    return JSONResponse(bot_engine.engine_state.get("signals", {}))

@app.get("/api/logs")
def get_logs():
    if not _bot_active: return JSONResponse([])
    return JSONResponse(bot_engine.engine_state.get("logs", []))

@app.get("/api/trades")
def get_trades():
    all_trades = []

    # 1. DB'deki bot işlemleri
    try:
        import db_manager
        db_trades = db_manager.get_trades(limit=100)
        for t in db_trades:
            for k in ["opened_at", "closed_at"]:
                if t.get(k) and hasattr(t[k], "isoformat"):
                    t[k] = t[k].isoformat()
            for k in ["entry_price","exit_price","pnl","pnl_pct"]:
                if t.get(k) is not None:
                    t[k] = float(t[k])
            t["source"] = "bot"
        all_trades.extend(db_trades)
    except Exception:
        pass

    # 2. OKX geçmiş işlemleri (son 50)
    if OKX_KEY:
        try:
            okx_data = _okx_get("/api/v5/trade/fills?instType=SWAP&limit=50")
            okx_fills = okx_data.get("data", [])

            # OKX fill'lerini trade formatına çevir
            seen_ids = {t.get("exchange_order_id") for t in all_trades if t.get("exchange_order_id")}
            for f in okx_fills:
                order_id = f.get("ordId", "")
                if order_id in seen_ids:
                    continue  # DB'de zaten var

                inst_id = f.get("instId", "")
                sym = inst_id.replace("-USDT-SWAP","USDT").replace("-USDT","USDT").replace("-","")
                side_raw = f.get("side", "buy")
                pos_side = f.get("posSide", "long")
                price = float(f.get("fillPx", 0) or 0)
                qty   = float(f.get("fillSz", 0) or 0)
                fee   = float(f.get("fee", 0) or 0)
                ts_ms = int(f.get("ts", 0) or 0)
                ts_str = datetime.utcfromtimestamp(ts_ms/1000).isoformat() if ts_ms else None

                # PnL: OKX fills'de pnl alanı var
                pnl = float(f.get("pnl", 0) or 0)

                all_trades.append({
                    "id": None,
                    "symbol": sym,
                    "side": pos_side,
                    "entry_price": price,
                    "exit_price": price if side_raw in ("sell","buy") else None,
                    "pnl": pnl,
                    "pnl_pct": 0.0,
                    "strategy": "OKX",
                    "mode": "live",
                    "status": "closed",
                    "opened_at": ts_str,
                    "closed_at": ts_str,
                    "exit_reason": side_raw,
                    "score": 0,
                    "source": "okx",
                    "exchange_order_id": order_id,
                })
        except Exception:
            pass

    # Tarihe göre sırala (en yeni önce)
    all_trades.sort(key=lambda t: t.get("opened_at") or "", reverse=True)
    return JSONResponse(all_trades[:100])

@app.get("/api/settings")
def get_settings():
    return {
        "trading_mode": "paper" if PAPER_TRADING else "live",
        "leverage": int(os.getenv("LEVERAGE","10")),
        "slot_notional": float(os.getenv("SLOT_NOTIONAL","1000")),
        "max_positions": int(os.getenv("MAX_POSITIONS","3")),
        "bot_running": True, "exchange": "okx",
        "strategy": "Pullback Long + Short v3",
        "allowed_coins": list(ALLOWED_COINS),
        "authenticated": bool(OKX_KEY)
    }

@app.put("/api/settings")
async def update_settings(request: Request): return {"ok": True}

@app.post("/api/bot/start")
def start():
    if _bot_active:
        bot_engine.engine_state["running"] = True
    return {"ok": True, "running": True}

@app.post("/api/bot/stop")
def stop():
    if _bot_active:
        bot_engine.engine_state["running"] = False
    return {"ok": True, "running": False}
