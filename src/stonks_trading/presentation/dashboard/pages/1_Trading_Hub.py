"""Trading Hub - Portfolio, Bot Control, Models/Training, and Configuration.

Phase 10C: Consolidates Portfolio Overview, Live Trading, and Strategy Management.
"""

from time import sleep

import pandas as pd
import plotly.graph_objects as go
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

# Get registered instruments for symbol selectors
instruments_data = fetch_sync("/api/v1/instruments")
registered_symbols = []
if instruments_data and instruments_data.get("instruments"):
    registered_symbols = [i["symbol"] for i in instruments_data["instruments"] if i.get("enabled")]
if not registered_symbols:
    registered_symbols = ["BTC_USD", "ETH_USD"]  # Fallback

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
            # Single symbol selection (One Bot = One Instrument)
            new_bot_symbol = st.selectbox(
                "Trading Symbol",
                options=registered_symbols,
                index=0 if registered_symbols else None,
                help="Each bot trades ONE instrument only",
            )
            new_bot_mode = st.selectbox("Mode", ["dry_run", "live", "backtest"], key="new_bot_mode")

        if st.button("Register Bot", key="register_bot_btn"):
            result = post_sync(
                "/api/v1/bots",
                {
                    "bot_type": new_bot_type,
                    "instance_id": new_instance_id,
                    "symbols": [new_bot_symbol] if new_bot_symbol else ["BTC_USD"],
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
        col1, col2, col3, col4 = st.columns(4)

        status_data = fetch_sync(f"/api/v1/bots/{bot_type}/{instance_id}/status")
        current_status = status_data.get("status", "unknown") if status_data else "unknown"
        is_running = current_status == "running"

        with col1:
            if st.button("▶️ Start", disabled=is_running, use_container_width=True):
                result = post_sync(
                    f"/api/v1/bots/{bot_type}/{instance_id}/start",
                    {"mode": "dry_run"},
                )
                if result:
                    st.success(f"Started! PID: {result.get('pid')}")
                    sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to start")

        with col2:
            if st.button("⏹️ Stop", disabled=not is_running, use_container_width=True):
                result = post_sync(f"/api/v1/bots/{bot_type}/{instance_id}/stop")
                if result:
                    st.success("Stopped")
                    sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to stop")

        with col3:
            if st.button("🔄 Restart", use_container_width=True):
                result = post_sync(f"/api/v1/bots/{bot_type}/{instance_id}/restart")
                if result:
                    st.success(f"Restarted! PID: {result.get('pid')}")
                    sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to restart")

        with col4:
            if st.button("🚨 Emergency Stop", use_container_width=True):
                result = post_sync(
                    f"/api/v1/bots/{bot_type}/{instance_id}/emergency-stop",
                    {"close_positions": True},
                )
                if result:
                    st.error(
                        f"Emergency stopped! Closed {result.get('positions_closed', 0)} positions"
                    )
                    sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to emergency stop")

        st.divider()

        # Bot Status Row
        col1, col2, col3, col4 = st.columns(4)

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

        # Live View Section
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

    # Strategy selector
    selected_strategy = _SELECTED_STRATEGY
    selected_type = _SELECTED_TYPE

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

    # Fetch models
    col1, col2 = st.columns(2)
    with col1:
        show_active_only = st.checkbox("Show Active Only", value=False)
    with col2:
        symbol_filter = st.selectbox(
            "Filter by Symbol",
            options=["All"] + registered_symbols,
            index=0,
        )

    params = {"strategy_type": selected_type}
    if show_active_only:
        params["is_active"] = "true"
    if symbol_filter and symbol_filter != "All":
        params["symbol"] = symbol_filter

    models_data = fetch_sync("/api/v1/models/", params)

    # Also fetch completed training jobs that can be converted to models
    training_jobs_data = fetch_sync("/api/v1/training/jobs")
    completed_jobs = []
    if training_jobs_data and training_jobs_data.get("jobs"):
        completed_jobs = [j for j in training_jobs_data["jobs"] if j.get("status") == "completed"]

    # Display models
    if models_data and models_data.get("models"):
        models = models_data["models"]
        df = pd.DataFrame(models)
        st.dataframe(df, use_container_width=True)

        # Model activation
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
        st.info(
            "No models in registry yet. Train a model or select from completed training jobs below."
        )

    # Show completed training jobs that can be activated
    if completed_jobs:
        st.subheader("Completed Training Jobs (Ready for Activation)")
        jobs_df = pd.DataFrame(completed_jobs)
        st.dataframe(
            jobs_df[["job_id", "symbol", "generations_total", "best_fitness", "status"]],
            use_container_width=True,
        )

        st.info("Select a checkpoint from the Training tab to activate it as a model.")
    else:
        st.info("No completed training jobs yet. Start training from the Training tab.")

# =============================================================================
# TRAINING TAB - Async Training with Real-time Progress
# =============================================================================
with tab_training:
    st.header("Async Training Jobs")

    # Check for active training job in session state
    if "active_training_job" not in st.session_state:
        st.session_state.active_training_job = None

    # Layout: Two columns - New Training Form | Active Job Monitor
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("Start New Training")

        # Symbol must be from registered instruments
        train_symbol = st.selectbox(
            "Symbol",
            options=registered_symbols if registered_symbols else ["BTC_USD", "ETH_USD"],
            index=0,
            help="Select from registered instruments with backfilled data",
        )

        generations = st.number_input(
            "Generations",
            min_value=1,
            max_value=100,
            value=30,
            key="train_generations",
        )
        pop_size = st.number_input(
            "Population Size",
            min_value=10,
            max_value=500,
            value=150,
            key="train_pop_size",
        )
        training_capital = st.number_input(
            "Training Capital ($)",
            min_value=1000.0,
            max_value=1000000.0,
            value=100000.0,
            step=10000.0,
            help="Simulation capital - any value for training",
        )
        checkpoint_interval = st.number_input(
            "Checkpoint Interval",
            min_value=1,
            max_value=10,
            value=5,
            help="Save checkpoint every N generations",
        )

        if st.button("🚀 Start Async Training", type="primary", key="start_training_btn"):
            with st.spinner("Starting training job..."):
                result = post_sync(
                    "/api/v1/training/jobs",
                    {
                        "symbol": train_symbol.upper() if train_symbol else "BTC_USD",
                        "generations": generations,
                        "population_size": pop_size,
                        "training_capital": training_capital,
                        "checkpoint_interval": checkpoint_interval,
                        "strategy_type": "neat_swing",
                    },
                )
                if result and result.get("job_id"):
                    st.session_state.active_training_job = result["job_id"]
                    st.success(f"Training started! Job ID: {result['job_id']}")
                    sleep(1)
                    st.rerun()
                else:
                    st.error("Failed to start training")

    with col_right:
        # Monitor active training job
        if st.session_state.active_training_job:
            job_id = st.session_state.active_training_job

            # Fetch job status
            job_data = fetch_sync(f"/api/v1/training/jobs/{job_id}")

            if job_data:
                st.subheader(f"Training Job: {job_id[:8]}...")

                # Status indicator
                status = job_data.get("status", "unknown")
                status_emoji = {
                    "queued": "⏳",
                    "running": "🟢",
                    "completed": "✅",
                    "failed": "❌",
                }.get(status, "⚪")
                st.write(f"Status: {status_emoji} {status.upper()}")

                # Progress bar
                progress = job_data.get("progress_pct", 0)
                st.progress(progress / 100)

                # Metrics
                col_m1, col_m2, col_m3 = st.columns(3)
                with col_m1:
                    gen_completed = job_data.get("generations_completed", 0)
                    gen_total = job_data.get("generations_total", 1)
                    st.metric("Progress", f"{gen_completed}/{gen_total}")
                with col_m2:
                    best_fitness = job_data.get("best_fitness")
                    st.metric("Best Fitness", f"{best_fitness:.4f}" if best_fitness else "N/A")
                with col_m3:
                    st.metric("Symbol", job_data.get("symbol", "Unknown"))

                # Checkpoints
                checkpoints = job_data.get("checkpoints", [])
                if checkpoints:
                    st.subheader("Checkpoints")

                    # Fitness curve visualization
                    if len(checkpoints) > 1:
                        fig = go.Figure()
                        fig.add_trace(
                            go.Scatter(
                                x=[c["generation"] for c in checkpoints],
                                y=[c["fitness"] for c in checkpoints],
                                mode="lines+markers",
                                name="Fitness",
                            )
                        )
                        fig.update_layout(
                            title="Fitness Curve",
                            xaxis_title="Generation",
                            yaxis_title="Fitness",
                            height=300,
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    # Checkpoint table with select buttons
                    for cp in checkpoints:
                        col_cp1, col_cp2, col_cp3, col_cp4 = st.columns([1, 1, 1, 1])
                        with col_cp1:
                            st.write(f"Gen {cp['generation']}")
                        with col_cp2:
                            st.write(f"Fitness: {cp['fitness']:.4f}")
                        with col_cp3:
                            roi = cp.get("roi")
                            if roi:
                                st.write(f"ROI: {roi:.2f}%")
                        with col_cp4:
                            if st.button("Select", key=f"select_{cp['generation']}"):
                                result = post_sync(
                                    f"/api/v1/training/jobs/{job_id}/select-checkpoint",
                                    {"generation": cp["generation"]},
                                )
                                if result:
                                    st.success(
                                        f"Selected gen {cp['generation']}! Go to Models tab to activate."
                                    )

                # Auto-refresh if running
                if status == "running":
                    sleep(2)
                    st.rerun()

                # Clear button
                if status in ["completed", "failed"] and st.button("Clear Job"):
                    st.session_state.active_training_job = None
                    st.rerun()
            else:
                st.error("Failed to fetch job status")
                st.session_state.active_training_job = None
        else:
            st.info("No active training job. Start one from the left panel!")

    # Show training history
    st.divider()
    st.subheader("Training History")

    history_data = fetch_sync("/api/v1/training")
    if history_data and history_data.get("runs"):
        runs = history_data["runs"]
        st.dataframe(pd.DataFrame(runs), use_container_width=True)
    else:
        st.info("No historical training runs")

# =============================================================================
# CONFIGURATION TAB
# =============================================================================
with tab_config:
    st.header("Strategy Configuration")

    # Strategy selector
    if strategies_data and strategies_data.get("strategies"):
        strategies = strategies_data["strategies"]
        strategy_options = {s["name"]: s["type"] for s in strategies}
        selected_strategy_name = st.selectbox(
            "Select Strategy",
            options=list(strategy_options.keys()),
            index=0,
        )
        config_type = strategy_options[selected_strategy_name]
    else:
        config_type = "neat_swing"

    config_data = fetch_sync(f"/api/v1/strategies/{config_type}/config-schema")
    if config_data and config_data.get("config_fields"):
        st.json(config_data)

        # Show editable config form
        st.subheader("Edit Configuration")
        config_fields = config_data.get("config_fields", [])

        for field in config_fields:
            field_name = field.get("name", "")
            field_type = field.get("type", "string")
            field_default = field.get("default")

            if field_type == "integer":
                st.number_input(
                    field_name,
                    value=field_default or 0,
                    key=f"config_{field_name}",
                )
            elif field_type == "float":
                st.number_input(
                    field_name,
                    value=float(field_default) if field_default else 0.0,
                    format="%.4f",
                    key=f"config_{field_name}",
                )
            else:
                st.text_input(
                    field_name,
                    value=str(field_default) if field_default else "",
                    key=f"config_{field_name}",
                )

        st.info("Configuration changes require bot restart to take effect.")
    else:
        st.info("No configuration schema available for this strategy")

# Auto-refresh
if auto_refresh:
    sleep(refresh_interval)
    st.rerun()
