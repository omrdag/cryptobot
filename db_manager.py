"""
DB Manager — PostgreSQL İşlem Geçmişi
=======================================
Tablo oluşturma, işlem kaydetme, okuma.
"""
import os, logging
from datetime import datetime, timezone

log = logging.getLogger("db_manager")

def get_conn():
    import psycopg2
    url = os.getenv("DATABASE_URL", "") or os.getenv("DATABASE_PUBLIC_URL", "")
    if not url:
        return None
    # Railway internal hostname bazen çözülemiyor — public URL'e geç
    if "railway.internal" in url:
        url = os.getenv("DATABASE_PUBLIC_URL", url)
    try:
        conn = psycopg2.connect(url, connect_timeout=5)
        return conn
    except Exception as e:
        log.error(f"DB bağlantı hatası: {e}")
        return None

def init_db():
    """Tabloları oluştur (yoksa)."""
    conn = get_conn()
    if not conn:
        log.warning("DATABASE_URL yok — DB devre dışı")
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id          SERIAL PRIMARY KEY,
                    symbol      VARCHAR(20),
                    side        VARCHAR(10),
                    entry_price NUMERIC(20,8),
                    exit_price  NUMERIC(20,8),
                    stop_loss   NUMERIC(20,8),
                    take_profit NUMERIC(20,8),
                    notional    NUMERIC(20,4),
                    pnl         NUMERIC(20,4),
                    pnl_pct     NUMERIC(10,4),
                    score       INTEGER,
                    strategy    VARCHAR(50),
                    mode        VARCHAR(10),
                    status      VARCHAR(10) DEFAULT 'open',
                    opened_at   TIMESTAMPTZ DEFAULT NOW(),
                    closed_at   TIMESTAMPTZ,
                    exit_reason VARCHAR(50)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id            SERIAL PRIMARY KEY,
                    symbol        VARCHAR(20) UNIQUE,
                    side          VARCHAR(10),
                    entry_price   NUMERIC(20,8),
                    current_price NUMERIC(20,8),
                    stop_loss     NUMERIC(20,8),
                    take_profit   NUMERIC(20,8),
                    notional      NUMERIC(20,4),
                    pnl           NUMERIC(20,4),
                    pnl_pct       NUMERIC(10,4),
                    score         INTEGER,
                    strategy      VARCHAR(50),
                    mode          VARCHAR(10),
                    opened_at     TIMESTAMPTZ DEFAULT NOW(),
                    updated_at    TIMESTAMPTZ DEFAULT NOW()
                )
            """)
        conn.commit()
        log.info("DB tabloları hazır")
        return True
    except Exception as e:
        log.error(f"DB init hatası: {e}")
        return False
    finally:
        conn.close()

def open_trade(symbol, side, entry_price, stop_loss, take_profit, notional, score, strategy, mode):
    """Yeni işlem kaydı aç."""
    conn = get_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trades
                  (symbol, side, entry_price, stop_loss, take_profit, notional, score, strategy, mode, status, opened_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'open', NOW())
                RETURNING id
            """, (symbol, side, entry_price, stop_loss, take_profit, notional, score, strategy, mode))
            trade_id = cur.fetchone()[0]

            # Positions tablosunu güncelle
            cur.execute("""
                INSERT INTO positions
                  (symbol, side, entry_price, current_price, stop_loss, take_profit, notional, pnl, pnl_pct, score, strategy, mode, opened_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,0,0,%s,%s,%s,NOW())
                ON CONFLICT (symbol) DO UPDATE SET
                  side=EXCLUDED.side, entry_price=EXCLUDED.entry_price,
                  stop_loss=EXCLUDED.stop_loss, take_profit=EXCLUDED.take_profit,
                  notional=EXCLUDED.notional, score=EXCLUDED.score,
                  strategy=EXCLUDED.strategy, mode=EXCLUDED.mode,
                  opened_at=NOW(), updated_at=NOW()
            """, (symbol, side, entry_price, entry_price, stop_loss, take_profit, notional, score, strategy, mode))

        conn.commit()
        log.info(f"DB: {symbol} {side} işlemi açıldı (id={trade_id})")
        return trade_id
    except Exception as e:
        log.error(f"DB open_trade hatası: {e}")
        return None
    finally:
        conn.close()

def close_trade(trade_id, symbol, exit_price, pnl, pnl_pct, exit_reason):
    """İşlemi kapat."""
    conn = get_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE trades SET
                  exit_price=%s, pnl=%s, pnl_pct=%s,
                  status='closed', closed_at=NOW(), exit_reason=%s
                WHERE id=%s
            """, (exit_price, pnl, pnl_pct, exit_reason, trade_id))

            cur.execute("DELETE FROM positions WHERE symbol=%s", (symbol,))
        conn.commit()
        log.info(f"DB: {symbol} işlemi kapatıldı (pnl={pnl:+.2f})")
    except Exception as e:
        log.error(f"DB close_trade hatası: {e}")
    finally:
        conn.close()

def update_position(symbol, current_price, pnl, pnl_pct):
    """Pozisyon anlık fiyat güncelle."""
    conn = get_conn()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE positions SET
                  current_price=%s, pnl=%s, pnl_pct=%s, updated_at=NOW()
                WHERE symbol=%s
            """, (current_price, pnl, pnl_pct, symbol))
        conn.commit()
    except Exception as e:
        log.error(f"DB update_position hatası: {e}")
    finally:
        conn.close()

def get_trades(limit=50, mode=None):
    """İşlem geçmişini getir."""
    conn = get_conn()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            if mode:
                cur.execute("""
                    SELECT id,symbol,side,entry_price,exit_price,pnl,pnl_pct,
                           strategy,mode,status,opened_at,closed_at,exit_reason,score
                    FROM trades WHERE mode=%s
                    ORDER BY opened_at DESC LIMIT %s
                """, (mode, limit))
            else:
                cur.execute("""
                    SELECT id,symbol,side,entry_price,exit_price,pnl,pnl_pct,
                           strategy,mode,status,opened_at,closed_at,exit_reason,score
                    FROM trades ORDER BY opened_at DESC LIMIT %s
                """, (limit,))
            rows = cur.fetchall()
            cols = ["id","symbol","side","entry_price","exit_price","pnl","pnl_pct",
                    "strategy","mode","status","opened_at","closed_at","exit_reason","score"]
            return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        log.error(f"DB get_trades hatası: {e}")
        return []
    finally:
        conn.close()

def get_stats(mode=None):
    """Özet istatistikler."""
    conn = get_conn()
    if not conn:
        return {}
    try:
        with conn.cursor() as cur:
            q = "WHERE status='closed'" + (f" AND mode='{mode}'" if mode else "")
            cur.execute(f"""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(pnl),0) as total_pnl,
                    COALESCE(AVG(pnl),0) as avg_pnl
                FROM trades {q}
            """)
            row = cur.fetchone()
            total, wins, losses, total_pnl, avg_pnl = row
            win_rate = (wins/total*100) if total else 0
            return {
                "totalTrades":  int(total or 0),
                "winningTrades":int(wins or 0),
                "losingTrades": int(losses or 0),
                "winRate":      round(float(win_rate), 1),
                "totalPnl":     round(float(total_pnl or 0), 2),
                "avgPnl":       round(float(avg_pnl or 0), 2),
            }
    except Exception as e:
        log.error(f"DB get_stats hatası: {e}")
        return {}
    finally:
        conn.close()
