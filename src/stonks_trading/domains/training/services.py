"""Training domain services - EXTERNAL API CALLS AND CALCULATIONS.

Services handle:
- NEAT-python interaction (TrainingExecutor)
- Genome evaluation on data (GenomeEvaluator)
- Genome serialization/deserialization (GenomeSerializer)
- Training data fetching (TrainingDataProvider)

Business logic belongs in use_cases.py - not here.

Service rules (per architecture.md):
- Classes allowed for service layer
- No business logic - only calculations and external calls
- Pure transformation functions where possible
"""

import json
import pickle
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import httpx
import neat
import pandas as pd

from stonks_trading.domains.strategies.neat_swing.config_builder import create_default_config
from stonks_trading.domains.strategies.neat_swing.features import engineer_features
from stonks_trading.domains.strategies.neat_swing.trainer import (
    NeatTrainer,
    evaluate_genome_on_data,
)
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.shared.logger import logger
from stonks_trading.shared.redis_client import get_redis
from stonks_trading.shared.storage.duckdb_client import DuckDBClient

from .entities import StartTrainingRequest, TrainingJob


class TrainingExecutor:
    """Executes NEAT training runs.

    Service - handles the external neat-python library.
    Business logic (when to train, which data) belongs in use cases.
    """

    def __init__(
        self,
        generations: int = 30,
        population_size: int = 150,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,
        decision_threshold: float = 0.6,
        min_trade_interval: int = 15,
    ):
        """Initialize training executor.

        Args:
            generations: Number of generations to train
            population_size: NEAT population size
            initial_capital: Starting capital for episodes
            fee_rate: Transaction fee rate
            decision_threshold: Probability threshold for trades
            min_trade_interval: Minimum steps between trades
        """
        self.generations = generations
        self.population_size = population_size
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.decision_threshold = decision_threshold
        self.min_trade_interval = min_trade_interval

    async def execute_training(
        self,
        train_data: pd.DataFrame,
        progress_callback: Callable[[int, float, float], None] | None = None,
    ) -> tuple[neat.DefaultGenome, list[dict[str, Any]]]:
        """Execute training and return winner + generation metrics.

        Args:
            train_data: Training data DataFrame
            progress_callback: Optional callback(generation, best_fitness, mean_fitness)

        Returns:
            Tuple of (best_genome, generation_metrics_list)
        """
        config = create_default_config()
        trainer = NeatTrainer(
            train_data=train_data,
            config=config,
            initial_capital=self.initial_capital,
            episode_steps=20160,
            fee_rate=self.fee_rate,
            decision_threshold=self.decision_threshold,
            min_trade_interval=self.min_trade_interval,
        )

        # Run training
        winner = trainer.train(generations=self.generations)

        # Build metrics list (simplified - full implementation would track per-generation)
        generation_metrics: list[dict[str, Any]] = []

        # TODO: Add custom reporter that calls progress_callback
        # For now, just return the winner
        return winner, generation_metrics

    def get_config(self) -> neat.Config:
        """Get NEAT configuration for this executor."""
        return create_default_config()


