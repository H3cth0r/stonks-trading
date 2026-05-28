"""Trading Hub - Portfolio, Bot Control, Models/Training, and Configuration.

Phase 10C: Consolidates Portfolio Overview, Live Trading, and Strategy Management.
"""

from time import sleep

import pandas as pd
import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync, post_sync

st.set_page_config(page_title="Trading Hub", page_icon="📊", layout="wide")

st.title("📊 Trading Hub")

# Tabs: Portfolio | Bot Control | Models/Training | Configuration
tab_portfolio, tab_bot, tab_models, tab_training, tab_config = st.tabs(
    ["Portfolio", "Bot Control", "Models", "Training", "Configuration"]
)

# Fetch strategy data once (shared across tabs)
strategies_data = fetch_sync("/api/v1/strategies/")
_SELECTED_STRATEGY = "NEAT Swing Trading"
_SELECTED_TYPE = "neat_swing"

if strategies_data and strategies_data.get("strategies"):
    strategies = strategies_data["strategies"]
    strategy_names = [s["name"] for s in strategies]
    if strategy_names:
        _SELECTED_STRATEGY = strategy_names[0] if strategy_names else _SELECTED_STRATEGY
        _SELECTED_TYPE = next(
            (s["type"] for s in strategies if s["name"] == _SELECTED_STRATEGY), "neat_swing"
        )

# =============================================================================
# PORTFOLIO TAB
# =============================================================================
with tab_portfolio:
    st.header("Portfolio Summary")
    summary_cols = st.columns(4)

    portfolio_data = fetch_sync("/api/v1/portfolio")
    if portfolio_data:
        with summary_cols[0]:
            total_value = portfolio_data.get("total_value", 0)
            st.metric("Total Value", f"${total_value:,.2f}")
        with summary_cols[1]:
            cash = portfolio_data.get("cash_value", 0)
            st.metric("Cash", f"${cash:,.2f}")
        with summary_cols[2]:
            positions_value = portfolio_data.get("positions_value", 0)
            st.metric("Positions", f"${positions_value:,.2f}")
        with summary_cols[3]:
            pnl = portfolio_data.get("unrealized_pnl", 0)
            delta_pct = f"{pnl / total_value * 100:.2f}%" if total_value > 0 else None
            st.metric("Unrealized P&L", f"${pnl:,.2f}", delta=delta_pct)
    else:
        st.info("No portfolio data available")

    # Trading Capital Info
    st.header("Trading Capital")
    balance_data = fetch_sync("/api/v1/balances/usdt")
    if balance_data and "balance" in balance_data:
        usdt_balance = balance_data["balance"]
        st.metric("Binance USDT Balance", f"${usdt_balance:,.2f}")
        st.info("Capital is used directly from Binance for live trading.")
    else:
        st.info("Binance balance unavailable. Check API connection.")

    # Positions
    st.header("Positions")
    positions_data = fetch_sync("/api/v1/positions")
    if positions_data and positions_data.get("positions"):
        positions = positions_data["positions"]

        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(positions, use_container_width=True)
        with col2:
            if positions:
                sides = [p.get("side", "UNKNOWN") for p in positions]
                long_count = sides.count("LONG")
                short_count = sides.count("SHORT")
                st.metric("Long Positions", long_count)
                st.metric("Short Positions", short_count)
    else:
        st.info("No open positions")

    # Recent Activity
    st.header("Recent Activity")
    activity_data = fetch_sync("/api/v1/trades", {"limit": 20})
    if activity_data and activity_data.get("trades"):
        trades = activity_data["trades"]
        st.dataframe(trades, use_container_width=True)
    else:
        st.info("No recent activity")

