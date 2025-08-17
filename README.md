# Kubernetes Control Operator (KCO)

A Python-based Kubernetes Operator that monitors Target Applications (TApp) through GraphQL endpoints and orchestrates Kubernetes resources based on observed state changes.

## Overview

KCO follows the controller pattern, continuously reconciling the desired state with the actual state while generating appropriate Kubernetes Events for observability. It polls GraphQL endpoints to monitor application health and state, then executes predefined actions when specific conditions are met.

## Features

- **GraphQL Monitoring**: Async polling of application GraphQL endpoints with configurable intervals
- **State Change Detection**: Intelligent diffing and caching to detect meaningful state transitions
- **Event Generation**: Automatic Kubernetes Event creation for state changes with deduplication
- **Pluggable Actions**: Extensible action system with built-in handlers for common operations
- **Production Ready**: Structured logging, Prometheus metrics, health checks, and graceful shutdown

## Quick Start

### Prerequisites

- Kubernetes cluster (1.19+)
- Python 3.11+ (for local development)
- Poetry (for dependency management)
- Podman or Docker (for container builds)

### Installation

#### Using Helm (Recommended)

1. **Add the chart repository:**
```bash
# For local development
helm install kco-operator ./charts/kco-operator \
  --namespace kco-system \
  --create-namespace
```

2. **Customize values (optional):**
```bash
# Download and customize values
helm show values ./charts/kco-operator > custom-values.yaml
# Edit custom-values.yaml as needed
helm install kco-operator ./charts/kco-operator \
  --namespace kco-system \
  --create-namespace \
  --values custom-values.yaml
```

#### Manual Installation

1. **Install the CRD:**
```bash
kubectl apply -f crd.yaml
```

2. **Deploy the operator:**
```bash
# Build the image
./build.sh

# Deploy to cluster (customize namespace and image as needed)
kubectl create namespace kco-system
kubectl run kco-operator --image=kco:latest --namespace=kco-system
```

#### Create a TargetApp Resource

```bash
kubectl apply -f examples/basic-targetapp.yaml
```

Or create a custom one:
```yaml
apiVersion: operator.kco.local/v1alpha1
kind: TargetApp
metadata:
  name: my-app
  namespace: default
spec:
  selector:
    matchLabels:
      app: my-app
  graphqlEndpoint: "/graphql"
  pollingInterval: 30
  stateQuery: |
    query AppState {
      application {
        status
        health
        pendingTasks
      }
    }
  actions:
  - trigger:
      field: "application.health"
      condition: "equals"
      value: "unhealthy"
    action: "restart_pod"
    parameters:
      gracePeriod: 30
```

## Development

### Local Setup

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Run operator locally (requires kubeconfig)
poetry run python -m kco_operator.main

# Build container image
./build.sh
```

### Architecture

The operator consists of three main layers:

- **Monitoring Layer**: GraphQL client with connection pooling and retry logic
- **Event Processing Layer**: State change detection and Kubernetes Event generation  
- **Action Execution Layer**: Plugin-based action system with built-in handlers

### Built-in Actions

- **`restart_pod`**: Restart pods by deleting them (requires controller to recreate)
- **`scale_deployment`**: Scale deployments to specified replica count
- **`patch_resource`**: Apply patches to Kubernetes resources
- **`webhook`**: Send HTTP webhook notifications to external systems
- **`exec_command`**: Execute commands inside target application pods

### Action Examples

#### Webhook Action
```yaml
action: "webhook"
parameters:
  url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
  method: "POST"
  timeout: 30
  headers:
    Content-Type: "application/json"
  payload:
    text: "Alert: {{tapp_name}} health changed"
    channel: "#alerts"
```

#### Command Execution
```yaml
action: "exec_command"
parameters:
  command: ["/scripts/health-check.sh", "--fix"]
  timeout: 120
  container: "app"
  workingDir: "/app"
```

## Configuration

The operator can be configured via environment variables with the `KCO_` prefix:

- `KCO_LOG_LEVEL`: Log level (DEBUG, INFO, WARNING, ERROR)
- `KCO_GRAPHQL_TIMEOUT`: Default GraphQL timeout in seconds
- `KCO_METRICS_PORT`: Prometheus metrics port (default: 8080)
- `KCO_HEALTH_PORT`: Health check port (default: 8081)

## Monitoring and Observability

### Health Checks

The operator exposes several health and monitoring endpoints:

- **Liveness**: `GET /healthz` - Basic health check
- **Readiness**: `GET /readyz` - Readiness check including dependencies
- **Statistics**: `GET /stats` - Operator and monitoring statistics
- **Metrics**: `GET /metrics` - Prometheus metrics

### Metrics

Key Prometheus metrics exposed by the operator:

- `operator_kco_tapp_polls_total`: Total GraphQL polls executed
- `operator_kco_tapp_poll_duration_seconds`: Poll duration histogram
- `operator_kco_events_generated_total`: Kubernetes Events created
- `operator_kco_actions_executed_total`: Actions executed by type
- `operator_kco_action_duration_seconds`: Action execution time
- `operator_kco_active_monitors`: Number of active TApp monitors
- `operator_kco_errors_total`: Errors by category

### Example Queries

```bash
# Check operator health
curl http://localhost:8081/healthz

# Get monitoring statistics
curl http://localhost:8081/stats

# View Prometheus metrics
curl http://localhost:8080/metrics
```

## Troubleshooting

### Common Issues

1. **No pods found for TargetApp**
   - Verify label selectors match your application pods
   - Check that pods are running in the specified namespace

2. **GraphQL endpoint unreachable**
   - Ensure your application exposes the GraphQL endpoint
   - Check network policies and firewall rules
   - Verify the endpoint path is correct

3. **Actions not executing**
   - Check operator logs for action execution errors
   - Verify trigger conditions match your state data
   - Ensure proper RBAC permissions for the action type

4. **High resource usage**
   - Adjust polling intervals to reduce frequency
   - Implement rate limiting (already enabled by default)
   - Review and optimize GraphQL queries

### Debugging

```bash
# View operator logs
kubectl logs -f deployment/kco-operator -n kco-system

# Check TargetApp status
kubectl get targetapps -o yaml

# View generated events
kubectl get events --field-selector involvedObject.kind=TargetApp

# Check operator metrics
kubectl port-forward svc/kco-operator 8080:8080 -n kco-system
curl http://localhost:8080/metrics
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Run tests: `poetry run pytest`
5. Run linting: `poetry run ruff check && poetry run black --check .`
6. Commit your changes: `git commit -m 'Add amazing feature'`
7. Push to the branch: `git push origin feature/amazing-feature`
8. Open a Pull Request

## License

MIT License - see LICENSE file for details.