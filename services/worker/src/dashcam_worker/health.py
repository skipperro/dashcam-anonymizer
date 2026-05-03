"""
Health check endpoint for the worker.

Provides a simple HTTP endpoint for container health checks and monitoring.
"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import threading
from typing import Dict, Any
import structlog

from .config import get_config
from .hardware import get_current_resource_usage


app = FastAPI(title="Dashcam Worker Health Check", version="1.0.0")
logger = structlog.get_logger("health_check")


@app.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint.
    
    Returns:
        JSON response with worker health status
    """
    try:
        config = get_config()
        cpu_percent, memory_percent, gpu_percent = get_current_resource_usage()
        
        health_data = {
            "status": "healthy",
            "worker_id": config.worker_id,
            "hostname": config.hostname,
            "resource_usage": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "gpu_percent": gpu_percent
            },
            "version": "1.0.0"
        }
        
        return JSONResponse(content=health_data, status_code=200)
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        error_data = {
            "status": "unhealthy",
            "error": str(e)
        }
        return JSONResponse(content=error_data, status_code=500)


@app.get("/ready")
async def readiness_check() -> JSONResponse:
    """
    Readiness check endpoint.
    
    Returns:
        JSON response indicating if worker is ready to accept tasks
    """
    try:
        # In a real implementation, this would check if all services are connected
        # (RabbitMQ, MongoDB, etc.)
        ready_data = {
            "status": "ready",
            "message": "Worker is ready to accept tasks"
        }
        
        return JSONResponse(content=ready_data, status_code=200)
        
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        error_data = {
            "status": "not_ready",
            "error": str(e)
        }
        return JSONResponse(content=error_data, status_code=503)


def start_health_server(port: int = 8080) -> None:
    """
    Start health check server in a separate thread.
    
    Args:
        port: Port to run health check server on
    """
    def run_server():
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    
    health_thread = threading.Thread(target=run_server, daemon=True)
    health_thread.start()
    
    logger.info("Health check server started", port=port)
