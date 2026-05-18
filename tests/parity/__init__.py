"""Parity tests for NEAT/main.py compatibility."""

"""
Parity Test Suite
=================

These tests verify that the extracted TradingEnv and related modules
produce identical results to the original NEAT/main.py.

Test Strategy:
1. Load the same data slice
2. Run both original and extracted TradingEnv with identical parameters
3. Compare equity curves, trade decisions, and final results
4. Assert they are identical within floating-point tolerance

Default parameters for parity (must match NEAT/main.py):
- fee_rate: 0.001
- slippage_bps: 0
- mode: "backtest"
- initial_capital: 10000.0
- decision_threshold: 0.6
- min_trade_interval: 15
"""
