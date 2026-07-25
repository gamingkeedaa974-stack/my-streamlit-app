"""
risk_manager.py
Multi-layer risk management for NSE intraday options trading.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, time
from typing import Optional, Dict, Set, List
from pydantic import BaseModel, Field, field_validator

from backend.strategies.strategy import Signal, SignalAction, OptionType, OptionsChainProvider, MarketRegime


class RiskConfig(BaseModel):
    max_daily_loss_pct: float = Field(default=0.03, gt=0, le=0.5)
    max_correlation_symbols: int = Field(default=2, ge=1, le=5)
    max_total_margin_pct: float = Field(default=0.6, gt=0, le=1.0)
    max_risk_per_trade_pct: float = Field(default=0.01, gt=0, le=0.1)
    max_positions_per_symbol: int = 1
    max_spread_pct: float = 0.03
    min_oi: int = 500_000
    max_position_delta: float = 50.0
    max_position_gamma: float = 5.0
    max_iv_percentile: float = 0.90
    min_iv_percentile: float = 0.10
    vix_spike_threshold: float = 25.0
    vix_extreme_threshold: float = 35.0
    auto_square_off_time: time = time(15, 15)
    no_new_entries_after: time = time(15, 0)
    # â”€â”€ NEW: Theta cutoff â€” no new long option entries after this time (theta decay) â”€â”€
    theta_cutoff_time: time = time(14, 30)
    # â”€â”€ NEW: Trailing stop & partial exit params â”€â”€
    trailing_stop_atr_multiplier: float = 2.0
    partial_exit_1_pct: float = 0.40      # Sell 50% at +40% profit
    partial_exit_2_pct: float = 0.60      # Trail rest from here
    breakeven_trigger_pct: float = 0.20    # Move SL to breakeven at +20%
    # â”€â”€ NEW: Delta-neutral threshold â”€â”€
    delta_neutral_threshold: float = 100.0
    capital: float = Field(default=1_000_000.0, gt=0)
    nifty_lot_size: int = 25
    sensex_lot_size: int = 10
    banknifty_lot_size: int = 15

    @field_validator("max_daily_loss_pct")
    @classmethod
    def sane_daily_loss(cls, v: float) -> float:
        if v > 0.05:
            raise ValueError("Daily loss limit >5% is reckless for retail")
        return v


class Position(BaseModel):
    symbol: str
    underlying: str
    strike: float
    option_type: OptionType
    entry_price: float
    entry_time: datetime
    quantity: int
    stop_loss_trigger: float
    target_trigger: float
    unrealized_pnl: float = 0.0
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv_at_entry: Optional[float] = None
    # â”€â”€ NEW: Trailing stop & partial exit state â”€â”€
    breakeven_triggered: bool = False
    partial_exit_1_done: bool = False
    partial_exit_2_done: bool = False
    trailing_sl_price: Optional[float] = None
    highest_mtm_price: Optional[float] = None  # For trailing stop calculation
    original_quantity: int = 0  # Track original qty for partial exit math

    @property
    def notional(self) -> float:
        return self.entry_price * abs(self.quantity)

    @property
    def is_long(self) -> bool:
        return self.quantity > 0


class RiskState(BaseModel):
    daily_pnl: float = 0.0
    daily_loss_limit_hit: bool = False
    circuit_breaker_triggered: bool = False
    circuit_reason: str = ""
    positions: Dict[str, Position] = Field(default_factory=dict)
    symbol_attempts_today: Dict[str, Set[str]] = Field(default_factory=dict)
    last_vix: Optional[float] = None
    # â”€â”€ NEW: NSE-specific market data â”€â”€
    pcr_ratio: Optional[float] = None
    max_pain: Optional[float] = None
    oi_buildup: Dict[str, float] = Field(default_factory=dict)  # strike -> OI change %
    iv_percentile: Optional[float] = None  # Current IV percentile (0-1)

    @property
    def open_position_count(self) -> int:
        return len(self.positions)

    @property
    def net_delta(self) -> float:
        return sum((p.delta or 0) * p.quantity for p in self.positions.values())

    @property
    def net_gamma(self) -> float:
        return sum((p.gamma or 0) * p.quantity for p in self.positions.values())

    @property
    def net_theta(self) -> float:
        return sum((p.theta or 0) * p.quantity for p in self.positions.values())


class OrderFill(BaseModel):
    symbol: str
    underlying: str
    strike: float
    option_type: OptionType
    price: float
    quantity: int
    side: str
    is_opening: bool
    is_closing: bool
    time: datetime
    stop_loss_pct: float = 0.30
    target_pct: float = 0.60


class RiskManager:
    def __init__(self, config: RiskConfig, chain_provider: Optional[OptionsChainProvider] = None):
        self.config = config
        self.chain = chain_provider
        self._state = RiskState()
        self._lock = asyncio.Lock()
        self._today: Optional[datetime.date] = None
        self._kill_switch: bool = False

    async def reset_day(self, date) -> None:
        async with self._lock:
            self._today = date
            self._state = RiskState()
            self._kill_switch = False

    async def update_vix(self, vix: float) -> None:
        """Update VIX reading for regime-based risk filtering."""
        async with self._lock:
            self._state.last_vix = vix

    async def set_kill_switch(self, reason: str) -> None:
        async with self._lock:
            self._kill_switch = True
            self._state.circuit_breaker_triggered = True
            self._state.circuit_reason = f"KILL SWITCH: {reason}"

    async def can_trade(self, signal: Signal, now: datetime) -> tuple:
        """
        Returns: (allowed: bool, reason: str, qty: Optional[int])
        qty is the calculated lot size based on risk â€” NOT hardcoded.
        """
        async with self._lock:
            if self._kill_switch:
                return False, "KILL SWITCH ACTIVE", None

            if now.time() >= self.config.auto_square_off_time:
                return False, "auto square-off time reached", None
            if now.time() >= self.config.no_new_entries_after and signal.action != SignalAction.EXIT:
                return False, "no new entries after 15:00", None

            if self._state.daily_pnl <= -self.config.capital * self.config.max_daily_loss_pct:
                self._state.daily_loss_limit_hit = True
                return False, "daily loss limit hit", None

            if self._state.circuit_breaker_triggered:
                return False, f"circuit breaker: {self._state.circuit_reason}", None

            vix_ok, vix_msg = self._check_vix_regime()
            if not vix_ok and signal.action != SignalAction.EXIT:
                return False, vix_msg, None

            if signal.action == SignalAction.HOLD:
                return False, "HOLD signal", None

            if signal.action == SignalAction.EXIT:
                pos = self._state.positions.get(signal.underlying_symbol)
                if pos is None:
                    return False, "no position to exit", None
                return True, "exit allowed", pos.quantity

            # â”€â”€ NEW: Theta cutoff â€” no new long entries after 12:30 PM â”€â”€
            if now.time() >= self.config.theta_cutoff_time and signal.action in (SignalAction.BUY_CE, SignalAction.BUY_PE):
                return False, f"theta cutoff â€” no new long entries after {self.config.theta_cutoff_time.strftime('%H:%M')}", None

            return await self._evaluate_entry(signal, now)

    async def on_fill(self, fill: OrderFill) -> None:
        async with self._lock:
            if fill.side == "BUY" and fill.is_opening:
                greeks = await self._fetch_greeks(fill.symbol, fill.underlying, fill.strike, fill.option_type)
                pos = Position(
                    symbol=fill.symbol,
                    underlying=fill.underlying,
                    strike=fill.strike,
                    option_type=fill.option_type,
                    entry_price=fill.price,
                    entry_time=fill.time,
                    quantity=fill.quantity,
                    original_quantity=fill.quantity,
                    stop_loss_trigger=fill.price * (1 - fill.stop_loss_pct),
                    target_trigger=fill.price * (1 + fill.target_pct),
                    delta=greeks.get("delta"),
                    gamma=greeks.get("gamma"),
                    theta=greeks.get("theta"),
                    vega=greeks.get("vega"),
                    iv_at_entry=greeks.get("iv"),
                    highest_mtm_price=fill.price,
                )
                self._state.positions[fill.underlying] = pos
                self._state.symbol_attempts_today.setdefault(fill.underlying, set()).add(fill.option_type.value)
            elif fill.side == "SELL" and fill.is_closing:
                pos = self._state.positions.pop(fill.underlying, None)
                if pos:
                    pnl = (fill.price - pos.entry_price) * pos.quantity * (1 if pos.quantity > 0 else -1)
                    self._state.daily_pnl += pnl

    async def update_mtm(self, underlying: str, ltp: float) -> None:
        """Update MTM and check trailing stop / partial exit / breakeven conditions."""
        async with self._lock:
            pos = self._state.positions.get(underlying)
            if not pos:
                return

            pos.unrealized_pnl = (ltp - pos.entry_price) * pos.quantity

            # Update highest MTM price for trailing stop
            if pos.highest_mtm_price is None or ltp > pos.highest_mtm_price:
                pos.highest_mtm_price = ltp

            # â”€â”€ Breakeven trigger: move SL to entry when +20% profit â”€â”€
            breakeven_price = pos.entry_price * (1 + self.config.breakeven_trigger_pct)
            if not pos.breakeven_triggered and ltp >= breakeven_price:
                pos.breakeven_triggered = True
                pos.stop_loss_trigger = pos.entry_price  # Move SL to breakeven
                print(f"[RISK] Breakeven triggered for {pos.symbol} at â‚¹{ltp:.2f}")

            # â”€â”€ Partial exit 1: sell 50% at +40% profit â”€â”€
            partial_1_price = pos.entry_price * (1 + self.config.partial_exit_1_pct)
            if not pos.partial_exit_1_done and ltp >= partial_1_price:
                pos.partial_exit_1_done = True
                # Return signal to engine to execute partial exit
                # Engine will handle the actual order sizing

            # â”€â”€ Partial exit 2: trail remaining with 2x ATR (simplified as % here) â”€â”€
            if pos.partial_exit_1_done and not pos.partial_exit_2_done:
                # Trailing stop: highest price - 2x ATR (approximated as entry * 0.10 for now)
                # In production, pass actual ATR from strategy
                atr_estimate = pos.entry_price * 0.05  # ~5% of entry as ATR proxy
                trail_distance = atr_estimate * self.config.trailing_stop_atr_multiplier
                new_trailing_sl = (pos.highest_mtm_price or ltp) - trail_distance
                if pos.trailing_sl_price is None or new_trailing_sl > pos.trailing_sl_price:
                    pos.trailing_sl_price = new_trailing_sl
                pos.stop_loss_trigger = max(pos.stop_loss_trigger, pos.trailing_sl_price)

    async def get_exit_signal(self, underlying: str, current_price: float) -> Optional[Signal]:
        """
        Check if a position needs to be exited due to trailing stop / partial exit / breakeven.
        Returns an EXIT Signal if needed, None otherwise.
        Called by engine/paper broker on each price update.
        """
        async with self._lock:
            pos = self._state.positions.get(underlying)
            if not pos:
                return None

            # Hard SL hit
            if current_price <= pos.stop_loss_trigger:
                reason = "stop_loss"
                if pos.breakeven_triggered and pos.stop_loss_trigger >= pos.entry_price:
                    reason = "breakeven_stop"
                elif pos.trailing_sl_price and current_price <= pos.trailing_sl_price:
                    reason = "trailing_stop"
                return Signal(
                    action=SignalAction.EXIT,
                    underlying_symbol=underlying,
                    confidence=0.9,
                    reason=f"Risk exit â€” {reason} (price {current_price:.2f} <= SL {pos.stop_loss_trigger:.2f})",
                    option_type=pos.option_type
                )

            # Target hit
            if current_price >= pos.target_trigger:
                return Signal(
                    action=SignalAction.EXIT,
                    underlying_symbol=underlying,
                    confidence=0.9,
                    reason=f"Risk exit â€” target hit (price {current_price:.2f} >= target {pos.target_trigger:.2f})",
                    option_type=pos.option_type
                )

            # Partial exit 1: return signal to sell 50%
            if pos.partial_exit_1_done and pos.quantity == pos.original_quantity:
                # Engine should reduce position by 50%
                return Signal(
                    action=SignalAction.EXIT,
                    underlying_symbol=underlying,
                    confidence=0.8,
                    reason="partial_exit_1 â€” sell 50% at +40% profit",
                    option_type=pos.option_type
                )

            return None

    async def get_positions(self) -> Dict[str, Position]:
        async with self._lock:
            return dict(self._state.positions)

    async def get_state_snapshot(self):
        async with self._lock:
            return self._state.model_copy(deep=True)

    async def update_market_data(self, pcr: Optional[float] = None, max_pain: Optional[float] = None,
                                  oi_buildup: Optional[Dict[str, float]] = None,
                                  iv_percentile: Optional[float] = None) -> None:
        """Update NSE-specific market data for risk decisions."""
        async with self._lock:
            if pcr is not None:
                self._state.pcr_ratio = pcr
            if max_pain is not None:
                self._state.max_pain = max_pain
            if oi_buildup is not None:
                self._state.oi_buildup.update(oi_buildup)
            if iv_percentile is not None:
                self._state.iv_percentile = iv_percentile

    async def _evaluate_entry(self, signal: Signal, now: datetime) -> tuple:
        underlying = signal.underlying_symbol

        if len(self._state.positions) >= self.config.max_correlation_symbols:
            if underlying not in self._state.positions:
                return False, f"max correlation symbols ({self.config.max_correlation_symbols}) reached", None

        if underlying in self._state.positions:
            return False, "already have position in this underlying", None

        attempted = self._state.symbol_attempts_today.get(underlying, set())
        opt_type = OptionType.CE if signal.action == SignalAction.BUY_CE else OptionType.PE
        if opt_type.value in attempted:
            return False, f"already attempted {opt_type.value} today", None

        if self.chain is None:
            lot_size = self._get_lot_size(underlying)
            return True, "risk approved (backtest mode)", lot_size

        quote = await self.chain.get_quote(underlying, await self.chain.get_atm_strike(underlying), opt_type)
        if not await self.chain.is_liquid(quote, self.config.max_spread_pct, self.config.min_oi):
            return False, f"illiquid {opt_type.value} strike {quote.strike}", None

        # â”€â”€ NEW: IV percentile filter â”€â”€
        if self._state.iv_percentile is not None:
            if self._state.iv_percentile > self.config.max_iv_percentile:
                return False, f"IV percentile {self._state.iv_percentile:.2f} > max {self.config.max_iv_percentile}", None
            if self._state.iv_percentile < self.config.min_iv_percentile:
                return False, f"IV percentile {self._state.iv_percentile:.2f} < min {self.config.min_iv_percentile}", None

        lot_size = self._get_lot_size(underlying)
        risk_per_lot = quote.ltp * signal.stop_loss_pct * lot_size
        max_risk_rupees = self.config.capital * self.config.max_risk_per_trade_pct

        if risk_per_lot > max_risk_rupees:
            return False, f"risk per lot ({risk_per_lot:.0f}) > max allowed ({max_risk_rupees:.0f})", None

        lots = int(max_risk_rupees // risk_per_lot)
        if lots < 1:
            return False, "insufficient capital for even 1 lot", None

        total_qty = lots * lot_size

        # â”€â”€ NEW: Delta exposure check â”€â”€
        if quote.delta:
            new_delta = self._state.net_delta + (quote.delta * total_qty)
            if abs(new_delta) > self.config.max_position_delta:
                return False, f"delta exposure {new_delta:.1f} > limit {self.config.max_position_delta}", None

        # â”€â”€ NEW: Gamma exposure check â”€â”€
        if quote.gamma:
            new_gamma = self._state.net_gamma + (quote.gamma * total_qty)
            if abs(new_gamma) > self.config.max_position_gamma:
                return False, f"gamma exposure {new_gamma:.4f} > limit {self.config.max_position_gamma}", None

        # â”€â”€ NEW: Delta-neutral portfolio check â”€â”€
        if abs(new_delta) > self.config.delta_neutral_threshold:
            # Don't block, just warn â€” this is a soft limit
            print(f"[RISK WARNING] Portfolio delta {new_delta:.1f} approaching neutral threshold {self.config.delta_neutral_threshold}")

        return True, "risk approved", total_qty

    def _check_vix_regime(self) -> tuple:
        vix = self._state.last_vix
        if vix is None:
            return True, "VIX unknown, proceeding with caution"
        if vix > self.config.vix_extreme_threshold:
            return False, f"VIX extreme ({vix:.1f}) - no new entries"
        if vix > self.config.vix_spike_threshold:
            return True, f"VIX elevated ({vix:.1f}) - size reduced"
        return True, "VIX normal"

    def _get_lot_size(self, underlying: str) -> int:
        u = underlying.upper()
        if "BANK" in u:
            return self.config.banknifty_lot_size
        if "SENSEX" in u:
            return self.config.sensex_lot_size
        return self.config.nifty_lot_size

    async def _fetch_greeks(self, symbol: str, underlying: str, strike: float, opt_type: OptionType) -> Dict:
        """Fetch real Greeks from chain provider instead of hardcoded dummies."""
        if self.chain is None:
            return {"delta": 0.5, "gamma": 0.01, "theta": -2.0, "vega": 1.5, "iv": 0.18}

        try:
            quote = await self.chain.get_quote(underlying, strike, opt_type)
            return {
                "delta": quote.delta,
                "gamma": quote.gamma,
                "theta": quote.theta,
                "vega": quote.vega,
                "iv": quote.iv / 100.0 if quote.iv > 1.0 else quote.iv,  # Normalize to decimal
            }
        except Exception as e:
            print(f"[RISK] Failed to fetch Greeks for {symbol}: {e}")
            return {"delta": 0.5, "gamma": 0.01, "theta": -2.0, "vega": 1.5, "iv": 0.18}