class GenomeEvaluator:
    """Evaluates genomes on validation data.

    Service - handles neat-python evaluation.
    Business logic (thresholds, decisions) belongs in use cases.
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        fee_rate: float = 0.001,
        decision_threshold: float = 0.6,
        min_trade_interval: int = 15,
    ):
        """Initialize genome evaluator.

        Args:
            initial_capital: Starting capital for evaluation
            fee_rate: Transaction fee rate
            decision_threshold: Probability threshold for trades
            min_trade_interval: Minimum steps between trades
        """
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.decision_threshold = decision_threshold
        self.min_trade_interval = min_trade_interval

    async def evaluate_on_data(
        self,
        genome: neat.DefaultGenome,
        data: pd.DataFrame,
    ) -> dict[str, Any]:
        """Evaluate genome on data and return metrics.

        Args:
            genome: NEAT genome to evaluate
            data: DataFrame with OHLCV data

        Returns:
            Dict with keys:
            - final_equity: Final portfolio value
            - final_roi_pct: ROI percentage
            - total_trades: Number of trades
            - max_drawdown: Maximum drawdown
            - equity_curve: List of equity values
        """
        config = create_default_config()  # For evaluation only
        results = evaluate_genome_on_data(
            genome=genome,
            config=config,
            data=data,
            initial_capital=self.initial_capital,
            fee_rate=self.fee_rate,
            decision_threshold=self.decision_threshold,
            min_trade_interval=self.min_trade_interval,
            verbose=False,
        )

        return {
            "final_equity": results["final_equity"],
            "final_roi_pct": results["final_roi_pct"],
            "total_trades": results["total_trades"],
            "max_drawdown": results["max_drawdown"],
            "equity_curve": results["equity_curve"],
        }

    def calculate_improvement(
        self,
        new_roi: float,
        prev_roi: float,
    ) -> float:
        """Calculate improvement percentage.

        Args:
            new_roi: New genome ROI
            prev_roi: Previous genome ROI

        Returns:
            Improvement as percentage points
        """
        return new_roi - prev_roi


class GenomeSerializer:
    """Serializes/deserializes genomes to/from storage.

    Service - handles pickle serialization.
    """

    @staticmethod
    def serialize(genome: neat.DefaultGenome, config: neat.Config) -> bytes:
        """Serialize genome and config to bytes.

        Args:
            genome: NEAT genome
            config: NEAT config

        Returns:
            Pickled bytes
        """
        return pickle.dumps((genome, config))

    @staticmethod
    def deserialize(data: bytes) -> tuple[neat.DefaultGenome, neat.Config]:
        """Deserialize genome from bytes.

        Args:
            data: Pickled bytes

        Returns:
            Tuple of (genome, config)
        """
        return pickle.loads(data)  # type: ignore[no-any-return]


class TrainingDataProvider:
    """Provides training data from multiple sources.

    Service - aggregates data from DuckDB, Parquet, etc.
    Business logic (which data, date ranges) in use cases.
    """

    REQUIRED_FEATURES = ["trend_1h", "rsi_1h", "rsi_15m", "roc", "bb_width"]
    COLUMN_MAPPING = {
        "timestamp": "Datetime",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }

    def __init__(
        self,
        db_path: str = "data/neat.db",
    ) -> None:
        """Initialize training data provider.

        Args:
            db_path: Path to DuckDB database file
        """
        self._db_client = DuckDBClient(db_path=db_path)

    async def fetch_training_window(
        self,
        symbol: str,
        days: int = 30,
    ) -> pd.DataFrame:
        """Fetch training data window from DuckDB.

        Args:
            symbol: Trading symbol
            days: Number of days of historical data

        Returns:
            DataFrame with OHLCV data and features
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        return await self._fetch_data(symbol, start_date, end_date, "training")

    async def fetch_validation_data(
        self,
        symbol: str,
        days: int = 14,
    ) -> pd.DataFrame:
        """Fetch validation data (last N days after training window).

        Args:
            symbol: Trading symbol
            days: Number of days of validation data

        Returns:
            DataFrame with OHLCV data for validation
        """
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        return await self._fetch_data(symbol, start_date, end_date, "validation")

    async def fetch_all_available_data(
        self,
        symbol: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Fetch ALL available data with 80/20 train/test split.

        Mimics NEAT/main.py load_data() behavior:
        - Uses entire available dataset from DuckDB
        - Splits 80% train, 20% test
        - Returns both train and test DataFrames

        Args:
            symbol: Trading symbol

        Returns:
            Tuple of (train_df, test_df)
        """
        self._db_client.connect()

        try:
            symbol_vo = Symbol(value=symbol)

            # Get ALL data (not just last 30 days)
            # Use a very early start date to get all available data
            start_date = datetime(2020, 1, 1)
            end_date = datetime.utcnow()

            raw_data = self._db_client.get_data_range(
                symbol=symbol_vo,
                start=start_date,
                end=end_date,
            )

            if not raw_data:
                raise ValueError(f"No data found for {symbol}")

            df = self._to_dataframe(raw_data)
            df = self._ensure_features(df)

            # 80/20 split like NEAT/main.py line 90-91
            split_idx = int(len(df) * 0.8)
            train_df = df.iloc[:split_idx]
            test_df = df.iloc[split_idx:]

            logger.info(
                "Loaded training data",
                symbol=symbol,
                total_rows=len(df),
                train_rows=len(train_df),
                test_rows=len(test_df),
            )

            return train_df, test_df

        finally:
            self._db_client.close()

    async def _fetch_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        data_type: str,
    ) -> pd.DataFrame:
        """Fetch data from DuckDB for specified range.

        Args:
            symbol: Trading symbol
            start_date: Start of date range
            end_date: End of date range
            data_type: "training" or "validation" (for error messages)

        Returns:
            DataFrame with OHLCV data and features

        Raises:
            ValueError: If no data found
        """
        self._db_client.connect()

        try:
            symbol_vo = Symbol(value=symbol)
            raw_data = self._db_client.get_data_range(
                symbol=symbol_vo,
                start=start_date,
                end=end_date,
            )

            if not raw_data:
                raise ValueError(
                    f"No {data_type} data found for {symbol} in date range "
                    f"{start_date} to {end_date}"
                )

            df = self._to_dataframe(raw_data)
            return self._ensure_features(df)

        finally:
            self._db_client.close()

    def _to_dataframe(self, raw_data: list[dict]) -> pd.DataFrame:
        """Convert raw DuckDB data to DataFrame with proper columns.

        Args:
            raw_data: List of dictionaries from DuckDB

        Returns:
            DataFrame with OHLCV and features
        """
        df = pd.DataFrame(raw_data)
        df = df.rename(columns=self.COLUMN_MAPPING)

        if "Datetime" in df.columns:
            df.set_index("Datetime", inplace=True)

        return df

    def _ensure_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure all required features exist and are populated.

        Recomputes features using engineer_features when required columns are
        missing or when any required feature contains NaN values. This guards
        against training on stale/corrupted DuckDB rows that were inserted
        without features (e.g., raw massive backfill candles).

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with all required features computed
        """
        if not all(feat in df.columns for feat in self.REQUIRED_FEATURES):
            return engineer_features(df)

        if df[self.REQUIRED_FEATURES].isna().any().any():
            # Drop stale/null feature columns so engineer_features can recreate them.
            df = df.drop(columns=[c for c in self.REQUIRED_FEATURES if c in df.columns])
            return engineer_features(df)

        return df


class CheckpointManager:
    """Manages training checkpoints with retention policy.

    Service - handles checkpoint creation and retention thinning.
    """

    def __init__(
        self,
        keep_every_nth: int = 5,
        max_checkpoints: int = 20,
    ):
        """Initialize checkpoint manager.

        Args:
            keep_every_nth: Keep every Nth checkpoint
            max_checkpoints: Maximum checkpoints to retain
        """
        self.keep_every_nth = keep_every_nth
        self.max_checkpoints = max_checkpoints

    def should_retain_checkpoint(
        self,
        generation: int,
        fitness: float,
        best_fitness: float,
    ) -> bool:
        """Determine if checkpoint should be retained.

        Args:
            generation: Generation number
            fitness: Generation fitness
            best_fitness: Best fitness so far

        Returns:
            True if checkpoint should be kept
        """
        # Always keep best
        if fitness >= best_fitness:
            return True
        # Keep every Nth
        return generation % self.keep_every_nth == 0

    def apply_retention_policy(
        self,
        checkpoints: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Apply retention policy to list of checkpoints.

        Args:
            checkpoints: List of checkpoint dicts with generation, fitness

        Returns:
            Filtered list of checkpoints to retain
        """
        if len(checkpoints) <= self.max_checkpoints:
            return checkpoints

        # Sort by fitness descending
        sorted_cp = sorted(checkpoints, key=lambda x: x.get("fitness", 0), reverse=True)

        # Keep best and every Nth
        kept = []
        for i, cp in enumerate(sorted_cp):
            gen = cp.get("generation", 0)
            if i < self.max_checkpoints // 2:
                kept.append(cp)  # Keep top performers
            elif gen % self.keep_every_nth == 0:
                kept.append(cp)

        return kept


class TrainingProcessManager:
    """Manages training jobs via Worker container.

    All training operations are delegated to the Bot Worker via HTTP API.
    The API container never runs NEAT training directly.

    Mirrors ProcessManager from botcontrol domain.
    """

    def __init__(self):
        """Initialize with Worker HTTP client."""
        self._worker_base_url = "http://bot-worker:8001"
        logger.info("TrainingProcessManager initialized (Worker delegation mode)")

    async def start_training(
        self,
        symbol: str,
        generations: int,
        population_size: int,
        training_capital: float,
        checkpoint_interval: int,
        strategy_type: str = "neat_swing",
        csv_path: str | None = None,
    ):
        """Start training by delegating to Worker.

        Args:
            symbol: Trading symbol (e.g., "BTC_USD")
            generations: Number of NEAT generations
            population_size: NEAT population size
            training_capital: Initial capital for training
            checkpoint_interval: Save checkpoint every N generations
            strategy_type: Strategy type (default: "neat_swing")
            csv_path: Optional CSV path to load data exactly like NEAT/main.py

        Returns:
            TrainingJob with job_id for polling
        """
        logger.info(
            f"Delegating training for {symbol} to Worker",
            generations=generations,
            population_size=population_size,
            csv_path=csv_path,
        )

        request = StartTrainingRequest(
            symbol=symbol,
            generations=generations,
            population_size=population_size,
            training_capital=training_capital,
            checkpoint_interval=checkpoint_interval,
            strategy_type=strategy_type,
            csv_path=csv_path,
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._worker_base_url}/training/jobs",
                    json={
                        "symbol": request.symbol,
                        "generations": request.generations,
                        "population_size": request.population_size,
                        "training_capital": request.training_capital,
                        "checkpoint_interval": request.checkpoint_interval,
                        "strategy_type": request.strategy_type,
                        "csv_path": request.csv_path,
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                return TrainingJob(
                    job_id=data["job_id"],
                    symbol=symbol,
                    status=data["status"],
                    generations_total=generations,
                    generations_completed=0,
                    best_fitness=None,
                    best_roi=None,
                    progress_pct=0.0,
                    checkpoint_dir=f"data/training/{data['job_id']}",
                    started_at=datetime.fromisoformat(data["started_at"]),
                    error=None,
                )

        except Exception as e:
            logger.error(f"Worker failed to start training: {e}")
            raise RuntimeError(f"Worker failed to start training: {e}") from e

    async def get_job_status(self, job_id: str):
        """Get training job status from Worker."""
        try:
            redis = await get_redis()
            data = await redis.get(f"training:job:{job_id}")

            if not data:
                return None

            if isinstance(data, bytes):
                data = data.decode("utf-8")

            job_data = json.loads(data)
            return TrainingJob(
                job_id=job_data["id"],
                symbol=job_data["symbol"],
                status=job_data["status"],
                generations_total=job_data["generations_total"],
                generations_completed=job_data["generations_completed"],
                best_fitness=job_data.get("best_fitness"),
                best_roi=job_data.get("best_roi"),
                progress_pct=job_data.get("progress_pct", 0.0),
                checkpoint_dir=job_data.get("checkpoint_dir"),
                started_at=datetime.fromisoformat(job_data["started_at"])
                if job_data.get("started_at")
                else None,
                error=job_data.get("error"),
                checkpoints=job_data.get("checkpoints", []),
            )

        except Exception as e:
            logger.error(f"Failed to get training status: {e}")
            return None

    async def stop_training(self, job_id: str, graceful: bool = True) -> bool:
        """Stop training job via Worker."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self._worker_base_url}/training/jobs/{job_id}/stop",
                    params={"graceful": graceful},
                    timeout=10.0,
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to stop training: {e}")
            return False

    async def list_checkpoints(self, job_id: str) -> list[dict[str, Any]]:
        """List all checkpoints for a training job."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._worker_base_url}/training/jobs/{job_id}/checkpoints",
                    timeout=10.0,
                )
                if response.status_code == 404:
                    return []
                response.raise_for_status()
                data = response.json()
                return data.get("checkpoints", [])
        except Exception as e:
            logger.error(f"Failed to list checkpoints: {e}")
            return []

    async def get_checkpoint(self, job_id: str, generation: int) -> dict[str, Any] | None:
        """Get checkpoint data from Worker."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._worker_base_url}/training/jobs/{job_id}/checkpoints/{generation}",
                    timeout=10.0,
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get checkpoint: {e}")
            return None

    async def get_checkpoint_plot(self, job_id: str, generation: int) -> str | None:
        """Get checkpoint plot HTML from Worker."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._worker_base_url}/training/jobs/{job_id}/checkpoints/{generation}/plot",
                    timeout=10.0,
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
                return data.get("plot_html")
        except Exception as e:
            logger.error(f"Failed to get checkpoint plot: {e}")
            return None


def get_training_process_manager() -> TrainingProcessManager:
    """Get or create global TrainingProcessManager."""
    global _training_process_manager
    if _training_process_manager is None:
        _training_process_manager = TrainingProcessManager()
    return _training_process_manager


_training_process_manager: TrainingProcessManager | None = None
