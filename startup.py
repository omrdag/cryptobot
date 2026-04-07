#!/usr/bin/env python3
"""
Railway Startup — Bot + API Server
"""
import os
import sys
import threading
import time
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("startup")


def run_bot():
    log.info("Bot 8 saniye sonra başlıyor...")
    time.sleep(8)
    log.info("Bot döngüsü başlatılıyor (paper mod)...")
    try:
        subprocess.run([sys.executable, "main.py", "--strategy", "pullback"], check=False)
    except Exception as e:
        log.error(f"Bot hatası: {e}")


def run_api():
    port = os.getenv("PORT", "8080")
    log.info(f"API server başlatılıyor → port {port}")
    os.execvp("uvicorn", ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", port])


if __name__ == "__main__":
    log.info(f"PAPER_TRADING={os.getenv('PAPER_TRADING','true')} | EXCHANGE={os.getenv('EXCHANGE','okx')}")
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
    run_api()
