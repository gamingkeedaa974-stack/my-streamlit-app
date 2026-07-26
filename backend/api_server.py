"""
api_server.py
FastAPI backend with WebSocket for real-time dashboard.
Includes Simulated Paper Trading + Self-Improving Agent.
"""

from __future__ import annotations
import asyncio
import json
from datetime import datetime, time, timedelta
from typing import Optional, Dict, List
from contextlib import asynccontextmanager
from pathlib import Path
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn
from backend.auth_manager import AuthManager
auth_manager = AuthManager()
from backend.user_session_manager import session_manager

from backend.strategies.strategy import BaseStrategy, StrategyConfig, Signal, SignalAction, StrategyRegistry, MarketRegime
from backend.risk_manager import RiskManager, RiskConfig, RiskState
from backend.audit_logger import AuditLogger
from backend.backtest_engine import BacktestEngine, DataGenerator, SyntheticOptionsChainProvider
from backend.paper_broker import PaperBroker
from backend.fyers_broker import FyersBroker
from backend.performance_monitor import PerformanceMonitor, PerformanceThresholds
from backend.self_improvement_loop import SelfImprovementLoop, SelfImprovementConfig


# ---------- API Models ----------
class BotStatus(BaseModel):
    running: bool
    mode: str
    uptime_seconds: float
    symbols: List[str]
    strategy: str
    connected_to_broker: bool
    last_heartbeat: Optional[datetime] = None
    # â”€â”€ NEW: Current market regime â”€â”€
    market_regime: Optional[str] = None

class PositionView(BaseModel):
    symbol: str
    underlying: str
    option_type: str
    strike: float
    entry_price: float
    current_price: float
    quantity: int
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss: float
    target: float
    time_in_trade: str
    # â”€â”€ NEW: Greeks â”€â”€
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None

class PortfolioSummary(BaseModel):
    capital: float
    daily_pnl: float
    daily_pnl_pct: float
    open_positions: int
    margin_used_pct: float
    available_margin: float
    net_delta: float
    # â”€â”€ NEW: Additional Greeks â”€â”€
    net_gamma: float = 0.0
    net_theta: float = 0.0
    net_vega: float = 0.0
    circuit_breaker: bool
    kill_switch: bool

class StrategyControl(BaseModel):
    action: str
    mode: Optional[str] = "PAPER"
    symbols: Optional[List[str]] = None
    strategy_name: Optional[str] = "orb"

class BacktestRequest(BaseModel):
    strategy: str
    symbol: str = "NIFTY50"
    days: int = 30
    mode: str = "synthetic"  # "synthetic", "real", "csv"
    data_path: Optional[str] = None
    data_source: Optional[str] = "auto"  # "auto", "nsepython", "fyers", "zerodha", "csv"
    start_date: Optional[str] = None  # YYYY-MM-DD (for real data)
    end_date: Optional[str] = None    # YYYY-MM-DD (for real data)
    interval: Optional[str] = "5minute"  # "1minute", "5minute", "15minute", etc.

class OptimizationRequest(BaseModel):
    strategy: str
    symbol: str = "NIFTY50"
    mode: str = "adaptive"
    iterations: int = 30
    days: int = 60



class StrategyCompareRequest(BaseModel):
    symbol: str = "NIFTY50"
    days: int = 30
    mode: str = "synthetic"
    data_path: Optional[str] = None
    data_source: Optional[str] = "auto"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    interval: Optional[str] = "5minute"

class StrategyComparisonResult(BaseModel):
    strategy: str
    total_pnl_pct: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    profit_factor: float
    avg_trade_pnl: float
    score: float
    ohlc_data: Optional[List[Dict]] = None
    trades: Optional[List[Dict]] = None
class SelfImprovementStatus(BaseModel):
    enabled: bool
    is_ab_testing: bool
    current_params: Dict
    candidate_params: Optional[Dict]
    optimization_count_today: int
    total_trades: int
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    should_optimize: bool


