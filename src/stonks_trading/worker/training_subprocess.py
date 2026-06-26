"""Training subprocess - runs actual NEAT training.

Called by Worker as subprocess via:
    python -m stonks_trading.worker.training_subprocess --job-id ...

Mirrors: bots/neat_swing/runner.py and NEAT/main.py

Responsibilities:
1. Parse CLI arguments (job config)
2. Load data via TrainingDataProvider (80/20 split from DuckDB) by default
3. Optionally load data from CSV to replicate NEAT/main.py exactly
4. Run NEAT training via NeatTrainer
5. Save checkpoints to disk (/app/data/training/{job_id}/)
6. Update Redis with progress (shared state)
7. Save final genomes to PostgreSQL via save_genome()
   - all-time-best genome (highest validation ROI)
   - last-generation winner (NEAT population.run() result)
8. Evaluate both winners on the test split and compare them

Required Environment:
- /app/data directory writable (shared volume)
- Redis accessible (shared state)
- PostgreSQL accessible (genome persistence)
- DuckDB at /app/data/neat.db (shared training data)
"""

import argparse
import asyncio
import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import neat
import pandas as pd
import plotly.graph_objects as go
import redis as redis_sync
from plotly.subplots import make_subplots

from stonks_trading.domains.strategies.neat_swing.config import create_default_config
from stonks_trading.domains.strategies.neat_swing.features import load_and_engineer
from stonks_trading.domains.strategies.neat_swing.trading_env import TradingEnv
from stonks_trading.domains.strategies.neat_swing.trainer import (
    NeatTrainer,
    evaluate_genome_on_data,
)
from stonks_trading.domains.trading.entities import Genome
from stonks_trading.domains.trading.value_objects import Symbol
from stonks_trading.domains.training.repositories import save_genome
from stonks_trading.domains.training.services import TrainingDataProvider
from stonks_trading.shared.config import settings
from stonks_trading.shared.database import init_db
from stonks_trading.shared.logger import logger

# Initialize Tortoise ORM at module load (before any DB calls)
_tortoise_initialized = False


async def _ensure_tortoise_initialized() -> None:
    """Initialize Tortoise ORM once for this subprocess."""
    global _tortoise_initialized
    if not _tortoise_initialized:
        await init_db()
        _tortoise_initialized = True


