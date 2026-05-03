#!/bin/bash
# Setup script for Dashcam Worker development environment

echo "Setting up Dashcam Worker development environment..."

# Get project root directory (two levels up from worker)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Create shared virtual environment in project root if it doesn't exist
if [ ! -d "$PROJECT_ROOT/venv" ]; then
    echo "Creating shared virtual environment in project root..."
    cd "$PROJECT_ROOT"
    python3 -m venv venv
    echo "   Virtual environment created in $PROJECT_ROOT/venv"
else
    echo "Using existing shared virtual environment in project root..."
fi

# Activate shared virtual environment
echo "Activating shared virtual environment..."
source "$PROJECT_ROOT/venv/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip3 install --upgrade pip

# Install requirements
echo "Installing requirements..."
pip3 install -r requirements.txt

# Install the package in development mode
echo "Installing dashcam-worker in development mode..."
pip3 install -e .

echo "Setup complete!"
echo ""
echo "To activate the environment in the future, run:"
echo "source $PROJECT_ROOT/venv/bin/activate"
echo ""
echo "To run tests:"
echo "./run_tests.sh"
echo ""
echo "To run the worker in local test mode:"
echo "python -m dashcam_worker.main --local-test --input input.mp4 --output output.mp4"
