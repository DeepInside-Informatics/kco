# GitHub Container Registry (GHCR) Setup

This document explains how to set up GitHub Container Registry for the KCO operator and use the automated CI/CD pipeline.

## Overview

The KCO project uses GitHub Container Registry (GHCR) to store and distribute container images. GHCR is tightly integrated with GitHub and provides:

- Free storage for public repositories
- Automatic cleanup and retention policies
- Integration with GitHub Actions
- Support for container vulnerability scanning

## Setup Steps

### 1. Enable GitHub Container Registry

GHCR is enabled by default for all GitHub repositories. No additional setup is required.

### 2. Repository Settings

To use GHCR with GitHub Actions, ensure the following permissions are configured:

1. Go to your repository settings
2. Navigate to **Actions** → **General**
3. Under **Workflow permissions**, ensure "Read and write permissions" is selected
4. Save the settings

### 3. Package Visibility

Container images can be:
- **Public**: Anyone can pull the images
- **Private**: Only repository collaborators can access

To configure visibility:
1. Go to the repository's **Packages** tab
2. Click on the package name (e.g., `kco`)
3. Go to **Package settings**
4. Under **Danger Zone**, change package visibility

## CI/CD Pipeline

### Automated Builds

The GitHub Actions workflow (`.github/workflows/ci-cd.yml`) automatically:

1. **Tests** the code on every push and PR
2. **Builds** container images using Podman
3. **Pushes** images to GHCR (only for main branch and tags)
4. **Scans** images for security vulnerabilities

### Image Tags

The CI/CD pipeline creates the following image tags:

| Trigger | Tags Created | Example |
|---------|-------------|---------|
| Push to `main` | `main`, `latest`, `main-<sha>-<date>` | `main`, `latest`, `main-abc1234-20240117` |
| Push to other branches | `<branch>`, `<branch>-<sha>-<date>` | `develop`, `develop-abc1234-20240117` |
| Pull Request | `pr-<number>` (build only, not pushed) | `pr-123` |
| Git Tag | `<tag>`, `latest`, version variants | `v1.0.0`, `1.0.0`, `1.0`, `1`, `latest` |

### Release Process

To create a release:

1. **Create a git tag** with semantic versioning:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **GitHub Actions will automatically**:
   - Build the release image
   - Push to GHCR with version tags
   - Create a GitHub Release with changelog
   - Generate deployment instructions

## Using Images

### Pull from GHCR

```bash
# Pull latest version
podman pull ghcr.io/deepinside-informatics/kco:latest

# Pull specific version
podman pull ghcr.io/deepinside-informatics/kco:v1.0.0

# Pull development branch
podman pull ghcr.io/deepinside-informatics/kco:main
```

### Deploy with Helm

```bash
# Deploy latest release
helm install kco-operator ./charts/kco-operator \
  --namespace kco-system \
  --create-namespace \
  --set image.repository=ghcr.io/deepinside-informatics/kco \
  --set image.tag=latest

# Deploy specific version
helm install kco-operator ./charts/kco-operator \
  --namespace kco-system \
  --create-namespace \
  --set image.repository=ghcr.io/deepinside-informatics/kco \
  --set image.tag=v1.0.0
```

### Local Development

```bash
# Build and push manually
PUSH=true REGISTRY=ghcr.io/deepinside-informatics/kco ./build.sh dev-branch

# Test local build against GHCR
./build.sh local-test
podman tag kco:local-test ghcr.io/deepinside-informatics/kco:local-test
```

## Authentication

### GitHub Actions

Authentication is handled automatically using the `GITHUB_TOKEN` secret, which is automatically provided by GitHub Actions.

### Local Development

To push images locally, authenticate with GHCR:

```bash
# Login with your GitHub personal access token
echo $GITHUB_TOKEN | podman login ghcr.io -u $GITHUB_USERNAME --password-stdin

# Or login interactively
podman login ghcr.io
```

**Personal Access Token Requirements:**
- Scope: `write:packages`, `read:packages`
- Can be created at: https://github.com/settings/tokens

### CI/CD on Other Platforms

If using the CI/CD pipeline on other platforms (GitLab CI, Jenkins, etc.), create a GitHub Personal Access Token with `write:packages` scope and configure it as a secret.

## Image Management

### Viewing Images

1. Go to the repository's main page
2. Click on **Packages** (right sidebar)
3. View image tags, download statistics, and vulnerability reports

### Cleanup Policies

GHCR automatically:
- Retains all tagged images indefinitely
- Cleans up untagged images after 7 days
- Provides usage analytics and storage metrics

### Manual Cleanup

```bash
# Delete specific tag (requires appropriate permissions)
curl -X DELETE \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/user/packages/container/kco/versions/VERSION_ID
```

## Security

### Vulnerability Scanning

The CI/CD pipeline includes:
- **Trivy scanning** for known vulnerabilities
- **Results uploaded** to GitHub Security tab
- **SARIF format** for integration with GitHub Advanced Security

### Image Signing (Optional)

For production deployments, consider implementing:
- **Cosign** for image signing
- **Policy enforcement** in Kubernetes clusters
- **SBOM generation** for software bill of materials

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   ```
   Error: unauthorized: unauthenticated
   ```
   - Verify GITHUB_TOKEN has correct permissions
   - Check package visibility settings
   - Ensure authentication is properly configured

2. **Push Failures**
   ```
   Error: denied: permission_denied
   ```
   - Verify repository permissions
   - Check if package exists and has correct visibility
   - Ensure the pushing user has write access

3. **Large Image Size**
   ```
   Warning: Image size exceeds recommended limits
   ```
   - Review Dockerfile for optimization opportunities
   - Use multi-stage builds to reduce final image size
   - Consider using distroless or alpine base images

### Debug Commands

```bash
# Check authentication
podman login ghcr.io --get-login

# Inspect image
podman inspect ghcr.io/deepinside-informatics/kco:latest

# Check image layers
podman history ghcr.io/deepinside-informatics/kco:latest

# Test image locally
podman run --rm ghcr.io/deepinside-informatics/kco:latest python -c "import kco_operator; print('OK')"
```

## Best Practices

1. **Use semantic versioning** for releases (v1.0.0, v1.1.0, etc.)
2. **Keep images small** by optimizing Dockerfiles
3. **Scan for vulnerabilities** regularly
4. **Use specific tags** in production deployments (avoid `latest`)
5. **Monitor image usage** and cleanup old images periodically
6. **Document breaking changes** in release notes
7. **Test images** before tagging as releases

## Integration with Existing Tools

### Helm Chart Updates

Update the default values in `charts/kco-operator/values.yaml`:

```yaml
image:
  repository: ghcr.io/deepinside-informatics/kco
  tag: "latest"
  pullPolicy: IfNotPresent
```

### Documentation Updates

Ensure all documentation references the GHCR image location:
- README.md deployment instructions
- TESTING.md examples
- Helm chart documentation

This completes the GitHub Container Registry setup for the KCO operator!