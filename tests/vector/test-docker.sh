#!/bin/bash

# Docker Vector Test Script
# This script runs Vector in a Docker container to process the audit logs

set -e

echo "🐳 Starting Vector Docker test..."

# Check if docker is installed and running
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "📁 Project root: $PROJECT_ROOT"
echo "📁 Script directory: $SCRIPT_DIR"
echo ""

# Check if audit logs exist
AUDIT_DIR="$SCRIPT_DIR/../audit"
if [ ! -d "$AUDIT_DIR" ]; then
    echo "❌ Audit directory not found: $AUDIT_DIR"
    exit 1
fi

# List available log files
echo "📋 Available log files:"
ls -la "$AUDIT_DIR"/*.log 2>/dev/null || echo "   No .log files found"
echo ""

echo "🔧 Using vector.yaml configuration directly"

echo ""
echo "🎯 Starting Vector in Docker container..."
echo "   Press Ctrl+C to stop"
echo "   Logs will be displayed in JSON format"
echo ""

# Run Vector in Docker container
docker run --rm \
  -v "$AUDIT_DIR:/app/audit:ro" \
  -v "$SCRIPT_DIR/vector.yaml:/etc/vector/vector.yaml:ro" \
  timberio/vector:latest-alpine \
  --config /etc/vector/vector.yaml
