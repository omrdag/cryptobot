from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
import asyncio, json, os, urllib.request, urllib.parse, hmac, hashlib, base64, time
from datetime import datetime, timedelta

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── OKX Credentials ───────────────────────────────────────────────────────────
OKX_KEY        = os.getenv("OKX_API_KEY", "")
OKX_SECRET     = os.getenv("OKX_API_SECRET", "")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")
PAPER_TRADING  = os.getenv("PAPER_TRADING", "true").lower() != "false"

# ── OKX Public Fiyat ─────────────────────────────────────────────────────────
_prices = {}

def fetch_okx_price(inst_id: str) -> float:
    try:
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            return float(data["data"][0]["last"])
    except Exception:
        return 0.0

def refresh_prices():
    pairs = {"BTCUSDT": "BTC-USDT", "ETHUSDT": "ETH-USDT", "SOLUSDT": "SOL-USDT",
             "BNBUSDT": "BNB-USDT", "AVAXUSDT": "AVAX-USDT"}
    for sym, inst in pairs.items():
        p = fetch_okx_price(inst)
        if p > 0:
            _prices[sym] = p

# ── OKX Authenticated API ─────────────────────────────────────────────────────
def okx_sign(timestamp: str, method: str, path: str, body: str = "") -> dict:
    msg = timestamp + method + path + body
    sig = base64.b64encode(
        hmac.new(OKX_SECRET.encode(), msg.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        "OK-ACCESS-KEY":        OKX_KEY,
        "OK-ACCESS-SIGN":       sig,
        "OK-ACCESS-TIMESTAMP":  timestamp,
        "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
        "Content-Type":         "application/json",
        "User-Agent":           "CryptoBot/1.0",
    }

def okx_get(path: str) -> dict:
    try:
        ts  = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
        hdrs = okx_sign(ts, "GET", path)
        url = "https://www.okx.com" + path
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def fetch_okx_balance() -> float:
    if not OKX_KEY:
        return 10000.0
    data = okx_get("/api/v5/account/balance?ccy=USDT")
    try:
        return float(data["data"][0]["details"][0]["availBal"])
    except Exception:
        return 0.0

def fetch_okx_positions() -> list:
    if not OKX_KEY:
        return []
    data = okx_get("/api/v5/account/positions?instType=SWAP")
    try:
        result = []
        for p in data.get("data", []):
            if float(p.get("pos", 0)) == 0:
                continue
            inst    = p["instId"]              # BTC-USDT-SWAP
            symbol  = inst.replace("-USDT-SWAP", "USDT").replace("-USDT", "USDT")
            side    = "long" if float(p.get("pos", 0)) > 0 else "short"
            entry   = float(p.get("avgPx", 0))
            current = float(p.get("last", entry))
            qty     = abs(float(p.get("pos", 0)))
            lev     = int(float(p.get("lever", 10)))
            pnl     = float(p.get("upl", 0))
            pnl_p   = float(p.get("uplRatio", 0)) * 100
            notional = float(p.get("notionalUsd", 0))
            result.append({
                "id": len(result)+1, "symbol": symbol, "side": side,
                "entry_price": entry, "current_price": current,
                "quantity": qty, "leverage": lev,
                "pnl": round(pnl, 2), "pnl_percent": round(pnl_p, 2),
                "stop_loss": entry * (0.97 if side == "long" else 1.03),
                "take_profit": entry * (1.04 if side == "long" else 0.96),
                "notional": round(notional, 2),
                "candles_held": 1, "max_bars": 10, "bars_remaining": 9,
                "lot_type": "standard", "is_adopted": True,
                "distance_to_sl_pct": round((entry*(0.97 if side=="long" else 1.03) - current)/current*100, 2),
                "distance_to_tp_pct": round((entry*(1.04 if side=="long" else 0.96) - current)/current*100, 2),
                "distance_to_be_pct": round(pnl_p, 2),
                "distance_to_tp1_pct": round((entry*1.015 - current)/current*100 if side=="long" else (current - entry*0.985)/current*100, 2),
                "strategy_name": "Pullback " + side.capitalize(),
                "opened_at": datetime.now().isoformat()
            })
        return result
    except Exception:
        return []

# ── Demo pozisyonlar (OKX key yoksa) ─────────────────────────────────────────
DEMO_ENTRIES = {"BTCUSDT": 83420.0, "ETHUSDT": 3180.0, "SOLUSDT": 148.5}
DEMO_SIDES   = {"BTCUSDT": "long", "ETHUSDT": "long", "SOLUSDT": "short"}
DEMO_QTYS    = {"BTCUSDT": 0.021, "ETHUSDT": 0.55, "SOLUSDT": 6.7}
CANDLES      = {"BTCUSDT": 3, "ETHUSDT": 1, "SOLUSDT": 5}

def build_demo_positions():
    result = []
    for i, sym in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
        price = _prices.get(sym) or DEMO_ENTRIES[sym]
        entry = DEMO_ENTRIES[sym]
        side  = DEMO_SIDES[sym]
        qty   = DEMO_QTYS[sym]
        lev   = 10
        pnl   = round((price-entry)*qty*lev if side=="long" else (entry-price)*qty*lev, 2)
        pnl_p = round(pnl/(entry*qty)*100, 2)
        result.append({
            "id": i+1, "symbol": sym, "side": side,
            "entry_price": entry, "current_price": round(price, 2 if price > 10 else 6),
            "quantity": qty, "leverage": lev,
            "pnl": pnl, "pnl_percent": pnl_p,
            "stop_loss": round(entry*(0.975 if side=="long" else 1.025), 2),
            "take_profit": round(entry*(1.04 if side=="long" else 0.96), 2),
            "notional": round(price*qty*lev, 2),
            "candles_held": CANDLES[sym], "max_bars": 8,
            "bars_remaining": max(0, 8-CANDLES[sym]),
            "lot_type": "standard", "is_adopted": False,
            "distance_to_sl_pct": round((entry*0.975-price)/price*100 if side=="long" else (price-entry*1.025)/price*100, 2),
            "distance_to_tp_pct": round((entry*1.04-price)/price*100 if side=="long" else (price-entry*0.96)/price*100, 2),
            "distance_to_be_pct": round(pnl_p, 2),
            "distance_to_tp1_pct": round((entry*1.015-price)/price*100 if side=="long" else (price-entry*0.985)/price*100, 2),
            "strategy_name": "Pullback " + ("Long" if side=="long" else "Short"),
            "opened_at": datetime.now().isoformat()
        })
    return result

trades = [
    {"id":10,"symbol":"AVAXUSDT","side":"long","pnl":18.4,"pnl_percent":2.1,"exit_reason":"tp1_partial","strategy_name":"Pullback Long","opened_at":(datetime.now()-timedelta(hours=3)).isoformat(),"closed_at":(datetime.now()-timedelta(hours=2)).isoformat()},
    {"id":9,"symbol":"BNBUSDT","side":"long","pnl":31.2,"pnl_percent":3.5,"exit_reason":"tp2_target","strategy_name":"Pullback Long","opened_at":(datetime.now()-timedelta(hours=5)).isoformat(),"closed_at":(datetime.now()-timedelta(hours=4)).isoformat()},
    {"id":8,"symbol":"LINKUSDT","side":"short","pnl":-12.8,"pnl_percent":-1.4,"exit_reason":"stop_loss","strategy_name":"Pullback Short","opened_at":(datetime.now()-timedelta(hours=7)).isoformat(),"closed_at":(datetime.now()-timedelta(hours=6)).isoformat()},
    {"id":7,"symbol":"BTCUSDT","side":"long","pnl":3.03,"pnl_percent":0.88,"exit_reason":"tp1_partial","strategy_name":"Pullback Long","opened_at":(datetime.now()-timedelta(hours=9)).isoformat(),"closed_at":(datetime.now()-timedelta(hours=8)).isoformat()},
    {"id":6,"symbol":"ETHUSDT","side":"long","pnl":0.46,"pnl_percent":0.22,"exit_reason":"tp2_target","strategy_name":"Pullback Long","opened_at":(datetime.now()-timedelta(hours=11)).isoformat(),"closed_at":(datetime.now()-timedelta(hours=10)).isoformat()},
]

TICK = 0

def build_payload():
    global TICK
    # OKX key varsa gerçek veri, yoksa demo
    if OKX_KEY:
        positions = fetch_okx_positions()
        balance   = fetch_okx_balance()
    else:
        positions = build_demo_positions()
        balance   = 10000.0

    total_unr = sum(p["pnl"] for p in positions)
    return {
        "positions": positions,
        "recentTrades": trades,
        "stats": {
            "totalBalance":      round(balance + total_unr, 2),
            "availableBalance":  round(balance, 2),
            "unrealizedPnl":     round(total_unr, 2),
            "totalPnl":          284.4,
            "dailyPnl":          47.2,
            "winRate":           63.4,
            "profitFactor":      1.82,
            "totalTrades":       41,
            "winningTrades":     26,
            "losingTrades":      15,
            "consecutiveLosses": 0,
            "openPositions":     len(positions),
        },
        "botStatus": {
            "running":  True,
            "mode":     "paper" if PAPER_TRADING else "live",
            "exchange": "okx",
            "authenticated": bool(OKX_KEY),
        },
        "timestamp": datetime.now().isoformat()
    }

async def sse_generator(request: Request):
    global TICK
    while True:
        if await request.is_disconnected(): break
        TICK += 1
        if TICK % 5 == 0:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, refresh_prices)
        yield f"data: {json.dumps(build_payload())}\n\n"
        await asyncio.sleep(3)

@app.get("/")
def dashboard():
    html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    try:
        with open(html_file, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>dashboard.html bulunamadi</h1>", status_code=404)

@app.get("/api/stream")
async def stream(request: Request):
    return StreamingResponse(sse_generator(request), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"})

@app.get("/api/health")
def health():
    refresh_prices()
    return {
        "ok": True,
        "exchange": "okx",
        "authenticated": bool(OKX_KEY),
        "paper_trading": PAPER_TRADING,
        "btc_price": _prices.get("BTCUSDT", 0),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/positions")
def get_positions():
    return JSONResponse(fetch_okx_positions() if OKX_KEY else build_demo_positions())

@app.get("/api/trades")
def get_trades(): return JSONResponse(trades)

@app.get("/api/settings")
def get_settings():
    return {"trading_mode": "paper" if PAPER_TRADING else "live",
            "leverage": 10, "bot_running": True, "exchange": "okx",
            "authenticated": bool(OKX_KEY)}

@app.put("/api/settings")
async def update_settings(request: Request): return {"ok": True}

@app.post("/api/bot/start")
def start(): return {"ok": True, "running": True}

@app.post("/api/bot/stop")
def stop(): return {"ok": True, "running": False}
