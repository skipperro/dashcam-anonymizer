#!/bin/bash
"""Run the backend service."""
import asyncio
import sys
import os

# Add the source directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dashcam_backend.main import cli_main

if __name__ == "__main__":
    cli_main()