def _update_job_in_redis(
    job_id: str,
    generations: int | None,
    checkpoints: list[dict[str, Any]],
    best_fitness: float,
    best_roi: float,
    status: str,
    progress_pct: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write a consolidated job update to Redis synchronously.

    Called from the NEAT reporter's synchronous post_evaluate hook, so it
    must use the synchronous redis client. NEAT calls post_evaluate
    sequentially per generation, so there is no read-modify-write race.
    """
    redis = redis_sync.Redis.from_url(settings.redis_url)
    data = redis.get(f"training:job:{job_id}")
    if not data:
        logger.warning(f"Cannot update Redis: job {job_id} not found")
        return

    if isinstance(data, bytes):
        data = data.decode("utf-8")
    job_data = json.loads(data)

    last_gen = checkpoints[-1]["generation"] if checkpoints else 0
    job_data["generations_completed"] = last_gen
    job_data["best_fitness"] = best_fitness
    job_data["best_roi"] = best_roi
    job_data["status"] = status
    if status == "completed" and generations is not None:
        # Ensure the final response reflects the requested generation total,
        # not just the last checkpoint generation (e.g. interval 5 -> 25 of 30).
        job_data["generations_completed"] = generations
        job_data["progress_pct"] = 100.0
    elif progress_pct is not None:
        job_data["progress_pct"] = progress_pct
    elif generations is not None and generations > 0:
        job_data["progress_pct"] = (last_gen / generations) * 100
    # If generations is None, leave existing progress_pct unchanged.
    job_data["checkpoints"] = checkpoints

    if extra:
        job_data.update(extra)

    redis.setex(
        f"training:job:{job_id}",
        86400 * 30,
        json.dumps(job_data),
    )


class RedisReporter(neat.reporting.BaseReporter):
    """NEAT reporter that updates Redis with progress.

    This reporter is called by neat.Population.run() after each generation.
    It evaluates the best genome and saves checkpoints.
    """

    def __init__(
        self,
        job_id: str,
        checkpoint_dir: Path,
        validation_data: pd.DataFrame,
        generations_total: int,
        checkpoint_interval: int = 5,
    ):
        self.job_id = job_id
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.validation_data = validation_data
        self.generations_total = generations_total
        self.checkpoint_interval = checkpoint_interval
        self.gen = 0
        self.best_all_time_roi = -float("inf")
        self.best_all_time_genome: neat.DefaultGenome | None = None
        self.best_all_time_config: neat.Config | None = None
        self.checkpoints: list[dict[str, Any]] = []

    def start_generation(self, generation: int) -> None:
        self.gen = generation

    def post_evaluate(
        self,
        config: neat.Config,
        population: neat.Population,
        species: Any,
        best_genome: neat.DefaultGenome,
    ) -> None:
        """Evaluate and save checkpoint."""
        net = neat.nn.RecurrentNetwork.create(best_genome, config)
        env = TradingEnv(self.validation_data)

        hist_eq: list[float] = []
        hist_cash: list[float] = []
        hist_holdings: list[float] = []
        for i in range(len(self.validation_data)):
            inputs = env.get_state(i)
            action = net.activate(inputs)
            eq = env.step(i, action)
            hist_eq.append(eq)
            hist_cash.append(env.cash)
            hist_holdings.append(env.holdings * env.closes[i])

        roi = (hist_eq[-1] - env.initial_capital) / env.initial_capital * 100

        if roi > self.best_all_time_roi:
            self.best_all_time_roi = roi
            self.best_all_time_genome = best_genome
            self.best_all_time_config = config
            logger.info(f"New all-time best! ROI: {roi:.2f}% at gen {self.gen}")

        if self.gen % self.checkpoint_interval == 0:
            checkpoint = self._create_checkpoint(
                generation=self.gen,
                genome=best_genome,
                config=config,
                fitness=best_genome.fitness or 0.0,
                roi=roi,
                equity=hist_eq,
                cash=hist_cash,
                holdings=hist_holdings,
                env=env,
                trades=env.trades,
            )
            self._save_checkpoint_files(checkpoint, best_genome, config)
            # Accumulate checkpoint metadata and synchronously push live
            # progress to Redis so the dashboard sees generation advancement.
            # NEAT calls post_evaluate sequentially, so this write is race-free.
            self.checkpoints.append(
                {
                    "generation": checkpoint["generation"],
                    "fitness": checkpoint["fitness"],
                    "roi": checkpoint["roi"],
                    "created_at": checkpoint["created_at"],
                    "plot_html": checkpoint.get("plot_html", ""),
                }
            )
            _update_job_in_redis(
                job_id=self.job_id,
                generations=self.generations_total,
                checkpoints=self.checkpoints,
                best_fitness=best_genome.fitness or 0.0,
                best_roi=self.best_all_time_roi,
                status="running",
            )

    def _create_checkpoint(
        self,
        generation: int,
        genome: neat.DefaultGenome,
        config: neat.Config,
        fitness: float,
        roi: float,
        equity: list[float],
        cash: list[float],
        holdings: list[float],
        env: Any,
        trades: list,
    ) -> dict[str, Any]:
        """Create checkpoint data dict."""
        trades_dicts = [
            {
                "step": t.step,
                "type": t.trade_type,
                "price": t.price,
                "time": t.timestamp.isoformat() if t.timestamp else None,
            }
            for t in trades
        ]

        plot_html = self._generate_plot_html(env, equity, cash, holdings, trades)

        return {
            "generation": generation,
            "fitness": fitness,
            "roi": roi,
            "created_at": datetime.utcnow().isoformat(),
            "plot_html": plot_html,
            "trades": trades_dicts,
            "cash_curve": cash,
            "holdings_curve": holdings,
        }

    def _save_checkpoint_files(
        self,
        checkpoint: dict[str, Any],
        genome: neat.DefaultGenome,
        config: neat.Config,
    ) -> None:
        """Save checkpoint files to disk."""
        gen = checkpoint["generation"]

        genome_file = self.checkpoint_dir / f"gen_{gen}.pkl"
        with open(genome_file, "wb") as f:
            pickle.dump((genome, config), f)

        plot_file = self.checkpoint_dir / f"gen_{gen}_plot.html"
        plot_file.write_text(checkpoint["plot_html"])

        logger.info(f"Saved checkpoint generation {gen}")

    def _generate_plot_html(
        self,
        env: Any,
        equity: list[float],
        cash: list[float],
        holdings: list[float],
        trades: list,
    ) -> str:
        """Generate Plotly HTML matching NEAT/main.py PeriodicReporter."""
        df = self.validation_data

        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=("Equity vs Buy&Hold", "Cash", "Holdings Value"),
        )

        bh = (df["Close"] / df.iloc[0]["Close"]) * env.initial_capital
        fig.add_trace(
            go.Scatter(x=df.index, y=bh, name="Buy & Hold", line={"color": "gray", "dash": "dot"}),
            row=1,
            col=1,
        )

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
                    x=[t.timestamp for t in buys],
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
                    x=[t.timestamp for t in sells],
                    y=[equity[t.step] for t in sells],
                    mode="markers",
                    marker={"symbol": "triangle-down", "color": "red", "size": 8},
                    name="Sell",
                ),
                row=1,
                col=1,
            )

        fig.add_trace(
            go.Scatter(x=df.index, y=cash, name="Cash", line={"color": "green"}, fill="tozeroy"),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=df.index, y=holdings, name="Holdings", line={"color": "orange"}, fill="tozeroy"
            ),
            row=3,
            col=1,
        )

        fig.update_layout(
            title=f"Generation {self.gen} Report",
            template="plotly_dark",
            height=1000,
        )

        return fig.to_html(full_html=False, include_plotlyjs="cdn")


def _evaluate_genome_on_test_data(
    genome: neat.DefaultGenome,
    config: neat.Config,
    test_data: pd.DataFrame,
    initial_capital: float,
    label: str,
    checkpoint_dir: Path,
) -> tuple[float, float, int, float]:
    """Evaluate a genome on the test split and save a plot.

    Returns:
        Tuple of (test_roi_pct, final_equity, total_trades, max_drawdown)
    """
    results = evaluate_genome_on_data(
        genome,
        config,
        test_data,
        initial_capital=initial_capital,
        fee_rate=0.001,
        decision_threshold=0.6,
        min_trade_interval=15,
        verbose=False,
    )

    test_roi = results["final_roi_pct"]
    final_equity = results["final_equity"]
    total_trades = results["total_trades"]
    max_drawdown = results["max_drawdown"]

    # Generate plot for this genome on test data
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=("Equity vs Buy&Hold", "Cash", "Holdings Value"),
    )

    bh = (test_data["Close"] / test_data.iloc[0]["Close"]) * initial_capital
    fig.add_trace(
        go.Scatter(
            x=test_data.index, y=bh, name="Buy & Hold", line={"color": "gray", "dash": "dot"}
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=test_data.index,
            y=results["equity_curve"],
            name=f"Strategy ({label})",
            line={"color": "purple"},
        ),
        row=1,
        col=1,
    )

    buys = [t for t in results["trades"] if t.trade_type == "buy"]
    sells = [t for t in results["trades"] if t.trade_type == "sell"]
    if buys:
        fig.add_trace(
            go.Scatter(
                x=[t.timestamp for t in buys],
                y=[results["equity_curve"][t.step] for t in buys],
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
                x=[t.timestamp for t in sells],
                y=[results["equity_curve"][t.step] for t in sells],
                mode="markers",
                marker={"symbol": "triangle-down", "color": "red", "size": 8},
                name="Sell",
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Scatter(
            x=test_data.index,
            y=results["cash_curve"],
            name="Cash",
            line={"color": "green"},
            fill="tozeroy",
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=test_data.index,
            y=results["holdings_curve"],
            name="Holdings",
            line={"color": "orange"},
            fill="tozeroy",
        ),
        row=3,
        col=1,
    )

    fig.update_layout(
        title=f"Final Test Report - {label}",
        template="plotly_dark",
        height=1000,
    )

    plot_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
    plot_file = checkpoint_dir / f"test_{label.lower().replace(' ', '_')}_plot.html"
    plot_file.write_text(plot_html)

    logger.info(
        f"Test evaluation for {label}: ROI={test_roi:.2f}%, trades={total_trades}, "
        f"max_dd={max_drawdown*100:.2f}%"
    )
    return test_roi, final_equity, total_trades, max_drawdown


async def _persist_genome(
    genome: neat.DefaultGenome,
    config: neat.Config,
    symbol: str,
    generation: int,
    roi_validation: float,
    roi_test: float | None,
    total_return: float,
    model_family: str,
    trained_at: datetime,
    num_trades: int = 0,
    max_drawdown: float = 0.0,
) -> Genome:
    """Persist a genome to PostgreSQL and return the saved entity."""
    genome_bytes = pickle.dumps((genome, config))
    entity = Genome(
        genome_data=genome_bytes,
        fitness=genome.fitness or 0.0,
        generation=generation,
        symbol=Symbol(value=symbol),
        roi_validation=roi_validation,
        roi_test=roi_test,
        total_return=total_return,
        trades_count=num_trades,
        max_drawdown=max_drawdown,
        is_active=False,
        model_family=model_family,
        trained_at=trained_at,
    )
    return await save_genome(entity)


async def run_training(
    job_id: str,
    symbol: str,
    generations: int,
    population_size: int,
    training_capital: float,
    checkpoint_interval: int,
    checkpoint_dir: str,
    strategy_type: str,
    csv_path: str | None = None,
) -> None:
    """Run NEAT training and save results.

    By default, loads data from DuckDB (the stored market data). If csv_path is
    provided, loads from CSV exactly like NEAT/main.py for parity runs.

    Persists both the all-time-best genome (highest validation ROI) and the
    last-generation winner (population.run() result) to PostgreSQL, evaluates
    both on the test split, and saves test plots.
    """
    try:
        # Initialize Tortoise ORM before any DB operations
        await _ensure_tortoise_initialized()

        logger.info(
            f"Starting training {job_id} for {symbol}",
            csv_path=csv_path,
            data_source="CSV" if csv_path else "DuckDB",
        )

        if csv_path:
            # Load data exactly like NEAT/main.py for parity runs.
            train_df, test_df = load_and_engineer(csv_path, train_split=0.8)
            logger.info(
                f"Loaded CSV data from {csv_path}: {len(train_df)} train rows, {len(test_df)} test rows"
            )
        else:
            # Default: use the DuckDB market data we are capturing.
            data_provider = TrainingDataProvider()
            train_df, test_df = await data_provider.fetch_all_available_data(symbol)
            logger.info(
                f"Loaded DuckDB data: {len(train_df)} train rows, {len(test_df)} test rows"
            )

        config = create_default_config()
        config.pop_size = population_size

        # Validation slice must match NEAT/main.py exactly:
        # val_slice = train.iloc[-EPISODE_STEPS:]
        episode_steps = 20160
        val_slice = train_df.iloc[-episode_steps:]

        checkpoint_path = Path(checkpoint_dir)
        checkpoint_path.mkdir(parents=True, exist_ok=True)

        reporter = RedisReporter(
            job_id=job_id,
            checkpoint_dir=checkpoint_path,
            validation_data=val_slice,
            generations_total=generations,
            checkpoint_interval=checkpoint_interval,
        )

        trainer = NeatTrainer(
            train_data=train_df,
            config=config,
            initial_capital=training_capital,
            episode_steps=episode_steps,
        )

        # NEAT main.py returns the last-generation winner.
        last_winner = trainer.train(generations=generations, reporters=[reporter])

        trained_at = datetime.utcnow()

        # ------------------------------------------------------------------
        # Persist the all-time-best genome (highest validation ROI), matching
        # NEAT/main.py which saves best_all_time.pkl separately from the last
        # generation winner.
        # ------------------------------------------------------------------
        all_time_best_id: int | None = None
        all_time_best_test_roi: float | None = None
        if reporter.best_all_time_genome is not None and reporter.best_all_time_config is not None:
            best_gen = reporter.best_all_time_genome
            best_config = reporter.best_all_time_config
            best_validation_roi = reporter.best_all_time_roi

            all_time_best_trades = 0
            all_time_best_drawdown = 0.0
            if test_df is not None and len(test_df) > 0:
                (
                    all_time_best_test_roi,
                    _,
                    all_time_best_trades,
                    all_time_best_drawdown,
                ) = _evaluate_genome_on_test_data(
                    genome=best_gen,
                    config=best_config,
                    test_data=test_df,
                    initial_capital=training_capital,
                    label="All_Time_Best",
                    checkpoint_dir=checkpoint_path,
                )

            saved_all_time_best = await _persist_genome(
                genome=best_gen,
                config=best_config,
                symbol=symbol,
                generation=generations,
                roi_validation=best_validation_roi,
                roi_test=all_time_best_test_roi,
                total_return=best_validation_roi / 100,
                model_family="NEAT_RNN_V1_ALL_TIME_BEST",
                trained_at=trained_at,
                num_trades=all_time_best_trades,
                max_drawdown=all_time_best_drawdown,
            )
            all_time_best_id = saved_all_time_best.id
            logger.info(
                f"Saved all-time-best genome {all_time_best_id} from job {job_id} "
                f"(fitness={saved_all_time_best.fitness:.2f}, "
                f"val_roi={best_validation_roi:.2f}%, "
                f"test_roi={all_time_best_test_roi or 0.0:.2f}%)"
            )

        # ------------------------------------------------------------------
        # Persist the last-generation winner, like NEAT/main.py last_winner.pkl.
        # ------------------------------------------------------------------
        last_winner_id: int | None = None
        last_winner_test_roi: float | None = None
        last_winner_validation_roi: float | None = None
        if last_winner is not None:
            # Evaluate last-generation winner on validation slice for comparison.
            last_val_results = evaluate_genome_on_data(
                last_winner,
                config,
                val_slice,
                initial_capital=training_capital,
                fee_rate=0.001,
                decision_threshold=0.6,
                min_trade_interval=15,
                verbose=False,
            )
            last_winner_validation_roi = last_val_results["final_roi_pct"]

            last_winner_trades = 0
            last_winner_drawdown = 0.0
            if test_df is not None and len(test_df) > 0:
                (
                    last_winner_test_roi,
                    _,
                    last_winner_trades,
                    last_winner_drawdown,
                ) = _evaluate_genome_on_test_data(
                    genome=last_winner,
                    config=config,
                    test_data=test_df,
                    initial_capital=training_capital,
                    label="Last_Winner",
                    checkpoint_dir=checkpoint_path,
                )

            saved_last_winner = await _persist_genome(
                genome=last_winner,
                config=config,
                symbol=symbol,
                generation=generations,
                roi_validation=last_winner_validation_roi,
                roi_test=last_winner_test_roi,
                total_return=last_winner_validation_roi / 100,
                model_family="NEAT_RNN_V1_LAST_WINNER",
                trained_at=trained_at,
                num_trades=last_winner_trades,
                max_drawdown=last_winner_drawdown,
            )
            last_winner_id = saved_last_winner.id
            logger.info(
                f"Saved last-generation winner genome {last_winner_id} from job {job_id} "
                f"(fitness={saved_last_winner.fitness:.2f}, "
                f"val_roi={last_winner_validation_roi:.2f}%, "
                f"test_roi={last_winner_test_roi or 0.0:.2f}%)"
            )

        # ------------------------------------------------------------------
        # Final comparison, mirroring NEAT/main.py:477-494.
        # ------------------------------------------------------------------
        selected_winner = None
        if (
            all_time_best_test_roi is not None
            and last_winner_test_roi is not None
            and last_winner_id is not None
            and all_time_best_id is not None
        ):
            if all_time_best_test_roi > last_winner_test_roi:
                selected_winner = "all_time_best"
                logger.info(
                    f"The All-Time Best genome performed better on test data: "
                    f"{all_time_best_test_roi:.2f}% vs {last_winner_test_roi:.2f}%"
                )
            else:
                selected_winner = "last_winner"
                logger.info(
                    f"The Last Generation winner performed better on test data: "
                    f"{last_winner_test_roi:.2f}% vs {all_time_best_test_roi:.2f}%"
                )
        elif all_time_best_id is not None:
            selected_winner = "all_time_best"
        elif last_winner_id is not None:
            selected_winner = "last_winner"

        # Final synchronous Redis update after training finishes.
        extra = {
            "all_time_best_model_id": all_time_best_id,
            "all_time_best_roi": reporter.best_all_time_roi,
            "all_time_best_test_roi": all_time_best_test_roi,
            "last_winner_model_id": last_winner_id,
            "last_winner_roi": last_winner_validation_roi,
            "last_winner_test_roi": last_winner_test_roi,
            "selected_winner": selected_winner,
        }
        _update_job_in_redis(
            job_id=job_id,
            generations=generations,
            checkpoints=reporter.checkpoints,
            best_fitness=reporter.best_all_time_genome.fitness
            if reporter.best_all_time_genome is not None
            else 0.0,
            best_roi=reporter.best_all_time_roi,
            status="completed",
            progress_pct=100.0,
            extra=extra,
        )

        logger.info(f"Training job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Training job {job_id} failed: {e}")
        redis = redis_sync.Redis.from_url(settings.redis_url)
        data = redis.get(f"training:job:{job_id}")
        if data:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            job_data = json.loads(data)
            job_data["status"] = "failed"
            job_data["error"] = str(e)
            redis.setex(
                f"training:job:{job_id}",
                86400 * 30,
                json.dumps(job_data),
            )
        raise


def main() -> None:
    """Entry point for subprocess."""
    parser = argparse.ArgumentParser(description="Run NEAT training")
    parser.add_argument("--job-id", required=True, help="Training job ID")
    parser.add_argument("--symbol", required=True, help="Trading symbol")
    parser.add_argument("--generations", type=int, required=True, help="Number of generations")
    parser.add_argument("--population-size", type=int, required=True, help="Population size")
    parser.add_argument("--training-capital", type=float, required=True, help="Initial capital")
    parser.add_argument(
        "--checkpoint-interval", type=int, required=True, help="Checkpoint interval"
    )
    parser.add_argument("--checkpoint-dir", required=True, help="Checkpoint directory")
    parser.add_argument("--strategy-type", default="neat_swing", help="Strategy type")
    parser.add_argument(
        "--csv-path",
        default=None,
        help="Optional CSV path to load data exactly like NEAT/main.py",
    )

    args = parser.parse_args()

    asyncio.run(
        run_training(
            job_id=args.job_id,
            symbol=args.symbol,
            generations=args.generations,
            population_size=args.population_size,
            training_capital=args.training_capital,
            checkpoint_interval=args.checkpoint_interval,
            checkpoint_dir=args.checkpoint_dir,
            strategy_type=args.strategy_type,
            csv_path=args.csv_path,
        )
    )


if __name__ == "__main__":
    main()
