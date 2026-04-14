#!/bin/bash
# Build NanoDeer Sandbox Docker Image
#
# Usage:
#   ./build.sh              # Build locally
#   ./build.sh --push       # Build and push to registry
#   ./build.sh --registry my-registry.com  # Use custom registry

set -e

REGISTRY="${REGISTRY:-nanodeer}"
IMAGE_NAME="sandbox"
TAG="${TAG:-latest}"

# Parse arguments
PUSH=false
CUSTOM_REGISTRY=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --push)
            PUSH=true
            shift
            ;;
        --registry)
            CUSTOM_REGISTRY="$2"
            shift 2
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Determine full image name
if [[ -n "$CUSTOM_REGISTRY" ]]; then
    FULL_IMAGE="${CUSTOM_REGISTRY}/${IMAGE_NAME}:${TAG}"
else
    FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "Building NanoDeer Sandbox Image"
echo "============================================"
echo "Image: $FULL_IMAGE"
echo "Context: $SCRIPT_DIR"
echo "============================================"

# Build the image
echo "Building..."
docker build -t "$FULL_IMAGE" .

echo ""
echo "============================================"
echo "Build complete!"
echo "============================================"
echo "Image: $FULL_IMAGE"
echo ""
echo "To run locally:"
echo "  docker run --rm -it $FULL_IMAGE"
echo ""
echo "To test exec:"
echo "  docker run --rm -it $FULL_IMAGE exec echo hello"
echo ""

# Push if requested
if [[ "$PUSH" == "true" ]]; then
    echo "Pushing to registry..."
    docker push "$FULL_IMAGE"
    echo "Push complete!"
fi