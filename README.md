# Kubernetes Control Operator (KCO)

A Python-based Kubernetes Operator that monitors Target Applications (TApp) through GraphQL endpoints and orchestrates Kubernetes resources based on observed state changes.

## Overview

KCO follows the controller pattern, continuously reconciling the desired state with the actual state while generating appropriate Kubernetes Events for observability. It polls GraphQL endpoints to monitor application health and state, then executes predefined actions when specific conditions are met.

## Features

- **GraphQL Monitoring**: Async polling of application GraphQL endpoints with configurable intervals
- **State Change Detection**: Intelligent diffing and caching to detect meaningful state transitions  
- **Event Generation**: Automatic Kubernetes Event creation for state changes with deduplication
- **Pluggable Actions**: Extensible action system with 5 built-in handlers for common operations
- **Webhook Integration**: HTTP webhook notifications with template variable support (Slack, PagerDuty, etc.)
- **Direct URL Support**: Monitor external GraphQL endpoints via direct URLs (port-forwarded, external services)
- **Production Ready**: Structured logging, Prometheus metrics, health checks, and graceful shutdown
- **Container Optimized**: Podman-first build system with KinD deployment support

## Quick Start

### Prerequisites

- Kubernetes cluster (1.19+)
- Python 3.11+ (for local development)
- Poetry (for dependency management)
- Podman or Docker (for container builds)

### Installation

#### Using Helm (Recommended)

1. **Install from GitHub Container Registry:**
```bash
# Install latest release
helm install kco-operator ./charts/kco-operator \
  --namespace kco-system \
  --create-namespace

# Install specific version
helm install kco-operator ./charts/kco-operator \
  --namespace kco-system \
  --create-namespace \
  --set image.tag=v1.0.0
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
# Using the pre-built image from GHCR
kubectl create namespace kco-system
kubectl run kco-operator \
  --image=ghcr.io/deepinside-informatics/kco:latest \
  --namespace=kco-system

# Or build locally and deploy
./build.sh
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
  # GraphQL endpoint - supports relative paths or direct URLs
  graphqlEndpoint: "/graphql"  # or "http://external-service:8080/graphql"
  pollingInterval: 30
  stateQuery: |
    query AppState {
      syncStatus
      application {
        health
        pendingTasks
      }
    }
  actions:
  - trigger:
      field: "syncStatus"
      condition: "equals"
      value: "SYNCED"
    action: "webhook"
    parameters:
      url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
      method: "POST"
      payload:
        text: "✅ {{tapp_name}} is now synced at {{timestamp}}"
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

# Build container image (uses Podman by default)
./build.sh

# Build for local testing
./build.sh debug
```

### Local Testing with KinD

For complete testing with a local Kubernetes cluster:

```bash
# Create KinD cluster
kind create cluster --name kco-test

# Build and load operator image
./build.sh debug
podman save localhost/kco:debug -o /tmp/kco-debug.tar
kind load image-archive /tmp/kco-debug.tar --name kco-test

# Deploy operator via Helm
helm install kco-operator ./charts/kco-operator \
  --namespace kco-system \
  --create-namespace \
  --set image.repository=localhost/kco \
  --set image.tag=debug \
  --set image.pullPolicy=IfNotPresent

# Test with production GraphQL endpoint (requires port-forwarding)
export NODE=localhost:3085/graphql
kubectl apply -f test-targetapp.yaml
```

See [TESTING.md](TESTING.md) for comprehensive testing instructions.

### Architecture

The operator consists of three main layers:

- **Monitoring Layer**: GraphQL client with connection pooling and retry logic
- **Event Processing Layer**: State change detection and Kubernetes Event generation  
- **Action Execution Layer**: Plugin-based action system with built-in handlers

### Built-in Actions

- **`restart_pod`**: Restart pods by deleting them (requires controller to recreate)
- **`scale_deployment`**: Scale deployments to specified replica count
- **`patch_resource`**: Apply patches to Kubernetes resources
- **`webhook`**: Send HTTP webhook notifications to external systems (Slack, PagerDuty, custom APIs)
- **`exec_command`**: Execute commands inside target application pods

