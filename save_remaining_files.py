# save_remaining_files.py
# Run this to generate all remaining project files

from pathlib import Path
import os

BASE = Path("/mnt/agents/output/nse_trading_bot")

# ============ FYERS_BOT.PY ============
(BASE / "backend" / "fyers_bot.py").write_text('''\
"""fyers_bot.py - Async execution engine with mock provider for Phase 1 testing"""

from __future__ import annotations
import asyncio
import uuid
import random
from datetime import datetime, time, timedelta
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field

from strategy import BaseStrategy, StrategyConfig, Signal, SignalAction, Bar, OptionType, OptionQuote
from risk_manager import RiskManager, RiskConfig, OrderFill
from audit_logger import AuditLogger, AuditEventType


class BotConfig(BaseModel):
    mode: str = Field(default="PAPER", pattern="^(PAPER|LIVE)$")
    symbols: List[str] = Field(default=["NSE:NIFTY50-INDEX", "NSE:SENSEX-INDEX"])
    bar_interval_seconds: int = 60
    ws_reconnect_max: int = 10
    ws_reconnect_base_delay: float = 1.0
    ws_reconnect_max_delay: float = 60.0
    heartbeat_interval: float = 30.0
    reconcile_interval_seconds: int = 60
    order_timeout_seconds: int = 10
    fyers_app_id: str = ""
    fyers_access_token: str = ""
    static_ip: str = ""


class MockOptionsChainProvider:
    """Local mock provider for Phase 1 testing without API costs."""
    
    def __init__(self):
        self._spot_prices = {
            "NSE:NIFTY50-INDEX": 24500.0,
            "NSE:BANKNIFTY-INDEX": 52000.0,
            "NSE:FINNIFTY-INDEX": 23500.0,
            "BSE:SENSEX-INDEX": 80000.0,
        }
    
    def update_spot(self, symbol: str, price: float):
        self._spot_prices[symbol] = price
    
    async def get_atm_strike(self, symbol: str) -> float:
        spot = self._spot_prices.get(symbol, 24500.0)
        step = 100 if "BANK" in symbol.upper() else 50
        return round(spot / step) * step
    
    async def get_quote(self, symbol: str, strike: float, opt_type) -> OptionQuote:
        spot = self._spot_prices.get(symbol, 24500.0)
        moneyness = abs(strike - spot) / spot
        intrinsic = max(0, (spot - strike) if opt_type == OptionType.CE else (strike - spot))
        time_value = max(20, 150 * (1 - moneyness * 2))
        base_premium = intrinsic + time_value
        
        return OptionQuote(
            symbol=f"{symbol.split(':')[-1].replace('-INDEX', '')}{strike:.0f}{opt_type.value}",
            strike=strike, option_type=opt_type, expiry=datetime.now(),
            ltp=base_premium, bid=base_premium - 0.3, ask=base_premium + 0.3,
            oi=random.randint(500_000, 2_000_000), iv=18.0 + moneyness * 15,
            delta=0.5 if opt_type == OptionType.CE else -0.5,
            gamma=0.01, theta=-2.0, vega=1.5,
        )
    
    async def is_liquid(self, quote, max_spread_pct=0.03, min_oi=500_000) -> bool:
        return quote.spread_pct <= max_spread_pct and quote.oi >= min_oi


class OrderRequest(BaseModel):
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str; qty: int; side: int; type: int
    limitPrice: float = 0.0; stopPrice: float = 0.0
    disclosedQty: int = 0; validity: str = "DAY"
    offlineOrder: bool = False; stopLoss: float = 0.0
    takeProfit: float = 0.0; algo_id: str = "RETAIL-WB-001"
    
    def to_fyers_payload(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol, "qty": self.qty, "type": self.type, "side": self.side,
            "limitPrice": self.limitPrice, "stopPrice": self.stopPrice,
            "disclosedQty": self.disclosedQty, "validity": self.validity,
            "offlineOrder": self.offlineOrder, "stopLoss": self.stopLoss,
            "takeProfit": self.takeProfit, "productType": "INTRADAY",
            "algo_id": self.algo_id,
        }


class PendingOrder(BaseModel):
    request: OrderRequest; submitted_at: datetime
    status: str = "PENDING"; broker_order_id: Optional[str] = None


class OrderManager:
    def __init__(self, audit: AuditLogger, timeout: int = 10):
        self.audit = audit; self.timeout = timeout
        self._pending: Dict[str, PendingOrder] = {}
        self._lock = asyncio.Lock()
    
    async def place_order(self, request: OrderRequest) -> tuple[bool, str, Optional[str]]:
        async with self._lock:
            if request.idempotency_key in self._pending:
                existing = self._pending[request.idempotency_key]
                if existing.status == "PENDING": return False, "duplicate pending", None
                if existing.status in ("ACK", "FILLED"): return True, "already processed", existing.broker_order_id
            pending = PendingOrder(request=request, submitted_at=datetime.now())
            self._pending[request.idempotency_key] = pending
        
        await asyncio.sleep(0.05)
        broker_id = str(uuid.uuid4())[:8]
        async with self._lock:
            pending.status = "ACK"; pending.broker_order_id = broker_id
        await self.audit.log(AuditEventType.ORDER_ACK, symbol=request.symbol,
                           details={"idempotency_key": request.idempotency_key, "broker_order_id": broker_id})
        return True, "order acknowledged", broker_id
    
    async def cancel_all_pending(self) -> None:
        async with self._lock:
            for key, pending in list(self._pending.items()):
                if pending.status == "PENDING": pending.status = "CANCELLED"


class FyersBot:
    def __init__(self, config: BotConfig, strategy: BaseStrategy, risk_config: RiskConfig):
        self.config = config; self.strategy = strategy
        self.chain = MockOptionsChainProvider()
        self.risk = RiskManager(risk_config, self.chain)
        self.audit = AuditLogger()
        self.orders = OrderManager(self.audit, timeout=config.order_timeout_seconds)
        self._running = False; self._reconnect_count = 0
        self._tasks: List[asyncio.Task] = []
    
    async def run(self) -> None:
        await self.audit.start_session()
        await self.risk.reset_day(datetime.now().date())
        self._running = True
        
        self._tasks = [
            asyncio.create_task(self._market_data_simulator(), name="market_data"),
            asyncio.create_task(self._heartbeat_loop(), name="heartbeat"),
        ]
        
        while self._running:
            now = datetime.now()
            if now.time() >= time(15, 20):
                await self._square_off_all("market close"); break
            state = await self.risk.get_state_snapshot()
            if state.circuit_breaker_triggered:
                await self._square_off_all("circuit breaker"); break
            await asyncio.sleep(1)
        await self.shutdown()
    
    async def shutdown(self) -> None:
        self._running = False
        for task in self._tasks:
            if task and not task.done():
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass
        await self.orders.cancel_all_pending()
        await self._square_off_all("shutdown")
        await self.audit.close()
    
    async def _market_data_simulator(self) -> None:
        import random
        base_prices = {
            "NSE:NIFTY50-INDEX": 24500.0, "NSE:BANKNIFTY-INDEX": 52000.0,
            "NSE:FINNIFTY-INDEX": 23500.0, "BSE:SENSEX-INDEX": 80000.0,
        }
        while self._running:
            now = datetime.now()
            if now.time() < time(9, 15) or now.time() > time(15, 30):
                await asyncio.sleep(60); continue
            for symbol in self.config.symbols:
                base = base_prices.get(symbol, 24500.0)
                change = random.gauss(0, base * 0.0005)
                new_price = base + change; base_prices[symbol] = new_price
                bar = Bar(symbol=symbol, timestamp=now,
                         open=new_price - change/2, high=new_price + abs(change),
                         low=new_price - abs(change), close=new_price,
                         volume=random.randint(1000, 10000))
                self.strategy.ingest_bar(bar)
                if now.second % self.config.bar_interval_seconds == 0:
                    signal = await self.strategy.generate_signal(symbol, now)
                    await self._process_signal(signal)
            await asyncio.sleep(1)
    
    async def _process_signal(self, signal: Signal) -> None:
        await self.audit.log_signal(signal, signal.underlying_symbol)
        allowed, reason, lot_size = await self.risk.can_trade(signal, datetime.now())
        await self.audit.log_risk_check(signal, allowed, reason, lot_size)
        if not allowed: return
        if signal.action == SignalAction.EXIT: await self._execute_exit(signal)
        elif signal.action in (SignalAction.BUY_CE, SignalAction.BUY_PE):
            await self._execute_entry(signal, lot_size or 0)
    
    async def _execute_entry(self, signal: Signal, qty: int) -> None:
        opt_type = OptionType.CE if signal.action == SignalAction.BUY_CE else OptionType.PE
        atm = await self.chain.get_atm_strike(signal.underlying_symbol)
        quote = await self.chain.get_quote(signal.underlying_symbol, atm, opt_type)
        order = OrderRequest(symbol=quote.symbol, qty=qty, side=1, type=2 if self.config.mode == "LIVE" else 1,
                           limitPrice=quote.ltp if self.config.mode == "PAPER" else 0.0,
                           stopLoss=signal.stop_loss_pct * 100, takeProfit=signal.target_pct * 100)
        success, msg, broker_id = await self.orders.place_order(order)
        if success and broker_id:
            fill = OrderFill(symbol=quote.symbol, underlying=signal.underlying_symbol, strike=atm,
                           option_type=opt_type, price=quote.ltp, quantity=qty, side="BUY",
                           is_opening=True, is_closing=False, time=datetime.now(),
                           stop_loss_pct=signal.stop_loss_pct, target_pct=signal.target_pct)
            await self.risk.on_fill(fill)
            print(f"[TRADE] ENTER {quote.symbol} @ ₹{quote.ltp:.2f} x {qty}")
    
    async def _execute_exit(self, signal: Signal) -> None:
        positions = await self.risk.get_positions()
        pos = positions.get(signal.underlying_symbol)
        if not pos: return
        order = OrderRequest(symbol=pos.symbol, qty=abs(pos.quantity), side=-1, type=2)
        success, msg, broker_id = await self.orders.place_order(order)
        if success:
            fill = OrderFill(symbol=pos.symbol, underlying=signal.underlying_symbol, strike=pos.strike,
                           option_type=pos.option_type, price=pos.entry_price, quantity=abs(pos.quantity),
                           side="SELL", is_opening=False, is_closing=True, time=datetime.now())
            await self.risk.on_fill(fill)
            print(f"[TRADE] EXIT {pos.symbol} @ ₹{pos.entry_price:.2f}")
    
    async def _square_off_all(self, reason: str) -> None:
        await self.audit.log(AuditEventType.CIRCUIT_BREAKER,
                           details={"reason": reason, "action": "square_off_all"})
        positions = await self.risk.get_positions()
        for underlying, pos in positions.items():
            signal = Signal(action=SignalAction.EXIT, underlying_symbol=underlying, reason=f"square off: {reason}")
            await self._execute_exit(signal)
    
    async def _heartbeat_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.config.heartbeat_interval)
            if self._reconnect_count > 3:
                await self.audit.log(AuditEventType.WEBSOCKET_STATUS,
                                   details={"warning": "multiple reconnects", "count": self._reconnect_count})
''')

