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

# Fetch data first (needed for stepper)
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
# WORKFLOW STEPPER - Guides users through the complete NEAT workflow
# =============================================================================
st.markdown("---")

# Initialize stepper state
if "workflow_step" not in st.session_state:
    st.session_state.workflow_step = 1
if "stepper_symbol" not in st.session_state:
    st.session_state.stepper_symbol = registered_symbols[0] if registered_symbols else "BTC_USD"
if "stepper_bot_id" not in st.session_state:
    st.session_state.stepper_bot_id = "my-bot-1"

# Check current state to determine available steps
has_instruments = len(registered_symbols) > 0
models_data = fetch_sync("/api/v1/models/")
has_models = models_data and models_data.get("models") and len(models_data.get("models", [])) > 0
bots_data = fetch_sync("/api/v1/bots")
has_bots = bots_data and bots_data.get("bots") and len(bots_data.get("bots", [])) > 0
training_jobs = fetch_sync("/api/v1/training")
has_training = training_jobs and training_jobs.get("runs") and len(training_jobs.get("runs", [])) > 0

# Stepper progress
stepper_cols = st.columns(5)
step_config = [
    ("1️⃣ Data", "Register instrument and backfill data", has_instruments),
    ("2️⃣ Train", "Train NEAT model on historical data", has_training),
    ("3️⃣ Models", "Activate trained model", has_models),
    ("4️⃣ Validate", "Backtest before deployment", True),  # Always available
    ("5️⃣ Deploy", "Register and start trading bot", has_bots),
]

for i, (stepper_col, (label, desc, completed)) in enumerate(zip(stepper_cols, step_config), 1):
    with stepper_col:
        if completed:
            st.success(f"**{label}** ✓")
        else:
            st.info(f"**{label}**")
        st.caption(desc)

# Determine current step
if not has_instruments:
    current_step = 1
    st.warning("👆 **Step 1**: You need to register an instrument first! Go to the **Market Hub** page to add symbols.")
elif not has_training:
    current_step = 2
    st.info("👆 **Step 2**: Start training a model. Go to the **Training** tab below.")
elif not has_models:
    current_step = 3
    st.info("👆 **Step 3**: Training complete! Activate your model in the **Models** tab.")
elif not has_bots:
    current_step = 5
    st.info("👆 **Step 5**: Deploy your bot! Go to the **Bot Control** tab to register and start trading.")
else:
    current_step = 5
    st.success("✅ **Workflow Complete!** You have bots deployed. Monitor them in the Bot Control tab.")

st.markdown("---")

# Tabs in WORKFLOW ORDER: Training → Models → Bot Control → Portfolio
# (Portfolio moved to end as it's the result of deployment)
tab_training, tab_models, tab_bot, tab_portfolio, tab_config = st.tabs(
    ["1️⃣ Training", "2️⃣ Models", "3️⃣ Bot Control", "4️⃣ Portfolio", "Configuration"]
)