# â”€â”€ NEW: NSE Data Feed stub â€” ready for PCR, max pain, OI buildup integration â”€â”€
class NSEDataFeed:
    """Stub for NSE-specific market data feed. Integrate with nsepython or broker API."""
    
    def __init__(self):
        self.pcr_ratio: Optional[float] = None
        self.max_pain: Optional[float] = None
        self.oi_buildup: Dict[str, float] = {}
        self.iv_percentile: Optional[float] = None
    
    async def fetch_data(self, symbol: str) -> Dict:
        """Fetch PCR, max pain, OI buildup for symbol. Override with real implementation."""
        # TODO: Integrate with nsepython or broker API
        return {
            "pcr_ratio": self.pcr_ratio,
            "max_pain": self.max_pain,
            "oi_buildup": self.oi_buildup,
            "iv_percentile": self.iv_percentile,
        }
    
    async def update_risk_manager(self, risk_manager):
        """Feed NSE data into risk manager for PCR, max pain, OI buildup, IV percentile."""
        data = await self.fetch_data("NIFTY50")
        if risk_manager:
            await risk_manager.update_market_data(
                pcr=data.get("pcr_ratio"),
                max_pain=data.get("max_pain"),
                oi_buildup=data.get("oi_buildup"),
                iv_percentile=data.get("iv_percentile"),
            )


# ---------- Connection Manager ----------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    async def broadcast(self, message: dict):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            if d in self.active_connections:
                self.active_connections.remove(d)
manager = ConnectionManager()
# ---------- Paper Trading Engine ----------
async def run_paper_trading(user_id: str):
    """Main paper trading loop for a specific user."""
    session = await session_manager.get_session(user_id)
    if session.synthetic_data is None:
        from backend.backtest_engine import DataGenerator
        session.synthetic_data = DataGenerator.generate_synthetic_data(days=1, symbol=session.current_strategy or "NIFTY50", seed=None)
        session.data_index = 0
    if session.strategy_instance is None:
        from backend.strategies.strategy import StrategyRegistry
        strategy_cls = StrategyRegistry.get(session.current_strategy or "orb")
        config_cls = StrategyRegistry.get_config_class(session.current_strategy or "orb")
        config = config_cls(name=session.current_strategy or "orb")
        session.strategy_instance = strategy_cls(config)
        session.strategy_instance.reset()
    from backend.strategies.strategy import Bar as BarModel, SignalAction
    data = session.synthetic_data
    while session.bot_running:
        if session.data_index >= len(data):
            session.synthetic_data = DataGenerator.generate_synthetic_data(days=1, symbol=session.current_strategy or "NIFTY50", seed=None)
            session.data_index = 0
            data = session.synthetic_data
        row = data.iloc[session.data_index]
        timestamp = data.index[session.data_index]
        bar_obj = BarModel(symbol="NIFTY50", timestamp=timestamp, open=row["open"], high=row["high"], low=row["low"], close=row["close"], volume=int(row["volume"]))
        session.strategy_instance.ingest_bar(bar_obj)
        if timestamp.minute % 5 == 0:
            try:
                signal = await session.strategy_instance.generate_signal("NIFTY50", timestamp)
                if signal.action != SignalAction.HOLD:
                    allowed, reason, qty = await session.risk_manager.can_trade(signal, timestamp)
                    if allowed:
                        pos = await session.paper_broker.place_order(signal, "NIFTY50", timestamp, qty=qty)
                        if pos:
                            session.alerts.append({"level": "INFO", "message": f"Paper trade: {signal.action.value} {pos.symbol} @ ?{pos.entry_price}", "timestamp": timestamp.isoformat()})
                    else:
                        session.alerts.append({"level": "WARNING", "message": f"Trade blocked: {reason}", "timestamp": timestamp.isoformat()})
            except Exception as e:
                session.alerts.append({"level": "ERROR", "message": f"Strategy error: {str(e)}", "timestamp": datetime.now().isoformat()})
        await session.paper_broker.update_prices(row["close"], timestamp)
        if len(session.alerts) > 500: session.alerts = session.alerts[-500:]
        if len(session.daily_pnl_history) > 1000: session.daily_pnl_history = session.daily_pnl_history[-1000:]
        pf = session.paper_broker.get_portfolio_summary()
        session.daily_pnl_history.append({"time": timestamp.strftime("%H:%M:%S"), "pnl": pf["daily_pnl"], "equity": pf["capital"]})
        await manager.broadcast({"type": "PORTFOLIO", "user_id": user_id, "data": pf})
        session.data_index += 1
        await asyncio.sleep(0.5)
