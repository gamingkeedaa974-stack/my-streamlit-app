"""
backtest_engine.py
High-fidelity backtest engine for NSE options strategies.
Uses synthetic but realistic option pricing based on underlying spot.
"""

from __future__ import annotations
import random
import sqlite3
from datetime import datetime, time, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd
import numpy as np

from backend.strategies.strategy import (
    BaseStrategy, StrategyConfig, Signal, SignalAction, OptionType, 
    OptionQuote, Bar, BacktestResult, OptionsChainProvider
)
from backend.risk_manager import RiskManager, RiskConfig, OrderFill


class SyntheticOptionsChainProvider:
    """Generates realistic option quotes for backtesting without API calls."""

    # ═══════════════════════════════════════════════════════════
    # SYMBOL-SPECIFIC VOLATILITY & PRICING
    # ═══════════════════════════════════════════════════════════
    SYMBOL_VOLATILITY = {
        "NIFTY50": 0.0008,
        "NIFTY": 0.0008,
        "BANKNIFTY": 0.0015,
        "FINNIFTY": 0.0012,
        "SENSEX": 0.0006,
        "MIDCPNIFTY": 0.0010,
    }

    def __init__(self, symbol: str = "NIFTY50", spot_price: float = None, iv_base: float = 0.18, 
                 iv_skew: float = 0.02, spread_base: float = 0.02):
        # Symbol-specific base spot prices for realistic ATM strike calculation
        symbol_spots = {
            "NIFTY50": 24500,
            "BANKNIFTY": 48000,
            "FINNIFTY": 20500,
            "SENSEX": 75000,
        }
        self.symbol = symbol.upper().replace("-INDEX", "").replace("NSE:", "").replace("BSE:", "")
        self.spot_price = spot_price or symbol_spots.get(self.symbol, 24500)
        self.iv_base = iv_base
        self.iv_skew = iv_skew
        self.spread_base = spread_base
        self._oi_data: Dict[str, int] = {}
        # Use symbol-specific volatility if available
        self._symbol_vol = self.SYMBOL_VOLATILITY.get(self.symbol, 0.0008)

    async def get_atm_strike(self, symbol: str) -> float:
        step = 100 if "BANK" in symbol.upper() else 50
        return round(self.spot_price / step) * step

    async def get_quote(self, symbol: str, strike: float, opt_type: OptionType) -> OptionQuote:
        moneyness = abs(strike - self.spot_price) / self.spot_price
        iv = self.iv_base + self.iv_skew * moneyness * 10
        days_to_expiry = 7
        t = days_to_expiry / 365

        # Time value based on strike (not spot) and decays with moneyness
        base_time_value = strike * iv * np.sqrt(t) * 0.4 * np.exp(-moneyness * 3)

        if opt_type == OptionType.CE:
            intrinsic = max(0, self.spot_price - strike)
            ltp = intrinsic + base_time_value
            # Delta: increases as spot goes above strike
            delta = 0.5 + (self.spot_price - strike) / (strike * iv * np.sqrt(t)) * 0.3
            delta = max(0.05, min(0.95, delta))
        else:
            intrinsic = max(0, strike - self.spot_price)
            ltp = intrinsic + base_time_value
            # Delta: decreases (more negative) as spot goes below strike
            delta = -0.5 + (self.spot_price - strike) / (strike * iv * np.sqrt(t)) * 0.3
            delta = min(-0.05, max(-0.95, delta))

        gamma = 0.01 / (1 + moneyness * 5)
        theta = -ltp * 0.15 / days_to_expiry
        vega = ltp * 0.1 * np.sqrt(t)
        spread = ltp * self.spread_base * (1 + moneyness * 2)

        oi_key = f"{symbol}_{strike}_{opt_type.value}"
        if oi_key not in self._oi_data:
            self._oi_data[oi_key] = random.randint(300_000, 2_000_000)

        return OptionQuote(
            symbol=f"{symbol}{strike}{opt_type.value}",
            strike=strike,
            option_type=opt_type,
            expiry=datetime.now() + timedelta(days=days_to_expiry),
            ltp=round(ltp, 2),
            bid=round(ltp - spread/2, 2),
            ask=round(ltp + spread/2, 2),
            oi=self._oi_data[oi_key],
            iv=round(iv * 100, 2),
            delta=round(delta, 4),
            gamma=round(gamma, 4),
            theta=round(theta, 4),
            vega=round(vega, 4),
        )

    async def is_liquid(self, quote: OptionQuote, max_spread_pct: float = 0.03, min_oi: int = 500_000) -> bool:
        return quote.spread_pct <= max_spread_pct and quote.oi >= min_oi

    def update_spot(self, new_spot: float) -> None:
        self.spot_price = new_spot


