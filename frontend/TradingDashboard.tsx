// TradingDashboard.tsx
// Complete React component for the trading bot dashboard
// Uses Vite + Tailwind CSS + Recharts for charts

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { AlertTriangle, Play, Square, Skull, TrendingUp, TrendingDown, Activity, Shield, Clock, DollarSign, Zap } from 'lucide-react';

// ---------- Types ----------
interface BotStatus {
  running: boolean;
  mode: string;
  uptime_seconds: number;
  symbols: string[];
  strategy: string;
  connected_to_broker: boolean;
  ws_reconnect_count: number;
  last_heartbeat: string | null;
}

interface PortfolioSummary {
  capital: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  open_positions: number;
  margin_used_pct: number;
  available_margin: number;
  net_delta: number;
  net_gamma: number;
  vix: number | null;
  circuit_breaker: boolean;
  kill_switch: boolean;
}

interface Position {
  symbol: string;
  underlying: string;
  option_type: string;
  strike: number;
  entry_price: number;
  current_price: number;
  quantity: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  stop_loss: number;
  target: number;
  delta: number | null;
  time_in_trade: string;
}

interface AlertMessage {
  level: string;
  message: string;
  timestamp: string;
  metadata: Record<string, any>;
}

// ---------- WebSocket Hook ----------
const useWebSocket = (url: string) => {
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<any>(null);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setLastMessage(data);
    };

    // Heartbeat ping every 25 seconds
    const heartbeat = setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ action: 'ping' }));
      }
    }, 25000);

    return () => {
      clearInterval(heartbeat);
      socket.close();
    };
  }, [url]);

  const send = useCallback((data: any) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(data));
    }
  }, []);

  return { connected, lastMessage, send };
};

// ---------- Components ----------
const PnLCard: React.FC<{ title: string; value: number; prefix?: string; suffix?: string; positiveGood?: boolean }> = 
  ({ title, value, prefix = '₹', suffix = '', positiveGood = true }) => {
  const isPositive = value >= 0;
  const colorClass = positiveGood 
    ? (isPositive ? 'text-green-400' : 'text-red-400')
    : (isPositive ? 'text-red-400' : 'text-green-400');
  
  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
      <div className="text-slate-400 text-sm mb-1">{title}</div>
      <div className={`text-2xl font-bold ${colorClass}`}>
        {prefix}{Math.abs(value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}{suffix}
      </div>
    </div>
  );
};

