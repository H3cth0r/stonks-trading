"""DTOs for strategy domain.

API layer Pydantic models for request/response serialization.
"""

from pydantic import BaseModel


class StrategyInfoResponse(BaseModel):
    """Response for strategy listing."""

    type: str
    name: str
    is_trainable: bool


class StrategyListResponse(BaseModel):
    """Response containing list of available strategies."""

    strategies: list[StrategyInfoResponse]


class ConfigFieldResponse(BaseModel):
    """Response for a single configuration field."""

    name: str
    type: str
    default: int | float | str | bool


class ConfigSchemaResponse(BaseModel):
    """Response for strategy configuration schema."""

    strategy_type: str
    config_fields: list[ConfigFieldResponse]
