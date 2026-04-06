from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio, json, random
from datetime import datetime, timedelta

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

positions = [
    {"id":1,"symbol":"BTCUSDT","side":"long","entry_price":83420,"current_price":84150,"quantity":0.021,"leverage":10,"pnl":153.3,"pnl_percent":1.84,"stop_loss":81200,"take_profit":88000,"candles_held":3,"max_bars":8,"bars_remaining":5,"lot_type":"large","is_adopted":False,"distance_to_sl_pct":-2.31,"distance_to_tp_pct":4.57,"distance_to_be_pct":0.87,"distance_to_tp1_pct":1.01,"strategy_name":"Pullback Long","opened_at":datetime.now().isoformat()},
    {"id":2,"symbol":"ETHUSDT","side":"long","entry_price":3180,"current_price":3210,"quantity":0.55,"leverage":10,"pnl":16.5,"pnl_percent":0.94,"stop_loss":3090,"take_profit":3380,"candles_held":1,"max_bars":8,"bars_remaining":7,"lot_type":"standard","is_adopted":False,"distance_to_sl_pct":-3.74,"distance_to_tp_pct":5.30,"distance_to_be_pct":0.94,"distance_to_tp1_pct":1.56,"strategy_name":"Pullback Long","opened_at":datetime.now().isoformat()},
]

trades = [
    {"id":10,"symbol":"AVAXUSDT","side":"long","pnl":18.4,"pnl_percent":2.1,"exit_reason":"tp1_partial","strategy_name":"Pullback Long","opened_at":(datetime.now()-timedelta(hours=3)).isoformat(),"closed_at":(datetime.now()-timedelta(hours=2)).isoformat()},
    {"id":9,"symbol":"BNBUSDT","side":"long","pnl":31.2,"pnl_percent":3.5,"exit_reason":"tp2_target","strategy_name":"Pullback Long","opened_at":(datetime.now()-timedelta(hours=5)).isoformat(),"closed_at":(datetime.now()-timedelta(hours=4)).isoformat()},
    {"id":8,"symbol":"LINKUSDT","side":"short","pnl":-12.8,"pnl_percent":-1.4,"exit_reason":"stop_loss","strategy_name":"Pullback Short","opened_at":(datetime.now()-timedelta(hours=7)).isoformat(),"closed_at":(datetime.now()-timedelta(hours=6)).isoformat()},
]

def build_payload():
    for p in positions:
        d = random.gauss(0, 0.001)
        p["current_price"] = round(p["current_price"] * (1 + d), 2)
        p["pnl"] = round((p["current_price"] - p["entry_price"]) * p["quantity"] * p["leverage"], 2)
    return {"positions": positions, "recentTrades": trades, "stats": {"totalBalance": 10284.0, "availableBalance": 6120.0, "unrealizedPnl": sum(p["pnl"] for p in pos
