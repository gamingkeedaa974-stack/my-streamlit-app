"""
strategy.py
Base strategy classes and concrete implementations for NSE options trading.
Supports both CE (Call) and PE (Put) signals based on market direction.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
import pandas as pd
import numpy as np


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ENUMS & DATA MODELS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class SignalAction(str, Enum):
    HOLD = "HOLD"
    BUY_CE = "BUY_CE"      # Bullish â€” buy Call option
    BUY_PE = "BUY_PE"      # Bearish â€” buy Put option
    EXIT = "EXIT"

class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"

class MarketRegime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass
class Bar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class OptionQuote(BaseModel):
    symbol: str
    strike: float
    option_type: OptionType
    expiry: datetime
    ltp: float
    bid: float
    ask: float
    oi: int
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        return self.spread / self.ltp if self.ltp > 0 else 0


class Signal(BaseModel):
    action: SignalAction
    underlying_symbol: str
    confidence: float = Field(ge=0.0, le=1.0)
    stop_loss_pct: float = 0.30
    target_pct: float = 0.60
    reason: str = ""
    timestamp: Optional[datetime] = None
    option_type: Optional[OptionType] = None
    strike: Optional[float] = None


class StrategyConfig(BaseModel):
    name: str = "base"
    lookback_period: int = 20
    confidence_threshold: float = 0.55


class BacktestResult(BaseModel):
    strategy_name: str
    symbol: str
    start_date: datetime
    end_date: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_profit_per_trade: float
    max_drawdown: float
    sharpe_ratio: float
    total_pnl: float
    total_pnl_pct: float
    profit_factor: float
    avg_trade_duration: float
    max_consecutive_losses: int
    params: Dict[str, Any] = Field(default_factory=dict)
    equity_curve: List[Dict] = Field(default_factory=list)
    trades: List[Dict] = Field(default_factory=list)

    def score(self) -> float:
        """Composite score for optimization ranking. Higher is better."""
        if self.total_trades == 0:
            return -999.0
        trade_penalty = -50 if self.total_trades < 3 else 0
        return (
            self.total_pnl_pct * 2.0 +
            self.sharpe_ratio * 10.0 +
            self.win_rate * 0.5 -
            self.max_drawdown * 1.5 +
            trade_penalty
        )


class OptionsChainProvider(ABC):
    @abstractmethod
    async def get_atm_strike(self, symbol: str) -> float:
        pass

    @abstractmethod
    async def get_quote(self, symbol: str, strike: float, opt_type: OptionType) -> OptionQuote:
        pass

    @abstractmethod
    async def is_liquid(self, quote: OptionQuote, max_spread_pct: float = 0.03, min_oi: int = 500_000) -> bool:
        pass


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# BASE STRATEGY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class BaseStrategy(ABC):
    # NSE intraday entry window: avoid 9:15-9:35 gap noise & 14:30-15:30 square-off spikes
    ENTRY_WINDOW_START: time = time(9, 35)
    ENTRY_WINDOW_END: time = time(14, 30)
    SQUARE_OFF_TIME: time = time(15, 15)

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.bars: List[Bar] = []
        self.chain: Optional[OptionsChainProvider] = None
        self._current_regime: MarketRegime = MarketRegime.UNKNOWN
        self._last_signal_time: Optional[datetime] = None

    @abstractmethod
    def reset(self) -> None:
        """Reset all daily/stateful strategy data. Called by engine at day boundaries."""
        pass

    def ingest_bar(self, bar: Bar) -> None:
        self.bars.append(bar)
        if len(self.bars) > 500:
            self.bars = self.bars[-500:]

    @abstractmethod
    async def generate_signal(self, symbol: str, timestamp: datetime) -> Signal:
        pass

    def get_current_params(self) -> Dict[str, Any]:
        return self.config.model_dump()

    def _get_bars_df(self) -> pd.DataFrame:
        if not self.bars:
            return pd.DataFrame()
        df = pd.DataFrame([{
            'open': b.open, 'high': b.high, 'low': b.low,
            'close': b.close, 'volume': b.volume, 'timestamp': b.timestamp
        } for b in self.bars])
        df.set_index('timestamp', inplace=True)
        return df

    def _detect_regime(self, df: pd.DataFrame) -> MarketRegime:
        if len(df) < 20:
            return MarketRegime.UNKNOWN

        returns = df['close'].pct_change().dropna()
        if len(returns) < 10:
            return MarketRegime.UNKNOWN

        # Annualize using 5-min bar factor: 252 days * 75 bars/day
        bars_per_day = 75
        vol = returns.rolling(20).std().iloc[-1] * np.sqrt(252 * bars_per_day)
        trend = (df['close'].iloc[-1] / df['close'].iloc[-20] - 1)

        # Thresholds calibrated for intraday 5-min bars:
        #   vol: NIFTY ~0.10-0.15, BANKNIFTY ~0.18-0.25
        #   trend: 100-min move, 0.3% is a meaningful intraday drift
        if vol > 0.15:
            regime = MarketRegime.VOLATILE
        elif trend > 0.003:
            regime = MarketRegime.TRENDING_UP
        elif trend < -0.003:
            regime = MarketRegime.TRENDING_DOWN
        else:
            regime = MarketRegime.RANGING

        self._current_regime = regime
        return regime

    def _is_entry_window(self, timestamp: datetime) -> bool:
        """Return True if timestamp is inside the allowed entry window."""
        t = timestamp.time()
        return self.ENTRY_WINDOW_START <= t <= self.ENTRY_WINDOW_END

    def _is_square_off_time(self, timestamp: datetime) -> bool:
        return timestamp.time() >= self.SQUARE_OFF_TIME

    def _allowed_regimes(self) -> List[MarketRegime]:
        """Override in subclass to declare which regimes this strategy trades."""
        return [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN,
                MarketRegime.RANGING, MarketRegime.VOLATILE]


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ORB STRATEGY (Opening Range Breakout)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class ORBConfig(StrategyConfig):
    name: str = "orb"
    opening_range_minutes: int = 15
    breakout_threshold: float = 0.0005
    volume_multiplier: float = 0.4
    min_confidence: float = 0.45

    def get_param_space(self) -> Dict[str, List]:
        return {
            "opening_range_minutes": [10, 15, 20, 25, 30],
            "breakout_threshold": [0.0003, 0.0005, 0.0008, 0.001, 0.0015],
            "volume_multiplier": [0.5, 0.8, 1.0, 1.2, 1.5],
            "min_confidence": [0.40, 0.45, 0.50, 0.55, 0.60],
            "lookback_period": [15, 20, 25, 30, 40],
            "confidence_threshold": [0.50, 0.55, 0.60, 0.65, 0.70],
        }


class ORBStrategy(BaseStrategy):
    """
    Opening Range Breakout with dual-direction support.
    - Break above OR high + volume â†’ BUY_CE (bullish)
    - Break below OR low + volume â†’ BUY_PE (bearish)
    - Exit: reversion to OR (price comes back inside the range)
    Regime: VOLATILE, TRENDING_UP, TRENDING_DOWN only.
    """

    def __init__(self, config: ORBConfig = None):
        super().__init__(config or ORBConfig())
        self._or_high: Optional[float] = None
        self._or_low: Optional[float] = None
        self._or_volume: Optional[float] = None
        self._or_set: bool = False
        self._attempted_today: set = set()
        self._current_trade: Dict[str, str] = {}  # symbol -> "CE"|"PE"

    def reset(self) -> None:
        self._or_high = None
        self._or_low = None
        self._or_volume = None
        self._or_set = False
        self._attempted_today.clear()
        self._current_trade.clear()

    def _allowed_regimes(self) -> List[MarketRegime]:
        return [MarketRegime.VOLATILE, MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]

    async def generate_signal(self, symbol: str, timestamp: datetime) -> Signal:
        df = self._get_bars_df()
        if len(df) < 5:
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        current_price = df['close'].iloc[-1]
        regime = self._detect_regime(df)

        # Regime gate
        if regime not in self._allowed_regimes():
            return Signal(
                action=SignalAction.HOLD,
                underlying_symbol=symbol,
                confidence=0.0,
                reason=f"ORB blocked â€” regime {regime.value}"
            )

        # â”€â”€ Build Opening Range in first N minutes â”€â”€
        or_end = time(9, 15 + self.config.opening_range_minutes)
        if timestamp.time() <= or_end:
            or_bars = df[df.index.map(lambda x: x.time() if hasattr(x, 'time') else x.to_pydatetime().time()) <= or_end]
            if len(or_bars) > 0:
                self._or_high = or_bars['high'].max()
                self._or_low = or_bars['low'].min()
                self._or_volume = or_bars['volume'].mean()
                self._or_set = True
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        if not self._or_set or self._or_high is None or self._or_low is None:
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        # â”€â”€ Exit logic: reversion to OR OR square-off time â”€â”€
        if symbol in self._current_trade:
            if self._is_square_off_time(timestamp):
                del self._current_trade[symbol]
                return Signal(
                    action=SignalAction.EXIT,
                    underlying_symbol=symbol,
                    confidence=0.9,
                    reason="ORB exit â€” square-off time"
                )
            # Real exit: price re-enters the opening range
            if self._or_low < current_price < self._or_high:
                trade_side = self._current_trade.pop(symbol, None)
                return Signal(
                    action=SignalAction.EXIT,
                    underlying_symbol=symbol,
                    confidence=0.8,
                    reason=f"ORB exit â€” reversion to OR (price {current_price:.2f} inside {self._or_low:.2f}-{self._or_high:.2f})",
                    option_type=OptionType.CE if trade_side == "CE" else OptionType.PE
                )
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        # â”€â”€ Entry logic â”€â”€
        if not self._is_entry_window(timestamp):
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        if symbol in self._attempted_today:
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        or_range = self._or_high - self._or_low
        if or_range <= 0:
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        upper_breakout = self._or_high + or_range * self.config.breakout_threshold
        lower_breakout = self._or_low - or_range * self.config.breakout_threshold

        current_volume = df['volume'].iloc[-1]
        volume_ok = self._or_volume and current_volume > self._or_volume * self.config.volume_multiplier

        confidence = 0.0
        action = SignalAction.HOLD
        reason = ""
        opt_type = None

        # Bullish breakout â†’ BUY CE
        if current_price > upper_breakout and volume_ok:
            confidence = min(0.95, 0.65 + (current_price - upper_breakout) / or_range * 0.3)
            action = SignalAction.BUY_CE
            reason = f"ORB bullish breakout: {current_price:.2f} > {upper_breakout:.2f} (vol: {current_volume:.0f} > {self._or_volume:.0f})"
            opt_type = OptionType.CE
            self._current_trade[symbol] = "CE"
            self._attempted_today.add(symbol)

        # Bearish breakout â†’ BUY PE
        elif current_price < lower_breakout and volume_ok:
            confidence = min(0.95, 0.65 + (lower_breakout - current_price) / or_range * 0.3)
            action = SignalAction.BUY_PE
            reason = f"ORB bearish breakout: {current_price:.2f} < {lower_breakout:.2f} (vol: {current_volume:.0f} > {self._or_volume:.0f})"
            opt_type = OptionType.PE
            self._current_trade[symbol] = "PE"
            self._attempted_today.add(symbol)

        if action != SignalAction.HOLD and confidence >= self.config.min_confidence:
            return Signal(
                action=action,
                underlying_symbol=symbol,
                confidence=confidence,
                reason=reason,
                timestamp=timestamp,
                option_type=opt_type
            )

        return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# VWAP MOMENTUM STRATEGY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class VWAPMomentumConfig(StrategyConfig):
    name: str = "vwap_momentum"
    vwap_lookback: int = 10
    momentum_threshold: float = 0.0003
    volume_confirm: bool = False
    min_confidence: float = 0.40

    def get_param_space(self) -> Dict[str, List]:
        return {
            "vwap_lookback": [5, 10, 15, 20, 25],
            "momentum_threshold": [0.0002, 0.0003, 0.0005, 0.0008, 0.001],
            "volume_confirm": [True, False],
            "min_confidence": [0.35, 0.40, 0.45, 0.50, 0.55],
            "lookback_period": [15, 20, 25, 30, 40],
            "confidence_threshold": [0.50, 0.55, 0.60, 0.65, 0.70],
        }


class VWAPMomentumStrategy(BaseStrategy):
    """
    VWAP-based momentum with dual-direction support.
    - Price > VWAP + momentum â†’ BUY_CE (bullish momentum)
    - Price < VWAP + momentum â†’ BUY_PE (bearish momentum)
    - Exit: VWAP cross (momentum reversal)
    Regime: TRENDING_UP, TRENDING_DOWN only.
    """

    def __init__(self, config: VWAPMomentumConfig = None):
        super().__init__(config or VWAPMomentumConfig())
        self._current_trade: Dict[str, str] = {}  # symbol -> "CE"|"PE"
        self._attempted_today: set = set()

    def reset(self) -> None:
        self._current_trade.clear()
        self._attempted_today.clear()

    def _allowed_regimes(self) -> List[MarketRegime]:
        return [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]

    def _calculate_vwap(self, df: pd.DataFrame) -> float:
        if len(df) < 2:
            return df['close'].iloc[-1] if len(df) > 0 else 0

        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        return vwap.iloc[-1]

    def _calculate_momentum(self, df: pd.DataFrame) -> float:
        if len(df) < 5:
            return 0.0
        return (df['close'].iloc[-1] - df['close'].iloc[-5]) / df['close'].iloc[-5]

    async def generate_signal(self, symbol: str, timestamp: datetime) -> Signal:
        df = self._get_bars_df()
        if len(df) < self.config.vwap_lookback:
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        current_price = df['close'].iloc[-1]
        vwap = self._calculate_vwap(df)
        momentum = self._calculate_momentum(df)

        if not vwap or vwap <= 0:
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        regime = self._detect_regime(df)

        # Regime gate
        if regime not in self._allowed_regimes():
            return Signal(
                action=SignalAction.HOLD,
                underlying_symbol=symbol,
                confidence=0.0,
                reason=f"VWAP blocked â€” regime {regime.value}"
            )

        # â”€â”€ Exit logic: VWAP cross OR square-off â”€â”€
        if symbol in self._current_trade:
            if self._is_square_off_time(timestamp):
                del self._current_trade[symbol]
                return Signal(
                    action=SignalAction.EXIT,
                    underlying_symbol=symbol,
                    confidence=0.9,
                    reason="VWAP exit â€” square-off time"
                )
            trade_side = self._current_trade[symbol]
            if (trade_side == "CE" and current_price < vwap) or \
               (trade_side == "PE" and current_price > vwap):
                del self._current_trade[symbol]
                return Signal(
                    action=SignalAction.EXIT,
                    underlying_symbol=symbol,
                    confidence=0.8,
                    reason=f"VWAP cross â€” momentum reversal (price {current_price:.2f} vs VWAP {vwap:.2f})",
                    option_type=OptionType.CE if trade_side == "CE" else OptionType.PE
                )
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        # â”€â”€ Entry logic â”€â”€
        if not self._is_entry_window(timestamp):
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        if symbol in self._attempted_today:
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        volume_ok = True
        if self.config.volume_confirm:
            avg_vol = df['volume'].rolling(10).mean().iloc[-1]
            current_vol = df['volume'].iloc[-1]
            volume_ok = current_vol > avg_vol * 1.1

        confidence = 0.0
        action = SignalAction.HOLD
        reason = ""
        opt_type = None

        # Bullish: Price above VWAP + positive momentum â†’ BUY CE
        if current_price > vwap * (1 + self.config.momentum_threshold) and momentum > 0 and volume_ok:
            confidence = min(0.95, 0.60 + abs(momentum) * 10)
            action = SignalAction.BUY_CE
            reason = f"VWAP momentum bullish: price {current_price:.2f} > VWAP {vwap:.2f}, mom {momentum:.4f}"
            opt_type = OptionType.CE
            self._current_trade[symbol] = "CE"
            self._attempted_today.add(symbol)

        # Bearish: Price below VWAP + negative momentum â†’ BUY PE
        elif current_price < vwap * (1 - self.config.momentum_threshold) and momentum < 0 and volume_ok:
            confidence = min(0.95, 0.60 + abs(momentum) * 10)
            action = SignalAction.BUY_PE
            reason = f"VWAP momentum bearish: price {current_price:.2f} < VWAP {vwap:.2f}, mom {momentum:.4f}"
            opt_type = OptionType.PE
            self._current_trade[symbol] = "PE"
            self._attempted_today.add(symbol)

        if action != SignalAction.HOLD and confidence >= self.config.min_confidence:
            return Signal(
                action=action,
                underlying_symbol=symbol,
                confidence=confidence,
                reason=reason,
                timestamp=timestamp,
                option_type=opt_type
            )

        return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# MEAN REVERSION STRATEGY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class MeanReversionConfig(StrategyConfig):
    name: str = "mean_reversion"
    lookback_period: int = 15
    deviation_threshold: float = 0.005
    min_confidence: float = 0.40
    rsi_period: int = 10
    rsi_oversold: float = 40.0
    rsi_overbought: float = 60.0

    def get_param_space(self) -> Dict[str, List]:
        return {
            "lookback_period": [10, 15, 20, 25, 30],
            "deviation_threshold": [0.003, 0.005, 0.008, 0.01, 0.015],
            "min_confidence": [0.35, 0.40, 0.45, 0.50, 0.55],
            "rsi_period": [7, 10, 14, 20, 25],
            "rsi_oversold": [30, 35, 40, 45],
            "rsi_overbought": [55, 60, 65, 70],
            "confidence_threshold": [0.50, 0.55, 0.60, 0.65, 0.70],
        }


class MeanReversionStrategy(BaseStrategy):
    """
    Mean reversion with dual-direction support.
    - Price far below mean + RSI oversold â†’ BUY_CE (expect bounce up)
    - Price far above mean + RSI overbought â†’ BUY_PE (expect pullback)
    - Exit: price returns to mean (deviation normalizes)
    Regime: RANGING only.
    """

    def __init__(self, config: MeanReversionConfig = None):
        super().__init__(config or MeanReversionConfig())
        self._current_trade: Dict[str, str] = {}  # symbol -> "CE"|"PE"
        self._attempted_today: set = set()

    def reset(self) -> None:
        self._current_trade.clear()
        self._attempted_today.clear()

    def _allowed_regimes(self) -> List[MarketRegime]:
        return [MarketRegime.RANGING]

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]

    async def generate_signal(self, symbol: str, timestamp: datetime) -> Signal:
        df = self._get_bars_df()
        if len(df) < self.config.lookback_period:
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        current_price = df['close'].iloc[-1]
        sma = df['close'].rolling(self.config.lookback_period).mean().iloc[-1]
        std = df['close'].rolling(self.config.lookback_period).std().iloc[-1]

        if not sma or not std or std == 0:
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        deviation = (current_price - sma) / std
        rsi = self._calculate_rsi(df['close'], self.config.rsi_period)
        regime = self._detect_regime(df)

        # Regime gate
        if regime not in self._allowed_regimes():
            return Signal(
                action=SignalAction.HOLD,
                underlying_symbol=symbol,
                confidence=0.0,
                reason=f"MeanRev blocked â€” regime {regime.value}"
            )

        # â”€â”€ Exit logic: mean touch OR square-off â”€â”€
        if symbol in self._current_trade:
            if self._is_square_off_time(timestamp):
                del self._current_trade[symbol]
                return Signal(
                    action=SignalAction.EXIT,
                    underlying_symbol=symbol,
                    confidence=0.9,
                    reason="MeanRev exit â€” square-off time"
                )
            # Real exit: price returns close to mean (deviation < 0.5 std)
            if abs(deviation) < 0.5:
                trade_side = self._current_trade.pop(symbol, None)
                return Signal(
                    action=SignalAction.EXIT,
                    underlying_symbol=symbol,
                    confidence=0.8,
                    reason=f"MeanRev exit â€” price back to mean (deviation {deviation:.2f})",
                    option_type=OptionType.CE if trade_side == "CE" else OptionType.PE
                )
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        # â”€â”€ Entry logic â”€â”€
        if not self._is_entry_window(timestamp):
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        if symbol in self._attempted_today:
            return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)

        confidence = 0.0
        action = SignalAction.HOLD
        reason = ""
        opt_type = None

        # Oversold â†’ expect bounce UP â†’ BUY CE
        if deviation < -self.config.deviation_threshold and rsi < self.config.rsi_oversold:
            confidence = min(0.95, 0.60 + abs(deviation) * 0.1 + (self.config.rsi_oversold - rsi) * 0.01)
            action = SignalAction.BUY_CE
            reason = f"Mean reversion bullish: dev {deviation:.2f}, RSI {rsi:.1f} (oversold)"
            opt_type = OptionType.CE
            self._current_trade[symbol] = "CE"
            self._attempted_today.add(symbol)

        # Overbought â†’ expect pullback DOWN â†’ BUY PE
        elif deviation > self.config.deviation_threshold and rsi > self.config.rsi_overbought:
            confidence = min(0.95, 0.60 + deviation * 0.1 + (rsi - self.config.rsi_overbought) * 0.01)
            action = SignalAction.BUY_PE
            reason = f"Mean reversion bearish: dev {deviation:.2f}, RSI {rsi:.1f} (overbought)"
            opt_type = OptionType.PE
            self._current_trade[symbol] = "PE"
            self._attempted_today.add(symbol)

        if action != SignalAction.HOLD and confidence >= self.config.min_confidence:
            return Signal(
                action=action,
                underlying_symbol=symbol,
                confidence=confidence,
                reason=reason,
                timestamp=timestamp,
                option_type=opt_type
            )

        return Signal(action=SignalAction.HOLD, underlying_symbol=symbol, confidence=0.0)


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# STRATEGY REGISTRY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class StrategyRegistry:
    _strategies = {
        "orb": ORBStrategy,
        "vwap_momentum": VWAPMomentumStrategy,
        "mean_reversion": MeanReversionStrategy,
    }

    _configs = {
        "orb": ORBConfig,
        "vwap_momentum": VWAPMomentumConfig,
        "mean_reversion": MeanReversionConfig,
    }

    @classmethod
    def get(cls, name: str):
        return cls._strategies.get(name, ORBStrategy)

    @classmethod
    def get_config_class(cls, name: str):
        return cls._configs.get(name, ORBConfig)

    @classmethod
    def list_strategies(cls) -> List[str]:
        return list(cls._strategies.keys())
