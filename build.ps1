# Build script for mcp-server-qdrant
# This script builds the entire project from scratch on Windows
# Usage: .\build.ps1 [-Test] [-Docker] [-Publish]

param(
    [switch]$Test,
    [switch]$Docker,
    [switch]$Publish
)

$ErrorActionPreference = "Stop"

function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

Write-ColorOutput Green "=== Building mcp-server-qdrant ==="

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-ColorOutput Green "Python version: $pythonVersion"
} catch {
    Write-ColorOutput Red "Error: Python is not installed or not in PATH"
    exit 1
}

# Check Python version (requires >= 3.10)
$versionMatch = $pythonVersion -match "Python (\d+)\.(\d+)"
if ($versionMatch) {
    $major = [int]$matches[1]
    $minor = [int]$matches[2]
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-ColorOutput Red "Error: Python 3.10 or higher is required. Found: $major.$minor"
        exit 1
    }
} else {
    Write-ColorOutput Yellow "Warning: Could not parse Python version"
}

# Install uv if not present
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-ColorOutput Yellow "Installing uv..."
    try {
        # Try using pip to install uv
        python -m pip install --user uv
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            # Try alternative installation method
            Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile "$env:TEMP\uv-install.ps1"
            & "$env:TEMP\uv-install.ps1"
            Remove-Item "$env:TEMP\uv-install.ps1"
        }
    } catch {
        Write-ColorOutput Red "Error: Failed to install uv"
        Write-ColorOutput Yellow "Please install uv manually: pip install uv"
        exit 1
    }
}

$uvVersion = uv --version
Write-ColorOutput Green "uv version: $uvVersion"

# Sync dependencies
Write-ColorOutput Yellow "Syncing dependencies..."
uv sync
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "Error: Failed to sync dependencies"
    exit 1
}

# Run tests if requested
if ($Test) {
    Write-ColorOutput Yellow "Running tests..."
    uv run pytest
    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput Red "Tests failed!"
        exit 1
    }
    Write-ColorOutput Green "All tests passed!"
}

# Build the package
Write-ColorOutput Yellow "Building package..."
uv build
if ($LASTEXITCODE -ne 0) {
    Write-ColorOutput Red "Error: Failed to build package"
    exit 1
}

# Build Docker image if requested
if ($Docker) {
    Write-ColorOutput Yellow "Building Docker image..."
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-ColorOutput Red "Error: Docker is not installed or not in PATH"
        exit 1
    }
    docker build -t mcp-server-qdrant:latest .
    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput Red "Error: Failed to build Docker image"
        exit 1
    }
    Write-ColorOutput Green "Docker image built successfully!"
    Write-ColorOutput Yellow "To run: docker run -p 3855:3855 -e QDRANT_URL=... -e COLLECTION_NAME=... mcp-server-qdrant:latest"
}

# Publish to PyPI if requested
if ($Publish) {
    Write-ColorOutput Yellow "Publishing to PyPI..."
    if (-not $env:UV_PUBLISH_TOKEN) {
        Write-ColorOutput Red "Error: UV_PUBLISH_TOKEN environment variable is not set"
        exit 1
    }
    uv publish
    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput Red "Error: Failed to publish to PyPI"
        exit 1
    }
    Write-ColorOutput Green "Published to PyPI successfully!"
}

Write-ColorOutput Green "=== Build complete! ==="
Write-ColorOutput Green "Package built in: dist\"