### Action Examples

#### Webhook Action with Template Variables
```yaml
action: "webhook"
parameters:
  url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
  method: "POST"
  timeout: 30
  payload:
    text: "🚨 KCO Alert: {{tapp_name}} in {{namespace}} has syncStatus={{syncStatus}} at {{timestamp}}"
    channel: "#alerts"
```

**Supported Template Variables:**
- `{{tapp_name}}` - TargetApp resource name
- `{{namespace}}` - TargetApp namespace
- `{{timestamp}}` - ISO timestamp of state change
- `{{syncStatus}}` - Direct access to syncStatus field from GraphQL response
- Additional state fields can be accessed by name if present in the GraphQL response

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

### GraphQL Endpoint Configuration

The operator supports two modes for GraphQL endpoint configuration:

1. **Pod Discovery Mode** (default): Uses `selector` to find pods and appends `graphqlEndpoint` path
   ```yaml
   graphqlEndpoint: "/graphql"  # Relative path
   ```

2. **Direct URL Mode**: Uses full URL directly (for external services, port-forwarded endpoints)
   ```yaml  
   graphqlEndpoint: "http://192.168.1.46:3085/graphql"  # Full URL
   ```

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
   - For direct URL mode, selector can be a dummy value

2. **GraphQL endpoint unreachable**
   - Ensure your application exposes the GraphQL endpoint
   - Check network policies and firewall rules
   - Verify the endpoint path is correct
   - For port-forwarded endpoints, use `--address 0.0.0.0` to bind to all interfaces
   - Test connectivity: `curl -X POST $ENDPOINT -H "Content-Type: application/json" -d '{"query": "{ __schema { queryType { name } } }"}'`

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

# Test GraphQL connectivity from within cluster
kubectl run debug --image=curlimages/curl -it --rm -- /bin/sh
# Then run: curl -X POST http://your-endpoint/graphql -H "Content-Type: application/json" -d '{"query": "{ syncStatus }"}'

# Check operator health and metrics
kubectl port-forward svc/kco-operator 8080:8080 8081:8081 -n kco-system
curl http://localhost:8081/healthz  # Health check
curl http://localhost:8081/stats    # Monitoring statistics
curl http://localhost:8080/metrics  # Prometheus metrics
```

## Testing

The project includes comprehensive testing capabilities:

- **Unit Tests**: `poetry run pytest`
- **Integration Tests**: Real Kubernetes cluster testing with KinD
- **E2E Tests**: Production GraphQL endpoint monitoring
- **Container Testing**: Podman-based image builds and deployment

For detailed testing instructions, see [TESTING.md](TESTING.md).

## CI/CD Pipeline

The project includes automated CI/CD with GitHub Actions:

### Automated Builds

- **Pull Requests**: Build and test (no image push)
- **Main Branch**: Build, test, and push to `ghcr.io/deepinside-informatics/kco:main`
- **Git Tags**: Build, test, push release images, and create GitHub releases

### Container Images

Pre-built images are available at GitHub Container Registry:

```bash
# Latest release
podman pull ghcr.io/deepinside-informatics/kco:latest

# Specific version
podman pull ghcr.io/deepinside-informatics/kco:v1.0.0

# Development builds
podman pull ghcr.io/deepinside-informatics/kco:main
```

### Creating Releases

To create a new release:

```bash
# Tag the release
git tag v1.0.0
git push origin v1.0.0

# GitHub Actions will automatically:
# 1. Build and test the code
# 2. Create container images with version tags
# 3. Push images to GitHub Container Registry
# 4. Create a GitHub Release with changelog
```

For more details, see [docs/github-container-registry.md](docs/github-container-registry.md).

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Run tests: `poetry run pytest`
5. Run linting: `poetry run ruff check && poetry run black --check .`
6. Test with KinD: Follow [TESTING.md](TESTING.md) for local deployment testing
7. Commit your changes: `git commit -m 'Add amazing feature'`
8. Push to the branch: `git push origin feature/amazing-feature`
9. Open a Pull Request

## License

MIT License - see LICENSE file for details.