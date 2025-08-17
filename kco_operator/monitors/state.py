"""State management and change detection for Target Applications."""

import asyncio
import hashlib
import json
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog


logger = structlog.get_logger(__name__)


@dataclass
class StateSnapshot:
    """Represents a point-in-time snapshot of TApp state."""
    
    timestamp: datetime
    data: Dict[str, Any]
    checksum: str
    
    @classmethod
    def create(cls, data: Dict[str, Any]) -> "StateSnapshot":
        """Create a new state snapshot from data."""
        # Create deterministic checksum of the data
        json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        checksum = hashlib.sha256(json_str.encode()).hexdigest()
        
        return cls(
            timestamp=datetime.now(timezone.utc),
            data=data,
            checksum=checksum
        )


@dataclass
class StateChange:
    """Represents a detected change in TApp state."""
    
    tapp_name: str
    namespace: str
    old_snapshot: Optional[StateSnapshot]
    new_snapshot: StateSnapshot
    changed_fields: Set[str] = field(default_factory=set)
    
    @property
    def is_initial(self) -> bool:
        """Check if this is the initial state (no previous snapshot)."""
        return self.old_snapshot is None
    
    @property
    def has_changes(self) -> bool:
        """Check if there are actual changes between snapshots."""
        if self.is_initial:
            return True
        return len(self.changed_fields) > 0


class StateManager:
    """Manages state tracking and change detection for multiple TApps."""
    
    def __init__(self) -> None:
        """Initialize the state manager."""
        self._states: Dict[str, StateSnapshot] = {}
        self._lock = asyncio.Lock()
        
        logger.info("Initialized StateManager")
    
    def _get_state_key(self, namespace: str, name: str) -> str:
        """Generate a unique key for a TApp's state."""
        return f"{namespace}/{name}"
    
    def _find_changed_fields(
        self, 
        old_data: Dict[str, Any], 
        new_data: Dict[str, Any], 
        path: str = ""
    ) -> Set[str]:
        """Recursively find changed fields between two data structures."""
        changed_fields = set()
        
        # Check for removed keys
        for key in old_data:
            current_path = f"{path}.{key}" if path else key
            if key not in new_data:
                changed_fields.add(current_path)
        
        # Check for added or modified keys
        for key, new_value in new_data.items():
            current_path = f"{path}.{key}" if path else key
            
            if key not in old_data:
                # New field
                changed_fields.add(current_path)
            else:
                old_value = old_data[key]
                
                if isinstance(old_value, dict) and isinstance(new_value, dict):
                    # Recursively check nested objects
                    nested_changes = self._find_changed_fields(old_value, new_value, current_path)
                    changed_fields.update(nested_changes)
                elif old_value != new_value:
                    # Value changed
                    changed_fields.add(current_path)
        
        return changed_fields
    
    async def update_state(
        self, 
        namespace: str, 
        name: str, 
        new_data: Dict[str, Any]
    ) -> StateChange:
        """Update the state for a TApp and return detected changes.
        
        Args:
            namespace: Kubernetes namespace of the TApp
            name: Name of the TApp
            new_data: New state data from GraphQL query
            
        Returns:
            StateChange object describing the detected changes
        """
        async with self._lock:
            state_key = self._get_state_key(namespace, name)
            old_snapshot = self._states.get(state_key)
            new_snapshot = StateSnapshot.create(new_data)
            
            # Detect changes
            changed_fields = set()
            if old_snapshot is not None:
                if old_snapshot.checksum != new_snapshot.checksum:
                    changed_fields = self._find_changed_fields(
                        old_snapshot.data, 
                        new_snapshot.data
                    )
            
            # Update stored state
            self._states[state_key] = new_snapshot
            
            state_change = StateChange(
                tapp_name=name,
                namespace=namespace,
                old_snapshot=old_snapshot,
                new_snapshot=new_snapshot,
                changed_fields=changed_fields
            )
            
            if state_change.has_changes:
                logger.info(
                    "State change detected",
                    namespace=namespace,
                    tapp=name,
                    is_initial=state_change.is_initial,
                    changed_fields=list(changed_fields),
                    checksum=new_snapshot.checksum[:8]
                )
            else:
                logger.debug(
                    "No state changes detected",
                    namespace=namespace,
                    tapp=name,
                    checksum=new_snapshot.checksum[:8]
                )
            
            return state_change
    
    async def get_current_state(self, namespace: str, name: str) -> Optional[StateSnapshot]:
        """Get the current state snapshot for a TApp.
        
        Args:
            namespace: Kubernetes namespace of the TApp
            name: Name of the TApp
            
        Returns:
            Current state snapshot or None if not found
        """
        async with self._lock:
            state_key = self._get_state_key(namespace, name)
            return self._states.get(state_key)
    
    async def remove_state(self, namespace: str, name: str) -> bool:
        """Remove stored state for a TApp.
        
        Args:
            namespace: Kubernetes namespace of the TApp
            name: Name of the TApp
            
        Returns:
            True if state was removed, False if not found
        """
        async with self._lock:
            state_key = self._get_state_key(namespace, name)
            if state_key in self._states:
                del self._states[state_key]
                logger.info("Removed state", namespace=namespace, tapp=name)
                return True
            return False
    
    async def list_monitored_tapps(self) -> List[Dict[str, str]]:
        """List all currently monitored TApps.
        
        Returns:
            List of dicts with 'namespace' and 'name' keys
        """
        async with self._lock:
            tapps = []
            for state_key in self._states.keys():
                namespace, name = state_key.split("/", 1)
                tapps.append({"namespace": namespace, "name": name})
            return tapps
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the state manager.
        
        Returns:
            Dictionary with statistics
        """
        return {
            "monitored_tapps": len(self._states),
            "memory_usage_mb": sum(
                len(json.dumps(snapshot.data).encode()) 
                for snapshot in self._states.values()
            ) / (1024 * 1024)
        }