#!/bin/bash

# Consolidated setup script for Dashcam Anonymizer development environment
# Creates a shared virtual environment and installs all service dependencies

set -e  # Exit on any error

echo "=== Dashcam Anonymizer - Development Environment Setup ==="
echo "Setting up shared virtual environment and dependencies for all services"
echo

# Get project root directory (where this script is located)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Create shared virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "🔧 Creating shared virtual environment..."
    python3 -m venv venv
    echo "   Virtual environment created in $PROJECT_ROOT/venv"
else
    echo "✓ Using existing shared virtual environment in $PROJECT_ROOT/venv"
fi

# Activate shared virtual environment
echo "🐍 Activating shared virtual environment..."
source venv/bin/activate
echo "   Virtual environment activated"

# Upgrade pip
echo "📦 Upgrading pip..."
pip3 install --upgrade pip

# Install worker dependencies
echo "📦 Installing worker dependencies..."
cd services/worker
pip3 install -r requirements.txt
pip3 install -e .
cd "$PROJECT_ROOT"

# Install backend dependencies  
if [ -f "services/backend/requirements.txt" ]; then
    echo "📦 Installing backend dependencies..."
    cd services/backend
    pip3 install -r requirements.txt
    pip3 install -e .
    pip3 install -e ".[dev]" 2>/dev/null || echo "   Note: dev dependencies not available"
    cd "$PROJECT_ROOT"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "🔧 Environment Details:"
echo "  Project root: $PROJECT_ROOT"
echo "  Virtual environment: $PROJECT_ROOT/venv"
echo "  Python version: $(python --version)"
echo ""
echo "📝 Next Steps:"
echo "1. Activate the environment: source venv/bin/activate"
echo "2. Run worker tests: cd services/worker && ./run_tests.sh"
echo "3. Run backend tests: cd services/backend && ./run_tests.sh"
echo ""
echo "🧪 Testing Guidelines:"
echo "  - ALWAYS run ./run_tests.sh (not pytest directly) for comprehensive testing"
echo "  - Each service has its own run_tests.sh that uses the shared virtual environment"
echo "  - Tests include unit tests, integration tests, and performance validations"
echo "  - All tests must pass before committing code changes"
echo ""
echo "🎯 Usage:"
echo "  - Worker local test: cd services/worker && python -m dashcam_worker.main --local-test --input input.mp4 --output output.mp4"
echo "  - Start infrastructure: docker-compose -f docker-compose.test.yml up"
echo ""