print("fyers_bot.py written")

# ============ API_SERVER.PY ============
(BASE / "backend" / "api_server.py").write_text('''\
"""api_server.py - FastAPI backend with WebSocket for trading dashboard"""

from __future__ import annotations
import asyncio
import json
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from strategy import BaseStrategy, StrategyConfig, Signal, SignalAction, Bar, StrategyRegistry
from risk_manager import RiskManager, RiskConfig, RiskState, OrderFill
from audit_logger import AuditLogger, AuditEventType
from fyers_bot import FyersBot, BotConfig


class BotStatus(BaseModel):
    running: bool; mode: str; uptime_seconds: float
    symbols: List[str]; strategy: str; connected_to_broker: bool
    ws_reconnect_count: int; last_heartbeat: Optional[datetime] = None

class PositionView(BaseModel):
    symbol: str; underlying: str; option_type: str; strike: float
    entry_price: float; current_price: float; quantity: int
    unrealized_pnl: float; unrealized_pnl_pct: float
    stop_loss: float; target: float; delta: Optional[float] = None
    time_in_trade: str

class PortfolioSummary(BaseModel):
    capital: float; daily_pnl: float; daily_pnl_pct: float
    open_positions: int; margin_used_pct: float; available_margin: float
    net_delta: float; net_gamma: float; vix: Optional[float] = None
    circuit_breaker: bool; kill_switch: bool

class StrategyControl(BaseModel):
    action: str; mode: Optional[str] = None
    symbols: Optional[List[str]] = None; strategy_name: Optional[str] = None

class AlertMessage(BaseModel):
    level: str; message: str; timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict = Field(default_factory=dict)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock: self.active_connections.append(websocket)
    
    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections: self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        dead = []
        async with self._lock: connections = list(self.active_connections)
        for conn in connections:
            try: await conn.send_json(message)
            except Exception: dead.append(conn)
        if dead:
            async with self._lock:
                for d in dead:
                    if d in self.active_connections: self.active_connections.remove(d)


class TradingServerState:
    def __init__(self):
        self.bot: Optional[FyersBot] = None
        self.bot_task: Optional[asyncio.Task] = None
        self.manager = ConnectionManager()
        self.alerts: List[AlertMessage] = []
        self.max_alerts = 100
        self.start_time: Optional[datetime] = None
        self.config = BotConfig()
        self.risk_config = RiskConfig()
    
    async def start_bot(self, mode: str = "PAPER", symbols: Optional[List[str]] = None,
                       strategy_name: str = "orb") -> bool:
        if self.bot_task and not self.bot_task.done(): return False
        self.config.mode = mode
        if symbols: self.config.symbols = symbols
        strategy_cls = StrategyRegistry.get(strategy_name)
        strategy_config = StrategyConfig(name=strategy_name)
        from fyers_bot import MockOptionsChainProvider
        chain_provider = MockOptionsChainProvider()
        self.bot = FyersBot(config=self.config,
                          strategy=strategy_cls(strategy_config, chain_provider),
                          risk_config=self.risk_config)
        self.bot_task = asyncio.create_task(self._bot_wrapper(), name="bot_main")
        self.start_time = datetime.now()
        return True
    
    async def _bot_wrapper(self):
        try: await self.bot.run()
        except Exception as e:
            await self._broadcast_alert("CRITICAL", f"Bot crashed: {str(e)}", {"error": str(e)})
        finally: self.bot = None; self.bot_task = None
    
    async def stop_bot(self) -> bool:
        if self.bot: await self.bot.shutdown()
        if self.bot_task and not self.bot_task.done():
            self.bot_task.cancel()
            try: await self.bot_task
            except asyncio.CancelledError: pass
        self.bot = None; self.bot_task = None
        return True
    
    async def trigger_kill_switch(self, reason: str) -> None:
        if self.bot: await self.bot.risk.set_kill_switch(reason)
        await self._broadcast_alert("CRITICAL", f"KILL SWITCH: {reason}", {})
    
    async def square_off_all(self, reason: str) -> None:
        if self.bot: await self.bot._square_off_all(reason)
        await self._broadcast_alert("WARNING", f"Square off: {reason}", {})
    
    async def _broadcast_alert(self, level: str, message: str, metadata: dict):
        alert = AlertMessage(level=level, message=message, metadata=metadata)
        self.alerts.append(alert)
        if len(self.alerts) > self.max_alerts: self.alerts.pop(0)
        await self.manager.broadcast({"type": "ALERT", "data": alert.model_dump()})
    
    def get_status(self) -> BotStatus:
        if not self.bot:
            return BotStatus(running=False, mode=self.config.mode, uptime_seconds=0,
                           symbols=self.config.symbols, strategy="", connected_to_broker=False,
                           ws_reconnect_count=0, last_heartbeat=None)
        uptime = 0
        if self.start_time: uptime = (datetime.now() - self.start_time).total_seconds()
        return BotStatus(running=self.bot_task is not None and not self.bot_task.done(),
                        mode=self.config.mode, uptime_seconds=uptime,
                        symbols=self.config.symbols, strategy=self.bot.strategy.config.name,
                        connected_to_broker=True,
                        ws_reconnect_count=getattr(self.bot, '_reconnect_count', 0),
                        last_heartbeat=datetime.now())
    
    async def get_portfolio(self) -> PortfolioSummary:
        if not self.bot:
            return PortfolioSummary(capital=self.risk_config.capital, daily_pnl=0, daily_pnl_pct=0,
                                  open_positions=0, margin_used_pct=0, available_margin=self.risk_config.capital,
                                  net_delta=0, net_gamma=0, vix=None, circuit_breaker=False, kill_switch=False)
        state = await self.bot.risk.get_state_snapshot()
        positions = await self.bot.risk.get_positions()
        margin_used = sum(p.notional for p in positions.values())
        margin_pct = (margin_used / self.risk_config.capital) * 100 if self.risk_config.capital else 0
        return PortfolioSummary(capital=self.risk_config.capital, daily_pnl=state.daily_pnl,
                               daily_pnl_pct=(state.daily_pnl / self.risk_config.capital) * 100,
                               open_positions=len(positions), margin_used_pct=min(margin_pct, 100),
                               available_margin=self.risk_config.capital - margin_used,
                               net_delta=state.net_delta, net_gamma=state.net_gamma,
                               vix=state.last_vix, circuit_breaker=state.circuit_breaker_triggered,
                               kill_switch=state.daily_loss_limit_hit)
    
    async def get_positions(self) -> List[PositionView]:
        if not self.bot: return []
        positions = await self.bot.risk.get_positions()
        result = []
        for underlying, pos in positions.items():
            current_price = pos.entry_price
            pnl = (current_price - pos.entry_price) * pos.quantity
            pnl_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100 if pos.entry_price else 0
            time_in_trade = "00:00:00"
            if pos.entry_time:
                delta = datetime.now() - pos.entry_time
                time_in_trade = str(delta).split('.')[0]
            result.append(PositionView(symbol=pos.symbol, underlying=pos.underlying,
                                      option_type=pos.option_type.value, strike=pos.strike,
                                      entry_price=pos.entry_price, current_price=current_price,
                                      quantity=pos.quantity, unrealized_pnl=pnl, unrealized_pnl_pct=pnl_pct,
                                      stop_loss=pos.stop_loss_trigger, target=pos.target_trigger,
                                      delta=pos.delta, time_in_trade=time_in_trade))
        return result


state = TradingServerState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Trading API Server starting..."); yield
    if state.bot: await state.stop_bot()
    print("Trading API Server stopped.")


app = FastAPI(title="NSE Options Trading Bot API", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                  allow_methods=["*"], allow_headers=["*"])


@app.get("/")
async def root(): return {"status": "NSE Options Trading Bot API", "version": "2.0.0"}

@app.get("/api/status", response_model=BotStatus)
async def get_status(): return state.get_status()

@app.get("/api/portfolio", response_model=PortfolioSummary)
async def get_portfolio(): return await state.get_portfolio()

@app.get("/api/positions", response_model=List[PositionView])
async def get_positions(): return await state.get_positions()

@app.get("/api/alerts", response_model=List[AlertMessage])
async def get_alerts(limit: int = 50): return state.alerts[-limit:]

@app.post("/api/control")
async def control_bot(control: StrategyControl, background_tasks: BackgroundTasks):
    if control.action == "START":
        if control.mode not in ("PAPER", "LIVE"): raise HTTPException(400, "Mode must be PAPER or LIVE")
        success = await state.start_bot(mode=control.mode, symbols=control.symbols,
                                       strategy_name=control.strategy_name or "orb")
        if not success: raise HTTPException(409, "Bot is already running")
        await state._broadcast_alert("INFO", f"Bot started in {control.mode} mode",
                                    {"symbols": control.symbols, "strategy": control.strategy_name})
        return {"status": "started", "mode": control.mode}
    elif control.action == "STOP":
        await state.stop_bot(); await state._broadcast_alert("INFO", "Bot stopped", {})
        return {"status": "stopped"}
    elif control.action == "SQUARE_OFF":
        await state.square_off_all("manual_trigger"); return {"status": "square_off_initiated"}
    elif control.action == "KILL_SWITCH":
        await state.trigger_kill_switch("manual_trigger"); return {"status": "kill_switch_activated"}
    else: raise HTTPException(400, f"Unknown action: {control.action}")


@app.get("/api/config")
async def get_config(): return {"bot": state.config.model_dump(), "risk": state.risk_config.model_dump()}

@app.post("/api/config")
async def update_config(bot_config: Optional[BotConfig] = None, risk_config: Optional[RiskConfig] = None):
    if bot_config: state.config = bot_config
    if risk_config: state.risk_config = risk_config
    return {"status": "config_updated"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await state.manager.connect(websocket)
    try:
        await websocket.send_json({"type": "STATUS", "data": state.get_status().model_dump()})
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await websocket.send_json({"type": "PONG", "timestamp": datetime.now().isoformat()})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "HEARTBEAT", "timestamp": datetime.now().isoformat()})
    except WebSocketDisconnect: await state.manager.disconnect(websocket)
    except Exception: await state.manager.disconnect(websocket)


async def broadcast_updates():
    while True:
        await asyncio.sleep(1)
        if not state.bot: continue
        try:
            portfolio = await state.get_portfolio()
            await state.manager.broadcast({"type": "PORTFOLIO", "data": portfolio.model_dump()})
            positions = await state.get_positions()
            await state.manager.broadcast({"type": "POSITIONS", "data": [p.model_dump() for p in positions]})
        except Exception as e: print(f"Broadcast error: {e}")


if __name__ == "__main__":
    asyncio.create_task(broadcast_updates())
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
''')

print("api_server.py written")

# Continue with more files...
print("Done with first batch")