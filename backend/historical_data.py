"""
historical_data.py
Real historical data provider for NSE backtesting.
Supports multiple sources: NSEPython (free), Fyers, Zerodha Kite Connect, CSV files.
"""

from __future__ import annotations
import os
import json
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import pandas as pd
import numpy as np


@dataclass
class DataSourceConfig:
    """Configuration for a data source."""
    name: str
    source_type: str  # "nsepython", "fyers", "zerodha", "csv", "synthetic"
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    access_token: Optional[str] = None
    data_dir: str = "data/historical"
    cache_enabled: bool = True
    cache_ttl_hours: int = 24


class HistoricalDataProvider:
    """
    Unified historical data provider for NSE indices and stocks.

    Usage:
        provider = HistoricalDataProvider(DataSourceConfig(
            source_type="nsepython",
            data_dir="data/historical"
        ))

        df = provider.get_data(
            symbol="NIFTY 50",
            start_date="2024-01-01",
            end_date="2024-06-30",
            interval="5minute",
            force_refresh=False
        )
    """

    # NSE symbol mappings
    SYMBOL_MAP = {
        "NIFTY50": "NIFTY 50",
        "NIFTY": "NIFTY 50",
        "BANKNIFTY": "NIFTY BANK",
        "FINNIFTY": "NIFTY FIN SERVICE",
        "MIDCPNIFTY": "NIFTY MIDCAP 100",
        "SENSEX": "SENSEX",
        "NIFTYIT": "NIFTY IT",
        "NIFTYPHARMA": "NIFTY PHARMA",
        "NIFTYAUTO": "NIFTY AUTO",
    }

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.data_dir = Path(config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir = self.data_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)

        # Initialize source-specific clients
        self._nsepython_available = False
        self._fyers_client = None
        self._zerodha_kite = None

        self._init_source()

    def _init_source(self):
        """Initialize the configured data source."""
        if self.config.source_type == "nsepython":
            try:
                from nsepython import equity_history, index_history
                self._nsepython_available = True
                print("[DATA] NSEPython initialized (free NSE data)")
            except ImportError:
                print("[DATA] NSEPython not installed. Run: pip install nsepython")
                print("[DATA] Falling back to synthetic data")

        elif self.config.source_type == "fyers":
            try:
                from fyers_apiv3 import fyersModel
                self._fyers_client = fyersModel.FyersModel(
                    client_id=self.config.api_key,
                    token=self.config.access_token,
                    log_path=self.data_dir / "fyers_logs"
                )
                print("[DATA] Fyers API initialized")
            except ImportError:
                print("[DATA] Fyers API not installed. Run: pip install fyers-apiv3")

        elif self.config.source_type == "zerodha":
            try:
                from kiteconnect import KiteConnect
                self._zerodha_kite = KiteConnect(api_key=self.config.api_key)
                self._zerodha_kite.set_access_token(self.config.access_token)
                print("[DATA] Zerodha Kite Connect initialized")
            except ImportError:
                print("[DATA] KiteConnect not installed. Run: pip install kiteconnect")

        elif self.config.source_type == "csv":
            print(f"[DATA] CSV source ready (directory: {self.data_dir})")

        elif self.config.source_type == "synthetic":
            print("[DATA] Synthetic data source ready")

    def get_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "5minute",
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data.

        Args:
            symbol: Symbol code (e.g., "NIFTY50", "BANKNIFTY", "RELIANCE")
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Candle interval - "1minute", "5minute", "15minute", "30minute", "60minute", "day"
            force_refresh: Ignore cache and fetch fresh data

        Returns:
            DataFrame with columns: open, high, low, close, volume
            Index: datetime
        """
        # Check cache first
        cache_key = f"{symbol}_{start_date}_{end_date}_{interval}"
        cache_file = self.cache_dir / f"{cache_key}.pkl"

        if not force_refresh and self.config.cache_enabled and cache_file.exists():
            cache_age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
            if cache_age < timedelta(hours=self.config.cache_ttl_hours):
                print(f"[DATA] Loading cached data: {cache_key}")
                return pd.read_pickle(cache_file)

        # Fetch from source
        df = None

        if self.config.source_type == "nsepython" and self._nsepython_available:
            df = self._fetch_nsepython(symbol, start_date, end_date, interval)
        elif self.config.source_type == "fyers" and self._fyers_client:
            df = self._fetch_fyers(symbol, start_date, end_date, interval)
        elif self.config.source_type == "zerodha" and self._zerodha_kite:
            df = self._fetch_zerodha(symbol, start_date, end_date, interval)
        elif self.config.source_type == "csv":
            df = self._fetch_csv(symbol, start_date, end_date, interval)

        # Fallback to synthetic if real data failed
        if df is None or df.empty:
            print(f"[DATA] Real data unavailable, generating synthetic data for {symbol}")
            df = self._generate_synthetic(symbol, start_date, end_date, interval)

        # Clean and standardize
        df = self._standardize_dataframe(df)

        # Cache the result
        if self.config.cache_enabled:
            df.to_pickle(cache_file)
            print(f"[DATA] Cached: {cache_file}")

        return df

    def _fetch_nsepython(
        self, symbol: str, start_date: str, end_date: str, interval: str
    ) -> Optional[pd.DataFrame]:
        """Fetch data using NSEPython (free, unofficial NSE API)."""
        try:
            from nsepython import equity_history, index_history

            nse_symbol = self.SYMBOL_MAP.get(symbol.upper(), symbol)

            # Convert interval to NSEPython format
            interval_map = {
                "1minute": "1",
                "5minute": "5",
                "15minute": "15",
                "30minute": "30",
                "60minute": "60",
                "day": "1D"
            }
            nse_interval = interval_map.get(interval, "5")

            # Format dates for NSEPython
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

            # NSEPython has 365-day limit, so we may need multiple calls
            all_data = []
            current_start = start_dt

            while current_start <= end_dt:
                current_end = min(current_start + timedelta(days=300), end_dt)

                try:
                    if "NIFTY" in nse_symbol.upper() or "SENSEX" in nse_symbol.upper():
                        data = index_history(nse_symbol, 
                            current_start.strftime("%d-%m-%Y"),
                            current_end.strftime("%d-%m-%Y"))
                    else:
                        data = equity_history(nse_symbol, "EQ",
                            current_start.strftime("%d-%m-%Y"),
                            current_end.strftime("%d-%m-%Y"))

                    if data is not None and not data.empty:
                        all_data.append(data)

                except Exception as e:
                    print(f"[DATA] NSEPython fetch error for {current_start}-{current_end}: {e}")

                current_start = current_end + timedelta(days=1)

            if not all_data:
                return None

            df = pd.concat(all_data, ignore_index=True)

            # Standardize column names
            column_map = {
                'CH_TIMESTAMP': 'timestamp',
                'CH_OPENING_PRICE': 'open',
                'CH_TRADE_HIGH_PRICE': 'high',
                'CH_TRADE_LOW_PRICE': 'low',
                'CH_CLOSING_PRICE': 'close',
                'CH_TOT_TRADED_QTY': 'volume',
                'TIMESTAMP': 'timestamp',
                'OPEN': 'open',
                'HIGH': 'high',
                'LOW': 'low',
                'CLOSE': 'close',
                'VOLUME': 'volume',
            }

            df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})

            # Parse timestamp
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)

            return df

        except Exception as e:
            print(f"[DATA] NSEPython error: {e}")
            return None

    def _fetch_fyers(
        self, symbol: str, start_date: str, end_date: str, interval: str
    ) -> Optional[pd.DataFrame]:
        """Fetch data using Fyers API."""
        try:
            # Fyers symbol format: NSE:NIFTY50-INDEX
            fyers_symbol = f"NSE:{symbol}-INDEX" if symbol in self.SYMBOL_MAP else symbol

            start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())

            data = {
                "symbol": fyers_symbol,
                "resolution": interval.replace("minute", "").replace("day", "D"),
                "date_format": "0",
                "range_from": start_ts,
                "range_to": end_ts,
                "cont_flag": "1"
            }

            response = self._fyers_client.history(data=data)

            if response.get("s") == "ok":
                candles = response.get("candles", [])
                df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
                df.set_index("timestamp", inplace=True)
                return df
            else:
                print(f"[DATA] Fyers API error: {response}")
                return None

        except Exception as e:
            print(f"[DATA] Fyers error: {e}")
            return None

    def _fetch_zerodha(
        self, symbol: str, start_date: str, end_date: str, interval: str
    ) -> Optional[pd.DataFrame]:
        """Fetch data using Zerodha Kite Connect."""
        try:
            # Get instrument token
            instruments = self._zerodha_kite.instruments("NSE")

            nse_symbol = self.SYMBOL_MAP.get(symbol.upper(), symbol)
            instrument = next(
                (i for i in instruments if i["tradingsymbol"] == nse_symbol or i["name"] == nse_symbol),
                None
            )

            if not instrument:
                print(f"[DATA] Instrument not found: {nse_symbol}")
                return None

            token = instrument["instrument_token"]

            # Fetch historical data
            from_dt = datetime.strptime(start_date, "%Y-%m-%d")
            to_dt = datetime.strptime(end_date, "%Y-%m-%d")

            candles = self._zerodha_kite.historical_data(
                instrument_token=token,
                from_date=from_dt,
                to_date=to_dt,
                interval=interval,
                continuous=False,
                oi=False
            )

            df = pd.DataFrame(candles)
            df["date"] = pd.to_datetime(df["date"])
            df.rename(columns={"date": "timestamp"}, inplace=True)
            df.set_index("timestamp", inplace=True)
            return df

        except Exception as e:
            print(f"[DATA] Zerodha error: {e}")
            return None

    def _fetch_csv(
        self, symbol: str, start_date: str, end_date: str, interval: str
    ) -> Optional[pd.DataFrame]:
        """Load data from CSV files in data directory."""
        try:
            # Look for CSV files matching the symbol
            pattern = f"{symbol.lower()}*{interval}*.csv"
            csv_files = list(self.data_dir.glob(pattern))

            if not csv_files:
                # Try broader search
                csv_files = list(self.data_dir.glob(f"{symbol.lower()}*.csv"))

            if not csv_files:
                print(f"[DATA] No CSV found for {symbol} in {self.data_dir}")
                return None

            df = pd.read_csv(csv_files[0])

            # Parse timestamp
            time_cols = ['timestamp', 'date', 'time', 'datetime', 'Timestamp', 'Date']
            for col in time_cols:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
                    df.set_index(col, inplace=True)
                    break

            # Filter date range
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            df = df[(df.index >= start_dt) & (df.index <= end_dt)]

            return df

        except Exception as e:
            print(f"[DATA] CSV error: {e}")
            return None

    def _generate_synthetic(
        self, symbol: str, start_date: str, end_date: str, interval: str
    ) -> pd.DataFrame:
        """Generate synthetic data as ultimate fallback."""
        from backend.backtest_engine import DataGenerator

        days = (datetime.strptime(end_date, "%Y-%m-%d") - 
                datetime.strptime(start_date, "%Y-%m-%d")).days + 1

        return DataGenerator.generate_synthetic_data(
            days=max(days, 30),
            symbol=symbol,
            seed=None  # Dynamic seed
        )

    def _standardize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize DataFrame to expected format."""
        required = ['open', 'high', 'low', 'close', 'volume']

        # Ensure all required columns exist
        for col in required:
            if col not in df.columns:
                if col.upper() in df.columns:
                    df[col] = df[col.upper()]
                else:
                    df[col] = 0.0

        # Select only required columns
        df = df[required].copy()

        # Ensure numeric types
        for col in required:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # Ensure index is datetime
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        # Sort by time
        df.sort_index(inplace=True)

        return df

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get latest price for a symbol (LTP)."""
        try:
            if self.config.source_type == "nsepython" and self._nsepython_available:
                from nsepython import nse_eq, nse_index

                nse_symbol = self.SYMBOL_MAP.get(symbol.upper(), symbol)

                if "NIFTY" in nse_symbol.upper() or "SENSEX" in nse_symbol.upper():
                    data = nse_index()
                    idx_data = data[data["indexName"] == nse_symbol]
                    if not idx_data.empty:
                        return float(idx_data.iloc[0]["last"])
                else:
                    data = nse_eq(nse_symbol)
                    return float(data["priceInfo"]["lastPrice"])

            elif self.config.source_type == "fyers" and self._fyers_client:
                fyers_symbol = f"NSE:{symbol}-INDEX" if symbol in self.SYMBOL_MAP else symbol
                response = self._fyers_client.quotes({"symbols": fyers_symbol})
                if response.get("s") == "ok":
                    return float(response["d"][0]["v"]["lp"])

            elif self.config.source_type == "zerodha" and self._zerodha_kite:
                instruments = self._zerodha_kite.instruments("NSE")
                nse_symbol = self.SYMBOL_MAP.get(symbol.upper(), symbol)
                instrument = next(
                    (i for i in instruments if i["tradingsymbol"] == nse_symbol),
                    None
                )
                if instrument:
                    ltp_data = self._zerodha_kite.ltp(instrument["instrument_token"])
                    return float(ltp_data[str(instrument["instrument_token"])]["last_price"])

        except Exception as e:
            print(f"[DATA] LTP error: {e}")

        return None

    def clear_cache(self):
        """Clear all cached data."""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(exist_ok=True)
            print("[DATA] Cache cleared")


# Convenience function for quick setup
def get_data_provider(source: str = "auto", **kwargs) -> HistoricalDataProvider:
    """
    Quick setup for historical data provider.

    Args:
        source: "auto", "nsepython", "fyers", "zerodha", "csv", "synthetic"
        **kwargs: Additional config parameters

    Returns:
        Configured HistoricalDataProvider
    """
    if source == "auto":
        # Try sources in order of preference
        for src in ["nsepython", "csv", "synthetic"]:
            config = DataSourceConfig(name=f"auto_{src}", source_type=src, **kwargs)
            provider = HistoricalDataProvider(config)
            if src == "nsepython" and provider._nsepython_available:
                return provider
            elif src == "csv":
                return provider
        # Fallback to synthetic
        config = DataSourceConfig(name="auto_synthetic", source_type="synthetic", **kwargs)
        return HistoricalDataProvider(config)

    config = DataSourceConfig(name=source, source_type=source, **kwargs)
    return HistoricalDataProvider(config)