# ---------- Lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Trading API Server starting...")
    yield
    print("Trading API Server stopped.")
# ---------- FastAPI App ----------
app = FastAPI(title="NSE Options Trading Bot API", version="3.6.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------- Auth Middleware ----------
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    exempt_paths = ["/api/login", "/", "/docs", "/docs/", "/redoc", "/redoc/", "/openapi.json"]
    request_path = request.url.path
    request.state.user_id = None
    if request_path == "/" or request_path == "/api/login" or request_path.startswith("/docs") or request_path.startswith("/redoc") or request_path.startswith("/openapi.json"):
        return await call_next(request)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    token = auth_header.split(" ", 1)[1].strip()
    user_id = auth_manager.verify_token(token)
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})
    request.state.user_id = user_id
    return await call_next(request)

def require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user_id
# ---------- Auth Routes ----------
from pydantic import BaseModel

# ---------- Auth Routes ----------
from pydantic import BaseModel



# ---------- Auth Routes ----------
from pydantic import BaseModel
class LoginRequest(BaseModel):
    username: str
    password: str
@app.post("/api/login")
async def login(req: LoginRequest = Body(...)):
    """User login endpoint."""
    if auth_manager.verify_user(req.username, req.password):
        token = auth_manager.create_token(req.username)
        return {"access_token": token, "token_type": "bearer", "user_id": req.username}
    raise HTTPException(status_code=401, detail="Invalid username or password")
# ---------- REST Endpoints ----------

