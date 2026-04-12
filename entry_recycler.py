"""
Entry Recycler Engine
=====================
Pozisyon kapanınca kör giriş yapmak yerine:
  1. Cooldown süresi bekle (kâr=2dk, SL=10dk)
  2. Momentum/hacim hâlâ uygunsa rescan yap
  3. Skor yeterliyse yeniden giriş planla

Mevcut sisteme dokunmaz — bot_engine.py'den
import edilerek check_exits() ve bot_loop() içine
minimal patch ile entegre olur.
"""

import os
import time
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime, timezone


# ── Ayarlar ──────────────────────────────────────────────────────────────────

COOLDOWN_WIN_SEC   = int(os.getenv("RECYCLE_COOLDOWN_WIN",  "120"))  # Kârlı kapanış → 2dk
COOLDOWN_LOSS_SEC  = int(os.getenv("RECYCLE_COOLDOWN_LOSS", "600"))  # SL → 10dk
RE_ENTRY_BOOST     = int(os.getenv("RE_ENTRY_BOOST",        "1"))    # Kârlı kapanış sonrası +1 puan
MAX_RECYCLES       = int(os.getenv("MAX_RECYCLES_PER_SYM",  "3"))    # Aynı coinde max tekrar giriş
RECYCLE_ENABLED    = os.getenv("RECYCLE_ENABLED", "true").lower() == "true"


# ── Veri Yapıları ─────────────────────────────────────────────────────────────

@dataclass
class ClosedTrade:
    """Kapanan işlem kaydı."""
    symbol:       str
    inst_id:      str
    side:         str
    entry_price:  float
    close_price:  float
    pnl_usdt:     float
    close_reason: str   # "TP", "SL", "MANUAL", "PROFIT_LOCK"
    close_time:   float = field(default_factory=time.time)

    @property
    def was_profitable(self) -> bool:
        return self.pnl_usdt > 0

    @property
    def cooldown_seconds(self) -> int:
        return COOLDOWN_WIN_SEC if self.was_profitable else COOLDOWN_LOSS_SEC


@dataclass
class RecycleItem:
    """Yeniden giriş kuyruğu öğesi."""
    trade:           ClosedTrade
    recycle_count:   int   = 0
    rescan_at:       float = 0.0   # Unix timestamp — ne zaman rescan yapılacak
    score_boost:     int   = 0     # Kârlı kapanış bonusu
    attempted:       bool  = False
    re_entered:      bool  = False

    def is_ready(self) -> bool:
        return time.time() >= self.rescan_at and not self.attempted

    def mark_attempted(self):
        self.attempted = True

    def reset_for_next_cycle(self):
        """Tekrar deneme için sıfırla."""
        self.attempted   = False
        self.rescan_at   = time.time() + COOLDOWN_WIN_SEC
        self.recycle_count += 1


# ── Entry Recycler ────────────────────────────────────────────────────────────

