"""Unit tests for StateManager."""

import pytest
from datetime import datetime, timezone

from operator.monitors.state import StateManager, StateSnapshot, StateChange


class TestStateSnapshot:
    """Test StateSnapshot class."""
    
    def test_create_snapshot(self):
        """Test creating a state snapshot."""
        data = {"status": "running", "health": "healthy"}
        snapshot = StateSnapshot.create(data)
        
        assert snapshot.data == data
        assert isinstance(snapshot.timestamp, datetime)
        assert isinstance(snapshot.checksum, str)
        assert len(snapshot.checksum) == 64  # SHA256 hex digest
    
    def test_identical_data_same_checksum(self):
        """Test that identical data produces the same checksum."""
        data = {"status": "running", "health": "healthy"}
        snapshot1 = StateSnapshot.create(data)
        snapshot2 = StateSnapshot.create(data)
        
        assert snapshot1.checksum == snapshot2.checksum
    
    def test_different_data_different_checksum(self):
        """Test that different data produces different checksums."""
        data1 = {"status": "running", "health": "healthy"}
        data2 = {"status": "stopped", "health": "unhealthy"}
        
        snapshot1 = StateSnapshot.create(data1)
        snapshot2 = StateSnapshot.create(data2)
        
        assert snapshot1.checksum != snapshot2.checksum


class TestStateChange:
    """Test StateChange class."""
    
    def test_initial_state_change(self):
        """Test initial state change detection."""
        new_snapshot = StateSnapshot.create({"status": "running"})
        change = StateChange(
            tapp_name="test-app",
            namespace="default",
            old_snapshot=None,
            new_snapshot=new_snapshot
        )
        
        assert change.is_initial
        assert change.has_changes
    
    def test_subsequent_state_change(self):
        """Test subsequent state change detection."""
        old_snapshot = StateSnapshot.create({"status": "running"})
        new_snapshot = StateSnapshot.create({"status": "stopped"})
        
        change = StateChange(
            tapp_name="test-app",
            namespace="default", 
            old_snapshot=old_snapshot,
            new_snapshot=new_snapshot,
            changed_fields={"status"}
        )
        
        assert not change.is_initial
        assert change.has_changes
    
    def test_no_changes(self):
        """Test when there are no changes."""
        old_snapshot = StateSnapshot.create({"status": "running"})
        new_snapshot = StateSnapshot.create({"status": "running"})
        
        change = StateChange(
            tapp_name="test-app",
            namespace="default",
            old_snapshot=old_snapshot,
            new_snapshot=new_snapshot,
            changed_fields=set()
        )
        
        assert not change.is_initial
        assert not change.has_changes


class TestStateManager:
    """Test StateManager class."""
    
    @pytest.mark.asyncio
    async def test_initial_state_update(self, state_manager):
        """Test updating state for the first time."""
        data = {"status": "running", "health": "healthy"}
        
        change = await state_manager.update_state("default", "test-app", data)
        
        assert change.is_initial
        assert change.has_changes
        assert change.tapp_name == "test-app"
        assert change.namespace == "default"
        assert change.new_snapshot.data == data
        assert change.old_snapshot is None
    
    @pytest.mark.asyncio
    async def test_subsequent_state_update_with_changes(self, state_manager):
        """Test updating state with actual changes."""
        # Initial state
        initial_data = {"status": "running", "health": "healthy"}
        await state_manager.update_state("default", "test-app", initial_data)
        
        # Updated state
        updated_data = {"status": "running", "health": "unhealthy"}
        change = await state_manager.update_state("default", "test-app", updated_data)
        
        assert not change.is_initial
        assert change.has_changes
        assert "health" in change.changed_fields
        assert len(change.changed_fields) == 1
    
    @pytest.mark.asyncio
    async def test_subsequent_state_update_no_changes(self, state_manager):
        """Test updating state with no actual changes."""
        # Initial state
        data = {"status": "running", "health": "healthy"}
        await state_manager.update_state("default", "test-app", data)
        
        # Same state again
        change = await state_manager.update_state("default", "test-app", data)
        
        assert not change.is_initial
        assert not change.has_changes
        assert len(change.changed_fields) == 0
    
    @pytest.mark.asyncio
    async def test_nested_field_changes(self, state_manager):
        """Test detection of nested field changes."""
        # Initial state with nested data
        initial_data = {
            "application": {
                "status": "running",
                "metrics": {
                    "cpu": 50,
                    "memory": 1024
                }
            }
        }
        await state_manager.update_state("default", "test-app", initial_data)
        
        # Update nested field
        updated_data = {
            "application": {
                "status": "running",
                "metrics": {
                    "cpu": 75,  # Changed
                    "memory": 1024
                }
            }
        }
        change = await state_manager.update_state("default", "test-app", updated_data)
        
        assert change.has_changes
        assert "application.metrics.cpu" in change.changed_fields
    
    @pytest.mark.asyncio
    async def test_get_current_state(self, state_manager):
        """Test getting current state."""
        data = {"status": "running", "health": "healthy"}
        await state_manager.update_state("default", "test-app", data)
        
        snapshot = await state_manager.get_current_state("default", "test-app")
        
        assert snapshot is not None
        assert snapshot.data == data
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_state(self, state_manager):
        """Test getting state for non-existent TApp."""
        snapshot = await state_manager.get_current_state("default", "nonexistent")
        assert snapshot is None
    
    @pytest.mark.asyncio
    async def test_remove_state(self, state_manager):
        """Test removing state."""
        data = {"status": "running"}
        await state_manager.update_state("default", "test-app", data)
        
        # Verify state exists
        snapshot = await state_manager.get_current_state("default", "test-app")
        assert snapshot is not None
        
        # Remove state
        removed = await state_manager.remove_state("default", "test-app")
        assert removed is True
        
        # Verify state is gone
        snapshot = await state_manager.get_current_state("default", "test-app")
        assert snapshot is None
    
    @pytest.mark.asyncio
    async def test_remove_nonexistent_state(self, state_manager):
        """Test removing non-existent state."""
        removed = await state_manager.remove_state("default", "nonexistent")
        assert removed is False
    
    @pytest.mark.asyncio
    async def test_list_monitored_tapps(self, state_manager):
        """Test listing monitored TApps."""
        # Add some TApps
        await state_manager.update_state("default", "app1", {"status": "running"})
        await state_manager.update_state("kube-system", "app2", {"status": "running"})
        
        tapps = await state_manager.list_monitored_tapps()
        
        assert len(tapps) == 2
        assert {"namespace": "default", "name": "app1"} in tapps
        assert {"namespace": "kube-system", "name": "app2"} in tapps
    
    def test_get_stats(self, state_manager):
        """Test getting statistics."""
        stats = state_manager.get_stats()
        
        assert "monitored_tapps" in stats
        assert "memory_usage_mb" in stats
        assert isinstance(stats["monitored_tapps"], int)
        assert isinstance(stats["memory_usage_mb"], float)