@dataclass
class SimulatedTrade:
    entry_time: datetime
    exit_time: Optional[datetime] = None
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: int = 0
    side: str = ""
    option_type: str = ""
    strike: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""
    max_mtm: float = 0.0
    min_mtm: float = 0.0
    # ── NEW: Track partial exits ──
    partial_exit_qty: int = 0  # Quantity already exited via partial
    is_partial_exit: bool = False


class SQLiteTradeStore:
    """SQLite persistence for backtest positions and trades."""

    def __init__(self, db_path: str = "data/backtest_trades.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy TEXT,
                    symbol TEXT,
                    entry_time TEXT,
                    exit_time TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    quantity INTEGER,
                    option_type TEXT,
                    strike REAL,
                    pnl REAL,
                    pnl_pct REAL,
                    exit_reason TEXT,
                    max_mtm REAL,
                    min_mtm REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS equity_curve (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy TEXT,
                    symbol TEXT,
                    timestamp TEXT,
                    equity REAL,
                    unrealized REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def save_trade(self, strategy: str, symbol: str, trade: SimulatedTrade):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO trades (strategy, symbol, entry_time, exit_time, entry_price, exit_price,
                    quantity, option_type, strike, pnl, pnl_pct, exit_reason, max_mtm, min_mtm)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                strategy, symbol, trade.entry_time.isoformat(),
                trade.exit_time.isoformat() if trade.exit_time else None,
                trade.entry_price, trade.exit_price, trade.quantity, trade.option_type,
                trade.strike, trade.pnl, trade.pnl_pct, trade.exit_reason,
                trade.max_mtm, trade.min_mtm
            ))
            conn.commit()

    def save_equity(self, strategy: str, symbol: str, timestamp: datetime, equity: float, unrealized: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO equity_curve (strategy, symbol, timestamp, equity, unrealized)
                VALUES (?, ?, ?, ?, ?)
            """, (strategy, symbol, timestamp.isoformat(), equity, unrealized))
            conn.commit()


class BacktestEngine:
    def __init__(self, 
                 strategy: BaseStrategy,
                 risk_config: RiskConfig,
                 data: pd.DataFrame,
                 symbol: str = "NIFTY50",
                 capital: float = 1_000_000,
                 lot_size: int = 25,
                 slippage_pct: float = 0.001,
                 transaction_cost_per_lot: float = 50.0,
                 max_trades_per_day: int = 2,
                 enable_sqlite: bool = True):
        self.strategy = strategy
        self.risk_config = risk_config
        self.data = data.copy()
        self.symbol = symbol
        self.capital = capital
        self.lot_size = lot_size
        self.slippage_pct = slippage_pct
        self.transaction_cost_per_lot = transaction_cost_per_lot
        self.max_trades_per_day = max_trades_per_day
        self.enable_sqlite = enable_sqlite
        
        self.chain = SyntheticOptionsChainProvider(symbol=self.symbol)
        self.risk = RiskManager(risk_config, self.chain)
        self.trades: List[SimulatedTrade] = []
        self.equity_curve: List[Dict] = []
        self.current_trade: Optional[SimulatedTrade] = None
        self.daily_trade_count: int = 0
        self.last_date: Optional[datetime.date] = None
        
        # ── NEW: SQLite persistence ──
        self._db = SQLiteTradeStore() if enable_sqlite else None
        
    async def run(self) -> BacktestResult:
        self.strategy.chain = self.chain
        
        required = ['open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in self.data.columns:
                raise ValueError(f"Missing column: {col}")
        
        current_equity = self.capital
        signal_count = 0
        trade_count = 0
        
        for idx, row in self.data.iterrows():
            timestamp = idx if isinstance(idx, datetime) else pd.to_datetime(idx)
            
            # ── NEW: Day boundary reset using strategy.reset() ──
            if self.last_date != timestamp.date():
                self.daily_trade_count = 0
                self.last_date = timestamp.date()
                self.strategy.reset()  # Replaces all hasattr hacks
                await self.risk.reset_day(timestamp.date())
            
            if timestamp.time() < time(9, 15) or timestamp.time() > time(15, 30):
                continue
            
            self.chain.update_spot(row['close'])
            
            bar = Bar(
                symbol=self.symbol,
                timestamp=timestamp,
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=int(row['volume'])
            )
            self.strategy.ingest_bar(bar)
            
            if timestamp.minute % 5 == 0:
                signal = await self.strategy.generate_signal(self.symbol, timestamp)
                if signal.action != SignalAction.HOLD:
                    signal_count += 1
                    print(f"[BACKTEST] Signal {signal_count}: {signal.action.value} at {timestamp} — conf: {signal.confidence:.2f}")
                    await self._process_signal(signal, timestamp, row['close'])
                    if self.current_trade:
                        trade_count += 1
            
            if self.current_trade:
                await self._update_mtm(timestamp, row['close'])
            
            unrealized = self.current_trade.pnl if self.current_trade else 0
            current_equity = self.capital + sum(t.pnl for t in self.trades) + unrealized
            self.equity_curve.append({
                'timestamp': timestamp,
                'equity': current_equity,
                'unrealized': unrealized
            })
            
            # Save equity to SQLite
            if self._db:
                self._db.save_equity(self.strategy.config.name, self.symbol, timestamp, current_equity, unrealized)
        
        # Force close any open position at end of data
        if self.current_trade:
            await self._close_position(
                self.data.index[-1], 
                self.data['close'].iloc[-1], 
                "end_of_data"
            )
        
        print(f"[BACKTEST] Complete: {signal_count} signals, {trade_count} trades executed, {len(self.trades)} total trades")
        return self._build_result()
    
    async def _process_signal(self, signal: Signal, timestamp: datetime, spot: float) -> None:
        if self.daily_trade_count >= self.max_trades_per_day:
            return
        
        allowed, reason, qty = await self.risk.can_trade(signal, timestamp)
        
        if not allowed:
            return
        
        if signal.action in (SignalAction.BUY_CE, SignalAction.BUY_PE) and not self.current_trade:
            # ── NEW: Use qty from risk manager, not hardcoded lot_size ──
            await self._open_position(signal, timestamp, spot, qty)
        elif signal.action == SignalAction.EXIT and self.current_trade:
            await self._close_position(timestamp, spot, signal.reason or "signal_exit")
    
    async def _open_position(self, signal: Signal, timestamp: datetime, spot: float, qty: int) -> None:
        opt_type = OptionType.CE if signal.action == SignalAction.BUY_CE else OptionType.PE
        quote = await self.chain.get_quote(self.symbol, await self.chain.get_atm_strike(self.symbol), opt_type)
        
        entry_price = quote.ask * (1 + self.slippage_pct)
        
        # ── NEW: Use qty from risk manager instead of hardcoded self.lot_size ──
        # qty is already calculated by risk manager based on risk per trade
        if qty is None or qty <= 0:
            qty = self.lot_size  # Fallback only if risk manager returned None
        
        self.current_trade = SimulatedTrade(
            entry_time=timestamp,
            entry_price=entry_price,
            quantity=qty,
            side="LONG",
            option_type=opt_type.value,
            strike=quote.strike,
        )
        
        self.daily_trade_count += 1
        
        fill = OrderFill(
            symbol=quote.symbol,
            underlying=self.symbol,
            strike=quote.strike,
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
    
    async def _update_mtm(self, timestamp: datetime, spot: float) -> None:
        if not self.current_trade:
            return
        
        opt_type = OptionType.CE if self.current_trade.option_type == "CE" else OptionType.PE
        quote = await self.chain.get_quote(self.symbol, self.current_trade.strike, opt_type)
        
        current_price = quote.bid * (1 - self.slippage_pct)
        
        pnl = (current_price - self.current_trade.entry_price) * self.current_trade.quantity
        pnl -= self.transaction_cost_per_lot * (self.current_trade.quantity / self.lot_size) * 2
        
        self.current_trade.pnl = pnl
        self.current_trade.pnl_pct = (pnl / (self.current_trade.entry_price * self.current_trade.quantity)) * 100
        
        if pnl > self.current_trade.max_mtm:
            self.current_trade.max_mtm = pnl
        if pnl < self.current_trade.min_mtm:
            self.current_trade.min_mtm = pnl
        
        # ── NEW: Update risk manager's MTM for trailing stop / partial exit logic ──
        await self.risk.update_mtm(self.symbol, current_price)
        
        # ── NEW: Check risk manager for exit signals (trailing stop, partial exit, breakeven) ──
        exit_signal = await self.risk.get_exit_signal(self.symbol, current_price)
        if exit_signal:
            if "partial_exit_1" in exit_signal.reason:
                # Handle partial exit: sell 50% of position
                await self._execute_partial_exit(timestamp, current_price, exit_signal.reason)
            else:
                await self._close_position(timestamp, spot, exit_signal.reason)
            return
        
        # ── REMOVED: Hardcoded 30% SL / 60% target — now handled by risk manager ──
        # Legacy hardcoded exits removed. All exits come from:
        # 1. Strategy signal (real exit logic: OR reversion, VWAP cross, mean touch)
        # 2. Risk manager (trailing stop, partial exit, breakeven, hard SL, target)
        
        # Square-off at market close
        if timestamp.time() >= time(15, 15):
            await self._close_position(timestamp, spot, "square_off")
    
    async def _execute_partial_exit(self, timestamp: datetime, current_price: float, reason: str) -> None:
        """Sell 50% of position at +40% profit, keep rest with trailing stop."""
        if not self.current_trade:
            return
        
        exit_qty = self.current_trade.quantity // 2
        if exit_qty < 1:
            exit_qty = 1
        
        exit_price = current_price * (1 - self.slippage_pct)
        
        pnl = (exit_price - self.current_trade.entry_price) * exit_qty
        pnl -= self.transaction_cost_per_lot * (exit_qty / self.lot_size)
        
        # Record partial exit as a separate trade
        partial_trade = SimulatedTrade(
            entry_time=self.current_trade.entry_time,
            exit_time=timestamp,
            entry_price=self.current_trade.entry_price,
            exit_price=exit_price,
            quantity=exit_qty,
            side="LONG",
            option_type=self.current_trade.option_type,
            strike=self.current_trade.strike,
            pnl=pnl,
            pnl_pct=(pnl / (self.current_trade.entry_price * exit_qty)) * 100,
            exit_reason=reason,
            is_partial_exit=True,
        )
        self.trades.append(partial_trade)
        
        # Save to SQLite
        if self._db:
            self._db.save_trade(self.strategy.config.name, self.symbol, partial_trade)
        
        # Reduce remaining position
        self.current_trade.quantity -= exit_qty
        self.current_trade.partial_exit_qty += exit_qty
        
        print(f"[BACKTEST] Partial exit: sold {exit_qty} qty at ₹{exit_price:.2f}, reason: {reason}")
    
    async def _close_position(self, timestamp: datetime, spot: float, reason: str) -> None:
        if not self.current_trade:
            return
        
        opt_type = OptionType.CE if self.current_trade.option_type == "CE" else OptionType.PE
        quote = await self.chain.get_quote(self.symbol, self.current_trade.strike, opt_type)
        
        exit_price = quote.bid * (1 - self.slippage_pct)
        
        pnl = (exit_price - self.current_trade.entry_price) * self.current_trade.quantity
        pnl -= self.transaction_cost_per_lot * (self.current_trade.quantity / self.lot_size) * 2
        
        self.current_trade.exit_time = timestamp
        self.current_trade.exit_price = exit_price
        self.current_trade.pnl = pnl
        self.current_trade.pnl_pct = (pnl / (self.current_trade.entry_price * self.current_trade.quantity)) * 100
        self.current_trade.exit_reason = reason
        
        self.trades.append(self.current_trade)
        
        # Save to SQLite
        if self._db:
            self._db.save_trade(self.strategy.config.name, self.symbol, self.current_trade)
        
        fill = OrderFill(
            symbol=quote.symbol,
            underlying=self.symbol,
            strike=self.current_trade.strike,
            option_type=opt_type,
            price=exit_price,
            quantity=self.current_trade.quantity,
            side="SELL",
            is_opening=False,
            is_closing=True,
            time=timestamp,
        )
        await self.risk.on_fill(fill)
        
        print(f"[BACKTEST] Close: {reason} at ₹{exit_price:.2f}, P&L: ₹{pnl:,.2f}")
        self.current_trade = None
    
    def _build_result(self) -> BacktestResult:
        if not self.trades:
            return BacktestResult(
                strategy_name=self.strategy.config.name,
                symbol=self.symbol,
                start_date=self.data.index[0],
                end_date=self.data.index[-1],
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                avg_profit_per_trade=0.0,
                max_drawdown=0.0,
                sharpe_ratio=0.0,
                total_pnl=0.0,
                total_pnl_pct=0.0,
                profit_factor=0.0,
                avg_trade_duration=0.0,
                max_consecutive_losses=0,
                params=self.strategy.get_current_params(),
                equity_curve=self.equity_curve,
                trades=[],
            )
        
        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl <= 0]
        
        equity_values = [e['equity'] for e in self.equity_curve]
        
        peak = equity_values[0]
        max_dd = 0
        for eq in equity_values:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
        
        returns = np.diff(equity_values) / equity_values[:-1]
        sharpe = np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(252 * 375)
        
        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        durations = []
        for t in self.trades:
            if t.exit_time and t.entry_time:
                durations.append((t.exit_time - t.entry_time).total_seconds() / 60)
        
        max_consec = 0
        current_consec = 0
        for t in self.trades:
            if t.pnl <= 0:
                current_consec += 1
                max_consec = max(max_consec, current_consec)
            else:
                current_consec = 0
        
        total_pnl = sum(t.pnl for t in self.trades)
        
        return BacktestResult(
            strategy_name=self.strategy.config.name,
            symbol=self.symbol,
            start_date=self.data.index[0],
            end_date=self.data.index[-1],
            total_trades=len(self.trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=len(winning) / len(self.trades) * 100,
            avg_profit_per_trade=total_pnl / len(self.trades),
            max_drawdown=max_dd * 100,
            sharpe_ratio=sharpe,
            total_pnl=total_pnl,
            total_pnl_pct=(total_pnl / self.capital) * 100,
            profit_factor=profit_factor,
            avg_trade_duration=np.mean(durations) if durations else 0,
            max_consecutive_losses=max_consec,
            params=self.strategy.get_current_params(),
            equity_curve=self.equity_curve,
            trades=[{
                'entry_time': t.entry_time.isoformat(),
                'exit_time': t.exit_time.isoformat() if t.exit_time else None,
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'pnl': t.pnl,
                'pnl_pct': t.pnl_pct,
                'exit_reason': t.exit_reason,
                'option_type': t.option_type,
                'strike': t.strike,
                'is_partial_exit': t.is_partial_exit,
            } for t in self.trades],
        )


class DataGenerator:
    """Generates synthetic NSE-like intraday data for testing."""

    # ═══════════════════════════════════════════════════════════
    # SYMBOL-SPECIFIC VOLATILITY
    # ═══════════════════════════════════════════════════════════
    SYMBOL_VOLATILITY = {
        "NIFTY50": 0.0008,
        "NIFTY": 0.0008,
        "BANKNIFTY": 0.0015,
        "FINNIFTY": 0.0012,
        "SENSEX": 0.0006,
        "MIDCPNIFTY": 0.0010,
    }

    @staticmethod
    def generate_synthetic_data(
        days: int = 30,
        symbol: str = "NIFTY50",
        start_price: float = None,
        volatility: float = None,  # Now optional — uses symbol-specific default
        trend_bias: float = 0.0001,
        seed: Optional[int] = None
    ) -> pd.DataFrame:
        # Symbol-specific base prices for realistic backtesting
        symbol_prices = {
            "NIFTY50": 24500,
            "BANKNIFTY": 48000,
            "FINNIFTY": 20500,
            "SENSEX": 75000,
        }
        
        # ── NEW: Use symbol-specific volatility ──
        clean_symbol = symbol.upper().replace("-INDEX", "").replace("NSE:", "").replace("BSE:", "")
        if volatility is None:
            volatility = DataGenerator.SYMBOL_VOLATILITY.get(clean_symbol, 0.0008)
        
        start_price = start_price or symbol_prices.get(clean_symbol, 24500)
        
        if seed is not None:
            np.random.seed(seed)
        else:
            # Dynamic seed based on current time for non-deterministic backtests
            np.random.seed(int(datetime.now().timestamp()) % (2**32))
        
        all_bars = []
        current_price = start_price
        
        for day in range(days):
            date = datetime(2024, 1, 1) + timedelta(days=day)
            if date.weekday() >= 5:
                continue
            
            daily_return = np.random.normal(trend_bias, volatility * 15)
            gap = np.random.normal(0, volatility * 5)
            open_price = current_price * (1 + gap)
            
            minutes = []
            prices = []
            volumes = []
            
            for minute in range(375):
                time_of_day = minute / 375
                vol_multiplier = 1.5 if time_of_day < 0.1 or time_of_day > 0.85 else 0.8
                deviation = (prices[-1] if prices else open_price) - open_price
                mean_reversion = -deviation * 0.001
                ret = np.random.normal(mean_reversion / 375, volatility * vol_multiplier)
                
                if minute == 0:
                    price = open_price
                else:
                    price = prices[-1] * (1 + ret)
                
                prices.append(price)
                base_vol = 100000
                vol_multiplier_vol = 2.0 if time_of_day < 0.1 or time_of_day > 0.85 else 0.5
                volume = int(np.random.poisson(base_vol * vol_multiplier_vol))
                volumes.append(volume)
                
                timestamp = datetime.combine(date.date(), datetime.min.time()) + \
                           timedelta(hours=9, minutes=15) + timedelta(minutes=minute)
                minutes.append(timestamp)
            
            for i in range(0, len(prices), 5):
                if i + 4 < len(prices):
                    all_bars.append({
                        'timestamp': minutes[i],
                        'open': prices[i],
                        'high': max(prices[i:i+5]),
                        'low': min(prices[i:i+5]),
                        'close': prices[i+4],
                        'volume': sum(volumes[i:i+5])
                    })
            
            current_price = prices[-1] * (1 + daily_return)
        
        df = pd.DataFrame(all_bars)
        df.set_index('timestamp', inplace=True)
        return df
    
    @staticmethod
    def load_csv_data(filepath: str) -> pd.DataFrame:
        df = pd.read_csv(filepath)
        time_cols = ['timestamp', 'date', 'time', 'datetime', 'Timestamp', 'Date']
        for col in time_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
                df.set_index(col, inplace=True)
                break
        
        required = ['open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing columns: {missing}. Available: {list(df.columns)}")
        
        return df