# KCO Operator Testing Guide

This document provides comprehensive testing instructions for the KCO (Kubernetes Control Operator) using a KinD cluster with Podman.

## Prerequisites

- **Container Engine**: Podman (preferred) - Docker is not supported in this testing setup
- **Kubernetes**: KinD (Kubernetes in Docker) v0.20.0+
- **Kubectl**: Compatible with your KinD cluster version
- **Production TApp**: A running target application with GraphQL endpoint

## Environment Setup

### 1. Required Environment Variables

Before running tests, set up the following environment variable that points to your GraphQL endpoint:

```bash
export NODE=localhost:3085/graphql
```

**Note**: This should point to a port-forwarded or accessible GraphQL endpoint from your production TApp. The operator will connect to this endpoint for monitoring.

### 2. KinD Cluster Setup

Create a KinD cluster for testing:

```bash
# Create KinD cluster (uses Podman automatically if available)
kind create cluster --name kco-test

# Verify cluster is running
kubectl cluster-info --context kind-kco-test
```

### 3. Build and Deploy Operator

Build the operator image with Podman and deploy to KinD:

```bash
# Build operator image (prefers Podman over Docker)
./build.sh debug

# Load image into KinD cluster
podman save localhost/kco:debug -o /tmp/kco-debug.tar
kind load image-archive /tmp/kco-debug.tar --name kco-test

# Deploy operator using Helm
helm install kco-operator ./charts/kco-operator \
  --namespace kco-system \
  --create-namespace \
  --set image.repository=localhost/kco \
  --set image.tag=debug \
  --set image.pullPolicy=IfNotPresent

# Wait for operator to be ready
kubectl wait --for=condition=available deployment/kco-operator -n kco-system --timeout=60s

# Verify operator is running
kubectl get pods -n kco-system
```

## Network Configuration for Testing

### Podman + KinD Network Access

When using Podman with KinD, the cluster needs to access services running on the host machine. The default gateway IP is typically `10.89.0.1`.

To verify the correct host IP from within the cluster:

```bash
podman exec kco-test-control-plane ip route show default
# Expected output: default via 10.89.0.1 dev eth0 proto static metric 100
```

### Port Forward Your Production TApp

Before testing, ensure your production TApp GraphQL endpoint is accessible from both the host and the KinD cluster:

```bash
# IMPORTANT: Port forward with --address 0.0.0.0 to bind to all interfaces
# This makes the endpoint accessible from inside the KinD cluster
kubectl port-forward --address 0.0.0.0 -n production svc/your-tapp-service 3085:80

# Test accessibility from host
NODE=localhost:3085/graphql
curl -X POST $NODE \
  -H "Content-Type: application/json" \
  -d '{"query": "{ syncStatus }"}'
```

**Expected Response**: `{"data":{"syncStatus":"SYNCED"}}`

**⚠️ Critical Networking Note**: 
- Using `--address 0.0.0.0` binds to all network interfaces, not just localhost
- Without this, the KinD cluster cannot reach the port-forwarded endpoint
- The default `kubectl port-forward` only binds to `127.0.0.1` (localhost only)

## Test Execution

### 1. Deploy Test TargetApp Resource

Apply the test TargetApp that monitors your production GraphQL endpoint:

```bash
# Deploy basic monitoring test TargetApp
kubectl apply -f test-targetapp.yaml

# Or deploy Slack webhook integration test
kubectl apply -f test-targetapp-slack.yaml

# Verify resource creation
kubectl get targetapp
kubectl describe targetapp production-tapp-test
```

### 1.1 Webhook Action Testing

For testing webhook actions (Slack integration):

```bash
# Deploy the Slack webhook test configuration
kubectl apply -f test-targetapp-slack.yaml

# Monitor logs for webhook execution
kubectl logs -n kco-system -l app.kubernetes.io/name=kco-operator -f

# Look for log entries like:
# - "Sending webhook" with URL and method
# - "Webhook sent successfully" with HTTP status 200
# - "Action execution completed" with success status
```

**Expected Slack Message Format:**
```
🚨 KCO Operator Alert: TargetApp production-tapp-slack-test in namespace default has syncStatus=SYNCED at 2025-08-17T16:34:22.061598Z
```

