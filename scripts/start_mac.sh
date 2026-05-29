#!/usr/bin/env bash
set -e

CONTAINER_NAME="finally"
IMAGE_NAME="finally"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Create db directory if it doesn't exist
mkdir -p "$PROJECT_ROOT/db"

# Check .env exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
  echo "ERROR: .env file not found. Copy .env.example to .env and fill in your API key."
  exit 1
fi

# Build image if --build flag passed or image doesn't exist
if [ "$1" = "--build" ] || ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
  echo "Building Docker image..."
  docker build -t "$IMAGE_NAME" "$PROJECT_ROOT"
fi

# Stop and remove existing container if present
if docker container inspect "$CONTAINER_NAME" &>/dev/null; then
  echo "Stopping existing container..."
  docker stop "$CONTAINER_NAME"
  docker rm "$CONTAINER_NAME"
fi

# Start container
echo "Starting FinAlly..."
docker run -d \
  --name "$CONTAINER_NAME" \
  -p 8000:8000 \
  -v "$PROJECT_ROOT/db:/app/db" \
  --env-file "$PROJECT_ROOT/.env" \
  "$IMAGE_NAME"

echo "FinAlly is running at http://localhost:8000"

# Open browser on macOS after a brief startup delay
if command -v open &>/dev/null; then
  sleep 1
  open "http://localhost:8000"
fi