const StatusBadge: React.FC<{ label: string; active: boolean; color: string }> = 
  ({ label, active, color }) => (
  <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
    active ? color : 'bg-slate-700 text-slate-400'
  }`}>
    {active ? '● ' : '○ '}{label}
  </span>
);

const ControlButton: React.FC<{ 
  onClick: () => void; 
  icon: React.ReactNode; 
  label: string; 
  variant: 'primary' | 'danger' | 'warning' | 'neutral';
  disabled?: boolean;
}> = ({ onClick, icon, label, variant, disabled }) => {
  const variants = {
    primary: 'bg-blue-600 hover:bg-blue-700 text-white',
    danger: 'bg-red-600 hover:bg-red-700 text-white',
    warning: 'bg-amber-600 hover:bg-amber-700 text-white',
    neutral: 'bg-slate-600 hover:bg-slate-700 text-white'
  };
  
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-2 px-6 py-3 rounded-lg font-semibold transition-all ${
        variants[variant]
      } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      {icon}
      {label}
    </button>
  );
};

// ---------- Main Dashboard ----------
const TradingDashboard: React.FC = () => {
  const API_URL = 'http://localhost:8000';
  const WS_URL = 'ws://localhost:8000/ws';
  
  const { connected: wsConnected, lastMessage } = useWebSocket(WS_URL);
  
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [alerts, setAlerts] = useState<AlertMessage[]>([]);
  const [pnlHistory, setPnlHistory] = useState<{ time: string; pnl: number }[]>([]);
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>(['NSE:NIFTY50-INDEX']);
  const [selectedStrategy, setSelectedStrategy] = useState('orb');
  const [mode, setMode] = useState<'PAPER' | 'LIVE'>('PAPER');

  // Fetch initial data
  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  // Handle WebSocket messages
  useEffect(() => {
    if (!lastMessage) return;
    
    switch (lastMessage.type) {
      case 'PORTFOLIO':
        setPortfolio(lastMessage.data);
        // Add to P&L history
        setPnlHistory(prev => [...prev.slice(-300), {
          time: new Date().toLocaleTimeString('en-IN'),
          pnl: lastMessage.data.daily_pnl
        }]);
        break;
      case 'POSITIONS':
        setPositions(lastMessage.data);
        break;
      case 'ALERT':
        setAlerts(prev => [lastMessage.data, ...prev].slice(0, 100));
        break;
      case 'STATUS':
        setStatus(lastMessage.data);
        break;
    }
  }, [lastMessage]);

  const fetchStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/api/status`);
      const data = await res.json();
      setStatus(data);
    } catch (e) {
      console.error('Failed to fetch status:', e);
    }
  };

  const sendControl = async (action: string) => {
    try {
      const res = await fetch(`${API_URL}/api/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          mode,
          symbols: selectedSymbols,
          strategy_name: selectedStrategy
        })
      });
      const data = await res.json();
      console.log('Control response:', data);
    } catch (e) {
      console.error('Control failed:', e);
    }
  };

  const isRunning = status?.running ?? false;
  const isKillSwitch = portfolio?.kill_switch ?? false;
  const isCircuitBreaker = portfolio?.circuit_breaker ?? false;

  return (
    <div className="min-h-screen bg-slate-900 text-white p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <Activity className="text-blue-400" />
            NSE Options Trading Bot
          </h1>
          <div className="flex gap-3 mt-2">
            <StatusBadge label="WebSocket" active={wsConnected} color="bg-green-600 text-white" />
            <StatusBadge label="Broker" active={status?.connected_to_broker ?? false} color="bg-blue-600 text-white" />
            <StatusBadge label="PAPER" active={status?.mode === 'PAPER'} color="bg-purple-600 text-white" />
            <StatusBadge label="LIVE" active={status?.mode === 'LIVE'} color="bg-orange-600 text-white" />
            {isKillSwitch && <StatusBadge label="KILL SWITCH" active={true} color="bg-red-600 text-white animate-pulse" />}
            {isCircuitBreaker && <StatusBadge label="CIRCUIT BREAKER" active={true} color="bg-amber-600 text-white animate-pulse" />}
          </div>
        </div>
        <div className="text-right text-slate-400 text-sm">
          <div>Uptime: {status ? formatUptime(status.uptime_seconds) : '--:--:--'}</div>
          <div>Strategy: {status?.strategy || 'None'}</div>
          <div>WS Reconnects: {status?.ws_reconnect_count || 0}</div>
        </div>
      </div>

      {/* Control Panel */}
      <div className="bg-slate-800 rounded-xl p-6 mb-6 border border-slate-700">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Shield className="text-blue-400" />
          Control Center
        </h2>
        
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
          {/* Symbol Selection */}
          <div>
            <label className="block text-sm text-slate-400 mb-2">Symbols</label>
            <select 
              multiple 
              className="w-full bg-slate-700 rounded-lg p-2 text-sm border border-slate-600"
              value={selectedSymbols}
              onChange={(e) => setSelectedSymbols(Array.from(e.target.selectedOptions, o => o.value))}
            >
              <option value="NSE:NIFTY50-INDEX">NIFTY 50</option>
              <option value="NSE:BANKNIFTY-INDEX">BANK NIFTY</option>
              <option value="NSE:FINNIFTY-INDEX">FIN NIFTY</option>
              <option value="BSE:SENSEX-INDEX">SENSEX</option>
            </select>
          </div>

          {/* Strategy Selection */}
          <div>
            <label className="block text-sm text-slate-400 mb-2">Strategy</label>
            <select 
              className="w-full bg-slate-700 rounded-lg p-2 border border-slate-600"
              value={selectedStrategy}
              onChange={(e) => setSelectedStrategy(e.target.value)}
            >
              <option value="orb">Opening Range Breakout</option>
              <option value="vwap_momentum">VWAP + RSI Momentum</option>
            </select>
          </div>

          {/* Mode Toggle */}
          <div>
            <label className="block text-sm text-slate-400 mb-2">Mode</label>
            <div className="flex bg-slate-700 rounded-lg p-1">
              <button
                className={`flex-1 py-2 rounded-md text-sm font-semibold transition-all ${
                  mode === 'PAPER' ? 'bg-purple-600 text-white' : 'text-slate-400'
                }`}
                onClick={() => setMode('PAPER')}
              >
                PAPER
              </button>
              <button
                className={`flex-1 py-2 rounded-md text-sm font-semibold transition-all ${
                  mode === 'LIVE' ? 'bg-orange-600 text-white' : 'text-slate-400'
                }`}
                onClick={() => setMode('LIVE')}
              >
                LIVE
              </button>
            </div>
          </div>

          {/* Capital Display */}
          <div>
            <label className="block text-sm text-slate-400 mb-2">Capital</label>
            <div className="text-2xl font-bold text-white">
              ₹{(portfolio?.capital || 1000000).toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-4">
          <ControlButton
            onClick={() => sendControl('START')}
            icon={<Play size={20} />}
            label={isRunning ? 'Running...' : 'Start Bot'}
            variant="primary"
            disabled={isRunning || isKillSwitch}
          />
          <ControlButton
            onClick={() => sendControl('STOP')}
            icon={<Square size={20} />}
            label="Stop Bot"
            variant="neutral"
            disabled={!isRunning}
          />
          <ControlButton
            onClick={() => sendControl('SQUARE_OFF')}
            icon={<TrendingDown size={20} />}
            label="Square Off All"
            variant="warning"
            disabled={!isRunning || positions.length === 0}
          />
          <ControlButton
            onClick={() => {
              if (window.confirm('ARE YOU SURE? This will IMMEDIATELY stop all trading and cannot be undone without manual reset.')) {
                sendControl('KILL_SWITCH');
              }
            }}
            icon={<Skull size={20} />}
            label="KILL SWITCH"
            variant="danger"
            disabled={isKillSwitch}
          />
        </div>
      </div>

      {/* Portfolio Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <PnLCard title="Daily P&L" value={portfolio?.daily_pnl || 0} />
        <PnLCard title="Daily P&L %" value={portfolio?.daily_pnl_pct || 0} suffix="%" />
        <PnLCard title="Open Positions" value={portfolio?.open_positions || 0} prefix="" positiveGood={false} />
        <PnLCard title="Margin Used" value={portfolio?.margin_used_pct || 0} suffix="%" positiveGood={false} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <PnLCard title="Available Margin" value={portfolio?.available_margin || 0} />
        <PnLCard title="Net Delta" value={portfolio?.net_delta || 0} prefix="" />
        <PnLCard title="VIX" value={portfolio?.vix || 0} prefix="" positiveGood={false} />
      </div>

      {/* P&L Chart */}
      <div className="bg-slate-800 rounded-xl p-6 mb-6 border border-slate-700">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <TrendingUp className="text-green-400" />
          Real-Time P&L
        </h2>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={pnlHistory}>
            <defs>
              <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="time" stroke="#94a3b8" tick={{fontSize: 12}} />
            <YAxis stroke="#94a3b8" tick={{fontSize: 12}} />
            <Tooltip 
              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }}
              formatter={(value: number) => [`₹${value.toFixed(2)}`, 'P&L']}
            />
            <Area 
              type="monotone" 
              dataKey="pnl" 
              stroke="#10b981" 
              fillOpacity={1} 
              fill="url(#pnlGradient)" 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Positions Table */}
      <div className="bg-slate-800 rounded-xl p-6 mb-6 border border-slate-700">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <DollarSign className="text-blue-400" />
          Open Positions
        </h2>
        
        {positions.length === 0 ? (
          <div className="text-slate-500 text-center py-8">No open positions</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 border-b border-slate-700">
                  <th className="text-left py-3 px-4">Symbol</th>
                  <th className="text-left py-3 px-4">Type</th>
                  <th className="text-right py-3 px-4">Strike</th>
                  <th className="text-right py-3 px-4">Qty</th>
                  <th className="text-right py-3 px-4">Entry</th>
                  <th className="text-right py-3 px-4">Current</th>
                  <th className="text-right py-3 px-4">P&L</th>
                  <th className="text-right py-3 px-4">P&L %</th>
                  <th className="text-right py-3 px-4">Stop Loss</th>
                  <th className="text-right py-3 px-4">Target</th>
                  <th className="text-right py-3 px-4">Delta</th>
                  <th className="text-right py-3 px-4">Time</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => (
                  <tr key={idx} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="py-3 px-4 font-mono">{pos.symbol}</td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-1 rounded text-xs font-bold ${
                        pos.option_type === 'CE' ? 'bg-green-900 text-green-400' : 'bg-red-900 text-red-400'
                      }`}>
                        {pos.option_type}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right">{pos.strike.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right">{pos.quantity}</td>
                    <td className="py-3 px-4 text-right">₹{pos.entry_price.toFixed(2)}</td>
                    <td className="py-3 px-4 text-right">₹{pos.current_price.toFixed(2)}</td>
                    <td className={`py-3 px-4 text-right font-semibold ${
                      pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {pos.unrealized_pnl >= 0 ? '+' : ''}₹{pos.unrealized_pnl.toFixed(2)}
                    </td>
                    <td className={`py-3 px-4 text-right ${
                      pos.unrealized_pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {pos.unrealized_pnl_pct >= 0 ? '+' : ''}{pos.unrealized_pnl_pct.toFixed(2)}%
                    </td>
                    <td className="py-3 px-4 text-right text-red-400">₹{pos.stop_loss.toFixed(2)}</td>
                    <td className="py-3 px-4 text-right text-green-400">₹{pos.target.toFixed(2)}</td>
                    <td className="py-3 px-4 text-right">{pos.delta?.toFixed(3) || '-'}</td>
                    <td className="py-3 px-4 text-right text-slate-400">{pos.time_in_trade}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Alerts Feed */}
      <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <AlertTriangle className="text-amber-400" />
          Alert Feed
        </h2>
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {alerts.length === 0 ? (
            <div className="text-slate-500 text-center py-8">No alerts yet</div>
          ) : (
            alerts.map((alert, idx) => (
              <div key={idx} className={`p-3 rounded-lg border ${
                alert.level === 'CRITICAL' ? 'bg-red-900/30 border-red-700 text-red-200' :
                alert.level === 'ERROR' ? 'bg-orange-900/30 border-orange-700 text-orange-200' :
                alert.level === 'WARNING' ? 'bg-amber-900/30 border-amber-700 text-amber-200' :
                'bg-blue-900/30 border-blue-700 text-blue-200'
              }`}>
                <div className="flex justify-between items-start">
                  <span className="font-semibold text-sm">{alert.level}</span>
                  <span className="text-xs opacity-70">
                    {new Date(alert.timestamp).toLocaleTimeString('en-IN')}
                  </span>
                </div>
                <div className="mt-1 text-sm">{alert.message}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

// Helper
const formatUptime = (seconds: number): string => {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
};

export default TradingDashboard;