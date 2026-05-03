"""Message handlers for different types of RabbitMQ messages."""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta

from .logging import get_logger
from .mongodb_client import ensure_connected as ensure_mongodb_connected
from .storage_client import get_storage_client
from .rabbitmq_client import get_rabbitmq_client
from .models import (
    UploadProgressMessage, UploadCompletionMessage,
    WorkerRegistrationMessage, WorkerHeartbeatMessage, TaskMessage,
    ProgressUpdateMessage, CompletionMessage, VideoListRequest, VideoListResponse,
    VideoDocument, TaskDocument, WorkerDocument, VideoInfo,
    VideoStatus, TaskStatus, WorkerStatus,
    generate_video_id, generate_task_id, get_current_timestamp
)


logger = get_logger(__name__)


class MessageHandlers:
    """Collection of message handlers for different message types."""
    
    def __init__(self):
        self.mongodb_client = None
        self.storage_client = get_storage_client()
        self.rabbitmq_client = get_rabbitmq_client()
    
    async def initialize(self) -> None:
        """Initialize all dependencies."""
        self.mongodb_client = await ensure_mongodb_connected()
        await self.storage_client.ensure_buckets_exist()
        logger.info("Message handlers initialized")
    
    async def handle_upload_progress(self, routing_key: str, message_data: Dict[str, Any]) -> None:
        """Handle upload progress update from upload service."""
        try:
            # Parse message
            progress_msg = UploadProgressMessage(**message_data)
            
            # Update video progress in database
            await self.mongodb_client.update_video_upload_progress(
                progress_msg.video_id,
                progress_msg.progress_percentage,
                progress_msg.bytes_uploaded
            )
            
            # Extend token expiration by 10 minutes
            new_expires = datetime.now(timezone.utc) + timedelta(minutes=10)
            expires_str = new_expires.isoformat().replace("+00:00", "Z")
            
            # Update expiration in database
            await self.mongodb_client.videos.update_one(
                {"video_id": progress_msg.video_id},
                {"$set": {"upload_expires_at": expires_str}}
            )
            
            # Forward progress to frontend (if session ID is available)
            # Note: In real implementation, we'd need to track session_id for each video
            
            logger.debug(
                "Updated upload progress",
                video_id=progress_msg.video_id,
                progress=progress_msg.progress_percentage
            )
            
        except Exception as e:
            logger.error("Failed to handle upload progress", error=str(e))
    
    async def handle_upload_completed(self, routing_key: str, message_data: Dict[str, Any]) -> None:
        """Handle upload completion from upload service."""
        try:
            # For integration testing, simplify to just parse the message we're receiving
            logger.info("Received upload completion notification", message_data=message_data)
            
            # Extract basic fields
            video_id = message_data.get('video_id')
            user_id = message_data.get('user_id')
            file_size = message_data.get('file_size')
            temp_file_path = message_data.get('temp_file_path')
            upload_time = message_data.get('upload_time')
            
            if not video_id:
                logger.error("Upload completion missing video_id")
                return
            
            # Update video status in database (simplified for testing)
            await self.mongodb_client.videos.update_one(
                {"video_id": video_id},
                {"$set": {
                    "upload_status": "completed", 
                    "upload_progress": 100,
                    "upload_completed_at": get_current_timestamp(),
                    "status": VideoStatus.UPLOADED.value,
                    "temp_file_path": temp_file_path,
                    "file_size": file_size
                }}
            )
            
            logger.info(
                "Upload completion processed",
                video_id=video_id,
                user_id=user_id,
                file_size=file_size,
                upload_time=upload_time
            )
            
        except Exception as e:
            logger.error("Failed to handle upload completion", error=str(e))
    
    async def handle_worker_registration(self, routing_key: str, message_data: Dict[str, Any]) -> None:
        """Handle worker registration."""
        try:
            # Parse message
            registration_msg = WorkerRegistrationMessage(**message_data)
            
            # Create worker document
            worker_doc = WorkerDocument(
                worker_id=registration_msg.worker_id,
                hostname=registration_msg.hostname,
                status=WorkerStatus.READY,
                capabilities=registration_msg.capabilities,
                current_task_id=None,
                resource_usage={}
            )
            
            # Register worker in database
            await self.mongodb_client.register_worker(worker_doc)
            
            # Create dedicated queue for this worker
            await self.rabbitmq_client.create_worker_queue(registration_msg.worker_id)
            
            logger.info(
                "Registered worker",
                worker_id=registration_msg.worker_id,
                hostname=registration_msg.hostname,
                compute_device=registration_msg.capabilities.get('compute_device', 'unknown')
            )
            
        except Exception as e:
            logger.error("Failed to handle worker registration", error=str(e))
    
    async def handle_worker_heartbeat(self, routing_key: str, message_data: Dict[str, Any]) -> None:
        """Handle worker heartbeat."""
        try:
            # Parse message
            heartbeat_msg = WorkerHeartbeatMessage(**message_data)
            
            # Update worker heartbeat
            await self.mongodb_client.update_worker_heartbeat(
                heartbeat_msg.worker_id,
                WorkerStatus(heartbeat_msg.status),
                heartbeat_msg.resource_usage
            )
            
            logger.debug(
                "Updated worker heartbeat",
                worker_id=heartbeat_msg.worker_id,
                status=heartbeat_msg.status
            )
            
        except Exception as e:
            logger.error("Failed to handle worker heartbeat", error=str(e))
    
    async def handle_processing_progress(self, routing_key: str, message_data: Dict[str, Any]) -> None:
        """Handle processing progress update from worker."""
        try:
            # Parse message
            progress_msg = ProgressUpdateMessage(**message_data)
            
            # Update task progress
            await self.mongodb_client.update_task_progress(
                progress_msg.task_id,
                progress_msg.progress_percentage,
                progress_msg.current_frame,
                progress_msg.fps,
                progress_msg.estimated_time_remaining
            )
            
            # Forward progress to frontend (implementation depends on session tracking)
            
            logger.debug(
                "Updated processing progress",
                task_id=progress_msg.task_id,
                progress=progress_msg.progress_percentage
            )
            
        except Exception as e:
            logger.error("Failed to handle processing progress", error=str(e))
    
    async def handle_processing_completion(self, routing_key: str, message_data: Dict[str, Any]) -> None:
        """Handle processing completion from worker."""
        try:
            # Parse message
            completion_msg = CompletionMessage(**message_data)
            
            # Update task status
            if completion_msg.success:
                await self.mongodb_client.update_task_status(
                    completion_msg.task_id,
                    TaskStatus.COMPLETED
                )
                
                # Update video status and processed file path
                await self.mongodb_client.videos.update_one(
                    {"video_id": completion_msg.video_id},
                    {"$set": {
                        "status": VideoStatus.COMPLETED.value,
                        "processed_file_path": completion_msg.output_file_path,
                        "processing_stats": completion_msg.processing_stats
                    }}
                )
            else:
                await self.mongodb_client.update_task_status(
                    completion_msg.task_id,
                    TaskStatus.FAILED
                )
                
                # Update video status with error
                await self.mongodb_client.videos.update_one(
                    {"video_id": completion_msg.video_id},
                    {"$set": {
                        "status": VideoStatus.FAILED.value,
                        "error_message": completion_msg.error_message
                    }}
                )
            
            # Free up worker
            await self.mongodb_client.workers.update_one(
                {"worker_id": completion_msg.worker_id},
                {"$set": {
                    "status": WorkerStatus.READY.value,
                    "current_task_id": None
                }}
            )
            
            logger.info(
                "Processing completed",
                task_id=completion_msg.task_id,
                success=completion_msg.success,
                worker_id=completion_msg.worker_id
            )
            
        except Exception as e:
            logger.error("Failed to handle processing completion", error=str(e))
    
    async def handle_video_list_request(self, routing_key: str, message_data: Dict[str, Any]) -> None:
        """Handle video list request from frontend."""
        try:
            # Parse request
            request = VideoListRequest(**message_data)
            
            # Get videos from database
            result = await self.mongodb_client.get_videos_by_user(
                request.user_id,
                request.page,
                request.per_page
            )
            
            # Convert to VideoInfo objects with signed URLs
            video_infos = []
            for video in result['videos']:
                thumbnail_url = ""
                if video.thumbnail_path:
                    thumbnail_url = await self.storage_client.generate_signed_download_url(
                        self.storage_client.config.bucket_thumbnails,
                        video.thumbnail_path,
                        expires_in=3600
                    )
                
                video_info = VideoInfo(
                    video_id=video.video_id,
                    filename=video.filename,
                    upload_date=video.upload_date or get_current_timestamp(),
                    status=video.status,
                    upload_progress=video.upload_progress,
                    processing_progress=0,  # Would need to get from task
                    file_size=video.file_size,
                    duration_seconds=video.duration_seconds,
                    thumbnail_url=thumbnail_url
                )
                video_infos.append(video_info)
            
            # Create response
            response = VideoListResponse(
                videos=video_infos,
                total=result['total'],
                page=result['page'],
                per_page=result['per_page']
            )
            
            # Send response to frontend
            await self.rabbitmq_client.publish_message(
                routing_key=f"frontend.{request.session_id}.response",
                message=response
            )
            
            logger.info(
                "Sent video list",
                user_id=request.user_id,
                count=len(video_infos),
                total=result['total']
            )
            
        except Exception as e:
            logger.error("Failed to handle video list request", error=str(e))
    
    async def _create_processing_task(self, video_id: str, user_id: str) -> None:
        """Create a processing task and assign to worker."""
        try:
            # Get video details
            video = await self.mongodb_client.get_video_by_id(video_id)
            if not video:
                raise ValueError(f"Video not found: {video_id}")
            
            # Generate task ID
            task_id = generate_task_id()
            
            # Create task document
            task_doc = TaskDocument(
                task_id=task_id,
                video_id=video_id,
                user_id=user_id,
                status=TaskStatus.PENDING,
                progress_percentage=0,
                current_frame=0,
                total_frames=0,
                estimated_time_remaining=0
            )
            
            # Save task to database
            await self.mongodb_client.create_task(task_doc)
            
            # Find available worker
            workers = await self.mongodb_client.get_available_workers()
            if not workers:
                logger.warning("No available workers for task", task_id=task_id)
                return
            
            # Select best worker (simple: first available)
            selected_worker = workers[0]
            
            # Create task message
            task_message = TaskMessage(
                task_id=task_id,
                video_id=video_id,
                user_id=user_id,
                input_file_path=video.raw_file_path,
                output_file_path=self.storage_client.generate_processed_path(user_id, video_id, task_id),
                processing_settings=video.processing_settings
            )
            
            # Assign task to worker
            await self.mongodb_client.assign_task_to_worker(task_id, selected_worker.worker_id)
            await self.rabbitmq_client.assign_task_to_worker(selected_worker.worker_id, task_message)
            
            logger.info(
                "Created and assigned processing task",
                task_id=task_id,
                video_id=video_id,
                worker_id=selected_worker.worker_id
            )
            
        except Exception as e:
            logger.error("Failed to create processing task", video_id=video_id, error=str(e))
            raise
    
    async def _get_user_id_for_video(self, video_id: str) -> Optional[str]:
        """Get user ID for a video."""
        try:
            video = await self.mongodb_client.get_video_by_id(video_id)
            return video.user_id if video else None
        except Exception as e:
            logger.error("Failed to get user ID for video", video_id=video_id, error=str(e))
            return None
    
    async def _send_error_response(self, session_id: str, error_message: str) -> None:
        """Send error response to frontend."""
        try:
            error_response = {
                "message_type": "error_response",
                "error": error_message
            }
            
            await self.rabbitmq_client.publish_message(
                routing_key=f"frontend.{session_id}.response",
                message=error_response
            )
            
        except Exception as e:
            logger.error("Failed to send error response", error=str(e))


# Global handlers instance
_message_handlers: Optional[MessageHandlers] = None


def get_message_handlers() -> MessageHandlers:
    """Get global message handlers instance."""
    global _message_handlers
    if _message_handlers is None:
        _message_handlers = MessageHandlers()
    return _message_handlers