### 2. Monitor Operator Logs

Watch the operator logs to see monitoring activity:

```bash
# Follow operator logs
kubectl logs -n kco-system -l app.kubernetes.io/name=kco-operator -f

# Check for successful GraphQL polling
# Look for log entries like:
# - "Starting monitoring for TargetApp"
# - "GraphQL request successful"
# - "State change detected"
```

### 3. Verify Health Endpoints

Test the operator's health endpoints:

```bash
# Port forward to access health endpoints
kubectl port-forward -n kco-system svc/kco-operator 8081:8081

# Test health endpoints
curl http://localhost:8081/healthz  # Should return {"status": "healthy"}
curl http://localhost:8081/readyz   # Should return {"status": "ready"}
curl http://localhost:8081/metrics  # Should return Prometheus metrics
```

### 4. Test State Change Detection

To test action triggering, modify your production TApp state (if safe to do so) or create a mock scenario:

```bash
# Monitor Kubernetes events for operator activity
kubectl get events --sort-by=.metadata.creationTimestamp

# Check TargetApp status
kubectl get targetapp production-tapp-test -o yaml
```

## Expected Behavior

### Successful Operation

The operator should:

1. **Connect to GraphQL endpoint**: No connection errors in logs
2. **Poll regularly**: Log entries every 30 seconds showing polling activity
3. **Update TargetApp status**: Status field should show "Monitoring" state
4. **Generate events**: Kubernetes events created for state changes
5. **Execute actions**: Webhook/other actions triggered when conditions are met
6. **Health checks pass**: All health endpoints return 200 OK

### Webhook Action Success Indicators

For webhook actions, successful execution shows:

1. **Action Detection**: Log entry "Action triggered" with webhook details
2. **HTTP Request**: Log entry "Sending webhook" with URL and method
3. **Success Response**: Log entry "Webhook sent successfully" with HTTP 200 status
4. **Template Interpolation**: Variables like `{{tapp_name}}`, `{{syncStatus}}` are replaced with actual values
5. **External Notification**: Message appears in target system (Slack channel, webhook endpoint)

### Log Examples

Successful operation logs:

```json
{"event": "Starting monitoring for TargetApp", "name": "production-tapp-test", "namespace": "default"}
{"event": "GraphQL request successful", "duration_ms": 45, "endpoint": "http://10.89.0.1:3085/graphql"}
{"event": "State comparison completed", "changes_detected": 0}
```

State change detection and webhook execution:

```json
{"event": "State change detected", "field": "syncStatus", "old_value": "CATCHING_UP", "new_value": "SYNCED"}
{"event": "Executing action", "action": "webhook", "tapp": "production-tapp-slack-test", "namespace": "default"}
{"event": "Sending webhook", "url": "https://hooks.slack.com/services/.../...", "method": "POST"}
{"event": "Webhook sent successfully", "status": 200, "url": "https://hooks.slack.com/services/.../..."}
{"event": "Action execution completed", "action": "webhook", "status": "success", "execution_time": 0.285}
```

## Troubleshooting

### Common Issues

1. **Connection Refused**
   ```
   Error: dial tcp 10.89.0.1:3085: connect: connection refused
   ```
   - Verify port forwarding is active: `netstat -an | grep 3085`
   - Check firewall settings on host machine
   - Confirm GraphQL endpoint is accessible from host

2. **DNS Resolution Errors**
   ```
   Error: no such host
   ```
   - Use IP address instead of hostname in GraphQL endpoint
   - Verify network connectivity with `kubectl exec` debug pod

3. **Permission Errors**
   ```
   Error: targetapps.operator.kco.local is forbidden
   ```
   - Check RBAC permissions: `kubectl auth can-i create targetapps`
   - Verify operator service account has correct permissions
   - Ensure Helm chart deployed with proper RBAC configuration

3. **Webhook Action Failures**
   ```
   Error: Webhook failed with HTTP 403/404/500
   ```
   - Verify webhook URL is correct and accessible
   - Check authentication tokens/credentials for webhook endpoint
   - Test webhook URL manually: `curl -X POST $WEBHOOK_URL -H "Content-Type: application/json" -d '{"text": "Test message"}'`
   - For Slack webhooks, ensure the webhook URL is active and has proper permissions

