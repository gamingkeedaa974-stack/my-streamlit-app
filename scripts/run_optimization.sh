#!/bin/bash

STRATEGY=${1:-orb}
MODE=${2:-adaptive}
ITERATIONS=${3:-30}

echo "Running optimization for $STRATEGY ($MODE, $ITERATIONS iterations)..."

source venv/bin/activate

python -m backend.agents.auto_improvement_agent \
    --strategy "$STRATEGY" \
    --mode "$MODE" \
    --iterations "$ITERATIONS" \
    --synthetic-days 60

echo "Results saved to data/backtest_results/"
ls -lt data/backtest_results/ | head -5