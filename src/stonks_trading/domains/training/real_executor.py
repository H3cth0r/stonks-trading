"""Real training executor that actually runs NEAT.

DEPRECATED: Training now runs in Worker container.
Use TrainingProcessManager from services.py instead.

This module is kept for reference during migration. Will be removed in future release.

Migration:
    BEFORE: from real_executor import get_real_training_executor
    AFTER:  from training.services import get_training_process_manager

Phase 10D: Complete NEAT training implementation with full data, checkpoints & plots.

This module provides:
- RealTrainingExecutor: Manages real NEAT training jobs with checkpoint saving
- PlotlyReporter: NEAT reporter that captures equity curves and generates plots
"""

import asyncio
import json
import pickle
import traceback
import uuid
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import neat
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from stonks_trading.domains.strategies.neat_swing.config import create_default_config
from stonks_trading.domains.strategies.neat_swing.trading_env import TradingEnv
from stonks_trading.domains.strategies.neat_swing.trainer import NeatTrainer
from stonks_trading.domains.trading.entities import Genome
from stonks_trading.domains.trading.repositories import save_genome as save_genome_to_db
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.domains.training.services import TrainingDataProvider
from stonks_trading.shared.logger import logger
from stonks_trading.shared.redis_client import get_redis

warnings.warn(
    "real_executor is deprecated. Use training_manager with Worker delegation.",
    DeprecationWarning,
    stacklevel=2,
)


@dataclass
class CheckpointData:
    """Complete checkpoint with equity curves and trades."""

    generation: int
    genome: neat.DefaultGenome
    fitness: float
    roi_pct: float
    equity_curve: list[float] = field(default_factory=list)
    cash_curve: list[float] = field(default_factory=list)
    holdings_curve: list[float] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    plot_html: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


