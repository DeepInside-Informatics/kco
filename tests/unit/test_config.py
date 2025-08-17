"""Unit tests for configuration models."""

import pytest
from pydantic import ValidationError

from operator.config import OperatorSettings, TAppConfig, ActionConfig


class TestActionConfig:
    """Test ActionConfig model."""
    
    def test_valid_action_config(self):
        """Test creating valid action config."""
        config = ActionConfig(
            trigger={"field": "health", "condition": "equals", "value": "unhealthy"},
            action="restart_pod",
            parameters={"gracePeriod": 30}
        )
        
        assert config.trigger["field"] == "health"
        assert config.action == "restart_pod"
        assert config.parameters["gracePeriod"] == 30
    
    def test_action_config_defaults(self):
        """Test action config with default parameters."""
        config = ActionConfig(
            trigger={"field": "health", "condition": "equals", "value": "unhealthy"},
            action="restart_pod"
        )
        
        assert config.parameters == {}


class TestTAppConfig:
    """Test TAppConfig model."""
    
    def test_valid_tapp_config(self):
        """Test creating valid TApp config."""
        config = TAppConfig(
            selector={"matchLabels": {"app": "test"}},
            state_query="query { status }"
        )
        
        assert config.selector == {"matchLabels": {"app": "test"}}
        assert config.graphql_endpoint == "/graphql"  # default
        assert config.polling_interval == 30  # default
        assert config.timeout == 10  # default
        assert config.max_retries == 3  # default
    
    def test_tapp_config_with_custom_values(self):
        """Test TApp config with custom values."""
        config = TAppConfig(
            selector={"matchLabels": {"app": "test"}},
            graphql_endpoint="/api/graphql",
            polling_interval=60,
            state_query="query { status }",
            timeout=20,
            max_retries=5
        )
        
        assert config.graphql_endpoint == "/api/graphql"
        assert config.polling_interval == 60
        assert config.timeout == 20
        assert config.max_retries == 5
    
    def test_polling_interval_validation(self):
        """Test polling interval validation."""
        # Valid range
        config = TAppConfig(
            selector={"matchLabels": {"app": "test"}},
            state_query="query { status }",
            polling_interval=30
        )
        assert config.polling_interval == 30
        
        # Too low
        with pytest.raises(ValidationError):
            TAppConfig(
                selector={"matchLabels": {"app": "test"}},
                state_query="query { status }",
                polling_interval=1
            )
        
        # Too high
        with pytest.raises(ValidationError):
            TAppConfig(
                selector={"matchLabels": {"app": "test"}},
                state_query="query { status }",
                polling_interval=5000
            )
    
    def test_timeout_validation(self):
        """Test timeout validation."""
        # Valid range
        config = TAppConfig(
            selector={"matchLabels": {"app": "test"}},
            state_query="query { status }",
            timeout=30
        )
        assert config.timeout == 30
        
        # Too low
        with pytest.raises(ValidationError):
            TAppConfig(
                selector={"matchLabels": {"app": "test"}},
                state_query="query { status }",
                timeout=0
            )
        
        # Too high
        with pytest.raises(ValidationError):
            TAppConfig(
                selector={"matchLabels": {"app": "test"}},
                state_query="query { status }",
                timeout=100
            )


class TestOperatorSettings:
    """Test OperatorSettings model."""
    
    def test_default_settings(self):
        """Test default operator settings."""
        settings = OperatorSettings()
        
        assert settings.log_level == "INFO"
        assert settings.log_format == "json"
        assert settings.graphql_timeout == 10
        assert settings.graphql_max_retries == 3
        assert settings.default_polling_interval == 30
        assert settings.action_execution_timeout == 300
        assert settings.metrics_enabled is True
        assert settings.metrics_port == 8080
        assert settings.health_port == 8081
        assert settings.namespace is None
        assert settings.rate_limit_requests == 100
    
    def test_custom_settings(self):
        """Test custom operator settings."""
        settings = OperatorSettings(
            log_level="DEBUG",
            log_format="plain",
            graphql_timeout=5,
            metrics_port=9090,
            namespace="kco-system"
        )
        
        assert settings.log_level == "DEBUG"
        assert settings.log_format == "plain"
        assert settings.graphql_timeout == 5
        assert settings.metrics_port == 9090
        assert settings.namespace == "kco-system"
    
    def test_port_validation(self):
        """Test port number validation."""
        # Valid ports
        settings = OperatorSettings(metrics_port=8080, health_port=8081)
        assert settings.metrics_port == 8080
        assert settings.health_port == 8081
        
        # Invalid ports (too low)
        with pytest.raises(ValidationError):
            OperatorSettings(metrics_port=1023)
        
        with pytest.raises(ValidationError):
            OperatorSettings(health_port=500)
        
        # Invalid ports (too high)
        with pytest.raises(ValidationError):
            OperatorSettings(metrics_port=70000)
    
    def test_timeout_validation(self):
        """Test timeout validation."""
        # Valid timeouts
        settings = OperatorSettings(
            graphql_timeout=30,
            action_execution_timeout=600
        )
        assert settings.graphql_timeout == 30
        assert settings.action_execution_timeout == 600
        
        # Invalid timeout (too low)
        with pytest.raises(ValidationError):
            OperatorSettings(graphql_timeout=0)
        
        # Invalid timeout (too high)
        with pytest.raises(ValidationError):
            OperatorSettings(action_execution_timeout=2000)
    
    def test_retry_validation(self):
        """Test retry count validation."""
        # Valid retry counts
        settings = OperatorSettings(graphql_max_retries=5)
        assert settings.graphql_max_retries == 5
        
        # Invalid retry count (negative)
        with pytest.raises(ValidationError):
            OperatorSettings(graphql_max_retries=-1)
        
        # Invalid retry count (too high)
        with pytest.raises(ValidationError):
            OperatorSettings(graphql_max_retries=20)