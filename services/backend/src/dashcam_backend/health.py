"""
Health check endpoint for the backend.

Provides a simple HTTP endpoint for container health checks and monitoring.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import uvicorn
import threading
from typing import Dict, Any
import structlog

from .config import get_config
from .video_api import router as video_router


app = FastAPI(title="Dashcam Backend API", version="1.0.0")
logger = structlog.get_logger("health_check")

# Add CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Frontend URLs
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["Location", "X-Thumbnail-Expires"],  # Expose redirect and custom headers
)

# Include video API routes
app.include_router(video_router)

# Contact form models
class ContactFormRequest(BaseModel):
    name: str
    email: str
    subject: str
    message: str

class ContactResponse(BaseModel):
    success: bool
    message: str


@app.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint.
    
    Returns:
        JSON response with backend health status
    """
    try:
        config = get_config()
        
        health_data = {
            "status": "healthy",
            "service": "dashcam_backend",
            "hostname": config.app.hostname,
            "log_level": config.app.log_level,
            "worker_id": config.app.worker_id,
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
        JSON response indicating if backend is ready to accept requests
    """
    try:
        # In a real implementation, this would check if all services are connected
        # (RabbitMQ, MongoDB, etc.)
        ready_data = {
            "status": "ready",
            "message": "Backend is ready to accept requests"
        }
        
        return JSONResponse(content=ready_data, status_code=200)
        
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        error_data = {
            "status": "not_ready",
            "error": str(e)
        }
        return JSONResponse(content=error_data, status_code=503)


@app.post("/contact")
async def contact_form(contact_data: ContactFormRequest) -> ContactResponse:
    """
    Contact form submission endpoint.
    
    Receives contact form data and logs it for now.
    In a real implementation, this would send emails or store in database.
    """
    try:
        # Log the contact form submission
        logger.info(
            "Contact form submission received",
            name=contact_data.name,
            email=contact_data.email,
            subject=contact_data.subject,
            message_length=len(contact_data.message),
            # Don't log the full message for privacy, just the length
        )
        
        # Log the full details for development (remove in production)
        logger.info(
            "Contact form details",
            name=contact_data.name,
            email=contact_data.email,
            subject=contact_data.subject,
            message=contact_data.message,
        )
        
        return ContactResponse(
            success=True,
            message="Contact form submitted successfully"
        )
        
    except Exception as e:
        logger.error("Contact form submission failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to process contact form submission"
        )


def start_health_server(port: int = 8000) -> None:
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
