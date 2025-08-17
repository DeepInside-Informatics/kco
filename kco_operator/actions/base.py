"""Base classes for action handlers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

from ..monitors.state import StateChange

logger = structlog.get_logger(__name__)


class ActionStatus(Enum):
    """Status of action execution."""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


@dataclass
class ActionResult:
    """Result of action execution."""

    status: ActionStatus
    message: str
    details: dict[str, Any]
    execution_time_seconds: float


@dataclass
class ActionContext:
    """Context passed to action handlers."""

    state_change: StateChange
    trigger_config: dict[str, Any]
    action_parameters: dict[str, Any]
    tapp_config: dict[str, Any]


class ActionHandler(ABC):
    """Base class for all action handlers."""

    def __init__(self, name: str, description: str) -> None:
        """Initialize action handler.

        Args:
            name: Unique name for this action type
            description: Human-readable description
        """
        self.name = name
        self.description = description

        logger.info("Registered action handler", action=name, description=description)

    @abstractmethod
    async def can_handle(self, context: ActionContext) -> bool:
        """Determine if this handler should process the action.

        Args:
            context: Action execution context

        Returns:
            True if this handler can process the action
        """
        pass

    @abstractmethod
    async def execute(self, context: ActionContext) -> ActionResult:
        """Execute the action.

        Args:
            context: Action execution context

        Returns:
            Result of action execution
        """
        pass

    def _evaluate_trigger_condition(
        self, state_change: StateChange, trigger_config: dict[str, Any]
    ) -> bool:
        """Evaluate if trigger condition is met.

        Args:
            state_change: The state change that occurred
            trigger_config: Trigger configuration from TargetApp spec

        Returns:
            True if trigger condition is satisfied
        """
        field = trigger_config.get("field")
        condition = trigger_config.get("condition")
        expected_value = trigger_config.get("value")

        if not all([field, condition]):
            logger.warning("Invalid trigger configuration", trigger=trigger_config)
            return False

        # For initial state changes, always evaluate condition
        # For subsequent changes, only evaluate if the monitored field actually changed
        if not state_change.is_initial and field not in state_change.changed_fields:
            # Field didn't change, so don't trigger action
            logger.debug(
                "Skipping trigger evaluation - field not changed",
                field=field,
                condition=condition,
                changed_fields=list(state_change.changed_fields),
            )
            return False

        # Get current value from state
        current_value = self._get_nested_value(
            state_change.new_snapshot.data, field or ""
        )

        # Evaluate condition
        if condition == "equals":
            result = bool(current_value == expected_value)
            logger.info(
                "Evaluating equals condition",
                field=field,
                current_value=current_value,
                expected_value=expected_value,
                result=result,
            )
            return result
        elif condition == "not_equals":
            return bool(current_value != expected_value)
        elif condition == "greater_than":
            try:
                return float(current_value or 0) > float(expected_value or 0)
            except (ValueError, TypeError):
                return False
        elif condition == "less_than":
            try:
                return float(current_value or 0) < float(expected_value or 0)
            except (ValueError, TypeError):
                return False
        elif condition == "contains":
            try:
                return str(expected_value) in str(current_value)
            except (ValueError, TypeError):
                return False
        elif condition == "exists":
            return current_value is not None
        elif condition == "not_exists":
            return current_value is None
        else:
            logger.warning(
                "Unknown trigger condition", condition=condition, field=field
            )
            return False

    def _get_nested_value(self, data: dict[str, Any], field_path: str) -> Any:
        """Get a nested value from data using dot notation.

        Args:
            data: Data dictionary
            field_path: Dot-separated path (e.g., "application.health")

        Returns:
            Value at the path or None if not found
        """
        try:
            value = data
            for part in field_path.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return None
            return value
        except Exception:
            return None
