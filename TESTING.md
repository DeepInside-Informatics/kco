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

Build the operator image with Podman:

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
# Deploy test TargetApp
kubectl apply -f test-targetapp.yaml

# Verify resource creation
kubectl get targetapp
kubectl describe targetapp production-tapp-test
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
2. **Poll regularly**: Log entries every 15 seconds showing polling activity
3. **Update TargetApp status**: Status field should show "Monitoring" state
4. **Generate events**: Kubernetes events created for state changes
5. **Health checks pass**: All health endpoints return 200 OK

### Log Examples

Successful operation logs:

```json
{"event": "Starting monitoring for TargetApp", "name": "production-tapp-test", "namespace": "default"}
{"event": "GraphQL request successful", "duration_ms": 45, "endpoint": "http://10.89.0.1:3085/graphql"}
{"event": "State comparison completed", "changes_detected": 0}
```

State change detection:

```json
{"event": "State change detected", "field": "syncStatus", "old_value": "SYNCED", "new_value": "CATCHING_UP"}
{"event": "Action triggered", "action": "webhook", "target": "https://httpbin.org/post"}
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

4. **Image Pull Errors**
   ```
   Error: ErrImagePull
   ```
   - Ensure image is loaded into KinD: `kind load docker-image localhost/kco:debug --name kco-test`
   - Check image pull policy is set to `IfNotPresent`

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
# Delete test TargetApp
kubectl delete -f test-targetapp.yaml

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

## Notes

- **Default Container Engine**: Podman is preferred over Docker for all operations
- **Network Configuration**: KinD with Podman uses different networking than Docker
- **Host Access**: Use gateway IP (10.89.0.1) to access host services from cluster
- **Port Forwarding**: Required for production TApp access during testing
- **Environment Variables**: $NODE must be configured before testing