class PlotlyReporter(neat.reporting.BaseReporter):
    """NEAT reporter that captures equity curves and generates plots.

    Mirrors NEAT/main.py PeriodicReporter functionality.
    """

    def __init__(
        self,
        validation_data: pd.DataFrame,
        job_id: str,
        checkpoint_dir: Path,
        checkpoint_interval: int = 5,
    ):
        """Initialize reporter.

        Args:
            validation_data: DataFrame for validation
            job_id: Training job ID
            checkpoint_dir: Directory to save checkpoints
            checkpoint_interval: Save checkpoint every N generations
        """
        self.validation_data = validation_data
        self.job_id = job_id
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_interval = checkpoint_interval

        self.gen = 0
        self.best_all_time_roi = -float("inf")
        self.best_all_time_genome: neat.DefaultGenome | None = None
        self.checkpoints: list[CheckpointData] = []
        self._config = create_default_config()

    def start_generation(self, generation: int) -> None:
        """Called at start of each generation."""
        self.gen = generation

    def post_evaluate(
        self,
        config: neat.Config,
        population: neat.Population,
        species: Any,
        best_genome: neat.DefaultGenome,
    ) -> None:
        """Called after population evaluation.

        Evaluates best genome on validation data and saves checkpoint.
        """
        # Evaluate on full validation set
        net = neat.nn.RecurrentNetwork.create(best_genome, config)
        env = TradingEnv(self.validation_data)

        hist_eq = []
        hist_cash = []
        hist_holdings = []

        for i in range(len(self.validation_data)):
            inputs = env.get_state(i)
            action = net.activate(inputs)
            eq = env.step(i, action)
            hist_eq.append(eq)
            hist_cash.append(env.cash)
            hist_holdings.append(env.holdings * env.closes[i])

        roi = (hist_eq[-1] - env.initial_capital) / env.initial_capital * 100

        # Track all-time best (like NEAT/main.py lines 296-301)
        if roi > self.best_all_time_roi:
            self.best_all_time_roi = roi
            self.best_all_time_genome = best_genome
            logger.info(f"New all-time best! ROI: {roi:.2f}% at gen {self.gen}")

        # Save checkpoint every N generations and at the end
        if self.gen % self.checkpoint_interval == 0 or self.gen == self.checkpoint_interval:
            checkpoint = self._create_checkpoint(
                generation=self.gen,
                genome=best_genome,
                fitness=best_genome.fitness or 0.0,
                roi=roi,
                equity=hist_eq,
                cash=hist_cash,
                holdings=hist_holdings,
                trades=env.trades,
            )
            self.checkpoints.append(checkpoint)

            # Save to disk
            self._save_checkpoint_file(checkpoint)
            self._save_best_all_time()

            # Generate plot HTML
            plot_html = self._generate_plot_html(env=env, equity=hist_eq, trades=env.trades)
            checkpoint.plot_html = plot_html

    def _create_checkpoint(
        self,
        generation: int,
        genome: neat.DefaultGenome,
        fitness: float,
        roi: float,
        equity: list[float],
        cash: list[float],
        holdings: list[float],
        trades: list,
    ) -> CheckpointData:
        """Create checkpoint data object."""
        # Convert TradeRecord objects to dicts for serialization
        trades_dicts = [
            {
                "step": t.step,
                "type": t.trade_type,
                "price": t.price,
                "time": t.timestamp.isoformat() if t.timestamp else None,
            }
            for t in trades
        ]

        return CheckpointData(
            generation=generation,
            genome=genome,
            fitness=fitness,
            roi_pct=roi,
            equity_curve=equity,
            cash_curve=cash,
            holdings_curve=holdings,
            trades=trades_dicts,
        )

    def _save_checkpoint_file(self, checkpoint: CheckpointData) -> None:
        """Save checkpoint to disk."""
        filepath = self.checkpoint_dir / f"gen_{checkpoint.generation}.pkl"
        with open(filepath, "wb") as f:
            pickle.dump(checkpoint.genome, f)
        logger.info(f"Saved checkpoint: {filepath}")

    def _save_best_all_time(self) -> None:
        """Save all-time best genome to disk."""
        if self.best_all_time_genome is not None:
            filepath = self.checkpoint_dir / "best_all_time.pkl"
            with open(filepath, "wb") as f:
                pickle.dump(self.best_all_time_genome, f)

    def _generate_plot_html(
        self,
        env: Any,
        equity: list[float],
        trades: list,
    ) -> str:
        """Generate Plotly HTML like NEAT/main.py lines 311-335.

        Returns HTML string for dashboard display.
        """
        df = self.validation_data

        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=("Equity vs Buy&Hold", "Cash", "Holdings Value"),
        )

        # Buy & Hold line
        bh = (df["Close"] / df.iloc[0]["Close"]) * env.initial_capital
        fig.add_trace(
            go.Scatter(x=df.index, y=bh, name="Buy & Hold", line={"color": "gray", "dash": "dot"}),
            row=1,
            col=1,
        )

        # Strategy equity
        fig.add_trace(
            go.Scatter(x=df.index, y=equity, name="Strategy", line={"color": "purple"}),
            row=1,
            col=1,
        )

        # Trade markers
        buys = [t for t in trades if t.trade_type == "buy"]
        sells = [t for t in trades if t.trade_type == "sell"]

        if buys:
            fig.add_trace(
                go.Scatter(
                    x=[env.dates[t.step] for t in buys],
                    y=[equity[t.step] for t in buys],
                    mode="markers",
                    marker={"symbol": "triangle-up", "color": "lime", "size": 8},
                    name="Buy",
                ),
                row=1,
                col=1,
            )

        if sells:
            fig.add_trace(
                go.Scatter(
                    x=[env.dates[t.step] for t in sells],
                    y=[equity[t.step] for t in sells],
                    mode="markers",
                    marker={"symbol": "triangle-down", "color": "red", "size": 8},
                    name="Sell",
                ),
                row=1,
                col=1,
            )

        # Cash and Holdings - using passed equity data
        # Generate from equity - assume all cash when not invested
        hist_cash = []
        hist_holdings = []
        is_invested = False
        cash_val = env.initial_capital
        holdings_val = 0.0

        for i in range(len(df)):
            # Determine if invested at step i
            step_trades = [t for t in trades if t.step == i]
            for t in step_trades:
                if t.trade_type == "buy":
                    is_invested = True
                    holdings_val = equity[i]
                    cash_val = 0.0
                elif t.trade_type == "sell":
                    is_invested = False
                    cash_val = equity[i]
                    holdings_val = 0.0

            if is_invested:
                hist_cash.append(0.0)
                hist_holdings.append(holdings_val)
            else:
                hist_cash.append(cash_val if cash_val > 0 else equity[i])
                hist_holdings.append(0.0)

        fig.add_trace(
            go.Scatter(x=df.index, y=hist_cash, name="Cash", line={"color": "green"}),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=hist_holdings, name="Holdings", line={"color": "orange"}),
            row=3,
            col=1,
        )

        fig.update_layout(title=f"Generation {self.gen} Report", template="plotly_dark", height=800)

        return fig.to_html(full_html=False, include_plotlyjs="cdn")


