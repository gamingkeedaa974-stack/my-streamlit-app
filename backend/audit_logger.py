"""
audit_logger.py
Structured, append-only audit log for SEBI compliance and post-trade analysis.
"""

from __future__ import annotations
import json
import hashlib
import asyncio
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class AuditEventType(str, Enum):
    SIGNAL_GENERATED = "SIGNAL_GENERATED"
    RISK_CHECK = "RISK_CHECK"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_ACK = "ORDER_ACK"
    ORDER_REJECTED = "ORDER_REJECTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_PARTIAL_FILL = "ORDER_PARTIAL_FILL"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_MODIFY = "ORDER_MODIFY"
    POSITION_UPDATE = "POSITION_UPDATE"
    M2M_UPDATE = "M2M_UPDATE"
    CIRCUIT_BREAKER = "CIRCUIT_BREAKER"
    KILL_SWITCH = "KILL_SWITCH"
    RECONCILIATION = "RECONCILIATION"
    WEBSOCKET_STATUS = "WEBSOCKET_STATUS"
    BACKTEST_START = "BACKTEST_START"
    BACKTEST_COMPLETE = "BACKTEST_COMPLETE"
    STRATEGY_OPTIMIZATION = "STRATEGY_OPTIMIZATION"
    ERROR = "ERROR"


class AuditEntry(BaseModel):
    event_id: str = Field(default_factory=lambda: hashlib.sha256(
        datetime.now().isoformat().encode()
    ).hexdigest()[:16])
    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: AuditEventType
    algo_id: str = "RETAIL-WB-001"
    session_id: str = ""
    symbol: Optional[str] = None
    underlying: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    previous_hash: Optional[str] = None
    
    def compute_hash(self) -> str:
        payload = f"{self.timestamp.isoformat()}|{self.event_type}|{self.algo_id}|{json.dumps(self.details, sort_keys=True)}"
        return hashlib.sha256(payload.encode()).hexdigest()[:32]


class AuditLogger:
    def __init__(self, log_dir: Path, algo_id: str = "RETAIL-WB-001"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.algo_id = algo_id
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._lock = asyncio.Lock()
        self._last_hash: Optional[str] = None
        self._current_file: Optional[Path] = None
        self._buffer: List[str] = []
        self._buffer_size = 100
        
    def start_session(self) -> None:
        self._current_file = self.log_dir / f"audit_{self._session_id}.jsonl"
        
    def close(self) -> None:
        if self._buffer:
            self._flush_buffer()
            
    def _flush_buffer(self) -> None:
        if not self._current_file or not self._buffer:
            return
        with open(self._current_file, "a") as f:
            for line in self._buffer:
                f.write(line + "\n")
        self._buffer = []
        
    def log(self, event_type: AuditEventType, **kwargs) -> AuditEntry:
        entry = AuditEntry(
            algo_id=self.algo_id,
            session_id=self._session_id,
            event_type=event_type,
            previous_hash=self._last_hash,
            **kwargs
        )
        entry_hash = entry.compute_hash()
        self._last_hash = entry_hash
        
        line = json.dumps(entry.model_dump(), default=str)
        self._buffer.append(line)
        
        if len(self._buffer) >= self._buffer_size:
            self._flush_buffer()
        
        if event_type in {AuditEventType.KILL_SWITCH, AuditEventType.CIRCUIT_BREAKER, AuditEventType.ERROR}:
            print(f"[AUDIT] {event_type.value}: {kwargs.get('details', {})}")
            
        return entry
    
    def log_signal(self, signal, underlying: str) -> None:
        self.log(
            event_type=AuditEventType.SIGNAL_GENERATED,
            underlying=underlying,
            details=signal.model_dump()
        )
        
    def log_risk_check(self, signal, allowed: bool, reason: str, lot_size: Optional[int]) -> None:
        self.log(
            event_type=AuditEventType.RISK_CHECK,
            underlying=signal.underlying_symbol,
            details={
                "action": signal.action,
                "allowed": allowed,
                "reason": reason,
                "lot_size": lot_size,
                "confidence": signal.confidence
            }
        )
        
    def log_websocket(self, status: str, reconnect_count: int, error: Optional[str] = None) -> None:
        self.log(
            event_type=AuditEventType.WEBSOCKET_STATUS,
            details={"status": status, "reconnect_count": reconnect_count, "error": error}
        )
        
    def log_backtest_start(self, strategy: str, symbol: str, params: Dict) -> None:
        self.log(
            event_type=AuditEventType.BACKTEST_START,
            details={"strategy": strategy, "symbol": symbol, "params": params}
        )
        
    def log_backtest_complete(self, strategy: str, symbol: str, result: Dict) -> None:
        self.log(
            event_type=AuditEventType.BACKTEST_COMPLETE,
            details={"strategy": strategy, "symbol": symbol, "result": result}
        )
        
    def log_optimization(self, strategy: str, old_params: Dict, new_params: Dict, improvement: float) -> None:
        self.log(
            event_type=AuditEventType.STRATEGY_OPTIMIZATION,
            details={
                "strategy": strategy,
                "old_params": old_params,
                "new_params": new_params,
                "improvement_pct": improvement
            }
        )