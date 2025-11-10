#!/bin/bash
# Build script for mcp-server-qdrant
# This script builds the entire project from scratch on any Linux/Unix instance
# Usage: ./build.sh [--test] [--docker] [--publish]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Flags
RUN_TESTS=false
BUILD_DOCKER=false
PUBLISH=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --test)
            RUN_TESTS=true
            shift
            ;;
        --docker)
            BUILD_DOCKER=true
            shift
            ;;
        --publish)
            PUBLISH=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: ./build.sh [--test] [--docker] [--publish]"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}=== Building mcp-server-qdrant ===${NC}"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed${NC}"
    exit 1
fi

# Check Python version (requires >= 3.10)
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo -e "${RED}Error: Python 3.10 or higher is required. Found: $PYTHON_VERSION${NC}"
    exit 1
fi

echo -e "${GREEN}Python version: $PYTHON_VERSION${NC}"

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}Installing uv...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    if ! command -v uv &> /dev/null; then
        echo -e "${RED}Error: Failed to install uv${NC}"
        exit 1
    fi
fi

echo -e "${GREEN}uv version: $(uv --version)${NC}"

# Sync dependencies
echo -e "${YELLOW}Syncing dependencies...${NC}"
uv sync

# Run tests if requested
if [ "$RUN_TESTS" = true ]; then
    echo -e "${YELLOW}Running tests...${NC}"
    uv run pytest
    if [ $? -ne 0 ]; then
        echo -e "${RED}Tests failed!${NC}"
        exit 1
    fi
    echo -e "${GREEN}All tests passed!${NC}"
fi

# Build the package
echo -e "${YELLOW}Building package...${NC}"
uv build

# Build Docker image if requested
if [ "$BUILD_DOCKER" = true ]; then
    echo -e "${YELLOW}Building Docker image...${NC}"
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed${NC}"
        exit 1
    fi
    docker build -t mcp-server-qdrant:latest .
    echo -e "${GREEN}Docker image built successfully!${NC}"
    echo -e "${YELLOW}To run: docker run -p 3855:3855 -e QDRANT_URL=... -e COLLECTION_NAME=... mcp-server-qdrant:latest${NC}"
fi

# Publish to PyPI if requested
if [ "$PUBLISH" = true ]; then
    echo -e "${YELLOW}Publishing to PyPI...${NC}"
    if [ -z "$UV_PUBLISH_TOKEN" ]; then
        echo -e "${RED}Error: UV_PUBLISH_TOKEN environment variable is not set${NC}"
        exit 1
    fi
    uv publish
    echo -e "${GREEN}Published to PyPI successfully!${NC}"
fi

echo -e "${GREEN}=== Build complete! ===${NC}"
echo -e "${GREEN}Package built in: dist/${NC}"
