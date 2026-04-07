"""
Bot API Server — FastAPI
=========================
Next.js dashboard için SSE + REST endpoint'leri sağlar.
Python trading botunu okuyup veriyi dashboard'a iletir.

Endpoint'ler:
  GET /api/stream          → SSE gerçek zamanlı veri akışı
  GET /api/positions       → Açık pozisyonlar
  GET /api/trades          → Trade geçmişi
  GET /api/stats           → Performans metrikleri
  GET /api/settings        → Bot ayarları
  PUT /api/settings        → Bot ayarlarını güncelle
  POST /api/bot/start      → Bot başlat
  POST /api/bot/stop       → Bot durdur
  GET /api/health          → Sağlık kontrolü
"""

import os
import json
import time
import asyncio
import threading
from datetime import datetime, date, timedelta
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

# ── Bot state (main.py bot thread ile paylaşılan global state) ────────────────
# main.py'deki bot_state dict'ini import ediyoruz
try:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    import config
    from db_writer import create_db_writer
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False

# ── SSE client yönetimi ────────────────────────────────────────────────────────
_sse_clients: set = set()
_sse_lock = threading.Lock()
_last_payload: dict = {}


def _build_payload() -> dict:
    """
    Veritabanından anlık durumu çekip SSE payload'ı oluşturur.
    """
    if not DB_AVAILABLE:
        return {"error": "DB bağlantısı yok", "timestamp": datetime.now().isoformat()}

    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        return {"error": "DATABASE_URL tanımsız", "timestamp": datetime.now().isoformat()}

    try:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(dsn)
        conn.autocommit = True

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Açık pozisyonlar
            cur.execute("""
                SELECT id, symbol, side, entry_price, current_price,
                       quantity, leverage, pnl, pnl_percent,
                       stop_loss, take_profit, candles_held, max_bars,
                       GREATEST(0, max_bars - candles_held) as bars_remaining,
                       lot_type, is_adopted, distance_to_sl_pct,
                       distance_to_tp_pct, distance_to_be_pct,
                       distance_to_tp1_pct, strategy_name, opened_at
                FROM positions WHERE status = 'open'
                ORDER BY opened_at DESC
            """)
            positions = [dict(r) for r in cur.fetchall()]

            # Son 30 trade
            cur.execute("""
                SELECT id, symbol, side, pnl, pnl_percent,
                       exit_reason, strategy_name, closed_at, opened_at
                FROM trades
                ORDER BY closed_at DESC LIMIT 30
            """)
            trades = [dict(r) for r in cur.fetchall()]

            # İstatistikler
            cur.execute("""
                SELECT
                  COALESCE(SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) as wins,
                  COALESCE(SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END), 0) as losses,
                  COALESCE(SUM(pnl), 0) as total_pnl,
                  COALESCE(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END), 0) as gross_profit,
                  COALESCE(SUM(CASE WHEN pnl < 0 THEN ABS(pnl) ELSE 0 END), 0) as gross_loss,
                  COUNT(*) as total
                FROM trades
            """)
            agg = dict(cur.fetchone() or {})

            # Bugünün PnL
            cur.execute("""
                SELECT COALESCE(SUM(pnl), 0) as daily_pnl
                FROM trades
                WHERE closed_at >= CURRENT_DATE
            """)
            daily = cur.fetchone()

            # Bakiye
            cur.execute("""
                SELECT total_balance, available_balance
                FROM balances ORDER BY recorded_at DESC LIMIT 1
            """)
            bal_row = cur.fetchone()

            # Bot ayarları
            cur.execute("""
                SELECT trading_mode, bot_running, exchange,
                       max_consecutive_losses
                FROM settings LIMIT 1
            """)
            s = cur.fetchone() or {}

            # Art arda kayıp (son trade'lerden)
            cur.execute("""
                SELECT pnl FROM trades
                ORDER BY closed_at DESC LIMIT 10
            """)
            recent_pnls = [r["pnl"] for r in cur.fetchall()]
            consec = 0
            for p in recent_pnls:
                if p < 0:
                    consec += 1
                else:
                    break

        conn.close()

        wins   = int(agg.get("wins", 0))
        losses = int(agg.get("losses", 0))
        total  = wins + losses
        gross_profit = float(agg.get("gross_profit", 0))
        gross_loss   = float(agg.get("gross_loss", 0))

        total_balance = float(bal_row["total_balance"]) if bal_row else 0.0
        avail_balance = float(bal_row["available_balance"]) if bal_row else 0.0
        unrealized    = sum(float(p.get("pnl") or 0) for p in positions)

        # Tarih/saat alanlarını string'e çevir
        def serialize(obj):
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            return obj

        positions_clean = [{k: serialize(v) for k, v in p.items()} for p in positions]
        trades_clean    = [{k: serialize(v) for k, v in t.items()} for t in trades]

        return {
            "positions": positions_clean,
            "recentTrades": trades_clean,
            "stats": {
                "totalBalance":       total_balance,
                "availableBalance":   avail_balance,
                "unrealizedPnl":      unrealized,
                "totalPnl":           float(agg.get("total_pnl", 0)),
                "dailyPnl":           float(daily["daily_pnl"]) if daily else 0.0,
                "winRate":            (wins / total * 100) if total > 0 else 0.0,
                "profitFactor":       (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0),
                "totalTrades":        total,
                "winningTrades":      wins,
                "losingTrades":       losses,
                "consecutiveLosses":  consec,
            },
            "botStatus": {
                "running":  bool(s.get("bot_running", False)),
                "mode":     str(s.get("trading_mode", "paper")),
                "exchange": str(s.get("exchange", "okx")),
            },
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# ── Background payload updater ─────────────────────────────────────────────────

def _payload_updater_loop():
    """Her 2 saniyede payload'ı günceller."""
    global _last_payload
    while True:
        try:
            _last_payload = _build_payload()
        except Exception:
            pass
        time.sleep(2)


# ── FastAPI app ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Background payload updater başlat
    t = threading.Thread(target=_payload_updater_loop, daemon=True)
    t.start()
    yield


app = FastAPI(title="CryptoBot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── SSE Endpoint ───────────────────────────────────────────────────────────────

async def sse_generator(request: Request) -> AsyncGenerator[str, None]:
    """SSE veri akışı — her 1.5 saniyede yeni veri."""
    yield f"data: {json.dumps(_last_payload)}\n\n"

    while True:
        if await request.is_disconnected():
            break
        try:
            payload_str = json.dumps(_last_payload)
            yield f"data: {payload_str}\n\n"
        except Exception:
            break
        await asyncio.sleep(1.5)


@app.get("/api/stream")
async def stream(request: Request):
    return StreamingResponse(
        sse_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"ok": True, "timestamp": datetime.now().isoformat()}


@app.get("/api/positions")
def get_positions():
    return JSONResponse(_last_payload.get("positions", []))


@app.get("/api/trades")
def get_trades():
    return JSONResponse(_last_payload.get("recentTrades", []))


@app.get("/api/stats")
def get_stats():
    return JSONResponse(_last_payload.get("stats", {}))


@app.get("/api/settings")
def get_settings():
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise HTTPException(500, "DATABASE_URL yok")
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(dsn)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM settings LIMIT 1")
            row = cur.fetchone()
        conn.close()
        return JSONResponse(dict(row) if row else {})
    except Exception as e:
        raise HTTPException(500, str(e))


@app.put("/api/settings")
async def update_settings(request: Request):
    body = await request.json()
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise HTTPException(500, "DATABASE_URL yok")
    try:
        import psycopg2
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        allowed = {
            "trading_mode", "leverage", "max_open_positions",
            "max_consecutive_losses", "max_daily_loss_pct",
            "paper_trading", "trading_pairs",
        }
        updates = {k: v for k, v in body.items() if k in allowed}
        if not updates:
            raise HTTPException(400, "Geçersiz alan")
        set_clause = ", ".join(f"{k} = %s" for k in updates)
        with conn.cursor() as cur:
            cur.execute(f"UPDATE settings SET {set_clause} WHERE id = (SELECT id FROM settings LIMIT 1)",
                        list(updates.values()))
        conn.close()
        return {"ok": True, "updated": list(updates.keys())}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/bot/start")
def bot_start():
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise HTTPException(500, "DATABASE_URL yok")
    try:
        import psycopg2
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("UPDATE settings SET bot_running = TRUE WHERE id = (SELECT id FROM settings LIMIT 1)")
        conn.close()
        return {"ok": True, "running": True}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/bot/stop")
def bot_stop():
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        raise HTTPException(500, "DATABASE_URL yok")
    try:
        import psycopg2
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("UPDATE settings SET bot_running = FALSE WHERE id = (SELECT id FROM settings LIMIT 1)")
        conn.close()
        return {"ok": True, "running": False}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Dev entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("API_PORT", "8080"))
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False)
