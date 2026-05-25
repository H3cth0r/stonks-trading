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

Parity Guarantees:
==================
The following components are guaranteed to produce identical results
(within 1% tolerance) to NEAT/main.py when using default parameters:

1. TradingEnv.step() - Trading logic parity
2. TradingEnv.get_state() - State vector construction
3. calculate_fitness() - Fitness score calculation
4. NEAT config - Network architecture and evolution parameters

Dry-Run vs Backtest Verification:
==================================
Tests verify that:
- dry_run mode produces worse results than backtest mode
- Slippage impact is measurable (at least 1% difference in most cases)
- This validates realistic simulation vs idealized backtesting
"""
