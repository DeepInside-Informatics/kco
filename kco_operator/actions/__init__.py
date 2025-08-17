"""Action execution subsystem with plugin architecture."""

from .base import ActionHandler, ActionContext, ActionResult
from .registry import ActionRegistry, register_action

__all__ = ["ActionHandler", "ActionContext", "ActionResult", "ActionRegistry", "register_action"]