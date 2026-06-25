# Parity Guarantees

## Overview

This document describes the parity guarantees between the extracted CLEAN architecture implementation and the original `NEAT/main.py` prototype.

## What Is Parity?

Parity means that the extracted modules produce **identical results** (within floating-point tolerance) to the original implementation when using the same parameters and data.

## Guaranteed Parity Components

### 1. TradingEnv (NEAT/main.py lines 97-179)

**Location:** `src/stonks_trading/domains/trading/neat/trading_env.py`

**Guarantee:** With default parameters (`fee_rate=0.001`, `slippage_bps=0`, `mode="backtest"`), the extracted `TradingEnv` produces identical results to the original.

**Verified Behaviors:**
- State vector construction: 7 inputs `[is_invested, unrealized_pnl, trend_1h, rsi_1h, rsi_15m, roc, bb_width]`
- All-in / all-out position sizing
- Minimum trade interval enforcement (15 steps)
- Transaction fee calculation (0.1%)
- Decision threshold (0.6)
- Drawdown tracking

**Test File:** `tests/parity/test_neat_main_py_parity.py::TestTradingEnvParity`

### 2. Fitness Calculation (NEAT/main.py lines 185-236)

**Location:** `src/stonks_trading/domains/trading/neat/fitness.py`

**Guarantee:** The `calculate_fitness()` function produces identical scores to the original implementation.

**Verified Behaviors:**
- Total return calculation
- Downside risk (Sortino-style)
- Market beta calculation
- Differential return calculation
- Treynor ratio calculation
- Composite score formula with weights:
  - `W_RETURN = 1.0`
  - `W_RISK = 0.5`
  - `W_DIFF = 3.0`
  - `W_TREYNOR = 1.0`
- Inactivity penalty (< 2 trades: -50)
- Churning penalty (> 40 trades: -(trades - 40))
- Bankruptcy penalty (< 60% equity: -500)

**Test File:** `tests/parity/test_neat_main_py_parity.py::TestFitnessParity`

### 3. NEAT Configuration (NEAT/main.py lines 341-421)

**Location:** `src/stonks_trading/domains/trading/neat/config_builder.py`

**Guarantee:** The NEAT configuration string and resulting `neat.Config` object match the original.

**Verified Parameters:**
- Population size: 150
- Genome: 7 inputs, 2 outputs, 1 hidden
- Activation functions: tanh (default), clamped, relu, sigmoid
- Structural mutation: 0.5 add, 0.2 delete (connections and nodes)
- Weight mutation: 0.7 rate, 0.5 power
- Stagnation: 15 generations max, 3 elite species
- Reproduction: 3 elite, 0.3 survival threshold

**Test File:** `tests/parity/test_config_parity.py`

### 4. Feature Engineering

**Location:** `src/stonks_trading/domains/strategies/neat_swing/features.py`

**Guarantee:** Feature columns match NEAT/main.py line 115.

**Verified Features:**
- `trend_1h`: 1-hour trend (SMA 50 vs 200)
- `rsi_1h`: 1-hour RSI (normalized to 0-1)
- `rsi_15m`: 15-minute RSI (normalized to 0-1)
- `roc`: Rate of change (1-minute)
- `bb_width`: Bollinger Bands width

**Test File:** `tests/parity/test_neat_main_py_parity.py::TestFeatureParity`

### 5. Live Strategy Features

**Location:** `src/stonks_trading/bots/neat_swing/strategy.py` and `src/stonks_trading/shared/features/live_features.py`

**Guarantee:** The bot strategy's `compute_features()` and the live `LiveFeatureComputer` use the same resampling and `ta` library calls as the training pipeline and `NEAT/main.py`, ensuring training/live feature parity. The live implementation uses actual candle timestamps via `pd.DatetimeIndex` rather than synthetic indices.

**Verified Behaviors:**
- 1-hour resampling for `trend_1h` and `rsi_1h`
- 15-minute resampling for `rsi_15m`
- 1-minute Bollinger Band width and ROC
- Same feature defaults when insufficient data is available

**References:**
- Live feature computer: `src/stonks_trading/shared/features/live_features.py`
- Training features: `src/stonks_trading/domains/strategies/neat_swing/features.py`
- Bot strategy: `src/stonks_trading/bots/neat_swing/strategy.py`
- Original: `/Users/h3cth0r/Documents/strategy-research/NEAT/main.py` lines 60-88

## Dry-Run vs Backtest Verification

### Purpose

The dry-run simulation mode must produce **worse results** than pure backtest mode due to slippage simulation. This validates that the simulation is realistic.

### Slippage Configuration

- **Backtest mode:** `slippage_bps = 0` (instant fills at close price)
- **Dry-run mode:** `slippage_bps = 5` (0.05% slippage on each trade)

### Expected Impact

With sufficient trading activity:
- Buy prices are 0.05% higher in dry-run
- Sell prices are 0.05% lower in dry-run
- Total impact: ~0.1% per round-trip trade

### Verification Tests

**Test File:** `tests/parity/test_neat_main_py_parity.py::TestDryRunVsBacktest`

**Verified Behaviors:**
1. `test_dry_run_produces_worse_roi`: Dry-run final equity <= backtest final equity
2. `test_slippage_applied_to_buys`: Buy prices higher in dry-run
3. `test_slippage_applied_to_sells`: Sell prices lower in dry-run
4. `test_verification_threshold`: Difference should be measurable (>= 0.1%)

## Tolerance Levels

| Component | Tolerance | Notes |
|-----------|-----------|-------|
| Equity values | 1e-10 relative | Floating-point precision |
| Trade prices | 0.01 absolute | Fee/slippage calculation |
| Fitness scores | 1e-6 relative | Score comparison |
| Holdings | 0.0001 absolute | Position sizing |

## Running Parity Tests

```bash
# Run all parity tests
pytest tests/parity/ -v

# Run specific parity test class
pytest tests/parity/test_neat_main_py_parity.py::TestTradingEnvParity -v

# Run dry-run vs backtest tests
pytest tests/parity/test_neat_main_py_parity.py::TestDryRunVsBacktest -v

# Run config parity tests
pytest tests/parity/test_config_parity.py -v
```

## Phase 8C Completion Checklist

- [x] TradingEnv parity tests implemented
- [x] Fitness calculation parity tests implemented
- [x] Feature engineering parity tests implemented
- [x] NEAT config parity tests implemented
- [x] Dry-run vs backtest verification tests implemented
- [x] < 1% tolerance documented
- [x] Slippage simulation documented
- [x] Parity guarantees documented

## Maintenance

When modifying trading logic, ensure:

1. Run parity tests before committing
2. Verify tolerance levels are still met
3. Update this document if new guarantees are added
4. Document any intentional deviations from original behavior

## References

- Original: `/Users/h3cth0r/Documents/strategy-research/NEAT/main.py`
- TradingEnv: `src/stonks_trading/domains/trading/neat/trading_env.py`
- Fitness: `src/stonks_trading/domains/trading/neat/fitness.py`
- Config: `src/stonks_trading/domains/trading/neat/config_builder.py`
- Features: `src/stonks_trading/domains/trading/neat/features.py`
- Tests: `tests/parity/`
