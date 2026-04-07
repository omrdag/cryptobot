"""
Exchange Client Factory — Binance + OKX
=========================================
EXCHANGE env değişkenine göre doğru client'ı oluşturur.
Paper modda sadece fiyat verisi çeker, emir göndermez.
"""

import os
from utils.logger import get_logger

logger = get_logger()


class BinanceClient:
    """
    Binance REST API client.
    Paper modda sadece public endpoint kullanır.
    """

    def __init__(self, api_key: str = "", api_secret: str = ""):
        try:
            import ccxt
            self._exchange = ccxt.binance({
                "apiKey":          api_key,
                "secret":          api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "future",  # USDT-M Futures
                },
            })
            self._live = bool(api_key and api_secret)
            logger.info(
                f"Binance client başlatıldı — "
                f"{'LIVE' if self._live else 'PUBLIC (paper mod)'}"
            )
        except ImportError:
            logger.error("ccxt bulunamadı: pip install ccxt")
            raise

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200):
        """OHLCV mum verisi. symbol: 'BTC/USDT' formatında."""
        # Binance futures formatına çevir
        sym = symbol.replace("USDT", "/USDT")
        if not "/" in sym:
            sym = sym + "/USDT"
        try:
            return self._exchange.fetch_ohlcv(sym, timeframe, limit=limit)
        except Exception as e:
            logger.warning(f"[Binance] OHLCV hatası {symbol}: {e}")
            return []

    def fetch_ticker(self, symbol: str):
        """Anlık fiyat."""
        sym = symbol.replace("USDT", "/USDT")
        if not "/" in sym:
            sym = sym + "/USDT"
        try:
            return self._exchange.fetch_ticker(sym)
        except Exception as e:
            logger.warning(f"[Binance] Ticker hatası {symbol}: {e}")
            return None

    def fetch_balance(self) -> dict:
        """Hesap bakiyesi — sadece live modda."""
        if not self._live:
            return {"USDT": {"free": 10000.0, "total": 10000.0}}
        try:
            return self._exchange.fetch_balance({"type": "future"})
        except Exception as e:
            logger.warning(f"[Binance] Bakiye hatası: {e}")
            return {}

    def fetch_positions(self) -> list:
        """Açık pozisyonlar."""
        if not self._live:
            return []
        try:
            return self._exchange.fetch_positions()
        except Exception as e:
            logger.warning(f"[Binance] Pozisyon hatası: {e}")
            return []

    def create_market_order(self, symbol: str, side: str, amount: float, params: dict = None):
        """Market emri — paper modda simüle edilir."""
        if not self._live:
            logger.info(f"[Binance PAPER] {side.upper()} {amount} {symbol} — simüle edildi")
            return {"id": "paper_order", "status": "filled", "filled": amount}
        try:
            sym = symbol.replace("USDT", "/USDT")
            return self._exchange.create_market_order(sym, side, amount, params=params or {})
        except Exception as e:
            logger.error(f"[Binance] Emir hatası {symbol}: {e}")
            return None

    def set_leverage(self, symbol: str, leverage: int, margin_mode: str = "cross") -> bool:
        if not self._live:
            return True
        try:
            sym = symbol.replace("USDT", "/USDT")
            self._exchange.set_leverage(leverage, sym)
            return True
        except Exception as e:
            logger.warning(f"[Binance] Kaldıraç hatası {symbol}: {e}")
            return False

    def is_authenticated(self) -> bool:
        return self._live

    # OKX ile uyumluluk
    _margin_unsupported: set = set()


class OKXClient:
    """OKX REST API client."""

    def __init__(self, api_key: str = "", api_secret: str = "", passphrase: str = ""):
        try:
            import ccxt
            self._exchange = ccxt.okx({
                "apiKey":          api_key,
                "secret":          api_secret,
                "password":        passphrase,
                "enableRateLimit": True,
                "options":         {"defaultType": "swap"},
            })
            self._live = bool(api_key and api_secret and passphrase)
            logger.info(f"OKX client başlatıldı — {'LIVE' if self._live else 'PUBLIC'}")
        except ImportError:
            logger.error("ccxt bulunamadı: pip install ccxt")
            raise

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 200):
        try:
            return self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            logger.warning(f"[OKX] OHLCV hatası {symbol}: {e}")
            return []

    def fetch_ticker(self, symbol: str):
        try:
            return self._exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.warning(f"[OKX] Ticker hatası {symbol}: {e}")
            return None

    def fetch_balance(self) -> dict:
        if not self._live:
            return {}
        try:
            return self._exchange.fetch_balance({"type": "swap"})
        except Exception as e:
            logger.warning(f"[OKX] Bakiye hatası: {e}")
            return {}

    def fetch_positions(self) -> list:
        if not self._live:
            return []
        try:
            return self._exchange.fetch_positions()
        except Exception as e:
            logger.warning(f"[OKX] Pozisyon hatası: {e}")
            return []

    def create_market_order(self, symbol: str, side: str, amount: float, params: dict = None):
        if not self._live:
            return {"id": "paper_order", "status": "filled"}
        try:
            return self._exchange.create_market_order(symbol, side, amount, params=params or {})
        except Exception as e:
            logger.error(f"[OKX] Emir hatası: {e}")
            return None

    def set_leverage(self, symbol: str, leverage: int, margin_mode: str = "cross") -> bool:
        if not self._live:
            return True
        try:
            self._exchange.set_leverage(leverage, symbol, {"mgnMode": margin_mode})
            return True
        except Exception as e:
            logger.warning(f"[OKX] Kaldıraç hatası: {e}")
            return False

    def is_authenticated(self) -> bool:
        return self._live

    _margin_unsupported: set = set()


def create_client(exchange: str = None, **kwargs):
    """
    Exchange'e göre doğru client döndür.
    EXCHANGE env değişkeni önceliklidir.
    """
    exc = (exchange or os.getenv("EXCHANGE", "okx")).lower().strip()

    if exc == "binance":
        key    = kwargs.get("api_key")    or os.getenv("BINANCE_API_KEY",    "")
        secret = kwargs.get("api_secret") or os.getenv("BINANCE_API_SECRET", "")
        logger.info(f"Binance client oluşturuluyor — key: {'var' if key else 'yok'}")
        return BinanceClient(api_key=key, api_secret=secret)

    elif exc == "okx":
        key    = kwargs.get("api_key")    or os.getenv("OKX_API_KEY",    "")
        secret = kwargs.get("api_secret") or os.getenv("OKX_API_SECRET", "")
        pwd    = kwargs.get("passphrase") or os.getenv("OKX_PASSPHRASE", "")
        logger.info(f"OKX client oluşturuluyor — key: {'var' if key else 'yok'}")
        return OKXClient(api_key=key, api_secret=secret, passphrase=pwd)

    else:
        logger.warning(f"Bilinmeyen borsa '{exc}', OKX kullanılıyor")
        return OKXClient()
