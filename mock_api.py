from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
import asyncio, json, os, urllib.request
from datetime import datetime, timedelta

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_prices = {"BTCUSDT": 0.0, "ETHUSDT": 0.0, "SOLUSDT": 0.0}
OKX_SYMBOLS = {"BTCUSDT": "BTC-USDT", "ETHUSDT": "ETH-USDT", "SOLUSDT": "SOL-USDT"}

def fetch_okx_price(symbol: str) -> float:
    """OKX public API — Railway'den erişilebilir, key gerekmez."""
    try:
        inst = OKX_SYMBOLS.get(symbol, symbol.replace("USDT", "-USDT"))
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst}"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
            return float(data["data"][0]["last"])
    except Exception:
        return 0.0

def refresh_prices():
    for sym in _prices:
        p = fetch_okx_price(sym)
        if p > 0:
            _prices[sym] = p

refresh_prices()

ENTRIES = {"BTCUSDT": 83420.0, "ETHUSDT": 3180.0, "SOLUSDT": 148.5}
SIDES   = {"BTCUSDT": "long",  "ETHUSDT": "long",  "SOLUSDT": "short"}
QTYS    = {"BTCUSDT": 0.021,   "ETHUSDT": 0.55,    "SOLUSDT": 6.7}
LOTS    = {"BTCUSDT": "large", "ETHUSDT": "standard", "SOLUSDT": "standard"}
STRATS  = {"BTCUSDT": "Pullback Long", "ETHUSDT": "Pullback Long", "SOLUSDT": "Pullback Short"}
CANDLES = {"BTCUSDT": 3, "ETHUSDT": 1, "SOLUSDT": 5}
TICK = 0

def build_positions():
    result = []
    for i, sym in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT"]):
        price = _prices.get(sym) or ENTRIES[sym]
        entry = ENTRIES[sym]
        side  = SIDES[sym]
        qty   = QTYS[sym]
        lev   = 10
        pnl   = round((price - entry) * qty * lev if side == "long" else (entry - price) * qty * lev, 2)
        pnl_p = round(pnl / (entry * qty) * 100, 2)
        sl    = entry * (0.975 if side == "long" else 1.025)
        tp    = entry * (1.04  if side == "long" else 0.96)
        result.append({
            "id": i+1, "symbol": sym, "side": side,
            "entry_price": entry,
            "current_price": round(price, 2 if price > 10 else 6),
            "quantity": qty, "leverage": lev,
            "pnl": pnl, "pnl_percent": pnl_p,
            "stop_loss": round(sl, 2), "take_profit": round(tp, 2),
            "notional": round(price * qty * lev, 2),
            "candles_held": CANDLES[sym], "max_bars": 8,
            "bars_remaining": max(0, 8 - CANDLES[sym]),
            "lot_type": LOTS[sym], "is_adopted": sym == "SOLUSDT",
            "distance_to_sl_pct": round((sl - price) / price * 100 if side == "long" else (price - sl) / price * 100, 2),
            "distance_to_tp_pct": round((tp - price) / price * 100 if side == "long" else (price - tp) / price * 100, 2),
            "distance_to_be_pct": round(pnl_p, 2),
            "distance_to_tp1_pct": round((entry * 1.015 - price) / price * 100 if side == "long" else (price - entry * 0.985) / price * 100, 2),
            "strategy_name": STRATS[sym],
            "opened_at": datetime.now().isoformat()
        })
    return result

trades = [
    {"id": 10, "symbol": "AVAXUSDT", "side": "long",  "pnl": 18.4,  "pnl_percent": 2.1,  "exit_reason": "tp1_partial", "strategy_name": "Pullback Long",  "opened_at": (datetime.now()-timedelta(hours=3)).isoformat(), "closed_at": (datetime.now()-timedelta(hours=2)).isoformat()},
    {"id": 9,  "symbol": "BNBUSDT",  "side": "long",  "pnl": 31.2,  "pnl_percent": 3.5,  "exit_reason": "tp2_target",  "strategy_name": "Pullback Long",  "opened_at": (datetime.now()-timedelta(hours=5)).isoformat(), "closed_at": (datetime.now()-timedelta(hours=4)).isoformat()},
    {"id": 8,  "symbol": "LINKUSDT", "side": "short", "pnl": -12.8, "pnl_percent": -1.4, "exit_reason": "stop_loss",   "strategy_name": "Pullback Short", "opened_at": (datetime.now()-timedelta(hours=7)).isoformat(), "closed_at": (datetime.now()-timedelta(hours=6)).isoformat()},
    {"id": 7,  "symbol": "ARBUSDT",  "side": "long",  "pnl": 8.6,   "pnl_percent": 1.0,  "exit_reason": "tp1_partial", "strategy_name": "Pullback Long",  "opened_at": (datetime.now()-timedelta(hours=9)).isoformat(), "closed_at": (datetime.now()-timedelta(hours=8)).isoformat()},
    {"id": 6,  "symbol": "DOGEUSDT", "side": "long",  "pnl": -6.2,  "pnl_percent": -0.7, "exit_reason": "time_exit",   "strategy_name": "Pullback Long",  "opened_at": (datetime.now()-timedelta(hours=11)).isoformat(), "closed_at": (datetime.now()-timedelta(hours=10)).isoformat()},
]

def build_payload():
    positions = build_positions()
    total_unr = sum(p["pnl"] for p in positions)
    return {
        "positions": positions, "recentTrades": trades,
        "stats": {
            "totalBalance": round(10000 + total_unr, 2),
            "availableBalance": 6120.0,
            "unrealizedPnl": round(total_unr, 2),
            "totalPnl": 284.4, "dailyPnl": 47.2,
            "winRate": 63.4, "profitFactor": 1.82,
            "totalTrades": 41, "winningTrades": 26,
            "losingTrades": 15, "consecutiveLosses": 0,
            "openPositions": len(positions),
        },
        "botStatus": {"running": True, "mode": "paper", "exchange": "okx"},
        "timestamp": datetime.now().isoformat()
    }

async def sse_generator(request: Request):
    global TICK
    while True:
        if await request.is_disconnected(): break
        TICK += 1
        if TICK % 3 == 0:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, refresh_prices)
        if TICK % 20 == 0:
            for sym in CANDLES:
                if CANDLES[sym] < 8: CANDLES[sym] += 1
        yield f"data: {json.dumps(build_payload())}\n\n"
        await asyncio.sleep(2)

@app.get("/")
def dashboard():
    html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    try:
        with open(html_file, "r", encoding="utf-8") as f: return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>dashboard.html bulunamadi</h1>", status_code=404)

@app.get("/api/stream")
async def stream(request: Request):
    return StreamingResponse(sse_generator(request), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"})

@app.get("/api/health")
def health():
    return {"ok": True, "exchange": "okx", "btc_price": _prices.get("BTCUSDT", 0), "timestamp": datetime.now().isoformat()}

@app.get("/api/positions")
def get_positions(): return JSONResponse(build_positions())

@app.get("/api/trades")
def get_trades(): return JSONResponse(trades)

@app.get("/api/settings")
def get_settings():
    return {"trading_mode": "paper", "leverage": 10, "bot_running": True, "exchange": "okx"}

@app.put("/api/settings")
async def update_settings(request: Request): return {"ok": True}

@app.post("/api/bot/start")
def start(): return {"ok": True, "running": True}

@app.post("/api/bot/stop")
def stop(): return {"ok": True, "running": False}
