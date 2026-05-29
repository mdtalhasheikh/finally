#!/usr/bin/env bash
set -e

CONTAINER_NAME="finally"

if docker container inspect "$CONTAINER_NAME" &>/dev/null; then
  docker stop "$CONTAINER_NAME"
  docker rm "$CONTAINER_NAME"
  echo "FinAlly stopped."
else
  echo "FinAlly is not running."
fi