class EntryRecycler:
    """
    Pozisyon kapanınca cooldown + rescan + re-entry yönetir.
    Thread-safe, bot_engine'den bağımsız çalışır.
    """

    def __init__(self):
        self._lock       = threading.Lock()
        self._queue:     Dict[str, RecycleItem] = {}   # sym → RecycleItem
        self._history:   Dict[str, ClosedTrade] = {}   # sym → son kapanan işlem
        self._recycle_counts: Dict[str, int]    = {}   # sym → toplam recycle sayısı

    def record_close(
        self,
        symbol:       str,
        inst_id:      str,
        side:         str,
        entry_price:  float,
        close_price:  float,
        pnl_usdt:     float,
        close_reason: str = "UNKNOWN",
    ) -> None:
        """
        Pozisyon kapanınca çağır.
        Cooldown süresini hesaplar ve kuyruğa ekler.
        """
        if not RECYCLE_ENABLED:
            return

        trade = ClosedTrade(
            symbol       = symbol,
            inst_id      = inst_id,
            side         = side,
            entry_price  = entry_price,
            close_price  = close_price,
            pnl_usdt     = pnl_usdt,
            close_reason = close_reason,
        )

        # Score boost: kârlı kapanış + yapı bozulmadıysa
        boost = RE_ENTRY_BOOST if trade.was_profitable else 0

        item = RecycleItem(
            trade        = trade,
            recycle_count = self._recycle_counts.get(symbol, 0),
            rescan_at    = time.time() + trade.cooldown_seconds,
            score_boost  = boost,
        )

        with self._lock:
            self._queue[symbol]   = item
            self._history[symbol] = trade

        direction = "kâr" if trade.was_profitable else "zarar"
        boost_txt = f" | +{boost} puan boost" if boost else ""
        _recycler_log(
            f"[RECYCLE] {symbol} kapandı ({direction}: ${pnl_usdt:+.2f}) | "
            f"Cooldown: {trade.cooldown_seconds}s | "
            f"Rescan: {datetime.fromtimestamp(item.rescan_at).strftime('%H:%M:%S')}"
            f"{boost_txt}"
        )

    def get_ready_items(self) -> list:
        """
        Cooldown süresi dolmuş ve rescan'a hazır öğeleri döndür.
        bot_loop içinde her döngüde çağrılır.
        """
        ready = []
        with self._lock:
            for sym, item in list(self._queue.items()):
                if item.is_ready():
                    # Max recycle kontrolü
                    total = self._recycle_counts.get(sym, 0)
                    if total >= MAX_RECYCLES:
                        _recycler_log(
                            f"[RECYCLE] {sym} max tekrar ({MAX_RECYCLES}) aşıldı — atlanıyor"
                        )
                        del self._queue[sym]
                        continue
                    ready.append(item)
        return ready

    def mark_re_entered(self, symbol: str, success: bool) -> None:
        """Yeniden giriş denemesi sonucunu kaydet."""
        with self._lock:
            if symbol not in self._queue:
                return
            item = self._queue[symbol]
            item.mark_attempted()

            if success:
                item.re_entered = True
                self._recycle_counts[symbol] = self._recycle_counts.get(symbol, 0) + 1
                _recycler_log(f"[RECYCLE] {symbol} yeniden girişi başarılı ✅")
                del self._queue[symbol]
            else:
                # Başarısız — bir sonraki döngüde tekrar dene mi?
                if item.recycle_count < MAX_RECYCLES - 1:
                    item.reset_for_next_cycle()
                    _recycler_log(f"[RECYCLE] {symbol} yeniden giriş başarısız — tekrar denenecek")
                else:
                    _recycler_log(f"[RECYCLE] {symbol} kuyruktan çıkarıldı")
                    del self._queue[symbol]

    def is_in_cooldown(self, symbol: str) -> bool:
        """Bu coin cooldown'da mı? (Yeni giriş engeli için)"""
        with self._lock:
            if symbol not in self._queue:
                return False
            item = self._queue[symbol]
            return not item.is_ready()

    def get_score_boost(self, symbol: str) -> int:
        """Bu coin için score boost değeri."""
        with self._lock:
            if symbol in self._queue:
                return self._queue[symbol].score_boost
            return 0

    def get_status(self) -> dict:
        """Dashboard için durum özeti."""
        with self._lock:
            return {
                "queue_size":    len(self._queue),
                "in_cooldown":   [
                    sym for sym, item in self._queue.items()
                    if not item.is_ready()
                ],
                "ready_rescan":  [
                    sym for sym, item in self._queue.items()
                    if item.is_ready()
                ],
                "recycle_counts": dict(self._recycle_counts),
            }

    def clear_symbol(self, symbol: str) -> None:
        """Belirli bir coini kuyruktan temizle (manuel pozisyon açılırsa)."""
        with self._lock:
            self._queue.pop(symbol, None)
            self._recycle_counts.pop(symbol, None)


# ── Logging ───────────────────────────────────────────────────────────────────

def _recycler_log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── Global Instance ───────────────────────────────────────────────────────────
# bot_engine.py tarafından import edilir

_recycler = EntryRecycler()


def get_recycler() -> EntryRecycler:
    return _recycler