class RealTrainingExecutor:
    """Real NEAT training executor with checkpoint saving.

    Replaces AsyncTrainingExecutor simulation.
    """

    def __init__(self) -> None:
        """Initialize executor."""
        self._running_jobs: dict[str, asyncio.Task] = {}
        self.data_provider = TrainingDataProvider()

    async def start_job(
        self,
        symbol: str,
        generations: int,
        population_size: int,
        training_capital: float,
        checkpoint_interval: int,
        strategy_type: str = "neat_swing",
    ) -> str:
        """Start a real NEAT training job.

        Args:
            symbol: Trading symbol
            generations: Number of generations
            population_size: NEAT population size
            training_capital: Initial capital
            checkpoint_interval: Save checkpoint every N generations
            strategy_type: Strategy type

        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())

        # Create job directory for checkpoints
        checkpoint_dir = Path(f"data/training/{job_id}")
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Initialize job state
        job_data = {
            "id": job_id,
            "symbol": symbol,
            "status": "queued",
            "generations_total": generations,
            "generations_completed": 0,
            "best_fitness": None,
            "best_roi": None,
            "genomes_evaluated": 0,
            "progress_pct": 0.0,
            "checkpoints": [],
            "checkpoint_dir": str(checkpoint_dir),
            "started_at": None,
            "updated_at": datetime.utcnow().isoformat(),
            "strategy_type": strategy_type,
            "population_size": population_size,
            "training_capital": training_capital,
            "checkpoint_interval": checkpoint_interval,
            "error": None,
        }

        await self._save_job_state(job_id, job_data)

        # Start actual training
        task = asyncio.create_task(
            self._run_training(
                job_id=job_id,
                symbol=symbol,
                generations=generations,
                population_size=population_size,
                training_capital=training_capital,
                checkpoint_interval=checkpoint_interval,
                checkpoint_dir=checkpoint_dir,
            )
        )
        self._running_jobs[job_id] = task

        logger.info(f"Started real training job {job_id} for {symbol}")
        return job_id

    async def _run_training(
        self,
        job_id: str,
        symbol: str,
        generations: int,
        population_size: int,
        training_capital: float,
        checkpoint_interval: int,
        checkpoint_dir: Path,
    ) -> None:
        """Run actual NEAT training."""
        try:
            # Update status to running
            job_data = await self._load_job_state(job_id)
            if not job_data:
                logger.error(f"Job {job_id} not found")
                return

            job_data["status"] = "running"
            job_data["started_at"] = datetime.utcnow().isoformat()
            await self._save_job_state(job_id, job_data)

            # Fetch ALL available data with 80/20 split
            train_df, test_df = await self.data_provider.fetch_all_available_data(symbol)

            logger.info(
                "Starting NEAT training",
                job_id=job_id,
                symbol=symbol,
                train_rows=len(train_df),
                test_rows=len(test_df),
                generations=generations,
            )

            # Create NEAT config with correct population size
            config = create_default_config()
            config.pop_size = population_size

            # Create reporter for checkpoints and plots
            reporter = PlotlyReporter(
                validation_data=test_df,
                job_id=job_id,
                checkpoint_dir=checkpoint_dir,
                checkpoint_interval=checkpoint_interval,
            )

            # Create trainer
            trainer = NeatTrainer(
                train_data=train_df,
                config=config,
                initial_capital=training_capital,
                episode_steps=20160,  # 14 days
            )

            # Run training with reporter
            winner = trainer.train(generations=generations, reporters=[reporter])

            # Save final winner
            final_checkpoint = CheckpointData(
                generation=generations,
                genome=winner,
                fitness=winner.fitness or 0.0,
                roi_pct=reporter.best_all_time_roi,
            )
            reporter._save_checkpoint_file(final_checkpoint)

            # Save winner to database - use reporter.gen for actual generation
            # NEAT uses 0-based indexing (gen 0, 1, ..., generations-1)
            # But checkpoint files use 1-based names (gen_1, gen_2, ..., gen_N)
            final_gen = reporter.gen if reporter.gen > 0 else generations
            if final_gen == generations - 1 and generations > 0:
                final_gen = generations  # Last checkpoint saved as gen_{generations}.pkl
            await self._save_winner_genome(
                job_id=job_id,
                genome=winner,
                symbol=symbol,
                roi=reporter.best_all_time_roi,
                fitness=winner.fitness or 0.0,
                generation=final_gen,
            )

            # Update job status
            job_data = await self._load_job_state(job_id)
            if job_data:
                job_data["status"] = "completed"
                job_data["progress_pct"] = 100.0
                job_data["best_fitness"] = winner.fitness
                job_data["best_roi"] = reporter.best_all_time_roi
                job_data["generations_completed"] = generations
                job_data["updated_at"] = datetime.utcnow().isoformat()

                # Update checkpoints with metadata
                job_data["checkpoints"] = [
                    {
                        "generation": cp.generation,
                        "fitness": cp.fitness,
                        "roi": cp.roi_pct,
                        "created_at": cp.timestamp.isoformat(),
                        "plot_html": getattr(cp, "plot_html", ""),
                    }
                    for cp in reporter.checkpoints
                ]

                await self._save_job_state(job_id, job_data)

            logger.info(f"Training job {job_id} completed successfully")

        except Exception as e:
            logger.error(f"Training job {job_id} failed: {e}")
            traceback.print_exc()
            job_data = await self._load_job_state(job_id)
            if job_data:
                job_data["status"] = "failed"
                job_data["error"] = str(e)
                await self._save_job_state(job_id, job_data)
        finally:
            if job_id in self._running_jobs:
                del self._running_jobs[job_id]

    async def _save_winner_genome(
        self,
        job_id: str,
        genome: neat.DefaultGenome,
        symbol: str,
        roi: float,
        fitness: float,
        generation: int,
    ) -> None:
        """Save winning genome to database.

        This makes the model appear in /api/v1/models/
        """
        # Serialize genome
        config = create_default_config()
        genome_bytes = pickle.dumps((genome, config))

        # Create Genome entity
        genome_entity = Genome(
            genome_data=genome_bytes,
            fitness=fitness,
            generation=generation,
            symbol=Symbol(value=symbol),
            roi_validation=roi,
            total_return=roi / 100,  # Convert % to decimal
            is_active=False,  # User must activate
            model_family="NEAT_RNN_V1",
            trained_at=datetime.utcnow(),
        )

        # Save to database
        saved = await save_genome_to_db(genome_entity)
        logger.info(f"Saved winner genome {saved.id} from job {job_id}")

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Get job status from Redis."""
        return await self._load_job_state(job_id)

    async def get_checkpoint_plot(self, job_id: str, generation: int) -> str | None:
        """Get plot HTML for a checkpoint."""
        checkpoint_dir = Path(f"data/training/{job_id}")
        plot_file = checkpoint_dir / f"gen_{generation}_plot.html"

        if plot_file.exists():
            return plot_file.read_text()

        return None

    async def get_checkpoint_data(self, job_id: str, generation: int) -> CheckpointData | None:
        """Get checkpoint data including genome."""
        checkpoint_dir = Path(f"data/training/{job_id}")
        checkpoint_file = checkpoint_dir / f"gen_{generation}.pkl"

        if not checkpoint_file.exists():
            return None

        with open(checkpoint_file, "rb") as f:
            genome = pickle.load(f)

        # Load job data for metadata
        job_data = await self._load_job_state(job_id)
        checkpoints = job_data.get("checkpoints", []) if job_data else []
        checkpoint_meta = next((c for c in checkpoints if c["generation"] == generation), None)

        return CheckpointData(
            generation=generation,
            genome=genome,
            fitness=genome.fitness or 0.0,
            roi_pct=checkpoint_meta.get("roi", 0) if checkpoint_meta else 0.0,
        )

    async def select_checkpoint(
        self,
        job_id: str,
        generation: int,
    ) -> dict[str, Any] | None:
        """Load a checkpoint genome from disk and return it."""
        checkpoint_dir = Path(f"data/training/{job_id}")
        checkpoint_file = checkpoint_dir / f"gen_{generation}.pkl"

        if not checkpoint_file.exists():
            return None

        with open(checkpoint_file, "rb") as f:
            genome = pickle.load(f)

        # Load job data
        job_data = await self._load_job_state(job_id)
        if not job_data:
            return None

        checkpoints = job_data.get("checkpoints", [])
        checkpoint_meta = next((c for c in checkpoints if c["generation"] == generation), None)

        return {
            "genome": genome,
            "generation": generation,
            "fitness": genome.fitness or 0.0,
            "roi": checkpoint_meta.get("roi", 0) if checkpoint_meta else 0.0,
            "symbol": job_data.get("symbol", "BTC_USD"),
            "checkpoint_dir": str(checkpoint_dir),
        }

    async def _save_job_state(self, job_id: str, job_data: dict[str, Any]) -> None:
        """Save job state to Redis."""
        redis = await get_redis()
        key = f"training:job:{job_id}"
        await redis.setex(
            key,
            86400 * 30,  # 30 days TTL
            json.dumps(job_data, default=str),
        )

    async def _load_job_state(self, job_id: str) -> dict[str, Any] | None:
        """Load job state from Redis."""
        redis = await get_redis()
        key = f"training:job:{job_id}"
        data = await redis.get(key)

        if not data:
            return None

        try:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return None


# Global executor instance
_real_executor: RealTrainingExecutor | None = None


def get_real_training_executor() -> RealTrainingExecutor:
    """Get or create the global real training executor."""
    global _real_executor
    if _real_executor is None:
        _real_executor = RealTrainingExecutor()
    return _real_executor
