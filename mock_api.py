from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
import asyncio
import json
import random
import os
from datetime import datetime, timedelta

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

positions = [
    {
        "id": 1, "symbol": "BTCUSDT", "side": "long",
        "entry_price": 83420, "current_price": 84150,
        "quantity": 0.021, "leverage": 10,
        "pnl": 153.3, "pnl_percent": 1.84,
        "stop_loss": 81200, "take_profit": 88000,
        "candles_held": 3, "max_bars": 8, "bars_remaining": 5,
        "lot_type": "large", "is_adopted": False,
        "distance_to_sl_pct": -2.31, "distance_to_tp_pct": 4.57,
        "distance_to_be_pct": 0.87, "distance_to_tp1_pct": 1.01,
        "strategy_name": "Pullback Long",
        "opened_at": datetime.now().isoformat()
    },
    {
        "id": 2, "symbol": "ETHUSDT", "side": "long",
        "entry_price": 3180, "current_price": 3210,
        "quantity": 0.55, "leverage": 10,
        "pnl": 16.5, "pnl_percent": 0.94,
        "stop_loss": 3090, "take_profit": 3380,
        "candles_held": 1, "max_bars": 8, "bars_remaining": 7,
        "lot_type": "standard", "is_adopted": False,
        "distance_to_sl_pct": -3.74, "distance_to_tp_pct": 5.30,
        "distance_to_be_pct": 0.94, "distance_to_tp1_pct": 1.56,
        "strategy_name": "Pullback Long",
        "opened_at": datetime.now().isoformat()
    },
    {
        "id": 3, "symbol": "SOLUSDT", "side": "short",
        "entry_price": 148.5, "current_price": 146.2,
        "quantity": 6.7, "leverage": 10,
        "pnl": 15.41, "pnl_percent": 1.55,
        "stop_loss": 153.0, "take_profit": 138.0,
        "candles_held": 5, "max_bars": 8, "bars_remaining": 3,
        "lot_type": "standard", "is_adopted": True,
        "distance_to_sl_pct": -2.97, "distance_to_tp_pct": 5.61,
        "distance_to_be_pct": -1.02, "distance_to_tp1_pct": 2.19,
        "strategy_name": "Pullback Short",
        "opened_at": datetime.now().isoformat()
    }
]

trades = [
    {"id": 10, "symbol": "AVAXUSDT", "side": "long",  "pnl": 18.4,  "pnl_percent": 2.1,  "exit_reason": "tp1_partial", "strategy_name": "Pullback Long",  "opened_at": (datetime.now() - timedelta(hours=3)).isoformat(), "closed_at": (datetime.now() - timedelta(hours=2)).isoformat()},
    {"id": 9,  "symbol": "BNBUSDT",  "side": "long",  "pnl": 31.2,  "pnl_percent": 3.5,  "exit_reason": "tp2_target",  "strategy_name": "Pullback Long",  "opened_at": (datetime.now() - timedelta(hours=5)).isoformat(), "closed_at": (datetime.now() - timedelta(hours=4)).isoformat()},
    {"id": 8,  "symbol": "LINKUSDT", "side": "short", "pnl": -12.8, "pnl_percent": -1.4, "exit_reason": "stop_loss",   "strategy_name": "Pullback Short", "opened_at": (datetime.now() - timedelta(hours=7)).isoformat(), "closed_at": (datetime.now() - timedelta(hours=6)).isoformat()},
    {"id": 7,  "symbol": "ARBUSDT",  "side": "long",  "pnl": 8.6,   "pnl_percent": 1.0,  "exit_reason": "tp1_partial", "strategy_name": "Pullback Long",  "opened_at": (datetime.now() - timedelta(hours=9)).isoformat(), "closed_at": (datetime.now() - timedelta(hours=8)).isoformat()},
    {"id": 6,  "symbol": "DOGEUSDT", "side": "long",  "pnl": -6.2,  "pnl_percent": -0.7, "exit_reason": "time_exit",   "strategy_name": "Pullback Long",  "opened_at": (datetime.now() - timedelta(hours=11)).isoformat(), "closed_at": (datetime.now() - timedelta(hours=10)).isoformat()},
]


def build_payload():
    for p in positions:
        d = random.gauss(0, 0.001)
        p["current_price"] = round(p["current_price"] * (1 + d), 2)
        if p["side"] == "long":
            p["pnl"] = round((p["current_price"] - p["entry_price"]) * p["quantity"] * p["leverage"], 2)
        else:
            p["pnl"] = round((p["entry_price"] - p["current_price"]) * p["quantity"] * p["leverage"], 2)
        p["pnl_percent"] = round(p["pnl"] / (p["entry_price"] * p["quantity"]) * 100, 2)

    return {
        "positions": positions,
        "recentTrades": trades,
        "stats": {
            "totalBalance": 10284.0,
            "availableBalance": 6120.0,
            "unrealizedPnl": round(sum(p["pnl"] for p in positions), 2),
            "totalPnl": 284.4,
            "dailyPnl": 47.2,
            "winRate": 63.4,
            "profitFactor": 1.82,
            "totalTrades": 41,
            "winningTrades": 26,
            "losingTrades": 15,
            "consecutiveLosses": 0
        },
        "botStatus": {
            "running": True,
            "mode": "paper",
            "exchange": "okx"
        },
        "timestamp": datetime.now().isoformat()
    }


async def sse_generator(request: Request):
    while True:
        if await request.is_disconnected():
            break
        yield f"data: {json.dumps(build_payload())}\n\n"
        await asyncio.sleep(1.5)


@app.get("/")
def dashboard():
    html_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
    try:
        with open(html_file, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>dashboard.html bulunamadi</h1><p>GitHub repoya dashboard.html yukle</p>", status_code=404)


@app.get("/api/stream")
async def stream(request: Request):
    return StreamingResponse(
        sse_generator(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"}
    )


@app.get("/api/health")
def health():
    return {"ok": True, "timestamp": datetime.now().isoformat()}


@app.get("/api/positions")
def get_positions():
    return JSONResponse(positions)


@app.get("/api/trades")
def get_trades():
    return JSONResponse(trades)


@app.get("/api/settings")
def get_settings():
    return {"trading_mode": "paper", "leverage": 10, "bot_running": True, "exchange": "okx"}


@app.put("/api/settings")
async def update_settings(request: Request):
    return {"ok": True}


@app.post("/api/bot/start")
def start():
    return {"ok": True, "running": True}


@app.post("/api/bot/stop")
def stop():
    return {"ok": True, "running": False}
