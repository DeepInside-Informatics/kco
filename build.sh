#!/bin/bash

# Local build script for KCO Operator
# Prefers Podman over Docker as specified in requirements

set -euo pipefail

# Configuration
IMAGE_NAME="kco"
IMAGE_TAG="${1:-latest}"
FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're on a supported platform
check_platform() {
    case "$(uname -s)" in
        Darwin)
            log_info "Building on macOS"
            ;;
        Linux)
            log_info "Building on Linux"
            ;;
        *)
            log_error "Unsupported platform: $(uname -s)"
            log_error "KCO supports only macOS and Linux for local development"
            exit 1
            ;;
    esac
}

# Detect container engine (prefer Podman)
detect_container_engine() {
    if command -v podman &> /dev/null; then
        CONTAINER_ENGINE="podman"
        log_info "Using Podman as container engine"
    elif command -v docker &> /dev/null; then
        CONTAINER_ENGINE="docker"
        log_warn "Using Docker as container engine (Podman is preferred)"
    else
        log_error "Neither Podman nor Docker found. Please install one of them."
        log_error "Preferred: Podman (https://podman.io/getting-started/installation)"
        exit 1
    fi
}

# Build the container image
build_image() {
    log_info "Building container image: ${FULL_IMAGE_NAME}"
    
    # Build with build arguments for optimization
    ${CONTAINER_ENGINE} build \
        --tag "${FULL_IMAGE_NAME}" \
        --file Dockerfile \
        --label "org.opencontainers.image.source=https://github.com/DeepInside-Informatics/kco" \
        --label "org.opencontainers.image.version=${IMAGE_TAG}" \
        --label "org.opencontainers.image.created=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        --label "org.opencontainers.image.title=KCO Operator" \
        --label "org.opencontainers.image.description=GraphQL-based Kubernetes Operator" \
        .
    
    if [ $? -eq 0 ]; then
        log_info "Successfully built image: ${FULL_IMAGE_NAME}"
    else
        log_error "Failed to build container image"
        exit 1
    fi
}

# Show image information
show_image_info() {
    log_info "Image information:"
    ${CONTAINER_ENGINE} images "${FULL_IMAGE_NAME}" --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Created}}\t{{.Size}}"
}

# Run basic image validation
validate_image() {
    log_info "Validating image..."
    
    # Check if image runs and shows help
    if ${CONTAINER_ENGINE} run --rm "${FULL_IMAGE_NAME}" python -c "import kco_operator; print('✓ Operator module loads successfully')"; then
        log_info "✓ Image validation passed"
    else
        log_error "✗ Image validation failed"
        exit 1
    fi
}

# Push image (optional)
push_image() {
    if [ "${PUSH:-false}" = "true" ]; then
        if [ -z "${REGISTRY:-}" ]; then
            log_error "REGISTRY environment variable not set. Cannot push image."
            exit 1
        fi
        
        REGISTRY_IMAGE="${REGISTRY}/${FULL_IMAGE_NAME}"
        log_info "Tagging image for registry: ${REGISTRY_IMAGE}"
        ${CONTAINER_ENGINE} tag "${FULL_IMAGE_NAME}" "${REGISTRY_IMAGE}"
        
        log_info "Pushing image to registry: ${REGISTRY_IMAGE}"
        ${CONTAINER_ENGINE} push "${REGISTRY_IMAGE}"
        
        if [ $? -eq 0 ]; then
            log_info "Successfully pushed image: ${REGISTRY_IMAGE}"
        else
            log_error "Failed to push image to registry"
            exit 1
        fi
    fi
}

# Show usage information
show_usage() {
    echo "Usage: $0 [TAG]"
    echo ""
    echo "Build KCO Operator container image locally"
    echo ""
    echo "Arguments:"
    echo "  TAG    Image tag (default: latest)"
    echo ""
    echo "Environment variables:"
    echo "  PUSH=true        Push image to registry after build"
    echo "  REGISTRY=<url>   Registry URL for pushing (required if PUSH=true)"
    echo ""
    echo "Examples:"
    echo "  $0                    # Build kco:latest"
    echo "  $0 v1.0.0            # Build kco:v1.0.0"
    echo "  PUSH=true REGISTRY=registry.example.com $0 v1.0.0"
    echo ""
    echo "Container engine preference: Podman > Docker"
}

# Main execution
main() {
    if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
        show_usage
        exit 0
    fi
    
    log_info "Starting KCO Operator build process"
    
    check_platform
    detect_container_engine
    build_image
    show_image_info
    validate_image
    push_image
    
    log_info "Build process completed successfully!"
    log_info "Run the operator locally with:"
    log_info "  ${CONTAINER_ENGINE} run --rm -it ${FULL_IMAGE_NAME}"
}

# Run main function
main "$@"