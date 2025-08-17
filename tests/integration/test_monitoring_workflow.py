"""Integration tests for the complete monitoring workflow."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from operator.config import TAppConfig
from operator.monitors.controller import MonitoringController
from operator.utils.k8s import KubernetesClient


class MockGraphQLServer:
    """Mock GraphQL server for testing."""
    
    def __init__(self):
        self.responses = []
        self.call_count = 0
    
    def set_response(self, response):
        """Set the response to return."""
        self.responses.append(response)
    
    async def query(self, query_string, variables=None):
        """Mock query method."""
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
        else:
            response = self.responses[-1] if self.responses else {}
        
        self.call_count += 1
        return response
    
    async def health_check(self):
        """Mock health check."""
        return True
    
    async def close(self):
        """Mock close method."""
        pass


@pytest.fixture
async def mock_k8s_client():
    """Provide a mocked Kubernetes client."""
    client = MagicMock(spec=KubernetesClient)
    
    # Mock pod for discovery
    pod = MagicMock()
    pod.metadata.name = "test-pod"
    pod.metadata.namespace = "default"
    pod.status.pod_ip = "192.168.1.100"
    
    client.get_pods_by_selector = AsyncMock(return_value=[pod])
    client.create_event = AsyncMock()
    client.scale_deployment = AsyncMock()
    client.restart_pod = AsyncMock()
    client.close = AsyncMock()
    
    return client


@pytest.fixture
async def monitoring_controller(mock_k8s_client):
    """Provide a MonitoringController for testing."""
    controller = MonitoringController(mock_k8s_client, rate_limit_rpm=1000)  # High limit for testing
    yield controller
    await controller.shutdown()


@pytest.fixture
def sample_tapp_spec():
    """Provide sample TApp specification."""
    return {
        "selector": {
            "matchLabels": {
                "app": "test-app"
            }
        },
        "graphqlEndpoint": "/graphql",
        "pollingInterval": 1,  # Fast polling for tests
        "stateQuery": """
            query {
                application {
                    status
                    health
                }
            }
        """,
        "actions": [
            {
                "trigger": {
                    "field": "application.health",
                    "condition": "equals",
                    "value": "unhealthy"
                },
                "action": "restart_pod",
                "parameters": {
                    "gracePeriod": 30
                }
            }
        ],
        "timeout": 5,
        "maxRetries": 2
    }


class TestMonitoringWorkflow:
    """Test the complete monitoring workflow."""
    
    @pytest.mark.asyncio
    async def test_basic_monitoring_lifecycle(self, monitoring_controller, sample_tapp_spec):
        """Test basic monitoring start/stop lifecycle."""
        namespace = "default"
        name = "test-app"
        
        # Start monitoring
        await monitoring_controller.start_monitoring(namespace, name, sample_tapp_spec)
        
        # Verify monitor was created
        stats = monitoring_controller.get_stats()
        assert stats["active_monitors"] == 1
        assert f"{namespace}/{name}" in stats["monitored_tapps"]
        
        # Stop monitoring
        await monitoring_controller.stop_monitoring(namespace, name)
        
        # Verify monitor was removed
        stats = monitoring_controller.get_stats()
        assert stats["active_monitors"] == 0
        assert len(stats["monitored_tapps"]) == 0
    
    @pytest.mark.asyncio
    async def test_state_change_detection(self, monitoring_controller, sample_tapp_spec, mock_k8s_client):
        """Test state change detection and event generation."""
        namespace = "default"
        name = "test-app"
        
        # Mock GraphQL responses
        mock_server = MockGraphQLServer()
        
        # Initial response
        mock_server.set_response({
            "application": {
                "status": "running",
                "health": "healthy"
            }
        })
        
        # Changed response
        mock_server.set_response({
            "application": {
                "status": "running", 
                "health": "unhealthy"  # This should trigger an action
            }
        })
        
        with patch('operator.monitors.graphql.GraphQLMonitor') as MockGraphQLMonitor:
            MockGraphQLMonitor.return_value = mock_server
            
            # Start monitoring
            await monitoring_controller.start_monitoring(namespace, name, sample_tapp_spec)
            
            # Wait for a few polling cycles
            await asyncio.sleep(2.5)
            
            # Stop monitoring
            await monitoring_controller.stop_monitoring(namespace, name)
        
        # Verify events were created (mocked)
        assert mock_k8s_client.create_event.called
        
        # Verify action was triggered due to health change
        # (In a real test, we'd check that restart_pod was called)
    
    @pytest.mark.asyncio
    async def test_multiple_tapps(self, monitoring_controller, sample_tapp_spec):
        """Test monitoring multiple TApps simultaneously."""
        # Start monitoring multiple TApps
        await monitoring_controller.start_monitoring("ns1", "app1", sample_tapp_spec)
        await monitoring_controller.start_monitoring("ns2", "app2", sample_tapp_spec)
        await monitoring_controller.start_monitoring("ns1", "app3", sample_tapp_spec)
        
        # Verify all monitors are active
        stats = monitoring_controller.get_stats()
        assert stats["active_monitors"] == 3
        assert "ns1/app1" in stats["monitored_tapps"]
        assert "ns2/app2" in stats["monitored_tapps"]
        assert "ns1/app3" in stats["monitored_tapps"]
        
        # Stop one monitor
        await monitoring_controller.stop_monitoring("ns2", "app2")
        
        stats = monitoring_controller.get_stats()
        assert stats["active_monitors"] == 2
        assert "ns2/app2" not in stats["monitored_tapps"]
    
    @pytest.mark.asyncio
    async def test_configuration_update(self, monitoring_controller, sample_tapp_spec):
        """Test updating TApp configuration."""
        namespace = "default"
        name = "test-app"
        
        # Start monitoring with initial config
        await monitoring_controller.start_monitoring(namespace, name, sample_tapp_spec)
        
        # Update configuration
        updated_spec = sample_tapp_spec.copy()
        updated_spec["pollingInterval"] = 5  # Change polling interval
        
        await monitoring_controller.update_monitoring(namespace, name, updated_spec)
        
        # Verify monitor is still active
        stats = monitoring_controller.get_stats()
        assert stats["active_monitors"] == 1
        assert f"{namespace}/{name}" in stats["monitored_tapps"]
    
    @pytest.mark.asyncio
    async def test_rate_limiting(self, monitoring_controller, sample_tapp_spec):
        """Test that rate limiting is applied."""
        # Create controller with very low rate limit
        low_limit_controller = MonitoringController(
            monitoring_controller.k8s_client, 
            rate_limit_rpm=1  # Very low limit
        )
        
        try:
            namespace = "default"
            name = "test-app"
            
            # Use very fast polling to trigger rate limiting
            fast_spec = sample_tapp_spec.copy()
            fast_spec["pollingInterval"] = 0.1  # 100ms polling
            
            await low_limit_controller.start_monitoring(namespace, name, fast_spec)
            
            # Wait briefly to allow some polls
            await asyncio.sleep(1)
            
            # Rate limiter should have active buckets
            stats = low_limit_controller.get_stats()
            assert stats["rate_limiter_stats"]["active_buckets"] > 0
            
        finally:
            await low_limit_controller.shutdown()
    
    @pytest.mark.asyncio
    async def test_error_handling(self, monitoring_controller, sample_tapp_spec, mock_k8s_client):
        """Test error handling in monitoring."""
        namespace = "default"
        name = "test-app"
        
        # Mock pod discovery to return no pods
        mock_k8s_client.get_pods_by_selector.return_value = []
        
        # Start monitoring - should handle gracefully
        await monitoring_controller.start_monitoring(namespace, name, sample_tapp_spec)
        
        # Monitor should still be created even if no pods are found
        stats = monitoring_controller.get_stats()
        assert stats["active_monitors"] == 1


class TestTAppConfig:
    """Test TApp configuration parsing and validation."""
    
    def test_valid_config_parsing(self, sample_tapp_spec):
        """Test parsing valid TApp configuration."""
        config = TAppConfig.parse_obj(sample_tapp_spec)
        
        assert config.polling_interval == 1
        assert config.graphql_endpoint == "/graphql"
        assert config.timeout == 5
        assert config.max_retries == 2
        assert len(config.actions) == 1
        assert config.actions[0].action == "restart_pod"
    
    def test_config_defaults(self):
        """Test that default values are applied correctly."""
        minimal_spec = {
            "selector": {"matchLabels": {"app": "test"}},
            "stateQuery": "query { status }"
        }
        
        config = TAppConfig.parse_obj(minimal_spec)
        
        assert config.polling_interval == 30  # default
        assert config.graphql_endpoint == "/graphql"  # default
        assert config.timeout == 10  # default
        assert config.max_retries == 3  # default
        assert config.actions == []  # default
    
    def test_invalid_config_validation(self):
        """Test that invalid configurations are rejected."""
        with pytest.raises(Exception):  # Should raise validation error
            TAppConfig.parse_obj({
                "selector": {"matchLabels": {"app": "test"}},
                "stateQuery": "query { status }",
                "pollingInterval": 3601  # Too high
            })
        
        with pytest.raises(Exception):  # Should raise validation error
            TAppConfig.parse_obj({
                "selector": {"matchLabels": {"app": "test"}},
                "stateQuery": "query { status }",
                "timeout": 0  # Too low
            })