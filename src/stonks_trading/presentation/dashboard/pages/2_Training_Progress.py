"""Training Progress - NEAT training runs and fitness evolution.

All imports at module level per CLEAN architecture - no lazy imports.
"""

import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync

st.set_page_config(page_title="Training Progress", page_icon="🧬")

st.title("🧬 Training Progress")

# Training Runs
st.header("Training Runs")
runs_data = fetch_sync("/api/v1/training", {"limit": 20})
if runs_data and "runs" in runs_data and runs_data["runs"]:
    runs = runs_data["runs"]
    st.dataframe(runs, use_container_width=True)

    # Training run summary
    if runs:
        col1, col2, col3, col4 = st.columns(4)
        total_runs = len(runs)
        running = sum(1 for r in runs if r.get("status") == "running")
        completed = sum(1 for r in runs if r.get("status") == "completed")
        failed = sum(1 for r in runs if r.get("status") == "failed")

        with col1:
            st.metric("Total Runs", total_runs)
        with col2:
            st.metric("Running", running)
        with col3:
            st.metric("Completed", completed)
        with col4:
            st.metric("Failed", failed)

        # Best fitness tracking
        completed_runs = [r for r in runs if r.get("status") == "completed"]
        if completed_runs and any(r.get("best_fitness") for r in completed_runs):
            best_fitness = max(
                (r.get("best_fitness", 0) for r in completed_runs if r.get("best_fitness")),
                default=0,
            )
            st.metric("Best Fitness Achieved", f"{best_fitness:.4f}")
else:
    st.info("No training runs recorded")

# Select a training run for details
st.header("Training Run Details")
if runs_data and "runs" in runs_data and runs_data["runs"]:
    runs = runs_data["runs"]
    run_options = [
        f"Run #{r['id']} - {r.get('symbol', 'Unknown')} ({r.get('status', 'unknown')})"
        for r in runs
    ]
    selected_run = st.selectbox("Select Training Run", run_options)

    if selected_run:
        run_id = int(selected_run.split("#")[1].split(" ")[0])
        run_details = fetch_sync(f"/api/v1/training/{run_id}")

        if run_details:
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Run Information")
                st.json(
                    {
                        "id": run_details.get("id"),
                        "symbol": run_details.get("symbol"),
                        "status": run_details.get("status"),
                        "started_at": run_details.get("started_at"),
                        "finished_at": run_details.get("finished_at"),
                        "bot_type": run_details.get("bot_type"),
                        "bot_instance_id": run_details.get("bot_instance_id"),
                    }
                )

            with col2:
                st.subheader("Performance Metrics")
                st.json(
                    {
                        "best_fitness": run_details.get("best_fitness"),
                        "best_validation_roi": run_details.get("best_validation_roi"),
                        "generations_completed": run_details.get("generations_completed"),
                        "git_sha": run_details.get("git_sha"),
                    }
                )

            # Checkpoints
            st.subheader("Checkpoints")
            checkpoints_data = fetch_sync(f"/api/v1/training/{run_id}/checkpoints")
            if (
                checkpoints_data
                and "checkpoints" in checkpoints_data
                and checkpoints_data["checkpoints"]
            ):
                st.dataframe(checkpoints_data["checkpoints"], use_container_width=True)
            else:
                st.info("No checkpoints available for this run")

            # Config
            if "config" in run_details and run_details["config"]:
                with st.expander("Training Configuration"):
                    st.json(run_details["config"])
else:
    st.info("Select a training run to view details")

# Fitness Chart Placeholder
st.header("Fitness Evolution")
st.info("Fitness charts require checkpoint history data. Implementation pending.")

# Species Diversity Placeholder
st.header("Species Diversity")
st.info("Species diversity visualization requires NEAT population data. Implementation pending.")
