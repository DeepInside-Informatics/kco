"""Action execution subsystem with plugin architecture."""

from .base import ActionContext, ActionHandler, ActionResult
from .registry import ActionRegistry, register_action

__all__ = ["ActionHandler", "ActionContext", "ActionResult", "ActionRegistry", "register_action"]
