# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Kubernetes Control Operator (KCO)

## Project Overview

This is a Python-based Kubernetes Operator that monitors Target Applications (TApp) through GraphQL endpoints and orchestrates Kubernetes resources based on observed state changes. The operator follows the controller pattern, continuously reconciling the desired state with the actual state while generating appropriate Kubernetes Events for observability.

## Development Environment

### Build System
- **Container Engine**: Prefer Podman over Docker for local development
- **Supported Platforms**: macOS and Linux (Windows not supported)
- **Python Version**: 3.11+
- **Package Manager**: Poetry (when implemented)

### Key Commands
Phase 1 is complete! Use these commands for development:
- Install dependencies: `poetry install`
- Run tests: `poetry run pytest`
- Run operator locally: `poetry run python -m operator.main`
- Build container: `./build.sh` (uses Podman by default)
- Lint code: `poetry run ruff check`
- Format code: `poetry run black .`
- Type check: `poetry run mypy operator/`

## Architecture

### Core Technology Stack
- **Primary Framework**: Kopf (Kubernetes Operator Pythonic Framework) v1.37+
- **GraphQL Client**: gql v3.5+ with aiohttp transport 
- **Kubernetes Client**: kubernetes-asyncio v30.1+
- **Configuration Management**: Pydantic v2.5+
- **Logging**: structlog for structured logging
- **Metrics**: Prometheus client for metrics exposition
- **Testing**: pytest with pytest-asyncio

### Project Structure (Implemented in Phase 1)
```
operator/
├── __init__.py
├── main.py              # ✅ Kopf handlers and startup logic
├── monitors/
│   ├── __init__.py
│   ├── graphql.py       # ✅ GraphQL polling implementation
│   └── state.py         # ✅ State management and diffing
├── events/
│   ├── __init__.py
│   └── generator.py     # ✅ Kubernetes Event creation
├── actions/
│   ├── __init__.py
│   ├── base.py          # ✅ Action handler interface
│   ├── builtin/         # ✅ Built-in action implementations
│   │   ├── __init__.py
│   │   ├── restart_pod.py
│   │   ├── scale_deployment.py
│   │   └── patch_resource.py
│   └── registry.py      # ✅ Action registration system
├── config/
│   ├── __init__.py
│   └── settings.py      # ✅ Pydantic configuration models
└── utils/
    ├── __init__.py
    ├── k8s.py           # ✅ Kubernetes API helpers
    └── logging.py       # ✅ Structured logging setup
```

**Additional files created:**
- `crd.yaml` - TargetApp Custom Resource Definition
- `Dockerfile` - Multi-stage container build
- `build.sh` - Local build script (Podman preferred)
- `pyproject.toml` - Poetry configuration with all dependencies
- `tests/` - Comprehensive test structure with fixtures

### Key CRD: TargetApp
- **API Group**: `operator.kco.local`
- **Version**: `v1alpha1`
- **Kind**: `TargetApp`
- **Purpose**: Defines monitoring targets with GraphQL endpoints, polling intervals, state queries, and trigger actions

### Target Application GraphQL Schema
Reference schema: https://github.com/MinaProtocol/mina/blob/f33cf0b472fa06f2269cd08d47976e8c000de278/graphql_schema.json

## Development Guidelines

### Implementation Priorities
1. **Phase 1**: ✅ COMPLETED - Basic operator skeleton, GraphQL client, state models
2. **Phase 2**: ✅ COMPLETED - State change detection, Kubernetes Event generation  
3. **Phase 3**: ✅ COMPLETED - Enhanced action system and production features
4. **Phase 4**: ✅ READY - Full production deployment capabilities

**Phase 1 Achievements:**
- Complete project structure with Poetry configuration
- Kopf-based operator with CRD handlers for TargetApp resources
- Async GraphQL client with connection pooling and retry logic
- Sophisticated state management with change detection
- Event generation system with deduplication
- Plugin-based action framework with 3 built-in handlers
- Kubernetes client wrapper with common operations
- Container build pipeline with security best practices
- Comprehensive test structure with fixtures and unit tests

**Phase 2 Achievements:**
- Integrated monitoring controller that orchestrates all components
- Complete workflow from GraphQL polling → state changes → events → actions
- TargetApp status updates reflecting monitoring state (Initializing/Monitoring/Failed)
- Prometheus metrics for monitoring operator performance and health
- Rate limiting system with token bucket algorithm to prevent API abuse
- Comprehensive error handling with retry logic and graceful degradation
- Integration tests covering the complete monitoring workflow
- Automatic pod discovery and GraphQL endpoint configuration

