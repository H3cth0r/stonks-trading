"""Model Registry - Genome management and activation.

All imports at module level per CLEAN architecture - no lazy imports.
"""

import streamlit as st

from stonks_trading.presentation.dashboard.utils import fetch_sync, post_sync

st.set_page_config(page_title="Model Registry", page_icon="🧠")

st.title("🧠 Model Registry")

# Genomes List
st.header("Genomes")
genomes_data = fetch_sync("/api/v1/genomes")
if genomes_data and "genomes" in genomes_data and genomes_data["genomes"]:
    genomes = genomes_data["genomes"]
    st.dataframe(genomes, use_container_width=True)

    # Genome summary stats
    col1, col2, col3 = st.columns(3)
    total_genomes = len(genomes)
    active_genomes = sum(1 for g in genomes if g.get("is_active", False))
    inactive_genomes = total_genomes - active_genomes

    with col1:
        st.metric("Total Genomes", total_genomes)
    with col2:
        st.metric("Active", active_genomes)
    with col3:
        st.metric("Inactive", inactive_genomes)

    # Genome activation/deactivation
    st.subheader("Genome Actions")
    genome_ids = [f"{g['id']} - {g.get('model_family', 'Unknown')}" for g in genomes]
    selected_genome = st.selectbox("Select Genome", genome_ids)

    if selected_genome:
        genome_id = int(selected_genome.split(" ")[0])
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Activate Genome", type="primary"):
                result = post_sync(f"/api/v1/genomes/{genome_id}/activate", {})
                if result:
                    st.success(f"Genome {genome_id} activated successfully!")
                    st.rerun()
                else:
                    st.error("Failed to activate genome")
        with col2:
            if st.button("Deactivate Genome"):
                result = post_sync(f"/api/v1/genomes/{genome_id}/deactivate", {})
                if result:
                    st.success(f"Genome {genome_id} deactivated successfully!")
                    st.rerun()
                else:
                    st.error("Failed to deactivate genome")
else:
    st.info("No genomes registered")

# Import Genome (Admin)
st.header("Import Genome (Admin)")
with st.form("import_genome"):
    col1, col2 = st.columns(2)
    with col1:
        model_family = st.text_input("Model Family", placeholder="neat-swing-v1")
        feature_schema_id = st.text_input("Feature Schema ID", placeholder="schema-001")
        trainer_git_sha = st.text_input("Trainer Git SHA", placeholder="abc123...")
    with col2:
        bot_type = st.text_input("Bot Type", placeholder="neat_swing")
        bot_instance_id = st.text_input("Bot Instance ID", placeholder="instance-001")
        symbol = st.text_input("Symbol", placeholder="BTCUSDT")

    artifact_uri = st.text_input("Artifact URI", placeholder="s3://bucket/genomes/model.pkl")
    checksum = st.text_input("Checksum", placeholder="sha256:...")

    config_json = st.text_area("Config (JSON)", placeholder='{"key": "value"}')

    submitted = st.form_submit_button("Import Genome")
    if submitted:
        if not all([model_family, bot_type, bot_instance_id, symbol, artifact_uri, checksum]):
            st.error("Please fill in all required fields")
        else:
            import_data = {
                "model_family": model_family,
                "feature_schema_id": feature_schema_id,
                "trainer_git_sha": trainer_git_sha,
                "bot_type": bot_type,
                "bot_instance_id": bot_instance_id,
                "symbol": symbol,
                "artifact_uri": artifact_uri,
                "checksum": checksum,
            }
            if config_json:
                import json
                try:
                    import_data["config"] = json.loads(config_json)
                except json.JSONDecodeError:
                    st.error("Invalid JSON in config field")
                    import_data = {}

            if import_data and import_data.get("model_family"):
                result = post_sync("/api/v1/genomes/import", import_data)
                if result:
                    st.success("Genome imported successfully!")
                    st.json(result)
                else:
                    st.error("Failed to import genome")

# Prune Genomes (Admin)
st.header("Prune Genomes (Admin)")
with st.expander("Prune Old Genomes"):
    col1, col2 = st.columns(2)
    with col1:
        retention_days = st.number_input("Retention Days", min_value=1, value=30)
    with col2:
        keep_active = st.checkbox("Keep Active Genomes", value=True)

    dry_run = st.checkbox("Dry Run (preview only)", value=True)

    if st.button("Prune Genomes", type="secondary"):
        prune_data = {
            "retention_days": int(retention_days),
            "keep_active": keep_active,
            "dry_run": dry_run,
        }
        result = post_sync("/api/v1/genomes/prune", prune_data)
        if result:
            if dry_run:
                st.info("Dry run results:")
            else:
                st.success("Pruning completed!")
            st.json(result)
        else:
            st.error("Failed to prune genomes")
