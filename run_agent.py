#!/usr/bin/env python3
"""
run_agent.py
Wrapper to run the auto-improvement agent from project root.
"""
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.agents.auto_improvement_agent import main

if __name__ == "__main__":
    main()