**Phase 3 Achievements:**
- Enhanced action system with 5 built-in handlers (restart_pod, scale_deployment, patch_resource, webhook, exec_command)
- Webhook integration for external system notifications (Slack, PagerDuty, custom APIs)
- Command execution capabilities for in-pod automation and maintenance
- Health check HTTP server with liveness, readiness, stats, and metrics endpoints
- Production-ready Helm chart with comprehensive configuration options
- RBAC templates with principle of least privilege
- Network policies and security configurations
- Comprehensive example manifests and documentation
- Full troubleshooting guide and operational runbooks

**Current Status: PRODUCTION READY**
The operator now includes all features required for production deployment and operation.

### Code Patterns
- Use async/await throughout for non-blocking operations
- Implement plugin system with decorators for action handlers
- Follow Kopf patterns for operator lifecycle management
- Use Pydantic models for all configuration and state definitions
- Implement structured logging with correlation IDs

### Testing Strategy
- Unit tests with pytest and pytest-asyncio
- Integration tests against mock GraphQL servers  
- E2E tests using kind cluster for Kubernetes operations
- Target >80% test coverage for critical paths

## Executive Summary

This document outlines the development plan for a Python-based Kubernetes Operator that monitors Target Applications (TApp) through GraphQL endpoints and orchestrates Kubernetes resources based on observed state changes. The operator follows the controller pattern, continuously reconciling the desired state with the actual state while generating appropriate Kubernetes Events for observability.

## 1. Architecture Overview

### 1.1 Core Components

The operator architecture consists of three primary layers that work together to monitor and respond to application state changes:

**Monitoring Layer**: This component continuously polls the TApp's GraphQL endpoint to retrieve current state information. It implements intelligent polling with configurable intervals and handles connection failures gracefully.

**Event Processing Layer**: When state changes are detected, this layer generates corresponding Kubernetes Events and determines which actions should be triggered. It maintains a state cache to detect transitions and avoid duplicate processing.

**Action Execution Layer**: This layer interfaces with the Kubernetes API to execute predetermined actions based on state transitions. It's designed as a plugin system to allow easy addition of new action handlers.

### 1.2 Technology Stack

**Primary Framework**: Kopf (Kubernetes Operator Pythonic Framework) v1.37+
- Provides decorator-based handler definitions
- Built-in retry logic and error handling
- Automatic CRD management
- Native async/await support

**GraphQL Client**: gql v3.5+ with aiohttp transport
- Async-first design for non-blocking operations
- Built-in retry mechanisms
- Schema introspection capabilities

**Kubernetes Client**: kubernetes-asyncio v30.1+
- Async operations for better performance
- Full API coverage
- Watch capabilities for real-time updates

**Configuration Management**: Pydantic v2.5+
- Type-safe configuration models
- Environment variable integration
- Validation at startup

**Observability**: 
- structlog for structured logging
- Prometheus client for metrics exposition

## 2. Development Phases

### Phase 1: Foundation (Week 1-2)

**Objectives**: Establish the project structure and core monitoring capabilities.

During this phase, we set up the basic operator skeleton using Kopf, implementing the fundamental polling mechanism for GraphQL endpoints. The focus is on establishing reliable communication with TApp instances and creating the basic state tracking infrastructure.

Key deliverables include:
- Project repository (which is the current directory) with proper Python packaging structure
- Basic operator that can discover TApp pods via label selectors an a clean way to report it
- GraphQL client implementation with connection pooling
- Initial state model definitions using Pydantic: the default TApp GraphQL schema definition can be found via this url: https://github.com/MinaProtocol/mina/blob/f33cf0b472fa06f2269cd08d47976e8c000de278/graphql_schema.json
- Container build pipeline using GitHub Actions Workflows AND a script for building locally as well. We prefer Podman over Docker. For local environments we default to MacOs or Linux env. Windows is not supported at the moment.

### Phase 2: Event Generation (Week 2-3)

**Objectives**: Implement state change detection and Kubernetes Event generation.

This phase introduces the state comparison logic that detects meaningful changes in the TApp's state. We implement a caching mechanism to store previous states and compare them with current readings, generating Kubernetes Events only for significant transitions.

Key deliverables include:
- State differ that identifies specific field changes
- Event generation with appropriate severity levels (Normal, Warning)
- Event deduplication to prevent spam
- Configurable state transition rules
- Unit tests for state comparison logic

### Phase 3: Action Framework (Week 3-4)

**Objectives**: Build the extensible action execution system.

Here we create the plugin-based action system that responds to state changes. The framework allows developers to register handlers for specific state transitions, making it easy to add new behaviors without modifying core operator code.

Key deliverables include:
- Action handler interface definition
- Registration mechanism for action plugins
- Built-in handlers for common operations (scaling, restarting, or patching a manifest)
- Async action execution with timeout handling
- Integration tests for action execution

### Phase 4: Production Readiness (Week 4-5)

