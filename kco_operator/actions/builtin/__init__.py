"""Built-in action handlers."""

# Import all built-in actions to register them
from . import restart_pod, scale_deployment, patch_resource, webhook, exec_command

__all__ = []