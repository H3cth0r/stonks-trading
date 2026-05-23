"""Base bot state for multi-bot architecture.

Abstract base class that all bot-specific states must implement.
Provides serialization contract for persistence.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class BaseBotState(ABC):
    """Abstract base class for bot state.

    Contract:
    1. Must be serializable to/from dict for persistence
    2. Tracks creation and update timestamps
    3. Subclasses add their own state fields

    Example:
        @dataclass
        class NeatSwingState(BaseBotState):
            positions: dict[Symbol, Position] = field(default_factory=dict)
            trades_today: int = 0

            def to_dict(self) -> dict[str, Any]:
                base = super().to_dict()
                base["positions"] = {...}
                return base
    """

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary for persistence.

        Returns:
            Dictionary containing all state fields.
        """
        ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseBotState":
        """Deserialize state from dictionary.

        Args:
            data: Dictionary from to_dict() or database.

        Returns:
            Reconstructed state instance.
        """
        ...