4. **Template Variable Issues**
   ```
   Slack message shows: "syncStatus={{syncStatus}}" instead of "syncStatus=SYNCED"
   ```
   - Check that the GraphQL response contains the expected field names
   - Verify template variables match available state fields
   - Ensure webhook action code supports the specific template variables used

5. **Image Pull Errors**
   ```
   Error: ErrImagePull
   ```
   - Ensure image is loaded into KinD: `kind load image-archive /tmp/kco-debug.tar --name kco-test`
   - Check image pull policy is set to `IfNotPresent`
   - Verify image exists in KinD: `podman exec kco-test-control-plane crictl images | grep kco`

### Debug Commands

```bash
# Check operator pod status
kubectl get pods -n kco-system

# Get detailed pod information
kubectl describe pod -n kco-system -l app.kubernetes.io/name=kco-operator

# Check operator configuration
kubectl get configmap -n kco-system kco-operator-config -o yaml

# Verify RBAC permissions
kubectl auth can-i --list --as=system:serviceaccount:kco-system:kco-operator
```

## Test Cleanup

Clean up test resources:

```bash
# Delete test TargetApps
kubectl delete -f test-targetapp.yaml
kubectl delete -f test-targetapp-slack.yaml  # if used

# Uninstall operator
helm uninstall kco-operator -n kco-system

# Delete namespace
kubectl delete namespace kco-system

# Delete KinD cluster
kind delete cluster --name kco-test
```

## CI/CD Integration

For automated testing in CI/CD pipelines:

```bash
#!/bin/bash
# CI test script example

set -e

# Set up environment
export NODE=localhost:3085/graphql

# Create cluster
kind create cluster --name ci-test

# Build and deploy
./build.sh test
podman save localhost/kco:test -o /tmp/kco-test.tar
kind load image-archive /tmp/kco-test.tar --name ci-test

# Deploy operator
helm install kco-operator ./charts/kco-operator \
  --namespace kco-system \
  --create-namespace \
  --set image.repository=localhost/kco \
  --set image.tag=test \
  --wait --timeout=300s

# Run tests
kubectl apply -f test-targetapp.yaml
sleep 30  # Allow time for monitoring to start

# Verify operation
kubectl logs -n kco-system -l app.kubernetes.io/name=kco-operator | grep "GraphQL request successful"

# Cleanup
kind delete cluster --name ci-test
```

## Webhook Testing Examples

### Slack Integration Test

Example `test-targetapp-slack.yaml` configuration:

```yaml
apiVersion: operator.kco.local/v1alpha1
kind: TargetApp
metadata:
  name: production-tapp-slack-test
  namespace: default
spec:
  selector:
    matchLabels:
      app: production-tapp  # Can be dummy for direct URL mode
  graphqlEndpoint: "http://192.168.1.46:3085/graphql"  # Direct URL
  pollingInterval: 30
  stateQuery: |
    query MonitorSync {
      syncStatus
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
        text: "🚨 KCO Operator Alert: TargetApp {{tapp_name}} in namespace {{namespace}} has syncStatus={{syncStatus}} at {{timestamp}}"
```

### Testing Template Variables

Supported template variables in webhook payloads:
- `{{tapp_name}}` → `production-tapp-slack-test`
- `{{namespace}}` → `default`
- `{{timestamp}}` → `2025-08-17T16:34:22.061598Z`
- `{{syncStatus}}` → `SYNCED` (from GraphQL response)
- Additional fields from GraphQL response can be accessed by field name

## Notes

- **Default Container Engine**: Podman is preferred over Docker for all operations
- **Network Configuration**: KinD with Podman uses different networking than Docker
- **Host Access**: Use gateway IP (typically 10.89.0.1) to access host services from cluster  
- **Port Forwarding**: Required for production TApp access during testing
- **Environment Variables**: $NODE must be configured before testing
- **Webhook Testing**: Use real webhook URLs (Slack, Discord, etc.) for complete E2E validation
- **Template Interpolation**: Webhook payloads support dynamic variable substitution from state data