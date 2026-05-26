"""Mappers for bot control domain.

Converts between entities and DTOs.
Pure transformation - no business logic.
"""

from datetime import datetime

from stonks_trading.domains.botcontrol.dtos import (
    BotStatusResponse,
    RestartBotResponse,
    RunningBotsResponse,
    StartBotResponse,
    StopBotResponse,
)
from stonks_trading.domains.botcontrol.entities import BotProcess, BotStatus, ProcessStatus


class BotProcessMapper:
    """Map between BotProcess entity and response DTOs."""

    @staticmethod
    def to_start_response(entity: BotProcess) -> StartBotResponse:
        """Convert BotProcess to StartBotResponse."""
        return StartBotResponse(
            bot_type=entity.bot_type,
            bot_instance_id=entity.bot_instance_id,
            status=entity.status.value,
            pid=entity.pid,
            started_at=entity.started_at or datetime.utcnow(),
            message=f"Bot {entity.bot_type}/{entity.bot_instance_id} started",
        )

    @staticmethod
    def to_stop_response(entity: BotProcess, exit_code: int | None = None) -> StopBotResponse:
        """Convert BotProcess to StopBotResponse."""
        return StopBotResponse(
            bot_type=entity.bot_type,
            bot_instance_id=entity.bot_instance_id,
            status=entity.status.value,
            stopped_at=entity.stopped_at or datetime.utcnow(),
            uptime_seconds=entity.uptime_seconds,
            exit_code=exit_code or entity.exit_code,
            message=entity.error_message
            or f"Bot {entity.bot_type}/{entity.bot_instance_id} stopped",
        )

    @staticmethod
    def to_restart_response(entity: BotProcess) -> RestartBotResponse:
        """Convert BotProcess to RestartBotResponse."""
        return RestartBotResponse(
            bot_type=entity.bot_type,
            bot_instance_id=entity.bot_instance_id,
            status=entity.status.value,
            pid=entity.pid,
            started_at=entity.started_at or datetime.utcnow(),
            message=f"Bot {entity.bot_type}/{entity.bot_instance_id} restarted",
        )


class BotStatusMapper:
    """Map between BotStatus entity and response DTOs."""

    @staticmethod
    def to_response(entity: BotStatus) -> BotStatusResponse:
        """Convert BotStatus entity to response DTO."""
        return BotStatusResponse(
            bot_type=entity.bot_type,
            bot_instance_id=entity.bot_instance_id,
            status=entity.status.value,
            mode=entity.mode,
            uptime_seconds=entity.uptime_seconds,
            last_seen=entity.last_seen,
            current_equity=entity.current_equity,
            position_count=entity.position_count,
            pid=entity.pid,
            message=entity.message,
        )

    @staticmethod
    def to_list_response(entities: list[BotStatus]) -> RunningBotsResponse:
        """Convert list of BotStatus to RunningBotsResponse."""
        bots = [BotStatusMapper.to_response(e) for e in entities]
        return RunningBotsResponse(
            bots=bots,
            total=len(bots),
        )


class ProcessStatusMapper:
    """Map ProcessStatus enum values."""

    @staticmethod
    def to_string(status: ProcessStatus) -> str:
        """Convert ProcessStatus to string."""
        return status.value

    @staticmethod
    def from_string(value: str) -> ProcessStatus:
        """Convert string to ProcessStatus."""
        try:
            return ProcessStatus(value)
        except ValueError:
            return ProcessStatus.UNKNOWN
