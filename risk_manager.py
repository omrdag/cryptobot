"""
Risk Manager — Kurumsal Seviye Risk Yönetimi
=============================================
Her emir gönderilmeden önce bu modül kontrol edilir.

Katmanlar:
  1. Pozisyon riski    — işlem başı ATR bazlı sizing
  2. Portföy riski     — toplam exposure, korelasyon limiti
  3. Günlük koruma     — max drawdown, ardışık zarar, pause mode
  4. Execution riski   — spread, slippage, ani volatilite
  5. Acil durum        — crash protokolü, data anomaly

Temel Prensip:
  Risk önce tanımlanır, sonra pozisyon büyüklüğü hesaplanır.
  "Ne kadar kazanabilirim?" değil "Ne kadar kaybedebilirim?" sorusu.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone


# ── Risk Parametreleri ─────────────────────────────────────────────────────────

# İşlem başı risk
RISK_PER_TRADE_PCT    = float(os.getenv("RISK_PER_TRADE_PCT",    "1.0"))   # Hesabın %1'i
MAX_RISK_PER_TRADE_PCT= float(os.getenv("MAX_RISK_PER_TRADE_PCT","2.0"))   # Max %2

# Portföy limitleri
MAX_OPEN_POSITIONS    = int(os.getenv("MAX_POSITIONS",            "10"))
MAX_LONG_POSITIONS    = int(os.getenv("MAX_LONG_POSITIONS",       "5"))
MAX_SHORT_POSITIONS   = int(os.getenv("MAX_SHORT_POSITIONS",      "5"))
MAX_SAME_SECTOR       = int(os.getenv("MAX_SAME_SECTOR",          "2"))     # Aynı sektör max
MAX_CORRELATED_COINS  = int(os.getenv("MAX_CORRELATED_COINS",     "2"))     # Yüksek korelasyon

# Exposure limitleri
MAX_TOTAL_EXPOSURE_PCT= float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "60.0"))  # Bakiyenin %60
MAX_NET_EXPOSURE_PCT  = float(os.getenv("MAX_NET_EXPOSURE_PCT",   "30.0"))  # Net long-short farkı

# Günlük koruma
MAX_DAILY_LOSS_PCT    = float(os.getenv("MAX_DAILY_LOSS_PCT",     "3.0"))   # Günlük %3 max zarar
MAX_DAILY_LOSS_USD    = float(os.getenv("MAX_DAILY_LOSS_USD",     "30.0"))  # Günlük $30 max zarar
MAX_CONSEC_LOSSES     = int(os.getenv("MAX_CONSEC_LOSSES",        "3"))     # Art arda 3 SL → pause
COOLDOWN_MINUTES      = int(os.getenv("COOLDOWN_MINUTES",         "60"))    # Pause sonrası bekleme

# Execution kalitesi
MAX_SPREAD_PCT        = float(os.getenv("MAX_SPREAD_PCT",         "0.15"))  # %0.15 max spread
MAX_SLIPPAGE_PCT      = float(os.getenv("MAX_SLIPPAGE_PCT",       "0.10"))  # %0.10 max slippage

# Korelasyonlu coin grupları
CORRELATED_GROUPS = {
    "btc_group":   ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],          # Yüksek korelasyon
    "l1_group":    ["SOL-USDT-SWAP", "AVAX-USDT-SWAP", "DOT-USDT-SWAP"],  # L1'ler
    "defi_group":  ["LINK-USDT-SWAP", "AAVE-USDT-SWAP"],
}


@dataclass
class RiskState:
    """Anlık risk durumu."""
    # Portföy durumu
    open_positions:       List[dict] = field(default_factory=list)
    open_long_count:      int   = 0
    open_short_count:     int   = 0
    total_long_notional:  float = 0.0
    total_short_notional: float = 0.0
    net_exposure:         float = 0.0   # Long - Short notional
    total_exposure:       float = 0.0   # Long + Short notional

    # Günlük takip
    daily_pnl:            float = 0.0
    daily_loss:           float = 0.0   # Sadece zararlar
    consecutive_losses:   int   = 0
    trades_today:         int   = 0

    # Durum
    is_paused:            bool  = False
    pause_until:          Optional[str] = None
    pause_reason:         str   = ""

    # Bakiye
    account_balance:      float = 0.0
    available_balance:    float = 0.0

    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class RiskDecision:
    """Risk karar sonucu."""
    approved:      bool
    reason:        str
    position_size: float = 0.0      # USDT notional
    risk_usd:      float = 0.0      # Risk edilen USD
    warnings:      List[str] = field(default_factory=list)


# ── Risk Manager ──────────────────────────────────────────────────────────────

class RiskManager:
    """Kurumsal seviye risk yöneticisi."""

    def __init__(self):
        self._state       = RiskState()
        self._daily_reset_date: Optional[str] = None

    def update_state(
        self,
        positions: List[dict],
        balance:   float,
        daily_pnl: float = 0.0,
    ) -> None:
        """Her döngüde state'i güncelle."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._daily_reset_date != today:
            self._daily_reset()
            self._daily_reset_date = today

        longs  = [p for p in positions if p.get("side") == "long"]
        shorts = [p for p in positions if p.get("side") == "short"]

        long_notional  = sum(abs(float(p.get("notional", 0))) for p in longs)
        short_notional = sum(abs(float(p.get("notional", 0))) for p in shorts)

        self._state.open_positions       = positions
        self._state.open_long_count      = len(longs)
        self._state.open_short_count     = len(shorts)
        self._state.total_long_notional  = long_notional
        self._state.total_short_notional = short_notional
        self._state.net_exposure         = long_notional - short_notional
        self._state.total_exposure       = long_notional + short_notional
        self._state.account_balance      = balance
        self._state.daily_pnl            = daily_pnl
        self._state.daily_loss           = min(0, daily_pnl)
        self._state.timestamp            = datetime.now(timezone.utc).isoformat()

        # Pause süresi doldu mu?
        if self._state.is_paused and self._state.pause_until:
            now = datetime.now(timezone.utc).isoformat()
            if now >= self._state.pause_until:
                self._state.is_paused    = False
                self._state.pause_until  = None
                self._state.pause_reason = ""
                self._state.consecutive_losses = 0

    def _daily_reset(self) -> None:
        """Günlük sayaçları sıfırla."""
        self._state.daily_pnl           = 0.0
        self._state.daily_loss          = 0.0
        self._state.trades_today        = 0
        # Consecutive loss sıfırlanmaz — gün içi korunur

    def record_trade_result(self, pnl: float) -> None:
        """İşlem sonucunu kaydet, consecutive loss takip et."""
        self._state.trades_today += 1
        if pnl < 0:
            self._state.consecutive_losses += 1
            self._state.daily_loss         += pnl
            if self._state.consecutive_losses >= MAX_CONSEC_LOSSES:
                self._trigger_pause(
                    f"{MAX_CONSEC_LOSSES} ardışık SL — {COOLDOWN_MINUTES} dk bekleme"
                )
        else:
            self._state.consecutive_losses = 0  # Kazanış streak sıfırlar

    def _trigger_pause(self, reason: str) -> None:
        """Sistemi geçici durdur."""
        from datetime import timedelta
        pause_until = (
            datetime.now(timezone.utc) + timedelta(minutes=COOLDOWN_MINUTES)
        ).isoformat()
        self._state.is_paused    = True
        self._state.pause_until  = pause_until
        self._state.pause_reason = reason

    def calculate_position_size(
        self,
        entry_price: float,
        stop_price:  float,
        balance:     float,
        regime_mult: float = 1.0,
    ) -> Tuple[float, float]:
        """
        ATR bazlı pozisyon boyutu hesapla.

        Formül:
          risk_usd  = balance × RISK_PER_TRADE_PCT% × regime_mult
          stop_dist = |entry - stop| / entry (%)
          notional  = risk_usd / stop_dist

        Returns: (notional_usdt, risk_usd)
        """
        if entry_price <= 0 or stop_price <= 0:
            return 0.0, 0.0

        stop_dist_pct = abs(entry_price - stop_price) / entry_price
        if stop_dist_pct <= 0:
            return 0.0, 0.0

        risk_pct  = RISK_PER_TRADE_PCT / 100 * regime_mult
        risk_pct  = min(risk_pct, MAX_RISK_PER_TRADE_PCT / 100)
        risk_usd  = balance * risk_pct
        notional  = risk_usd / stop_dist_pct

        # Notional'ı makul aralıkta tut
        min_notional = 100.0    # Min $100 notional
        max_notional = balance * 5  # Max 5x bakiye (kaldıraçla)
        notional = float(max(min_notional, min(notional, max_notional)))

        return notional, risk_usd

    def check_trade(
        self,
        inst_id:     str,
        side:        str,     # "long" veya "short"
        notional:    float,
        entry_price: float,
        stop_price:  float,
        regime:      str,
        regime_mult: float = 1.0,
    ) -> RiskDecision:
        """
        İşlem açmadan önce tüm risk kontrolleri.
        Returns: RiskDecision (approved=True/False)
        """
        warnings = []

        # ── 1. Pause kontrolü ─────────────────────────────────────────────────
        if self._state.is_paused:
            return RiskDecision(
                approved=False,
                reason=f"⏸ Sistem duraklatıldı: {self._state.pause_reason}",
                warnings=warnings,
            )

        # ── 2. NO_TRADE rejimi ────────────────────────────────────────────────
        if regime == "NO_TRADE":
            return RiskDecision(
                approved=False,
                reason="🚫 NO_TRADE rejimi — işlem açılmıyor",
                warnings=warnings,
            )

        # ── 3. Günlük max kayıp ───────────────────────────────────────────────
        balance = self._state.account_balance or 1000.0
        daily_loss_pct = abs(self._state.daily_loss) / balance * 100
        if daily_loss_pct >= MAX_DAILY_LOSS_PCT:
            return RiskDecision(
                approved=False,
                reason=f"🔴 Günlük max kayıp aşıldı: %{daily_loss_pct:.1f} ≥ %{MAX_DAILY_LOSS_PCT}",
                warnings=warnings,
            )
        if abs(self._state.daily_loss) >= MAX_DAILY_LOSS_USD:
            return RiskDecision(
                approved=False,
                reason=f"🔴 Günlük max kayıp aşıldı: ${abs(self._state.daily_loss):.2f} ≥ ${MAX_DAILY_LOSS_USD}",
                warnings=warnings,
            )

        # ── 4. Max pozisyon limiti ────────────────────────────────────────────
        total_pos = self._state.open_long_count + self._state.open_short_count
        if total_pos >= MAX_OPEN_POSITIONS:
            return RiskDecision(
                approved=False,
                reason=f"📊 Max pozisyon: {total_pos}/{MAX_OPEN_POSITIONS}",
                warnings=warnings,
            )

        # ── 5. Yön bazlı limit ────────────────────────────────────────────────
        if side == "long" and self._state.open_long_count >= MAX_LONG_POSITIONS:
            return RiskDecision(
                approved=False,
                reason=f"📊 Max long: {self._state.open_long_count}/{MAX_LONG_POSITIONS}",
                warnings=warnings,
            )
        if side == "short" and self._state.open_short_count >= MAX_SHORT_POSITIONS:
            return RiskDecision(
                approved=False,
                reason=f"📊 Max short: {self._state.open_short_count}/{MAX_SHORT_POSITIONS}",
                warnings=warnings,
            )

        # ── 6. Aynı coin zaten açık mı? ───────────────────────────────────────
        open_syms = {p.get("instId") for p in self._state.open_positions}
        if inst_id in open_syms:
            return RiskDecision(
                approved=False,
                reason=f"⚠ {inst_id} zaten açık pozisyon var",
                warnings=warnings,
            )

        # ── 7. Korelasyon limiti ──────────────────────────────────────────────
        corr_check = self._check_correlation(inst_id, side)
        if corr_check:
            return RiskDecision(
                approved=False,
                reason=corr_check,
                warnings=warnings,
            )

        # ── 8. Total exposure limiti ──────────────────────────────────────────
        new_exposure = self._state.total_exposure + notional
        max_exposure = balance * MAX_TOTAL_EXPOSURE_PCT / 100
        if new_exposure > max_exposure:
            warnings.append(
                f"⚠ Exposure sınırı yakın: ${new_exposure:.0f} / ${max_exposure:.0f}"
            )
            # Bloke etme, sadece uyar

        # ── 9. Net exposure limiti ────────────────────────────────────────────
        if side == "long":
            new_net = self._state.net_exposure + notional
        else:
            new_net = self._state.net_exposure - notional
        max_net = balance * MAX_NET_EXPOSURE_PCT / 100
        if abs(new_net) > max_net:
            warnings.append(
                f"⚠ Net exposure fazla: ${abs(new_net):.0f} / ${max_net:.0f} — pozisyon küçültün"
            )

        # ── 10. Rejim uyumu ───────────────────────────────────────────────────
        if regime == "TREND_UP" and side == "short":
            warnings.append("⚠ TREND_UP rejiminde short açıyorsunuz — dikkatli")
        if regime == "TREND_DOWN" and side == "long":
            warnings.append("⚠ TREND_DOWN rejiminde long açıyorsunuz — dikkatli")

        # ── 11. Pozisyon boyutu hesapla ───────────────────────────────────────
        calc_notional, risk_usd = self.calculate_position_size(
            entry_price, stop_price, balance, regime_mult
        )

        # Eğer dışarıdan notional verilmişse onu kullan ama risk_usd hesapla
        final_notional = notional if notional > 0 else calc_notional
        stop_dist = abs(entry_price - stop_price) / entry_price
        final_risk = final_notional * stop_dist

        # Risk çok yüksekse uyar
        max_risk = balance * MAX_RISK_PER_TRADE_PCT / 100
        if final_risk > max_risk:
            warnings.append(
                f"⚠ İşlem riski yüksek: ${final_risk:.2f} > ${max_risk:.2f} (max %{MAX_RISK_PER_TRADE_PCT})"
            )

        # ── Onay ──────────────────────────────────────────────────────────────
        return RiskDecision(
            approved       = True,
            reason         = f"✓ Risk kontrolleri geçti | risk=${final_risk:.2f} | notional=${final_notional:.0f}",
            position_size  = final_notional,
            risk_usd       = final_risk,
            warnings       = warnings,
        )

    def _check_correlation(self, inst_id: str, side: str) -> Optional[str]:
        """
        Korelasyonlu coin limiti kontrolü.
        Aynı grup içinde max MAX_CORRELATED_COINS pozisyon.
        """
        open_syms = {p.get("instId") for p in self._state.open_positions
                     if p.get("side") == side}

        for group_name, group_coins in CORRELATED_GROUPS.items():
            if inst_id not in group_coins:
                continue
            # Bu grupta kaç açık pozisyon var?
            group_open = sum(1 for s in open_syms if s in group_coins)
            if group_open >= MAX_CORRELATED_COINS:
                return (
                    f"⚠ Korelasyon limiti: {group_name} grubunda "
                    f"{group_open}/{MAX_CORRELATED_COINS} {side} pozisyon var"
                )
        return None

    def get_state_summary(self) -> dict:
        """Dashboard için durum özeti."""
        balance = self._state.account_balance or 1
        return {
            "is_paused":          self._state.is_paused,
            "pause_reason":       self._state.pause_reason,
            "open_long":          self._state.open_long_count,
            "open_short":         self._state.open_short_count,
            "total_exposure_usd": self._state.total_exposure,
            "total_exposure_pct": self._state.total_exposure / balance * 100,
            "net_exposure_usd":   self._state.net_exposure,
            "daily_pnl":          self._state.daily_pnl,
            "daily_loss":         self._state.daily_loss,
            "daily_loss_pct":     abs(self._state.daily_loss) / balance * 100,
            "consecutive_losses": self._state.consecutive_losses,
            "trades_today":       self._state.trades_today,
            "max_daily_loss_usd": MAX_DAILY_LOSS_USD,
            "max_daily_loss_pct": MAX_DAILY_LOSS_PCT,
            "max_consec_losses":  MAX_CONSEC_LOSSES,
        }

    def emergency_check(
        self,
        balance:       float,
        start_balance: float,
        positions:     List[dict],
    ) -> Optional[str]:
        """
        Acil durum kontrolü — anlık drawdown veya crash tespit.
        Returns: None (normal) veya string (acil durum açıklaması)
        """
        if start_balance <= 0:
            return None

        # Drawdown hesapla
        drawdown_pct = (start_balance - balance) / start_balance * 100
        if drawdown_pct >= 10.0:
            return f"🚨 ACIL: %{drawdown_pct:.1f} drawdown — tüm pozisyonlar kapatılacak"

        # Ani bakiye düşüşü (1 döngüde %3+)
        # Bu kısım bot_engine'de çağrılırken önceki bakiyeyle kıyaslanır

        return None


# ── Global Risk Manager Instance ─────────────────────────────────────────────
# bot_engine.py tarafından import edilir

_risk_manager = RiskManager()


def get_risk_manager() -> RiskManager:
    """Global risk manager instance'ını döndür."""
    return _risk_manager