# =============================================================================
# BOT CONTROL TAB
# =============================================================================
with tab_bot:
    st.header("Bot Selection")
    bots_data = fetch_sync("/api/v1/bots")
    bot_options = []
    if bots_data and "bots" in bots_data and bots_data["bots"]:
        bot_options = [f"{b['bot_type']}/{b['instance_id']}" for b in bots_data["bots"]]

    selected_bot = st.selectbox("Select Bot", bot_options if bot_options else ["No bots available"])

    # Bot Registration Form
    with st.expander("Register New Bot"):
        col1, col2 = st.columns(2)
        with col1:
            new_bot_type = st.text_input("Bot Type", value="neat_swing", key="new_bot_type")
            new_instance_id = st.text_input("Instance ID", value="default", key="new_instance_id")
        with col2:
            new_bot_symbols = st.text_input(
                "Trading Symbols", value="BTC_USD,ETH_USD", key="new_bot_symbols"
            )
            new_bot_mode = st.selectbox("Mode", ["dry_run", "live", "backtest"], key="new_bot_mode")

        if st.button("Register Bot", key="register_bot_btn"):
            symbols = [s.strip() for s in new_bot_symbols.split(",")]
            result = post_sync(
                "/api/v1/bots",
                {
                    "bot_type": new_bot_type,
                    "instance_id": new_instance_id,
                    "symbols": symbols,
                    "mode": new_bot_mode,
                },
            )
            if result:
                st.success(f"Bot {new_bot_type}/{new_instance_id} registered!")
                sleep(1)
                st.rerun()
            else:
                st.error("Failed to register bot")

    auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
    refresh_interval = st.sidebar.slider("Refresh interval (seconds)", 10, 300, 30)

    if selected_bot and selected_bot != "No bots available":
        bot_type, instance_id = selected_bot.split("/", 1)

        # Bot Control Section
        st.subheader("Bot Control")
        col1, col2, col3 = st.columns(3)

        status_data = fetch_sync(f"/api/v1/bots/{bot_type}/{instance_id}/status")
        current_status = status_data.get("status", "unknown") if status_data else "unknown"
        is_running = current_status == "running"

        with col1:
            if st.button("▶️ Start Bot", disabled=is_running, use_container_width=True):
                result = post_sync(
                    f"/api/v1/bots/{bot_type}/{instance_id}/start",
                    {"symbols": ["BTC_USD"], "mode": "dry_run"},
                )
                if result:
                    st.success(f"Bot started! PID: {result.get('pid')}")
                    sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to start bot")

        with col2:
            if st.button("⏹️ Stop Bot", disabled=not is_running, use_container_width=True):
                result = post_sync(f"/api/v1/bots/{bot_type}/{instance_id}/stop")
                if result:
                    st.success("Bot stopped")
                    sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to stop bot")

        with col3:
            if st.button("🔄 Restart Bot", use_container_width=True):
                result = post_sync(f"/api/v1/bots/{bot_type}/{instance_id}/restart")
                if result:
                    st.success(f"Bot restarted! PID: {result.get('pid')}")
                    sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to restart bot")

        st.divider()

        # Bot Status Row
        col1, col2, col3, col4 = st.columns(4)
        status_data = fetch_sync(f"/api/v1/bots/{bot_type}/{instance_id}/status")

        with col1:
            status = status_data.get("status", "Unknown") if status_data else "Unknown"
            st.metric("Status", status)
        with col2:
            mode = status_data.get("mode", "Unknown") if status_data else "Unknown"
            st.metric("Mode", mode)
        with col3:
            last_seen = status_data.get("last_seen", "Never") if status_data else "Never"
            st.metric("Last Seen", last_seen)
        with col4:
            uptime = status_data.get("uptime_seconds", 0) if status_data else 0
            uptime_str = f"{uptime // 3600}h {(uptime % 3600) // 60}m" if uptime > 0 else "N/A"
            st.metric("Uptime", uptime_str)

        st.divider()

        # Live View Section (WebSocket Phase 10E)
        st.subheader("Live View")
        ws_url = f"ws://localhost:8000/ws/bots/{bot_type}/{instance_id}/state"
        st.caption(f"WebSocket: {ws_url}")

        try:
            equity_data = fetch_sync(f"/api/v1/bots/{bot_type}/{instance_id}/equity-history")
            if equity_data and "history" in equity_data and equity_data["history"]:
                df = pd.DataFrame(equity_data["history"])
                if not df.empty:
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    st.line_chart(df.set_index("timestamp")["equity"], use_container_width=True)
                else:
                    st.info("Collecting equity data... Bot needs to be running.")
            else:
                st.info("Equity curve will appear when bot starts trading.")
        except Exception as e:
            st.warning(f"Real-time charts unavailable: {e}")
            equity_data = fetch_sync(f"/api/v1/bots/{bot_type}/{instance_id}/equity-history")
            if equity_data and "history" in equity_data and equity_data["history"]:
                df = pd.DataFrame(equity_data["history"])
                if not df.empty:
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    st.line_chart(df.set_index("timestamp")["equity"], use_container_width=True)

        st.divider()

        # Positions
        st.subheader("Positions")
        positions_data = fetch_sync("/api/v1/positions")
        if positions_data and "positions" in positions_data and positions_data["positions"]:
            positions = positions_data["positions"]
            st.dataframe(positions, use_container_width=True)

            long_positions = sum(1 for p in positions if p.get("side") == "LONG")
            short_positions = sum(1 for p in positions if p.get("side") == "SHORT")
            total_exposure = sum(p.get("market_value", 0) for p in positions)

            cols = st.columns(3)
            with cols[0]:
                st.metric("Long Positions", long_positions)
            with cols[1]:
                st.metric("Short Positions", short_positions)
            with cols[2]:
                st.metric("Total Exposure", f"${total_exposure:,.2f}")
        else:
            st.info("No open positions")

        # Recent Trades
        st.subheader("Recent Trades")
        trades_data = fetch_sync(f"/api/v1/bots/{bot_type}/{instance_id}/trades", {"limit": 20})
        if trades_data and "trades" in trades_data and trades_data["trades"]:
            trades = trades_data["trades"]
            st.dataframe(trades, use_container_width=True)

            buy_trades = [t for t in trades if t.get("side") == "BUY"]
            sell_trades = [t for t in trades if t.get("side") == "SELL"]
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Buys", len(buy_trades))
            with col2:
                st.metric("Total Sells", len(sell_trades))
        else:
            st.info("No recent trades")

    else:
        st.warning("No bots available. Please register a bot first.")

    if auto_refresh:
        sleep(refresh_interval)
        st.rerun()

