"""Action handler registry and decorator."""

import asyncio
import time
from typing import Any, Dict, List, Optional, Type
from functools import wraps

import structlog

from .base import ActionHandler, ActionContext, ActionResult, ActionStatus


logger = structlog.get_logger(__name__)


class ActionRegistry:
    """Registry for action handlers with plugin architecture."""
    
    def __init__(self) -> None:
        """Initialize the action registry."""
        self._handlers: Dict[str, ActionHandler] = {}
        self._lock = asyncio.Lock()
        
        logger.info("Initialized ActionRegistry")
    
    async def register(self, handler: ActionHandler) -> None:
        """Register an action handler.
        
        Args:
            handler: Action handler instance to register
        """
        async with self._lock:
            if handler.name in self._handlers:
                logger.warning(
                    "Overriding existing action handler",
                    action=handler.name
                )
            
            self._handlers[handler.name] = handler
            
            logger.info(
                "Registered action handler",
                action=handler.name,
                description=handler.description
            )
    
    async def execute_action(
        self,
        action_name: str,
        context: ActionContext,
        timeout_seconds: int = 300
    ) -> ActionResult:
        """Execute an action with the specified context.
        
        Args:
            action_name: Name of the action to execute
            context: Action execution context
            timeout_seconds: Maximum execution time
            
        Returns:
            Result of action execution
        """
        start_time = time.time()
        
        async with self._lock:
            handler = self._handlers.get(action_name)
        
        if handler is None:
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Action handler '{action_name}' not found",
                details={"available_actions": list(self._handlers.keys())},
                execution_time_seconds=time.time() - start_time
            )
        
        try:
            # Check if handler can process this action
            if not await handler.can_handle(context):
                return ActionResult(
                    status=ActionStatus.SKIPPED,
                    message=f"Action handler '{action_name}' cannot handle this context",
                    details={},
                    execution_time_seconds=time.time() - start_time
                )
            
            logger.info(
                "Executing action",
                action=action_name,
                tapp=context.state_change.tapp_name,
                namespace=context.state_change.namespace
            )
            
            # Execute with timeout
            result = await asyncio.wait_for(
                handler.execute(context),
                timeout=timeout_seconds
            )
            
            result.execution_time_seconds = time.time() - start_time
            
            logger.info(
                "Action execution completed",
                action=action_name,
                status=result.status.value,
                execution_time=result.execution_time_seconds,
                tapp=context.state_change.tapp_name
            )
            
            return result
            
        except asyncio.TimeoutError:
            execution_time = time.time() - start_time
            logger.error(
                "Action execution timed out",
                action=action_name,
                timeout=timeout_seconds,
                execution_time=execution_time,
                tapp=context.state_change.tapp_name
            )
            
            return ActionResult(
                status=ActionStatus.TIMEOUT,
                message=f"Action '{action_name}' timed out after {timeout_seconds}s",
                details={"timeout_seconds": timeout_seconds},
                execution_time_seconds=execution_time
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                "Action execution failed",
                action=action_name,
                error=str(e),
                execution_time=execution_time,
                tapp=context.state_change.tapp_name
            )
            
            return ActionResult(
                status=ActionStatus.FAILED,
                message=f"Action '{action_name}' failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__},
                execution_time_seconds=execution_time
            )
    
    async def list_actions(self) -> List[Dict[str, str]]:
        """List all registered actions.
        
        Returns:
            List of action info dictionaries
        """
        async with self._lock:
            return [
                {
                    "name": name,
                    "description": handler.description
                }
                for name, handler in self._handlers.items()
            ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics.
        
        Returns:
            Dictionary with statistics
        """
        return {
            "registered_actions": len(self._handlers),
            "action_names": list(self._handlers.keys())
        }


# Global action registry instance
_action_registry = ActionRegistry()


def register_action(action_name: str, description: str = "") -> Any:
    """Decorator to register action handlers.
    
    Args:
        action_name: Name of the action
        description: Optional description
        
    Returns:
        Decorator function
    """
    def decorator(cls: Type[ActionHandler]) -> Type[ActionHandler]:
        @wraps(cls)
        async def wrapper(*args: Any, **kwargs: Any) -> ActionHandler:
            # Create instance of the handler
            instance = cls(action_name, description or f"Action handler for {action_name}")
            
            # Register it with the global registry
            await _action_registry.register(instance)
            
            return instance
        
        # Create and register the instance immediately
        async def _register() -> None:
            instance = cls(action_name, description or f"Action handler for {action_name}")
            await _action_registry.register(instance)
        
        # Schedule registration for next event loop iteration
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_register())
            else:
                loop.run_until_complete(_register())
        except RuntimeError:
            # No event loop running, will register later
            pass
        
        return cls
    
    return decorator


async def get_action_registry() -> ActionRegistry:
    """Get the global action registry instance.
    
    Returns:
        Global ActionRegistry instance
    """
    return _action_registry