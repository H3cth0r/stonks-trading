"""Strategy Management - Training, models, and strategy configuration.

Phase 10H: Merges Training Progress + Model Registry pages.
"""

from time import sleep

import pandas as pd
import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync, post_sync

st.set_page_config(page_title="Strategy Management", page_icon="🧠", layout="wide")

st.title("🧠 Strategy Management")

# Strategy Selection
strategies_data = fetch_sync("/api/v1/strategies/")
selected_strategy = "NEAT Swing Trading"
selected_type = "neat_swing"

if strategies_data and strategies_data.get("strategies"):
    strategies = strategies_data["strategies"]
    strategy_names = [s["name"] for s in strategies]
    if strategy_names:
        selected_strategy = st.selectbox("Strategy", strategy_names)
        selected_type = next(
            (s["type"] for s in strategies if s["name"] == selected_strategy), "neat_swing"
        )

# Tabs for different sections
tab_models, tab_training, tab_config = st.tabs(["Models", "Training Runs", "Configuration"])

with tab_models:
    st.header(f"{selected_strategy} Models")

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        show_active_only = st.checkbox("Show Active Only", value=False)
    with col2:
        symbol_filter = st.text_input("Filter by Symbol", placeholder="BTC_USD")

    # Fetch models
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
        st.info("No models found")

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

with tab_config:
    st.header(f"{selected_strategy} Configuration")

    config_data = fetch_sync(f"/api/v1/strategies/{selected_type}/config-schema")
    if config_data and config_data.get("config_fields"):
        st.json(config_data)
    else:
        st.info("No configuration schema available")

# Auto-refresh
auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
if auto_refresh:
    sleep(30)
    st.rerun()
