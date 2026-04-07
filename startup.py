#!/usr/bin/env python3
"""
Railway Startup — Mock API + Dashboard
"""
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("startup")

if __name__ == "__main__":
    port = os.getenv("PORT", "8080")
    log.info(f"CryptoBot başlatılıyor → port {port}")
    log.info(f"PAPER_TRADING={os.getenv('PAPER_TRADING','true')} | EXCHANGE={os.getenv('EXCHANGE','okx')}")
    os.execvp("uvicorn", ["uvicorn", "mock_api:app", "--host", "0.0.0.0", "--port", port])