# =============================================================================
# TRAINING TAB - Step 2: Train NEAT model
# =============================================================================
with tab_training:
    st.header("Async Training Jobs")

    # Step guidance
    st.info("""
    **Step 2: NEAT Training** 🧠

    Train a NEAT model on historical market data. This process evolves trading strategies
    using genetic algorithms, similar to NEAT/main.py.

    **Before starting:**
    - Make sure you have registered instruments (Step 1 - Market Hub)
    - Ensure historical data is available via backfill

    **What happens:**
    - Population evolves over generations
    - Best genomes saved as checkpoints
    - Fitness curve shows improvement
    - Training completes automatically
    """)

    # Check for active training job in session state
    if "active_training_job" not in st.session_state:
        st.session_state.active_training_job = None

    # Layout: Two columns - New Training Form | Active Job Monitor
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("Start New Training")

        # Check if instruments exist
        if not registered_symbols:
            st.error("""
            ❌ **No Instruments Registered!**

            You must register an instrument before training.

            👉 Go to **Market Hub** page to add symbols first.
            """)
            st.stop()

        # Symbol must be from registered instruments
        train_symbol = st.selectbox(
            "Symbol",
            options=registered_symbols,
            index=0,
            help="Select from registered instruments with backfilled data",
        )

        # Check if data exists for this symbol
        candles_data = fetch_sync(f"/api/v1/market/candles/{train_symbol}", {"limit": 10})
        has_data = candles_data and candles_data.get("candles") and len(candles_data.get("candles", [])) > 0

        if not has_data:
            st.warning(f"""
            ⚠️ **No Market Data for {train_symbol}**

            You need to backfill historical data before training.

            👉 Go to **Market Hub** page and run Massive Backfill for {train_symbol}
            """)

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

        # Disable button if no data
        can_train = has_data and registered_symbols

        if st.button(
            "🚀 Start Async Training",
            type="primary",
            key="start_training_btn",
            disabled=not can_train,
        ):
            if not can_train:
                st.error("Cannot start training: No data available")
            else:
                with st.spinner("Starting training job..."):
                    result = post_sync(
                        "/api/v1/training/jobs",
                        {
                            "symbol": train_symbol.upper() if train_symbol else "BTC_USD",
                            "generations": int(generations),
                            "population_size": int(pop_size),
                            "training_capital": float(training_capital),
                            "checkpoint_interval": int(checkpoint_interval),
                            "strategy_type": "neat_swing",
                        },
                    )
                    if result and result.get("job_id"):
                        st.session_state.active_training_job = result["job_id"]
                        st.success(f"Training started! Job ID: {result['job_id']}")
                        sleep(1)
                        st.rerun()
                    else:
                        st.error(f"Failed to start training. Response: {result}")

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
# MODELS TAB - Step 3: Activate trained model
# =============================================================================
with tab_models:
    st.header("Model Registry")

    # Step guidance
    st.info("""
    **Step 3: Model Activation** 📋

    After training completes, your best genomes are saved as checkpoints.
    Activate a checkpoint to make it available for live trading.

    **Workflow:**
    1. Train a model (Step 2 - Training tab)
    2. Select the best checkpoint from completed training
    3. Activate it here
    4. Deploy bot with activated model (Step 5 - Bot Control tab)
    """)

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
    training_jobs_data = fetch_sync("/api/v1/training")
    completed_jobs = []
    if training_jobs_data and training_jobs_data.get("runs"):
        completed_jobs = [j for j in training_jobs_data["runs"] if j.get("status") == "completed"]

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
# BOT CONTROL TAB - Step 5: Deploy and Monitor Bot
# =============================================================================
with tab_bot:
    st.header("Bot Control Center")

    # Check prerequisites
    active_model = fetch_sync("/api/v1/models/", {"is_active": "true"})
    has_active_model = active_model and active_model.get("models") and len(active_model["models"]) > 0

    if not has_active_model:
        st.error("""
        ❌ **Cannot Deploy: No Active Model!**

        You must complete the workflow before deploying a bot:

        **Current Status:**
        1. ✅ Data: Instruments registered
        2. ⚠️ Training: Check Training tab
        3. ❌ Model: **No active model found**

        **Next Steps:**
        1. Go to **Training** tab and complete a training run
        2. Go to **Models** tab and activate your best checkpoint
        3. Return here to deploy
        """)
        st.stop()

    st.success(f"""
    ✅ **Step 5: Bot Deployment** 🚀

    Active model ready: **{active_model['models'][0].get('id', 'Unknown')}**

    **Prerequisites Complete:**
    1. ✅ Register instrument (Market Hub)
    2. ✅ Train model (Training tab)
    3. ✅ Activate model: {active_model['models'][0].get('symbol', 'Unknown')}
    4. ✅ (Optional) Run backtest for validation (Analytics Hub)

    **Now you can:**
    1. Register a new bot below
    2. Select trading mode (dry_run recommended for testing)
    3. Click Start to deploy with the active model
    """)
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
            uptime = status_data.get("uptime_seconds") if status_data else None
            uptime = uptime or 0  # Handle None values
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
# CONFIGURATION TAB - NEAT Configuration
# =============================================================================
with tab_config:
    st.header("Strategy Configuration")

    # Step guidance
    st.info("""
    **NEAT Configuration Settings** ⚙️

    These settings control how the NEAT algorithm evolves trading strategies.
    They match the configuration from NEAT/main.py.

    **Key Parameters:**
    - **Population Size**: Number of genomes per generation (default: 150)
    - **Generations**: Training iterations (default: 30)
    - **Decision Threshold**: Signal threshold for buy/sell (default: 0.6)
    - **Min Trade Interval**: Minimum minutes between trades (default: 15)
    - **Transaction Fee**: Trading fee percentage (default: 0.001)

    *Changes require restarting training to take effect.*
    """)

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
