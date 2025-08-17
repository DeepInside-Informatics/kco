"""Kubernetes Event generation for state changes."""

import asyncio
from typing import Dict, Set
from datetime import datetime, timezone

import structlog

from ..monitors.state import StateChange
from ..utils.k8s import KubernetesClient


logger = structlog.get_logger(__name__)


class EventGenerator:
    """Generates Kubernetes Events for TApp state changes."""
    
    def __init__(self, k8s_client: KubernetesClient) -> None:
        """Initialize event generator.
        
        Args:
            k8s_client: Kubernetes client for creating events
        """
        self.k8s_client = k8s_client
        self._recent_events: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        self._deduplication_window_seconds = 300  # 5 minutes
        
        logger.info("Initialized EventGenerator")
    
    def _get_event_key(
        self, 
        namespace: str, 
        tapp_name: str, 
        reason: str, 
        message: str
    ) -> str:
        """Generate a unique key for event deduplication."""
        return f"{namespace}/{tapp_name}/{reason}/{hash(message)}"
    
    async def _should_create_event(self, event_key: str) -> bool:
        """Check if event should be created based on deduplication logic."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            
            # Clean up old events
            cutoff = now.timestamp() - self._deduplication_window_seconds
            keys_to_remove = [
                key for key, timestamp in self._recent_events.items()
                if timestamp.timestamp() < cutoff
            ]
            for key in keys_to_remove:
                del self._recent_events[key]
            
            # Check if we've seen this event recently
            if event_key in self._recent_events:
                logger.debug(
                    "Skipping duplicate event",
                    event_key=event_key,
                    last_seen=self._recent_events[event_key]
                )
                return False
            
            # Record this event
            self._recent_events[event_key] = now
            return True
    
    async def generate_state_change_event(self, state_change: StateChange) -> None:
        """Generate events for a state change.
        
        Args:
            state_change: The state change to generate events for
        """
        if state_change.is_initial:
            await self._generate_initial_state_event(state_change)
        elif state_change.has_changes:
            await self._generate_change_events(state_change)
    
    async def _generate_initial_state_event(self, state_change: StateChange) -> None:
        """Generate event for initial state detection."""
        reason = "InitialStateDetected"
        message = f"Initial state detected for TApp '{state_change.tapp_name}'"
        
        event_key = self._get_event_key(
            state_change.namespace,
            state_change.tapp_name,
            reason,
            message
        )
        
        if await self._should_create_event(event_key):
            try:
                await self.k8s_client.create_event(
                    namespace=state_change.namespace,
                    involved_object_name=state_change.tapp_name,
                    involved_object_kind="TargetApp",
                    reason=reason,
                    message=message,
                    event_type="Normal"
                )
                
                logger.info(
                    "Generated initial state event",
                    namespace=state_change.namespace,
                    tapp=state_change.tapp_name
                )
                
            except Exception as e:
                logger.error(
                    "Failed to create initial state event",
                    namespace=state_change.namespace,
                    tapp=state_change.tapp_name,
                    error=str(e)
                )
    
    async def _generate_change_events(self, state_change: StateChange) -> None:
        """Generate events for specific field changes."""
        # Generate a summary event for all changes
        changed_fields_list = list(state_change.changed_fields)
        
        if len(changed_fields_list) == 1:
            reason = "StateFieldChanged"
            message = f"Field '{changed_fields_list[0]}' changed in TApp '{state_change.tapp_name}'"
        else:
            reason = "StateChanged"
            message = f"Multiple fields changed in TApp '{state_change.tapp_name}': {', '.join(changed_fields_list[:5])}"
            if len(changed_fields_list) > 5:
                message += f" and {len(changed_fields_list) - 5} more"
        
        # Determine event type based on field names
        event_type = self._determine_event_type(changed_fields_list, state_change)
        
        event_key = self._get_event_key(
            state_change.namespace,
            state_change.tapp_name,
            reason,
            message
        )
        
        if await self._should_create_event(event_key):
            try:
                await self.k8s_client.create_event(
                    namespace=state_change.namespace,
                    involved_object_name=state_change.tapp_name,
                    involved_object_kind="TargetApp",
                    reason=reason,
                    message=message,
                    event_type=event_type
                )
                
                logger.info(
                    "Generated state change event",
                    namespace=state_change.namespace,
                    tapp=state_change.tapp_name,
                    changed_fields=changed_fields_list,
                    event_type=event_type
                )
                
            except Exception as e:
                logger.error(
                    "Failed to create state change event",
                    namespace=state_change.namespace,
                    tapp=state_change.tapp_name,
                    error=str(e)
                )
        
        # Generate specific events for critical field changes
        await self._generate_specific_field_events(state_change)
    
    def _determine_event_type(
        self, 
        changed_fields: list, 
        state_change: StateChange
    ) -> str:
        """Determine event type based on changed fields and values."""
        # Check for fields that typically indicate problems
        warning_fields = {
            "health", "status", "error", "errors", "failed", "failure"
        }
        
        for field in changed_fields:
            field_lower = field.lower()
            if any(warning in field_lower for warning in warning_fields):
                # Check the actual value to determine severity
                current_value = self._get_field_value(state_change.new_snapshot.data, field)
                if current_value and isinstance(current_value, str):
                    value_lower = current_value.lower()
                    if any(bad in value_lower for bad in ["error", "failed", "unhealthy", "down"]):
                        return "Warning"
        
        return "Normal"
    
    async def _generate_specific_field_events(self, state_change: StateChange) -> None:
        """Generate specific events for critical field changes."""
        critical_fields = {
            "health": "HealthStatusChanged",
            "status": "StatusChanged", 
            "error": "ErrorStateChanged",
            "errors": "ErrorsDetected"
        }
        
        for field in state_change.changed_fields:
            field_name = field.split(".")[-1].lower()  # Get the last part of nested field
            
            if field_name in critical_fields:
                reason = critical_fields[field_name]
                
                old_value = self._get_field_value(
                    state_change.old_snapshot.data if state_change.old_snapshot else {},
                    field
                )
                new_value = self._get_field_value(state_change.new_snapshot.data, field)
                
                message = f"Field '{field}' changed from '{old_value}' to '{new_value}' in TApp '{state_change.tapp_name}'"
                
                # Determine event type based on new value
                event_type = "Warning" if self._is_problematic_value(new_value) else "Normal"
                
                event_key = self._get_event_key(
                    state_change.namespace,
                    state_change.tapp_name,
                    reason,
                    message
                )
                
                if await self._should_create_event(event_key):
                    try:
                        await self.k8s_client.create_event(
                            namespace=state_change.namespace,
                            involved_object_name=state_change.tapp_name,
                            involved_object_kind="TargetApp",
                            reason=reason,
                            message=message,
                            event_type=event_type
                        )
                        
                        logger.info(
                            "Generated specific field event",
                            namespace=state_change.namespace,
                            tapp=state_change.tapp_name,
                            field=field,
                            reason=reason,
                            event_type=event_type
                        )
                        
                    except Exception as e:
                        logger.error(
                            "Failed to create specific field event",
                            namespace=state_change.namespace,
                            tapp=state_change.tapp_name,
                            field=field,
                            error=str(e)
                        )
    
    def _get_field_value(self, data: Dict, field_path: str) -> str:
        """Get field value as string for display."""
        try:
            value = data
            for part in field_path.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return "null"
            return str(value) if value is not None else "null"
        except Exception:
            return "null"
    
    def _is_problematic_value(self, value: str) -> bool:
        """Check if a value indicates a problem."""
        if not value:
            return False
        
        value_lower = str(value).lower()
        problematic_keywords = [
            "error", "failed", "failure", "unhealthy", "down", 
            "critical", "fatal", "exception", "timeout"
        ]
        
        return any(keyword in value_lower for keyword in problematic_keywords)
    
    def get_stats(self) -> Dict[str, int]:
        """Get event generator statistics."""
        return {
            "cached_events": len(self._recent_events),
            "deduplication_window_seconds": self._deduplication_window_seconds
        }