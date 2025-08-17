"""Pytest configuration and fixtures for KCO Operator tests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from kco_operator.config import OperatorSettings
from kco_operator.monitors.state import StateManager
from kco_operator.utils.k8s import KubernetesClient


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def operator_settings():
    """Provide test operator settings."""
    return OperatorSettings(
        log_level="DEBUG",
        graphql_timeout=5,
        graphql_max_retries=2,
        default_polling_interval=10,
        metrics_enabled=False,
        health_port=9999,
    )


@pytest.fixture
async def state_manager():
    """Provide a StateManager instance for testing."""
    manager = StateManager()
    yield manager


@pytest.fixture
def mock_k8s_client():
    """Provide a mocked Kubernetes client."""
    client = MagicMock(spec=KubernetesClient)

    # Mock async methods
    client.get_pods_by_selector = AsyncMock(return_value=[])
    client.create_event = AsyncMock()
    client.scale_deployment = AsyncMock()
    client.restart_pod = AsyncMock()
    client.close = AsyncMock()

    return client


@pytest.fixture
def sample_tapp_config():
    """Provide sample TApp configuration."""
    return {
        "selector": {"matchLabels": {"app": "test-app"}},
        "graphqlEndpoint": "/graphql",
        "pollingInterval": 30,
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
                    "value": "unhealthy",
                },
                "action": "restart_pod",
                "parameters": {"gracePeriod": 30},
            }
        ],
    }


@pytest.fixture
def sample_graphql_response():
    """Provide sample GraphQL response data."""
    return {
        "data": {
            "application": {
                "status": "running",
                "health": "healthy",
                "version": "1.0.0",
                "uptime": 3600,
            }
        }
    }


@pytest.fixture
def sample_pod():
    """Provide sample Kubernetes pod object."""
    from kubernetes_asyncio.client import V1ObjectMeta, V1Pod

    return V1Pod(
        metadata=V1ObjectMeta(
            name="test-pod", namespace="default", labels={"app": "test-app"}
        )
    )
