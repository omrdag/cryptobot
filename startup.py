#!/usr/bin/env python3
"""
Railway Startup — Bot + API Server birlikte çalıştırır
=======================================================
Railway'de tek servis olarak hem bot döngüsünü hem de
dashboard API'sini paralel çalıştırır.

Çalışma şekli:
  Thread 1 → api_server.py  (FastAPI SSE + REST, port=$PORT)
  Thread 2 → main.py bot döngüsü (paper mod)
"""

import os
import sys
import threading
import time
import subprocess
from utils.logger import get_logger

logger = get_logger()


def run_api_server():
    """FastAPI dashboard API'sini başlat."""
    port = os.getenv("PORT", "8080")
    logger.info(f"[STARTUP] API server başlatılıyor → port {port}")
    os.system(f"uvicorn api_server:app --host 0.0.0.0 --port {port}")


def run_bot():
    """Bot döngüsünü başlat — DB hazır olana kadar bekle."""
    logger.info("[STARTUP] Bot döngüsü 8 saniye sonra başlayacak (DB bekleniyor)...")
    time.sleep(8)

    dsn = os.getenv("DATABASE_URL", "")
    if not dsn:
        logger.warning("[STARTUP] DATABASE_URL yok — bot paper modda DB'siz çalışır")

    logger.info("[STARTUP] Bot döngüsü başlatılıyor...")
    try:
        # main.py'yi ayrı process olarak çalıştır
        result = subprocess.run(
            [sys.executable, "main.py", "--strategy", "pullback"],
            check=False
        )
        if result.returncode != 0:
            logger.error(f"[STARTUP] Bot döngüsü hatayla kapandı: {result.returncode}")
    except Exception as e:
        logger.error(f"[STARTUP] Bot başlatma hatası: {e}")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("CryptoBot Railway Startup")
    logger.info(f"PAPER_TRADING: {os.getenv('PAPER_TRADING', 'true')}")
    logger.info(f"EXCHANGE: {os.getenv('EXCHANGE', 'okx')}")
    logger.info(f"LEVERAGE: {os.getenv('LEVERAGE', '10')}")
    logger.info("=" * 60)

    # Bot'u arka planda başlat
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # API server'ı ana thread'de çalıştır (Railway PORT'u buraya bağlar)
    run_api_server()
