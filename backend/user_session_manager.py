"""
user_session_manager.py
Manages isolated trading environments (PaperBroker, RiskManager) for each user.
"""
import asyncio
from typing import Dict, Optional
from backend.paper_broker import PaperBroker
from backend.risk_manager import RiskManager, RiskConfig
from backend.performance_monitor import PerformanceMonitor, PerformanceThresholds
class UserSession:
    """Holds all state for a single authenticated user."""
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.paper_broker: Optional[PaperBroker] = None
        self.risk_manager: Optional[RiskManager] = None
        self.performance_monitor: Optional[PerformanceMonitor] = None
        self.bot_running: bool = False
        self.bot_task = None
        self.current_strategy: Optional[str] = None
        self.strategy_instance = None
        self.synthetic_data = None
        self.data_index = 0
        self.positions = []
        self.alerts = []
        self.backtest_results = []
        self.optimization_results = []
        self.daily_pnl_history = []
    def init_components(self):
        if self.paper_broker is None:
            self.paper_broker = PaperBroker()
        if self.risk_manager is None:
            self.risk_manager = RiskManager(RiskConfig())
        if self.performance_monitor is None:
            self.performance_monitor = PerformanceMonitor(PerformanceThresholds())
class UserSessionManager:
    def __init__(self):
        self._sessions: Dict[str, UserSession] = {}
        self._lock = asyncio.Lock()
    async def get_session(self, user_id: str) -> UserSession:
        async with self._lock:
            if user_id not in self._sessions:
                session = UserSession(user_id)
                session.init_components()
                self._sessions[user_id] = session
            return self._sessions[user_id]
# Singleton instance
session_manager = UserSessionManager()