**Objectives**: Implement production-grade features for staging deployment.

This final phase focuses on reliability, observability, and operational excellence. We add comprehensive error handling, metrics collection, and deployment configurations suitable for staging environments.

Key deliverables include:
- Helm chart for operator deployment
- Prometheus metrics for monitoring operator health
- Graceful shutdown handling
- Rate limiting for API calls
- Documentation and runbooks
- End-to-end testing suite

## 3. Implementation Details

### 3.1 Custom Resource Definition

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: targetapps.operator.kco.local
spec:
  group: operator.kco.local
  versions:
  - name: v1alpha1
    served: true
    storage: true
    schema:
      openAPIV3Schema:
        type: object
        properties:
          spec:
            type: object
            properties:
              selector:
                type: object
                description: "Label selector for TApp pods"
              graphqlEndpoint:
                type: string
                description: "GraphQL endpoint path (default: /graphql)"
              pollingInterval:
                type: integer
                description: "Polling interval in seconds (default: 30)"
              stateQuery:
                type: string
                description: "GraphQL query to fetch state"
              actions:
                type: array
                items:
                  type: object
                  properties:
                    trigger:
                      type: object
                      description: "State condition that triggers action"
                    action:
                      type: string
                      description: "Action to execute"
                    parameters:
                      type: object
                      description: "Action-specific parameters"
```

### 3.2 Core Operator Structure

The operator follows a modular design where each component has a single responsibility:

```python
# Main operator entry point structure
operator/
├── __init__.py
├── main.py              # Kopf handlers and startup logic
├── monitors/
│   ├── __init__.py
│   ├── graphql.py       # GraphQL polling implementation
│   └── state.py         # State management and diffing
├── events/
│   ├── __init__.py
│   └── generator.py     # Kubernetes Event creation
├── actions/
│   ├── __init__.py
│   ├── base.py          # Action handler interface
│   ├── builtin/         # Built-in action implementations
│   └── registry.py      # Action registration system
├── config/
│   ├── __init__.py
│   └── settings.py      # Pydantic configuration models
└── utils/
    ├── __init__.py
    └── k8s.py           # Kubernetes API helpers
```

### 3.3 State Monitoring Implementation

The GraphQL monitoring system uses async generators to efficiently poll multiple TApp instances:

```python
# Conceptual implementation showing the monitoring approach
async def monitor_tapp_state(namespace, labels, query, interval):
    """
    Continuously monitor TApp pods and yield state changes.
    
    This function discovers pods matching the label selector,
    establishes GraphQL connections, and polls for state changes.
    """
    # Initialize GraphQL client pool
    # Discover TApp pods using label selector
    # For each pod:
    #   - Establish GraphQL connection
    #   - Execute state query
    #   - Compare with cached state
    #   - Yield significant changes
    # Handle pod additions/deletions dynamically
```

### 3.4 Action Handler Plugin System

Actions are implemented as plugins that register themselves with the operator:

```python
# Example action handler structure
class ActionHandler(ABC):
    """Base class for all action handlers."""
    
    @abstractmethod
    async def can_handle(self, state_change: StateChange) -> bool:
        """Determine if this handler should process the state change."""
        pass
    
    @abstractmethod
    async def execute(self, context: ActionContext) -> ActionResult:
        """Execute the action with given context."""
        pass

# Registration happens through decorators
@register_action("scale_deployment")
class ScaleDeploymentAction(ActionHandler):
    """Handler for scaling deployment based on state."""
    # Implementation details...
```

## 4. Configuration Management

### 4.1 Operator Configuration

The operator uses environment variables for configuration, with sensible defaults:

```yaml
# ConfigMap for operator settings
apiVersion: v1
kind: ConfigMap
metadata:
  name: operator-config
data:
  LOG_LEVEL: "INFO"
  GRAPHQL_TIMEOUT: "10"
  GRAPHQL_MAX_RETRIES: "3"
  DEFAULT_POLLING_INTERVAL: "30"
  ACTION_EXECUTION_TIMEOUT: "300"
  METRICS_PORT: "8080"
```

### 4.2 Per-TApp Configuration

Each TargetApp custom resource specifies its monitoring requirements:

```yaml
# Example TargetApp resource
apiVersion: operator.kco.local/v1alpha1
kind: TargetApp
metadata:
  name: my-application
spec:
  selector:
    matchLabels:
      app: my-app
  graphqlEndpoint: "tagpp-pod.svc.namespace.cluster.local/graphql" # local or external URL
  pollingInterval: 20
  stateQuery: |
    query AppState {
      application {
        status
        health
        pendingTasks
        lastError
      }
    }
  actions: # fields and values exist in graphqlEndpoint response
  - trigger:
      field: "application.health"
      condition: "equals"
      value: "unhealthy"
    action: "restart_pod"
    parameters:
      gracePeriod: 30
