#!/bin/bash

# Test runner for Dashcam Backend Service
# Runs all tests with detailed reporting

set -e  # Exit on any error

echo "=== Dashcam Backend - Test Suite ==="
echo "Setting up test environment..."
echo

# Get directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR"

# Navigate to backend directory
cd "$BACKEND_DIR"

# Get project root directory (two levels up from backend)
PROJECT_ROOT="$(cd "$BACKEND_DIR/../.." && pwd)"

# Check if shared virtual environment exists in project root
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo "🔧 Creating shared virtual environment in project root..."
    cd "$PROJECT_ROOT"
    python3 -m venv venv
    echo "   Virtual environment created in $PROJECT_ROOT/venv"
    cd "$BACKEND_DIR"
fi

# Activate shared virtual environment
echo "🐍 Activating shared virtual environment..."
source "$PROJECT_ROOT/venv/bin/activate"
echo "   Virtual environment activated"

# Install dependencies
echo "📦 Installing dependencies..."
pip3 install -e .
pip3 install -e ".[dev]" 2>/dev/null || echo "   Note: dev dependencies not available"
echo "   Dependencies installed"

# Set Python path
export PYTHONPATH="$BACKEND_DIR/src:$PYTHONPATH"

echo "🔧 Environment Setup:"
echo "  Backend directory: $BACKEND_DIR"
echo "  Python version: $(python --version)"
echo "  PYTHONPATH: $PYTHONPATH"
echo

# Run tests
echo "🧪 Running Tests..."
echo "========================================"

python3 -m pytest tests/ \
    -v \
    --tb=short \
    --timeout=1 \
    --strict-markers || test_exit_code=$?

echo
echo "========================================"
echo "📊 TEST SUMMARY"
echo "========================================"

if [ ${test_exit_code:-0} -eq 0 ]; then
    echo "🎉 ALL TESTS PASSED!"
    echo
    echo "✅ Backend configuration is working correctly."
    echo "✅ Data models are properly defined."
    echo "✅ Test infrastructure is set up."
    echo
else
    echo "❌ Some tests failed - please review the output above"
    echo
fi

exit ${test_exit_code:-0}