# =============================================================================
# MODELS TAB
# =============================================================================
with tab_models:
    st.header("Model Registry")

    # Strategy info from shared fetch (if strategy selector was changed, reflect it)
    selected_strategy = _SELECTED_STRATEGY
    selected_type = _SELECTED_TYPE

    # Allow user to change strategy selection
    if strategies_data and strategies_data.get("strategies"):
        strategies = strategies_data["strategies"]
        strategy_names = [s["name"] for s in strategies]
        if strategy_names:
            selected_strategy = st.selectbox(
                "Strategy",
                strategy_names,
                index=strategy_names.index(selected_strategy)
                if selected_strategy in strategy_names
                else 0,
            )
            selected_type = next(
                (s["type"] for s in strategies if s["name"] == selected_strategy), "neat_swing"
            )

    st.subheader(f"{selected_strategy} Models")

    col1, col2 = st.columns(2)
    with col1:
        show_active_only = st.checkbox("Show Active Only", value=False)
    with col2:
        symbol_filter = st.text_input("Filter by Symbol", placeholder="BTC_USD")

    params = {"strategy_type": selected_type}
    if show_active_only:
        params["is_active"] = "true"
    if symbol_filter:
        params["symbol"] = symbol_filter.upper()

    models_data = fetch_sync("/api/v1/models/", params)
    if models_data and models_data.get("models"):
        models = models_data["models"]
        df = pd.DataFrame(models)
        st.dataframe(df, use_container_width=True)

        st.subheader("Activate Model")
        col1, col2, col3 = st.columns(3)
        with col1:
            model_id = st.number_input("Model ID", min_value=1, step=1, key="model_id_input")
        with col2:
            bot_type = st.text_input("Bot Type", value="neat_swing", key="model_bot_type")
        with col3:
            instance_id = st.text_input("Instance ID", value="default", key="model_instance_id")

        if st.button("Activate Model", key="activate_model_btn"):
            result = post_sync(
                f"/api/v1/models/{model_id}/activate",
                {"bot_type": bot_type, "bot_instance_id": instance_id},
            )
            if result and result.get("success"):
                st.success(f"Model {model_id} activated!")
            else:
                st.error("Activation failed")
    else:
        st.info("No models found")

# =============================================================================
# TRAINING TAB
# =============================================================================
with tab_training:
    st.header("Training Runs")

    runs_data = fetch_sync("/api/v1/training")
    if runs_data and runs_data.get("runs"):
        runs = runs_data["runs"]
        st.dataframe(pd.DataFrame(runs), use_container_width=True)
    else:
        st.info("No training runs")

    # Start new training
    with st.expander("Start New Training"):
        col1, col2 = st.columns(2)
        with col1:
            train_symbol = st.text_input("Symbol", value="BTC_USD", key="train_symbol")
            train_strategy = st.selectbox("Strategy", ["neat_swing"], key="train_strategy")
        with col2:
            generations = st.number_input(
                "Generations", min_value=1, max_value=100, value=30, key="train_generations"
            )
            pop_size = st.number_input(
                "Population Size", min_value=10, max_value=500, value=150, key="train_pop_size"
            )

        if st.button("Start Training", key="start_training_btn"):
            result = post_sync(
                "/api/v1/training/runs",
                {
                    "strategy_type": train_strategy,
                    "symbol": train_symbol.upper(),
                    "generations": generations,
                    "population_size": pop_size,
                    "bot_type": "neat_swing",
                    "bot_instance_id": "default",
                },
            )
            if result:
                st.success("Training started!")
            else:
                st.error("Failed to start training")

# =============================================================================
# CONFIGURATION TAB
# =============================================================================
with tab_config:
    st.header("Strategy Configuration")

    config_data = fetch_sync(f"/api/v1/strategies/{_SELECTED_TYPE}/config-schema")
    if config_data and config_data.get("config_fields"):
        st.json(config_data)
    else:
        st.info("No configuration schema available")

# Auto-refresh
if auto_refresh:
    sleep(refresh_interval)
    st.rerun()
