"""Mappers for converting between training domain entities and API DTOs.

Mappers are used ONLY by the API layer - not imported by the bot.
They handle conversion between internal domain representation
and external API format.
"""

from stonks_trading.domains.trading.entities import GenerationMetric, TrainingRun
from stonks_trading.domains.training.dtos import (
    GenerationMetricResponse,
    GenomeComparisonResponse,
    RetrainingJobResponse,
    TrainingProgressResponse,
    TrainingRunResponse,
)
from stonks_trading.domains.training.entities import (
    GenomeComparisonResult,
    RetrainingJob,
    TrainingSession,
)


class TrainingRunMapper:
    """Maps between TrainingRun entity and API DTOs."""

    @staticmethod
    def to_response(entity: TrainingRun) -> TrainingRunResponse:
        """Convert domain entity to API response DTO."""
        return TrainingRunResponse(
            id=entity.id or 0,
            symbol=entity.symbol.value if entity.symbol else None,
            status=entity.status,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
            best_fitness=entity.best_fitness,
            best_roi_validation=entity.best_roi_validation,
            generations=entity.generations,
            pop_size=entity.pop_size,
            git_sha=entity.trainer_git_sha,
        )

    @staticmethod
    def to_response_list(entities: list[TrainingRun]) -> list[TrainingRunResponse]:
        """Convert list of entities to response DTOs."""
        return [TrainingRunMapper.to_response(e) for e in entities]


class GenomeComparisonMapper:
    """Maps between GenomeComparisonResult entity and API DTOs."""

    @staticmethod
    def to_response(entity: GenomeComparisonResult) -> GenomeComparisonResponse:
        """Convert domain entity to API response DTO."""
        return GenomeComparisonResponse(
            improved=entity.improved,
            new_roi=entity.new_roi,
            prev_roi=entity.prev_roi,
            improvement_pct=entity.improvement_pct,
            new_genome_id=entity.new_genome_id,
            prev_genome_id=entity.prev_genome_id,
            symbol=entity.symbol,
            reason=entity.reason,
        )

    @staticmethod
    def to_response_list(entities: list[GenomeComparisonResult]) -> list[GenomeComparisonResponse]:
        """Convert list of entities to response DTOs."""
        return [GenomeComparisonMapper.to_response(e) for e in entities]


class RetrainingJobMapper:
    """Maps between RetrainingJob entity and API DTOs."""

    @staticmethod
    def to_response(entity: RetrainingJob) -> RetrainingJobResponse:
        """Convert domain entity to API response DTO."""
        result = None
        if entity.result:
            result = GenomeComparisonMapper.to_response(entity.result)

        return RetrainingJobResponse(
            symbol=entity.symbol,
            bot_type=entity.bot_context.bot_type,
            bot_instance_id=entity.bot_context.instance_id,
            status=entity.status,
            result=result,
            scheduled_at=entity.scheduled_at,
            started_at=entity.started_at,
            finished_at=entity.finished_at,
            error_message=entity.error_message,
        )

    @staticmethod
    def to_response_list(entities: list[RetrainingJob]) -> list[RetrainingJobResponse]:
        """Convert list of entities to response DTOs."""
        return [RetrainingJobMapper.to_response(e) for e in entities]


class TrainingProgressMapper:
    """Maps between TrainingSession entity and API DTOs."""

    @staticmethod
    def to_response(entity: TrainingSession) -> TrainingProgressResponse:
        """Convert domain entity to API response DTO."""
        return TrainingProgressResponse(
            run_id=entity.run_id,
            symbol=entity.symbol,
            status=entity.status,
            current_generation=entity.current_generation,
            best_fitness_so_far=entity.best_fitness_so_far,
            started_at=entity.started_at,
        )

    @staticmethod
    def to_response_list(entities: list[TrainingSession]) -> list[TrainingProgressResponse]:
        """Convert list of entities to response DTOs."""
        return [TrainingProgressMapper.to_response(e) for e in entities]


class GenerationMetricMapper:
    """Maps between GenerationMetric entity and API DTOs."""

    @staticmethod
    def to_response(entity: GenerationMetric) -> GenerationMetricResponse:
        """Convert domain entity to API response DTO."""
        return GenerationMetricResponse(
            run_id=entity.run_id,
            generation=entity.generation,
            best_fitness=entity.best_fitness,
            mean_fitness=entity.mean_fitness,
            worst_fitness=entity.worst_fitness,
            num_species=entity.num_species,
            num_genomes=entity.num_genomes,
            best_roi_validation=entity.best_roi_validation,
            stagnation_count=entity.stagnation_count,
            num_trades_best=entity.num_trades_best,
            max_drawdown_best=entity.max_drawdown_best,
        )

    @staticmethod
    def to_response_list(entities: list[GenerationMetric]) -> list[GenerationMetricResponse]:
        """Convert list of entities to response DTOs."""
        return [GenerationMetricMapper.to_response(e) for e in entities]