@app.get("/api/status")
async def get_status(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    return {
        "running": session.bot_running,
        "mode": "PAPER",
        "strategy": session.current_strategy or "none",
        "connected_to_broker": False,
        "market_regime": getattr(session.strategy_instance, '_current_regime', None).value if session.strategy_instance else None
    }
@app.get("/api/portfolio")
async def get_portfolio(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    return session.paper_broker.get_portfolio_summary()
@app.get("/api/positions")
async def get_positions(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    return session.paper_broker.get_positions()
@app.get("/api/alerts")
async def get_alerts(request: Request, limit: int = 50):
    session = await session_manager.get_session(require_user_id(request))
    return session.alerts[-limit:]
@app.get("/api/backtest-results")
async def get_backtest_results(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    return session.backtest_results[-50:]
@app.get("/api/optimization-results")
async def get_optimization_results(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    return session.optimization_results[-50:]

@app.get("/api/dashboard")
async def get_dashboard(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    status = {
        "running": session.bot_running,
        "mode": "PAPER",
        "strategy": session.current_strategy or "none",
        "connected_to_broker": False,
        "market_regime": getattr(session.strategy_instance, '_current_regime', None).value if session.strategy_instance else None,
    }
    return {
        "status": status,
        "portfolio": session.paper_broker.get_portfolio_summary(),
        "positions": session.paper_broker.get_positions(),
        "alerts": session.alerts[-50:],
        "backtest_results": session.backtest_results[-50:],
        "optimization_results": session.optimization_results[-50:],
        "self_improvement": None,
        "nse_data": None,
    }

@app.post("/api/control")
async def control_bot(request: Request, control: StrategyControl):
    session = await session_manager.get_session(require_user_id(request))
    if control.action == "START":
        if session.bot_running:
            return {"status": "already_running"}
        session.bot_running = True
        session.current_strategy = control.strategy_name or "orb"
        if session.strategy_instance:
            session.strategy_instance.reset()
        if session.paper_broker:
            session.paper_broker.reset()
        session.bot_task = asyncio.create_task(run_paper_trading(request.state.user_id))
        session.alerts.append({"level": "INFO", "message": "Bot started", "timestamp": datetime.now().isoformat()})
        return {"status": "started"}
    elif control.action == "STOP":
        session.bot_running = False
        if session.bot_task:
            session.bot_task.cancel()
            session.bot_task = None
        session.alerts.append({"level": "INFO", "message": "Bot stopped", "timestamp": datetime.now().isoformat()})
        return {"status": "stopped"}
    elif control.action == "SQUARE_OFF":
        if session.paper_broker:
            await session.paper_broker.square_off_all(datetime.now())
        return {"status": "square_off_initiated"}
    elif control.action == "KILL_SWITCH":
        session.bot_running = False
        if session.bot_task:
            session.bot_task.cancel()
            session.bot_task = None
        return {"status": "kill_switch_activated"}
    elif control.action == "TOGGLE_SELF_IMPROVE":
        return {"status": "si_toggled", "enabled": False}
    raise HTTPException(400, f"Unknown action: {control.action}")
@app.post("/api/backtest")
async def run_backtest(request: Request, req: BacktestRequest):
    try:
        session = await session_manager.get_session(require_user_id(request))
        from backend.strategies.strategy import StrategyRegistry
        from backend.backtest_engine import BacktestEngine, DataGenerator
        from backend.risk_manager import RiskConfig
        import math

        data = DataGenerator.generate_synthetic_data(days=req.days, symbol=req.symbol, seed=None)
        strategy_cls = StrategyRegistry.get(req.strategy)
        config_cls = StrategyRegistry.get_config_class(req.strategy)
        config = config_cls(name=req.strategy)
        strategy = strategy_cls(config)
        strategy.reset()
        bt_risk_config = RiskConfig(theta_cutoff_time=time(15, 0))
        engine = BacktestEngine(strategy, bt_risk_config, data, symbol=req.symbol)
        result = await engine.run()
        ohlc_data = [{
            "timestamp": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
            "open": float(row["open"]), "high": float(row["high"]), "low": float(row["low"]), "close": float(row["close"]),
            "volume": int(row["volume"]) if not math.isnan(float(row["volume"])) else 0
        } for idx, row in data.iterrows()]
        result_data = {
            "strategy": req.strategy, "symbol": req.symbol,
            "total_pnl": result.total_pnl, "total_pnl_pct": result.total_pnl_pct,
            "win_rate": result.win_rate, "sharpe_ratio": result.sharpe_ratio,
            "max_drawdown": result.max_drawdown, "total_trades": result.total_trades,
            "profit_factor": 999.99 if result.profit_factor == float("inf") else result.profit_factor,
            "avg_trade_pnl": result.avg_profit_per_trade, "max_consecutive_losses": result.max_consecutive_losses,
            "params": result.params, "equity_curve": [e["equity"] for e in result.equity_curve],
            "trades": result.trades, "ohlc_data": ohlc_data, "timestamp": datetime.now().isoformat()
        }
        session.backtest_results.append(result_data)
        return result_data
    except Exception:
        return JSONResponse(status_code=500, content={"detail": "Backtest failed"})

@app.post("/api/backtest/compare")
async def run_backtest_compare(request: Request, req: StrategyCompareRequest):
    """Run all strategies on the SAME synthetic data and return comparison."""
    try:
        from backend.strategies.strategy import StrategyRegistry
        from backend.backtest_engine import BacktestEngine, DataGenerator
        from backend.risk_manager import RiskConfig
        import math

        # Generate data ONCE so all strategies use identical data
        np_seed = int(datetime.now().timestamp()) % (2**32)
        data = DataGenerator.generate_synthetic_data(days=req.days, symbol=req.symbol, seed=np_seed)
        ohlc_data = [{
            "timestamp": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
            "open": float(row["open"]), "high": float(row["high"]), "low": float(row["low"]), "close": float(row["close"]),
            "volume": int(row["volume"]) if not math.isnan(float(row["volume"])) else 0
        } for idx, row in data.iterrows()]

        comparisons = []
        best_score = -999
        winner = "orb"

        for strat_name in StrategyRegistry.list_strategies():
            try:
                strategy_cls = StrategyRegistry.get(strat_name)
                config_cls = StrategyRegistry.get_config_class(strat_name)
                config = config_cls(name=strat_name)
                strategy = strategy_cls(config)
                strategy.reset()

                bt_risk_config = RiskConfig(theta_cutoff_time=time(15, 0))
                engine = BacktestEngine(strategy, bt_risk_config, data, symbol=req.symbol)
                result = await engine.run()

                score_val = result.score() if hasattr(result, 'score') else result.total_pnl_pct

                comp = {
                    "strategy": strat_name,
                    "total_pnl_pct": result.total_pnl_pct,
                    "win_rate": result.win_rate,
                    "sharpe_ratio": result.sharpe_ratio,
                    "max_drawdown": result.max_drawdown,
                    "total_trades": result.total_trades,
                    "profit_factor": 999.99 if result.profit_factor == float("inf") else result.profit_factor,
                    "avg_trade_pnl": result.avg_profit_per_trade,
                    "score": score_val,
                    "ohlc_data": ohlc_data,
                    "trades": result.trades,
                }
                comparisons.append(comp)

                if score_val > best_score:
                    best_score = score_val
                    winner = strat_name

                print(f"[COMPARE] {strat_name}: score={score_val:.2f}, trades={result.total_trades}, pnl%={result.total_pnl_pct:.2f}")
            except Exception as e:
                print(f"[COMPARE] {strat_name} failed: {e}")
                comparisons.append({
                    "strategy": strat_name, "total_pnl_pct": 0, "win_rate": 0,
                    "sharpe_ratio": 0, "max_drawdown": 0, "total_trades": 0,
                    "profit_factor": 0, "avg_trade_pnl": 0, "score": -999,
                    "ohlc_data": [], "trades": [],
                })

        result_data = {
            "comparisons": comparisons,
            "winner": winner,
            "symbol": req.symbol,
            "timestamp": datetime.now().isoformat(),
        }
        session = await session_manager.get_session(require_user_id(request))
        session.backtest_results.append(result_data)
        return result_data
    except Exception:
        return JSONResponse(status_code=500, content={"detail": "Backtest compare failed"})


# ---------- Fyers API Endpoints ----------
@app.get("/api/fyers/status")
async def fyers_status(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker
        session._fyers_broker = FyersBroker(
            app_id=os.environ.get("FYERS_API_KEY"),
            secret_key=os.environ.get("FYERS_SECRET"),
            redirect_uri=os.environ.get("FYERS_REDIRECT_URI", "http://localhost:8501"),
        )
    return session._fyers_broker.get_connection_status()

@app.post("/api/fyers/save-creds")
async def fyers_save_creds(request: Request):
    body = await request.json()
    from backend.fyers_broker import FyersBroker
    # Prefer explicit request body values; fall back to environment variables when present.
    app_id = body.get("app_id") or os.environ.get("FYERS_API_KEY")
    secret_key = body.get("secret_key") or os.environ.get("FYERS_SECRET")
    redirect_uri = body.get("redirect_uri") or os.environ.get("FYERS_REDIRECT_URI") or "http://localhost:8501"
    session = await session_manager.get_session(require_user_id(request))
    session._fyers_broker = FyersBroker(app_id=app_id, secret_key=secret_key, redirect_uri=redirect_uri)
    return {"status": "saved", "has_app_id": bool(app_id)}

@app.post("/api/fyers/auth-url")
async def fyers_auth_url(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker
        session._fyers_broker = FyersBroker(
            app_id=os.environ.get("FYERS_API_KEY"),
            secret_key=os.environ.get("FYERS_SECRET"),
            redirect_uri=os.environ.get("FYERS_REDIRECT_URI", "http://localhost:8501"),
        )
    url = session._fyers_broker.generate_auth_url()
    if url:
        return {"auth_url": url}
    return JSONResponse(status_code=400, content={"error": session._fyers_broker.last_error})


@app.get("/api/fyers/auth-url")
async def fyers_auth_url_get(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker
        session._fyers_broker = FyersBroker(
            app_id=os.environ.get("FYERS_API_KEY"),
            secret_key=os.environ.get("FYERS_SECRET"),
            redirect_uri=os.environ.get("FYERS_REDIRECT_URI", "http://localhost:8501"),
        )
    url = session._fyers_broker.generate_auth_url()
    if url:
        return {"auth_url": url}
    return JSONResponse(status_code=400, content={"error": session._fyers_broker.last_error})

@app.post("/api/fyers/auth-token")
async def fyers_auth_token(request: Request):
    body = await request.json()
    auth_code = body.get("auth_code", "")
    session = await session_manager.get_session(require_user_id(request))
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker
        session._fyers_broker = FyersBroker(
            app_id=os.environ.get("FYERS_API_KEY"),
            secret_key=os.environ.get("FYERS_SECRET"),
            redirect_uri=os.environ.get("FYERS_REDIRECT_URI", "http://localhost:8501"),
        )
    result = await session._fyers_broker.exchange_auth_code(auth_code)
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result

@app.post("/api/fyers/refresh-token")
async def fyers_refresh_token(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker
        session._fyers_broker = FyersBroker(
            app_id=os.environ.get("FYERS_API_KEY"),
            secret_key=os.environ.get("FYERS_SECRET"),
            redirect_uri=os.environ.get("FYERS_REDIRECT_URI", "http://localhost:8501"),
        )
    result = await session._fyers_broker.refresh_access_token()
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result

@app.post("/api/fyers/test")
async def fyers_test(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker
        session._fyers_broker = FyersBroker(
            app_id=os.environ.get("FYERS_API_KEY"),
            secret_key=os.environ.get("FYERS_SECRET"),
            redirect_uri=os.environ.get("FYERS_REDIRECT_URI", "http://localhost:8501"),
        )
    broker = session._fyers_broker
    if not broker.is_connected:
        # Try refresh first
        if broker.config.refresh_token:
            refresh_result = await broker.refresh_access_token()
            if not refresh_result["success"]:
                return JSONResponse(status_code=400, content={"error": broker.last_error, "refresh_result": refresh_result})
        else:
            return JSONResponse(status_code=400, content={"error": broker.last_error})
    profile = broker.get_profile()
    if profile:
        return {"status": "connected", "profile": profile.get("data", {})}
    return JSONResponse(status_code=400, content={"error": "Connected but profile fetch failed"})


@app.get("/api/fyers/profile")
async def fyers_profile(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker
        session._fyers_broker = FyersBroker(
            app_id=os.environ.get("FYERS_API_KEY"),
            secret_key=os.environ.get("FYERS_SECRET"),
            redirect_uri=os.environ.get("FYERS_REDIRECT_URI", "http://localhost:8501"),
        )
    broker = session._fyers_broker
    try:
        data = broker.get_profile()
        return {"status": "ok", "data": data.get("data", {}) if isinstance(data, dict) else data}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": "Profile fetch failed"})


@app.get("/api/fyers/funds")
async def fyers_funds(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker
        session._fyers_broker = FyersBroker(
            app_id=os.environ.get("FYERS_API_KEY"),
            secret_key=os.environ.get("FYERS_SECRET"),
            redirect_uri=os.environ.get("FYERS_REDIRECT_URI", "http://localhost:8501"),
        )
    broker = session._fyers_broker
    try:
        data = broker.get_funds()
        return {"status": "ok", "data": data.get("data", {}) if isinstance(data, dict) else data}
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Funds fetch failed"})


@app.get("/api/fyers/positions")
async def fyers_positions(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker
        session._fyers_broker = FyersBroker(
            app_id=os.environ.get("FYERS_API_KEY"),
            secret_key=os.environ.get("FYERS_SECRET"),
            redirect_uri=os.environ.get("FYERS_REDIRECT_URI", "http://localhost:8501"),
        )
    broker = session._fyers_broker
    try:
        data = broker.get_fyers_positions()
        return {"status": "ok", "data": data.get("data", {}) if isinstance(data, dict) else data}
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Positions fetch failed"})


@app.get("/api/fyers/orders")
async def fyers_orders(request: Request):
    session = await session_manager.get_session(require_user_id(request))
    if not hasattr(session, '_fyers_broker') or session._fyers_broker is None:
        from backend.fyers_broker import FyersBroker
        session._fyers_broker = FyersBroker(
            app_id=os.environ.get("FYERS_API_KEY"),
            secret_key=os.environ.get("FYERS_SECRET"),
            redirect_uri=os.environ.get("FYERS_REDIRECT_URI", "http://localhost:8501"),
        )
    broker = session._fyers_broker
    try:
        data = broker.get_orders()
        return {"status": "ok", "data": data.get("data", {}) if isinstance(data, dict) else data}
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Orders fetch failed"})
# ---------- WebSocket ----------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await asyncio.sleep(10)
            await websocket.send_json({"type": "HEARTBEAT", "timestamp": datetime.now().isoformat()})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("backend.api_server:app", host=args.host, port=args.port, reload=not args.no_reload)


