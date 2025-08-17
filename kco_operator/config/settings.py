"""Configuration models using Pydantic."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ActionConfig(BaseModel):
    """Configuration for a single action."""
    
    trigger: Dict[str, Any] = Field(
        description="State condition that triggers this action"
    )
    action: str = Field(
        description="Name of the action to execute"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action-specific parameters"
    )


class TAppConfig(BaseModel):
    """Configuration for a Target Application."""
    
    selector: Dict[str, Any] = Field(
        description="Label selector for TApp pods"
    )
    graphql_endpoint: str = Field(
        default="/graphql",
        description="GraphQL endpoint path"
    )
    polling_interval: int = Field(
        default=30,
        ge=5,
        le=3600,
        description="Polling interval in seconds"
    )
    state_query: str = Field(
        description="GraphQL query to fetch application state"
    )
    actions: List[ActionConfig] = Field(
        default_factory=list,
        description="List of actions to execute on state changes"
    )
    timeout: int = Field(
        default=10,
        ge=1,
        le=60,
        description="GraphQL request timeout in seconds"
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retry attempts"
    )


class OperatorSettings(BaseSettings):
    """Global operator configuration settings."""
    
    # Logging configuration
    log_level: str = Field(
        default="INFO",
        description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_format: str = Field(
        default="json",
        description="Log format (json, plain)"
    )
    
    # GraphQL configuration
    graphql_timeout: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Default GraphQL request timeout in seconds"
    )
    graphql_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Default maximum number of GraphQL retry attempts"
    )
    
    # Polling configuration
    default_polling_interval: int = Field(
        default=30,
        ge=5,
        le=3600,
        description="Default polling interval in seconds"
    )
    
    # Action execution configuration
    action_execution_timeout: int = Field(
        default=300,
        ge=10,
        le=1800,
        description="Action execution timeout in seconds"
    )
    
    # Metrics configuration
    metrics_enabled: bool = Field(
        default=True,
        description="Enable Prometheus metrics"
    )
    metrics_port: int = Field(
        default=8080,
        ge=1024,
        le=65535,
        description="Port for Prometheus metrics server"
    )
    
    # Health check configuration
    health_port: int = Field(
        default=8081,
        ge=1024,
        le=65535,
        description="Port for health check endpoint"
    )
    
    # Kubernetes configuration
    namespace: Optional[str] = Field(
        default=None,
        description="Namespace to monitor (None for cluster-wide)"
    )
    
    # Rate limiting
    rate_limit_requests: int = Field(
        default=100,
        ge=1,
        description="Maximum requests per minute per TApp"
    )
    
    class Config:
        """Pydantic configuration."""
        env_prefix = "KCO_"
        case_sensitive = False
        validate_assignment = True