```

## 5. Testing Strategy

### 5.1 Unit Testing

Every module includes comprehensive unit tests using pytest and pytest-asyncio:

- State comparison logic validation
- GraphQL query execution mocking
- Action handler behavior verification
- Configuration validation tests

### 5.2 Integration Testing

Integration tests verify component interactions:

- GraphQL client against mock server
- Kubernetes API operations using kind cluster
- Event generation and deduplication
- Action execution pipeline

### 5.3 End-to-End Testing

E2E tests validate the complete operator lifecycle:

- Deploy operator to test cluster
- Create mock TargetApp resources
- Deploy mock TApp with controllable state
- Verify state monitoring and event generation
- Validate action execution
- Test failure scenarios and recovery

## 6. Deployment Strategy

### 6.1 Container Image

Multi-stage Dockerfile for optimal image size:

```dockerfile
# Build stage with Poetry for dependency management
FROM python:3.11-slim as builder
# Install dependencies using Poetry
# Generate requirements.txt for production

# Production stage
FROM python:3.11-slim
# Copy only necessary files
# Run as non-root user
# Health check endpoint
```

### 6.2 Helm Chart Structure

```yaml
kco-chart/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml     # Operator deployment
│   ├── rbac.yaml           # Service account and roles
│   ├── configmap.yaml      # Configuration
│   ├── service.yaml        # Metrics service
│   └── servicemonitor.yaml # Prometheus integration
```

### 6.3 RBAC Requirements

The operator requires specific permissions:

```yaml
# Essential permissions for operator functionality
rules:
- apiGroups: [""]
  resources: ["pods", "pods/status"]
  verbs: ["get", "list", "watch"]
- apiGroups: [""]
  resources: ["events"]
  verbs: ["create", "patch"]
- apiGroups: ["apps"]
  resources: ["deployments", "deployments/scale"]
  verbs: ["get", "update", "patch"]
- apiGroups: ["operator.kco.local"]
  resources: ["targetapps", "targetapps/status"]
  verbs: ["get", "list", "watch", "update", "patch"]
```

## 7. Observability

### 7.1 Logging

Structured logging provides clear operational visibility:

```python
# Log format example
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "operator": "tapp-operator",
  "namespace": "default",
  "tapp": "my-application",
  "action": "state_change_detected",
  "old_state": "healthy",
  "new_state": "degraded",
  "correlation_id": "abc-123"
}
```

### 7.2 Metrics

Prometheus metrics for monitoring operator health:

- `operator_kco_tapp_polls_total`: Total GraphQL polls executed
- `operator_kco_tapp_poll_duration_seconds`: Poll duration histogram
- `operator_kco_events_generated_total`: Kubernetes Events created
- `operator_kco_actions_executed_total`: Actions executed by type
- `operator_kco_action_duration_seconds`: Action execution time
- `operator_kco_errors_total`: Errors by category

## 8. Security Considerations

### 8.1 Network Security

- TLS verification for GraphQL endpoints when available
- Network policies to restrict operator communication (included in Chart's templates)
**NOTE** on Secrets management for authentication tokens: this is handled at deployment-time and should be User's responsibility.

### 8.2 Pod Security

- Run as non-root user (UID 1000)
- Read-only root filesystem
- No privileged escalation
- Minimal required capabilities

## 9. Future Enhancements

While not part of the MVP, these features are designed to be easily added:

- **WebSocket Support**: Replace polling with GraphQL subscriptions for real-time updates
- **Multi-cluster Support**: Monitor TApps across multiple clusters
- **Custom Metrics**: Export TApp state as Prometheus metrics
- **Webhook Actions**: Trigger external systems via webhooks
- **Command Execution**: Run commands in TApp pods via kubectl exec
- **State Persistence**: Store historical state in external database
- **Machine Learning**: Predict state transitions and preemptive actions

## 10. Success Criteria

The MVP is considered complete when:

1. Operator successfully monitors TApp GraphQL endpoints
2. State changes generate appropriate Kubernetes Events
3. At least three built-in actions are implemented and tested
4. Operator runs stable for 24 hours in staging environment
5. Documentation covers installation and basic usage
6. Metrics and logs provide sufficient operational visibility
7. Helm chart enables single-command deployment
8. All critical paths have >80% test coverage

## 11. Maintenance and Support

### 11.1 Documentation

- README with quick start guide
- Architecture decision records (ADRs)
- API documentation using docstrings
- Runbook for common operational tasks
- Troubleshooting guide

### 11.2 Version Strategy

- Semantic versioning (MAJOR.MINOR.PATCH)
- Alpha/beta releases for testing new features
- Backward compatibility for minor versions
- Clear upgrade paths between versions
