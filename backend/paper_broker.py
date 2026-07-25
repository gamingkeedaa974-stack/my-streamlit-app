"""
paper_broker.py
Simulated broker for paper trading. No real API calls.
Generates realistic option fills and tracks live P&L.
"""

from __future__ import annotations
import asyncio
from datetime import datetime, time
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import random

from backend.strategies.strategy import Signal, SignalAction, OptionType, OptionQuote, Bar
from backend.backtest_engine import SyntheticOptionsChainProvider
from backend.risk_manager import RiskManager, RiskConfig, OrderFill


@dataclass
class SimulatedPosition:
    symbol: str
    underlying: str
    option_type: str
    strike: float
    entry_price: float
    current_price: float
    quantity: int
    entry_time: datetime
    stop_loss: float
    target: float
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv_at_entry: Optional[float] = None
    time_in_trade: str = ""
    # ── NEW: Trailing stop & partial exit state ──
    breakeven_triggered: bool = False
    partial_exit_done: bool = False
    trailing_sl_price: Optional[float] = None
    highest_mtm_price: Optional[float] = None
    original_quantity: int = 0


class PaperBroker:
    """Simulated broker that mimics real fills, slippage, and P&L tracking."""

    def __init__(self, capital: float = 1_000_000, lot_size: int = 25, slippage_pct: float = 0.001):
        self.capital = capital
        self.initial_capital = capital
        self.lot_size = lot_size
        self.slippage_pct = slippage_pct
        self.positions: List[SimulatedPosition] = []
        self.closed_trades: List[Dict] = []
        self.daily_pnl = 0.0
        self.daily_pnl_pct = 0.0
        self.chain = SyntheticOptionsChainProvider(symbol="NIFTY50")
        self._lock = asyncio.Lock()
        # ── NEW: Risk manager for dynamic exit logic ──
        self.risk = RiskManager(RiskConfig(), self.chain)
        # ── NEW: Batch price update buffer ──
        self._price_buffer: Dict[str, float] = {}

    async def place_order(self, signal: Signal, underlying: str, timestamp: datetime, qty: Optional[int] = None) -> Optional[SimulatedPosition]:
        """
        Simulate a market order fill with slippage.
        qty comes from risk manager calculation. Falls back to lot_size if not provided.
        """
        async with self._lock:
            opt_type = OptionType.CE if signal.action == SignalAction.BUY_CE else OptionType.PE
            strike = await self.chain.get_atm_strike(underlying)
            quote = await self.chain.get_quote(underlying, strike, opt_type)

            # Apply slippage on entry (worse price for buyer)
            entry_price = round(quote.ask * (1 + self.slippage_pct), 2)

            # ── NEW: Use qty from risk manager, fallback to lot_size ──
            if qty is None or qty <= 0:
                qty = self.lot_size

            # ── NEW: Dynamic SL/Target from risk manager instead of hardcoded signal values ──
            # Risk manager will compute trailing stops, breakeven, partial exits
            stop_loss = round(entry_price * (1 - signal.stop_loss_pct), 2)
            target = round(entry_price * (1 + signal.target_pct), 2)

            pos = SimulatedPosition(
                symbol=quote.symbol,
                underlying=underlying,
                option_type=opt_type.value,
                strike=strike,
                entry_price=entry_price,
                current_price=entry_price,
                quantity=qty,
                original_quantity=qty,
                entry_time=timestamp,
                stop_loss=stop_loss,
                target=target,
                delta=quote.delta,
                gamma=quote.gamma,
                theta=quote.theta,
                vega=quote.vega,
                iv_at_entry=quote.iv / 100.0 if quote.iv > 1.0 else quote.iv,
                highest_mtm_price=entry_price,
            )

            # Notify risk manager of fill
            fill = OrderFill(
                symbol=quote.symbol,
                underlying=underlying,
                strike=strike,
                option_type=opt_type,
                price=entry_price,
                quantity=qty,
                side="BUY",
                is_opening=True,
                is_closing=False,
                time=timestamp,
                stop_loss_pct=signal.stop_loss_pct,
                target_pct=signal.target_pct,
            )
            await self.risk.on_fill(fill)

            self.positions.append(pos)
            return pos

    async def update_prices(self, underlying_spot: float, timestamp: datetime):
        """
        Update all position prices based on new underlying spot.
        ── FIXED: Batch update — single lock acquisition for all positions ──
        """
        async with self._lock:
            self.chain.update_spot(underlying_spot)

            # Batch update all positions
            for pos in self.positions[:]:
                opt_type = OptionType.CE if pos.option_type == "CE" else OptionType.PE
                quote = await self.chain.get_quote(pos.underlying, pos.strike, opt_type)

                # Apply slippage on current price (worse for seller)
                current_price = round(quote.bid * (1 - self.slippage_pct), 2)
                pos.current_price = current_price

                # Calculate P&L
                pos.unrealized_pnl = round((current_price - pos.entry_price) * pos.quantity, 2)
                pos.unrealized_pnl_pct = round(((current_price - pos.entry_price) / pos.entry_price) * 100, 2)

                # Update time in trade
                duration = timestamp - pos.entry_time
                minutes = int(duration.total_seconds() / 60)
                pos.time_in_trade = f"{minutes}m"

                # Update highest MTM for trailing stop
                if pos.highest_mtm_price is None or current_price > pos.highest_mtm_price:
                    pos.highest_mtm_price = current_price

                # ── NEW: Update risk manager MTM for trailing stop logic ──
                await self.risk.update_mtm(pos.underlying, current_price)

        # ── NEW: Check exit conditions OUTSIDE the main lock to avoid deadlock ──
        # Risk manager may need its own lock
        await self._check_exit_conditions(timestamp)

    async def _check_exit_conditions(self, timestamp: datetime):
        """
        Check all positions for exit conditions.
        Delegates to RiskManager for trailing stop / partial exit / breakeven logic.
        """
        positions_to_check = []
        async with self._lock:
            positions_to_check = self.positions[:]

        for pos in positions_to_check:
            # ── NEW: Get dynamic exit signal from risk manager ──
            exit_signal = await self.risk.get_exit_signal(pos.underlying, pos.current_price)

            if exit_signal:
                if "partial_exit" in exit_signal.reason:
                    await self._execute_partial_exit(pos, timestamp, exit_signal.reason)
                else:
                    await self._close_position(pos, timestamp, exit_signal.reason)
                continue

            # ── REMOVED: Hardcoded SL/Target checks — now handled by risk manager ──
            # Legacy checks removed. All exits come from:
            # 1. Strategy signal (real exit logic)
            # 2. Risk manager (trailing stop, partial exit, breakeven, hard SL, target)

            # Square-off at market close (kept as broker-level safety)
            if timestamp.time() >= time(15, 15):
                await self._close_position(pos, timestamp, "square_off")

    async def _execute_partial_exit(self, pos: SimulatedPosition, timestamp: datetime, reason: str):
        """Sell 50% of position at +40% profit, keep rest with trailing stop."""
        async with self._lock:
            if pos not in self.positions:
                return

            exit_qty = pos.quantity // 2
            if exit_qty < 1:
                exit_qty = 1

            exit_price = pos.current_price

            pnl = round((exit_price - pos.entry_price) * exit_qty, 2)
            self.daily_pnl += pnl
            self.capital += pnl
            self.daily_pnl_pct = round((self.daily_pnl / self.initial_capital) * 100, 2)

            self.closed_trades.append({
                "symbol": pos.symbol,
                "entry_price": pos.entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": round(((exit_price - pos.entry_price) / pos.entry_price) * 100, 2),
                "reason": reason,
                "entry_time": pos.entry_time.isoformat(),
                "exit_time": timestamp.isoformat(),
                "is_partial_exit": True,
                "quantity": exit_qty,
            })

            # Reduce position
            pos.quantity -= exit_qty
            pos.partial_exit_done = True

            # Notify risk manager of partial fill
            fill = OrderFill(
                symbol=pos.symbol,
                underlying=pos.underlying,
                strike=pos.strike,
                option_type=OptionType.CE if pos.option_type == "CE" else OptionType.PE,
                price=exit_price,
                quantity=exit_qty,
                side="SELL",
                is_opening=False,
                is_closing=False,  # Partial — not fully closed
                time=timestamp,
            )
            await self.risk.on_fill(fill)

            print(f"[PAPER] Partial exit: sold {exit_qty} of {pos.symbol} at ₹{exit_price:.2f}, reason: {reason}")

    async def _close_position(self, pos: SimulatedPosition, timestamp: datetime, reason: str):
        """Close a position and realize P&L."""
        async with self._lock:
            if pos not in self.positions:
                return

            exit_price = pos.current_price
            pnl = round((exit_price - pos.entry_price) * pos.quantity, 2)

            self.daily_pnl += pnl
            self.capital += pnl
            self.daily_pnl_pct = round((self.daily_pnl / self.initial_capital) * 100, 2)

            self.closed_trades.append({
                "symbol": pos.symbol,
                "entry_price": pos.entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_pct": pos.unrealized_pnl_pct,
                "reason": reason,  # ── NEW: Real exit reason from strategy/risk manager ──
                "entry_time": pos.entry_time.isoformat(),
                "exit_time": timestamp.isoformat(),
                "is_partial_exit": False,
                "quantity": pos.quantity,
                "delta": pos.delta,
                "gamma": pos.gamma,
                "theta": pos.theta,
                "vega": pos.vega,
            })

            # Notify risk manager of fill
            fill = OrderFill(
                symbol=pos.symbol,
                underlying=pos.underlying,
                strike=pos.strike,
                option_type=OptionType.CE if pos.option_type == "CE" else OptionType.PE,
                price=exit_price,
                quantity=pos.quantity,
                side="SELL",
                is_opening=False,
                is_closing=True,
                time=timestamp,
            )
            await self.risk.on_fill(fill)

            # Remove from positions
            self.positions = [p for p in self.positions if p.symbol != pos.symbol]

            print(f"[PAPER] Close: {pos.symbol} — {reason} at ₹{exit_price:.2f}, P&L: ₹{pnl:,.2f}")

    async def square_off_all(self, timestamp: datetime):
        """Close all open positions."""
        async with self._lock:
            positions_to_close = self.positions[:]

        for pos in positions_to_close:
            await self._close_position(pos, timestamp, "manual_square_off")

    # ── NEW: Feed NSE-specific market data into risk manager ──
    async def update_market_data(self, pcr: Optional[float] = None,
                                  max_pain: Optional[float] = None,
                                  oi_buildup: Optional[Dict[str, float]] = None,
                                  iv_percentile: Optional[float] = None) -> None:
        """Update NSE-specific market data for risk decisions."""
        await self.risk.update_market_data(pcr, max_pain, oi_buildup, iv_percentile)

    def get_portfolio_summary(self) -> Dict:
        """Get current portfolio state for dashboard."""
        unrealized = sum(p.unrealized_pnl for p in self.positions)
        margin_used = sum(p.entry_price * p.quantity for p in self.positions)

        # ── NEW: Calculate net Greeks from positions ──
        net_delta = sum((p.delta or 0) * p.quantity for p in self.positions)
        net_gamma = sum((p.gamma or 0) * p.quantity for p in self.positions)
        net_theta = sum((p.theta or 0) * p.quantity for p in self.positions)
        net_vega = sum((p.vega or 0) * p.quantity for p in self.positions)

        return {
            "capital": round(self.capital, 2),
            "daily_pnl": round(self.daily_pnl + unrealized, 2),
            "daily_pnl_pct": round(self.daily_pnl_pct, 2),
            "open_positions": len(self.positions),
            "margin_used_pct": round(min(100, (margin_used / self.capital) * 100), 2) if self.capital > 0 else 0,
            "available_margin": round(self.capital - margin_used, 2),
            "net_delta": round(net_delta, 2),
            "net_gamma": round(net_gamma, 4),
            "net_theta": round(net_theta, 2),
            "net_vega": round(net_vega, 2),
            "circuit_breaker": False,
            "kill_switch": False,
        }

    def get_positions(self) -> List[Dict]:
        """Return positions in dashboard format."""
        return [
            {
                "symbol": p.symbol,
                "underlying": p.underlying,
                "option_type": p.option_type,
                "strike": p.strike,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "quantity": p.quantity,
                "original_quantity": p.original_quantity,
                "unrealized_pnl": p.unrealized_pnl,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
                "stop_loss": p.stop_loss,
                "target": p.target,
                "delta": p.delta,
                "gamma": p.gamma,
                "theta": p.theta,
                "vega": p.vega,
                "time_in_trade": p.time_in_trade,
                "breakeven_triggered": p.breakeven_triggered,
                "partial_exit_done": p.partial_exit_done,
                "trailing_sl_price": p.trailing_sl_price,
            }
            for p in self.positions
        ]

    def reset(self):
        """Reset all state."""
        self.positions = []
        self.closed_trades = []
        self.daily_pnl = 0.0
        self.daily_pnl_pct = 0.0
        self.capital = self.initial_capital
        self._price_buffer.clear()