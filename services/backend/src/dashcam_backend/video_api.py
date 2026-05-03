"""
Video upload and management API endpoints.

Provides streaming upload with background thumbnail generation and video management.
"""

import asyncio
import tempfile
import os
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, UTC, timedelta
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, ValidationError
import structlog
import ffmpeg

from .models import ProcessingSettings, VideoStatus, VideoDocument, UploadSessionDocument, UploadStatus
from .storage_client import StorageClient
from .mongodb_client import MongoDBClient
from .config import get_config


logger = structlog.get_logger("video_api")
router = APIRouter(prefix="/videos", tags=["videos"])


# WebSocket connection manager
class WebSocketManager:
    """Manages WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept WebSocket connection and store it."""
        await websocket.accept()
        self.active_connections[user_id] = websocket
        logger.info("WebSocket connected", user_id=user_id)
    
    async def disconnect(self, user_id: str):
        """Remove WebSocket connection."""
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            logger.info("WebSocket disconnected", user_id=user_id)
    
    async def send_progress_update(self, user_id: str, video_id: str, progress: float, status: str = None):
        """Send progress update to user's WebSocket connection."""
        if user_id in self.active_connections:
            try:
                message = {
                    "type": "upload_progress",
                    "video_id": video_id,
                    "progress": progress,
                    "timestamp": datetime.now(UTC).isoformat()
                }
                if status:
                    message["status"] = status
                
                await self.active_connections[user_id].send_json(message)
                logger.debug("Sent WebSocket progress update", 
                           user_id=user_id, video_id=video_id, progress=progress)
            except Exception as e:
                logger.warning("Failed to send WebSocket message", 
                              user_id=user_id, error=str(e))
                # Remove broken connection
                await self.disconnect(user_id)


# Global client instances
_storage_client: Optional[StorageClient] = None
_mongodb_client: Optional[MongoDBClient] = None
_websocket_manager = WebSocketManager()


async def get_storage_client() -> StorageClient:
    """Get or create storage client instance."""
    global _storage_client
    if _storage_client is None:
        _storage_client = StorageClient()
    return _storage_client


async def get_mongodb_client() -> MongoDBClient:
    """Get or create MongoDB client instance."""
    global _mongodb_client
    if _mongodb_client is None:
        _mongodb_client = MongoDBClient()
        await _mongodb_client.connect()
    return _mongodb_client


# Response models
class UploadResponse(BaseModel):
    video_id: str
    status: str
    message: str


class UploadInitiateResponse(BaseModel):
    video_id: str
    session_id: str
    chunk_size: int
    total_chunks: int
    status: str
    message: str


class ChunkUploadResponse(BaseModel):
    session_id: str
    chunk_number: int
    status: str
    progress_percentage: float
    message: str


class UploadCompleteResponse(BaseModel):
    video_id: str
    session_id: str
    status: str
    file_size: int
    message: str


class VideoInfo(BaseModel):
    video_id: str
    filename: str
    upload_date: str
    status: str
    upload_progress: float
    file_size: int
    duration_seconds: Optional[int] = None
    thumbnail_available: bool = False
    thumbnail_url: Optional[str] = None


class VideoListResponse(BaseModel):
    videos: List[VideoInfo]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class ProgressResponse(BaseModel):
    video_id: str
    status: str
    progress_percentage: float
    current_frame: Optional[int] = None
    total_frames: Optional[int] = None
    estimated_time_remaining: Optional[int] = None
    error_message: Optional[str] = None


class DeleteResponse(BaseModel):
    video_id: str
    message: str


class DownloadResponse(BaseModel):
    video_id: str
    download_url: str
    expires_in: int


def generate_video_id() -> str:
    """Generate unique video ID."""
    return str(uuid.uuid4())


def generate_session_id() -> str:
    """Generate unique upload session ID."""
    return str(uuid.uuid4())


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for real-time progress updates.
    
    Args:
        websocket: WebSocket connection
        user_id: User identifier
    """
    await _websocket_manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive by receiving pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await _websocket_manager.disconnect(user_id)


async def generate_thumbnail_background(video_id: str, raw_video_key: str, bucket_raw: str) -> None:
    """
    Generate thumbnail from a fully assembled video in storage.

    Triggered after upload is complete so the file is intact and ffmpeg can
    seek inside it (required for MP4 files whose moov atom sits at the end).

    Args:
        video_id: Unique video identifier
        raw_video_key: Storage key of the assembled raw video
        bucket_raw: Bucket that contains the raw video
    """
    thumbnail_path = None

    try:
        storage_client = await get_storage_client()
        mongodb_client = await get_mongodb_client()

        logger.info("Starting thumbnail generation", video_id=video_id)

        # Build an internal presigned URL so ffmpeg running server-side can
        # fetch the complete video via HTTP range requests.  This correctly
        # handles MP4 files whose moov atom is at the end of the file.
        video_url = storage_client.generate_internal_presigned_url(
            raw_video_key, expires_in=3600, bucket=bucket_raw
        )

        thumbnail_path = f"/tmp/{video_id}_thumb.jpg"

        try:
            (
                ffmpeg
                .input(video_url, ss=0)
                .output(
                    thumbnail_path,
                    vframes=1,
                    format='image2',
                    vcodec='mjpeg',
                    s='320x240',
                    **{'q:v': 2}
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
        except ffmpeg.Error as e:
            logger.error("FFmpeg error during thumbnail generation",
                         video_id=video_id, error=str(e.stderr.decode()))
            return  # Thumbnail is optional – do not propagate

        # Upload thumbnail to storage
        thumbnail_key = f"thumbnails/{video_id}.jpg"
        success = await asyncio.get_event_loop().run_in_executor(
            None,
            storage_client.upload_file,
            thumbnail_path,
            thumbnail_key
        )

        if success:
            await mongodb_client.update_video_thumbnail_status(video_id, True)
            logger.info("Thumbnail generated successfully", video_id=video_id)
        else:
            logger.error("Failed to upload thumbnail", video_id=video_id)

    except Exception as e:
        logger.error("Thumbnail generation failed", video_id=video_id, error=str(e))

    finally:
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                os.unlink(thumbnail_path)
            except:
                pass


@router.post("/upload/initiate", response_model=UploadInitiateResponse)
async def initiate_upload(
    filename: str = Form(...),
    file_size: int = Form(...),
    storage_client: StorageClient = Depends(get_storage_client),
    mongodb_client: MongoDBClient = Depends(get_mongodb_client)
) -> UploadInitiateResponse:
    """
    Initiate a chunked video upload session.
    
    Args:
        filename: Original filename of the video
        file_size: Total size of the file in bytes
        
    Returns:
        Upload session details including video_id and chunk configuration
    """
    try:
        # Validate file
        if not filename:
            raise HTTPException(400, "No filename provided")
            
        # Validate file type
        allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}
        file_extension = os.path.splitext(filename)[1].lower()
        if file_extension not in allowed_extensions:
            raise HTTPException(400, f"Unsupported file type: {file_extension}")
        
        # Validate file size (max 2GB)
        max_file_size = 2 * 1024 * 1024 * 1024  # 2GB
        if file_size > max_file_size:
            raise HTTPException(400, f"File too large. Maximum size: {max_file_size} bytes")
        
        # Generate IDs
        video_id = generate_video_id()
        session_id = generate_session_id()
        
        # Calculate chunk configuration
        chunk_size = 50 * 1024 * 1024  # 50MB chunks
        total_chunks = (file_size + chunk_size - 1) // chunk_size  # Ceiling division
        
        logger.info("Initiating chunked upload", 
                   video_id=video_id, session_id=session_id, 
                   filename=filename, file_size=file_size, 
                   total_chunks=total_chunks)
        
        # Actual MinIO object key (no bucket-prefix — stored inside the raw bucket)
        raw_storage_key = f"{video_id}{file_extension}"
        # Virtual path used for task routing: encodes bucket via prefix
        raw_file_path = f"raw-videos/{video_id}{file_extension}"
        
        # Create video document immediately (this makes it visible in the list)
        video_doc = VideoDocument(
            video_id=video_id,
            user_id="anonymous",  # No auth for now
            filename=filename,
            file_size=file_size,
            status=VideoStatus.UPLOADING,
            upload_status=UploadStatus.IN_PROGRESS,
            raw_file_path=raw_file_path,
            upload_date=datetime.now(UTC),
            upload_progress=0.0,
            upload_session_id=session_id,
            total_chunks=total_chunks,
            chunks_uploaded=[]
        )
        
        # Try to create video record with retry logic for duplicates
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await mongodb_client.create_video(video_doc)
                logger.info("Successfully created video document", 
                           video_id=video_id, session_id=session_id)
                break
            except ValueError as e:
                if "Video already exists" in str(e) and attempt < max_retries - 1:
                    # Generate new video_id and update paths
                    logger.warning("Video ID collision, retrying with new ID", 
                                 old_video_id=video_id, attempt=attempt + 1)
                    video_id = generate_video_id()
                    raw_storage_key = f"{video_id}{file_extension}"
                    raw_file_path = f"raw-videos/{video_id}{file_extension}"
                    video_doc.video_id = video_id
                    video_doc.raw_file_path = raw_file_path
                else:
                    logger.error("Failed to create video after retries", error=str(e))
                    raise HTTPException(500, f"Failed to create video: {str(e)}")
        
        # Initialize multipart upload to storage
        upload_id = await asyncio.get_event_loop().run_in_executor(
            None,
            storage_client.initiate_multipart_upload,
            raw_storage_key
        )
        
        # Create upload session document
        upload_session = UploadSessionDocument(
            session_id=session_id,
            video_id=video_id,
            user_id="anonymous",
            filename=filename,
            total_size=file_size,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            uploaded_chunks=[],
            multipart_upload_id=upload_id,
            storage_key=raw_storage_key,
            status=UploadStatus.IN_PROGRESS
        )
        
        # Save upload session to database
        await mongodb_client.create_upload_session(upload_session)
        
        # Send initial progress update via WebSocket
        await _websocket_manager.send_progress_update(
            "anonymous", video_id, 0.0, VideoStatus.UPLOADING
        )
        
        logger.info("Upload session initiated successfully", 
                   video_id=video_id, session_id=session_id,
                   chunk_size=chunk_size, total_chunks=total_chunks)
        
        return UploadInitiateResponse(
            video_id=video_id,
            session_id=session_id,
            chunk_size=chunk_size,
            total_chunks=total_chunks,
            status="initiated",
            message="Upload session created successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to initiate upload", error=str(e))
        raise HTTPException(500, "Failed to initiate upload")


@router.post("/upload/chunk/{session_id}/{chunk_number}", response_model=ChunkUploadResponse)
async def upload_chunk(
    session_id: str,
    chunk_number: int,
    chunk_data: UploadFile = File(...),
    storage_client: StorageClient = Depends(get_storage_client),
    mongodb_client: MongoDBClient = Depends(get_mongodb_client)
) -> ChunkUploadResponse:
    """
    Upload a single chunk of the video file.
    
    Args:
        session_id: Upload session identifier
        chunk_number: Chunk number (0-based)
        chunk_data: Chunk file data
        
    Returns:
        Chunk upload response with progress
    """
    try:
        # Get upload session
        upload_session = await mongodb_client.get_upload_session(session_id)
        if not upload_session:
            raise HTTPException(404, "Upload session not found")
        
        if upload_session.status != UploadStatus.IN_PROGRESS:
            raise HTTPException(400, f"Upload session is not active: {upload_session.status}")
        
        # Validate chunk number
        if chunk_number < 0 or chunk_number >= upload_session.total_chunks:
            raise HTTPException(400, f"Invalid chunk number: {chunk_number}")
        
        # Check if chunk already uploaded
        if chunk_number in upload_session.uploaded_chunks:
            logger.info("Chunk already uploaded", 
                       session_id=session_id, chunk_number=chunk_number)
            progress = len(upload_session.uploaded_chunks) / upload_session.total_chunks * 100
            return ChunkUploadResponse(
                session_id=session_id,
                chunk_number=chunk_number,
                status="already_uploaded",
                progress_percentage=progress,
                message="Chunk already uploaded"
            )
        
        logger.info("Uploading chunk", 
                   session_id=session_id, chunk_number=chunk_number)
        
        # Read chunk data
        chunk_bytes = await chunk_data.read()
        
        # Upload chunk to storage (1-based part number for S3)
        part_number = chunk_number + 1
        etag = await asyncio.get_event_loop().run_in_executor(
            None,
            storage_client.upload_part,
            upload_session.storage_key,
            upload_session.multipart_upload_id,
            part_number,
            chunk_bytes
        )
        
        # Update upload session with completed chunk
        await mongodb_client.update_upload_session_chunk(session_id, chunk_number, etag)
        
        # Get updated session to calculate progress
        updated_session = await mongodb_client.get_upload_session(session_id)
        progress = len(updated_session.uploaded_chunks) / updated_session.total_chunks * 100
        
        # Update video progress in database
        await mongodb_client.update_video_upload_progress(
            upload_session.video_id, progress, len(updated_session.uploaded_chunks) * upload_session.chunk_size
        )
        
        # Send progress update via WebSocket
        await _websocket_manager.send_progress_update(
            upload_session.user_id, upload_session.video_id, progress
        )
        
        # Thumbnail is generated after the full upload completes (in complete_upload),
        # not here – a partial chunk cannot be reliably decoded by ffmpeg.

        logger.info("Chunk uploaded successfully", 
                   session_id=session_id, chunk_number=chunk_number, 
                   progress=progress)
        
        return ChunkUploadResponse(
            session_id=session_id,
            chunk_number=chunk_number,
            status="uploaded",
            progress_percentage=progress,
            message="Chunk uploaded successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload chunk", 
                    session_id=session_id, chunk_number=chunk_number, error=str(e))
        # Mark session as failed
        try:
            await mongodb_client.update_upload_session_status(session_id, UploadStatus.FAILED)
            await mongodb_client.update_video_status(upload_session.video_id, VideoStatus.FAILED)
        except:
            pass
        raise HTTPException(500, "Failed to upload chunk")


@router.post("/upload/complete/{session_id}", response_model=UploadCompleteResponse)
async def complete_upload(
    session_id: str,
    background_tasks: BackgroundTasks,
    storage_client: StorageClient = Depends(get_storage_client),
    mongodb_client: MongoDBClient = Depends(get_mongodb_client)
) -> UploadCompleteResponse:
    """
    Complete a chunked upload session.
    
    Args:
        session_id: Upload session identifier
        
    Returns:
        Upload completion response
    """
    try:
        # Get upload session
        upload_session = await mongodb_client.get_upload_session(session_id)
        if not upload_session:
            raise HTTPException(404, "Upload session not found")
        
        if upload_session.status != UploadStatus.IN_PROGRESS:
            raise HTTPException(400, f"Upload session is not active: {upload_session.status}")
        
        # Verify all chunks are uploaded
        if len(upload_session.uploaded_chunks) != upload_session.total_chunks:
            missing_chunks = set(range(upload_session.total_chunks)) - set(upload_session.uploaded_chunks)
            raise HTTPException(400, f"Upload incomplete. Missing chunks: {sorted(missing_chunks)}")
        
        logger.info("Completing upload session", session_id=session_id)
        
        # Get parts list for S3 completion
        parts_list = await mongodb_client.get_upload_session_parts(session_id)
        
        # Complete multipart upload
        await asyncio.get_event_loop().run_in_executor(
            None,
            storage_client.complete_multipart_upload,
            upload_session.storage_key,
            upload_session.multipart_upload_id,
            parts_list
        )
        
        # Update upload session status
        await mongodb_client.update_upload_session_status(session_id, UploadStatus.COMPLETED)
        
        # Update video status and progress
        await mongodb_client.update_video_upload_progress(upload_session.video_id, 100.0, upload_session.total_size)
        await mongodb_client.update_video_status(upload_session.video_id, VideoStatus.UPLOADED)
        
        # Update final file size
        await mongodb_client.videos.update_one(
            {"video_id": upload_session.video_id},
            {"$set": {"file_size": upload_session.total_size}}
        )
        
        # Send completion update via WebSocket
        await _websocket_manager.send_progress_update(
            upload_session.user_id, upload_session.video_id, 100.0, VideoStatus.UPLOADED
        )

        # Schedule thumbnail generation now that the full file is assembled in storage.
        # ffmpeg reads the complete video via HTTP range requests, which correctly
        # handles MP4 files whose moov atom sits at the end.
        background_tasks.add_task(
            generate_thumbnail_background,
            upload_session.video_id,
            upload_session.storage_key,
            storage_client.config.bucket_raw
        )

        logger.info("Upload completed successfully", 
                   session_id=session_id, video_id=upload_session.video_id,
                   file_size=upload_session.total_size)
        
        return UploadCompleteResponse(
            video_id=upload_session.video_id,
            session_id=session_id,
            status="completed",
            file_size=upload_session.total_size,
            message="Upload completed successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to complete upload", session_id=session_id, error=str(e))
        # Mark session as failed
        try:
            await mongodb_client.update_upload_session_status(session_id, UploadStatus.FAILED)
        except:
            pass
        raise HTTPException(500, "Failed to complete upload")


@router.post("/upload", response_model=UploadResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    storage_client: StorageClient = Depends(get_storage_client),
    mongodb_client: MongoDBClient = Depends(get_mongodb_client)
) -> UploadResponse:
    """
    Upload a video file for processing.
    
    Args:
        file: Video file to upload
        background_tasks: Background tasks for processing
        
    Returns:
        Upload response with video ID and status
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(400, "No filename provided")
            
        # Generate video ID
        video_id = generate_video_id()
        
        # Validate file type
        allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm'}
        file_extension = os.path.splitext(file.filename)[1].lower()
        if file_extension not in allowed_extensions:
            raise HTTPException(400, f"Unsupported file type: {file_extension}")
        
        logger.info("Starting video upload", video_id=video_id, filename=file.filename)
        
        # Actual MinIO object key (no bucket-prefix — stored inside the raw bucket)
        raw_storage_key = f"{video_id}{file_extension}"
        # Virtual path used for task routing: encodes bucket via prefix
        raw_file_path = f"raw-videos/{video_id}{file_extension}"
        
        # Create initial video record in database with 0% progress
        video_doc = VideoDocument(
            video_id=video_id,
            user_id="anonymous",  # No auth for now
            filename=file.filename or 'unknown.mp4',
            file_size=0,  # Will be updated as we go
            status=VideoStatus.UPLOADING,
            raw_file_path=raw_file_path,
            upload_date=datetime.now(UTC),
            upload_progress=0.0
        )
        
        logger.info("About to create video document in database", 
                   video_id=video_id, 
                   status=video_doc.status, 
                   user_id=video_doc.user_id)
        
        # Try to create video record with retry logic for duplicates
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await mongodb_client.create_video(video_doc)
                logger.info("Successfully created video document", 
                           video_id=video_id, 
                           db_result=result)
                break  # Success, exit retry loop
            except ValueError as e:
                if "Video already exists" in str(e) and attempt < max_retries - 1:
                    # Generate new video_id and update paths
                    logger.warning(
                        "Video ID collision, retrying with new ID", 
                        old_video_id=video_id, 
                        attempt=attempt + 1
                    )
                    video_id = generate_video_id()
                    raw_storage_key = f"{video_id}{file_extension}"
                    raw_file_path = f"raw-videos/{video_id}{file_extension}"
                    
                    # Update video document with new IDs
                    video_doc.video_id = video_id
                    video_doc.raw_file_path = raw_file_path
                    
                    logger.info("Retrying video upload", video_id=video_id, filename=file.filename)
                else:
                    # Max retries exceeded or different error
                    logger.error("Failed to create video after retries", error=str(e))
                    raise HTTPException(500, f"Failed to create video: {str(e)}")
        
        # Start streaming upload to storage
        first_chunk_buffer = bytearray()
        thumbnail_triggered = False
        total_size = 0
        chunk_size = 8192  # 8KB chunks
        
        try:
            # Initialize upload to storage
            upload_id = await asyncio.get_event_loop().run_in_executor(
                None,
                storage_client.initiate_multipart_upload,
                raw_storage_key
            )
            
            parts = []
            part_number = 1
            current_part_data = bytearray()
            part_size = 50 * 1024 * 1024  # 50MB parts
            progress_chunk_size = 5 * 1024 * 1024  # Report progress every 5MB
            last_progress_bytes = 0
            
            # Stream file chunks
            while chunk := await file.read(chunk_size):
                total_size += len(chunk)
                current_part_data.extend(chunk)
                
                # Report progress every 5MB for better user feedback
                if total_size - last_progress_bytes >= progress_chunk_size:
                    # Use a unified progress calculation for all file sizes
                    # Progress increases smoothly from 0% to 95%, leaving 5% for completion
                    if total_size <= 50 * 1024 * 1024:  # Files up to 50MB
                        progress = min(90.0, (total_size / (50 * 1024 * 1024)) * 90.0)
                    else:  # Files larger than 50MB
                        # 90% for first 50MB, then slower progress for remaining data
                        extra_size = total_size - 50 * 1024 * 1024
                        extra_progress = min(5.0, (extra_size / (100 * 1024 * 1024)) * 5.0)  # 5% for next 100MB
                        progress = 90.0 + extra_progress
                    
                    logger.debug("Upload progress update", video_id=video_id, progress=progress, total_size=total_size)
                    await mongodb_client.update_video_upload_progress(video_id, progress, total_size)
                    last_progress_bytes = total_size
                
                # Buffer first 10MB for thumbnail generation
                if len(first_chunk_buffer) < 10 * 1024 * 1024:
                    first_chunk_buffer.extend(chunk)
                    
                    # Trigger thumbnail generation when we have 10MB
                    if len(first_chunk_buffer) >= 10 * 1024 * 1024 and not thumbnail_triggered:
                        background_tasks.add_task(
                            generate_thumbnail_background,
                            video_id,
                            bytes(first_chunk_buffer),
                            file.filename or 'video.mp4'
                        )
                        thumbnail_triggered = True
                
                # Upload parts in 50MB chunks
                if len(current_part_data) >= part_size:
                    etag = await asyncio.get_event_loop().run_in_executor(
                        None,
                        storage_client.upload_part,
                        raw_storage_key,
                        upload_id,
                        part_number,
                        bytes(current_part_data)
                    )
                    parts.append({'ETag': etag, 'PartNumber': part_number})
                    
                    part_number += 1
                    current_part_data = bytearray()
                    
                    # Update last_progress_bytes to the uploaded size to avoid duplicate progress updates
                    last_progress_bytes = max(last_progress_bytes, part_number * part_size)
            
            # Upload final part if any data remains
            if current_part_data:
                etag = await asyncio.get_event_loop().run_in_executor(
                    None,
                    storage_client.upload_part,
                    raw_storage_key,
                    upload_id,
                    part_number,
                    bytes(current_part_data)
                )
                parts.append({'ETag': etag, 'PartNumber': part_number})
            
            # Complete multipart upload
            await asyncio.get_event_loop().run_in_executor(
                None,
                storage_client.complete_multipart_upload,
                raw_storage_key,
                upload_id,
                parts
            )
            
            # Update to 100% progress with final file size, then update status to UPLOADED
            await mongodb_client.update_video_upload_progress(video_id, 100.0, total_size)
            await mongodb_client.update_video_status(video_id, VideoStatus.UPLOADED)
            
            # Update file_size field directly since it's not in upload_progress method
            await mongodb_client.videos.update_one(
                {"video_id": video_id},
                {"$set": {"file_size": total_size}}
            )
            
            # Trigger thumbnail generation for smaller files (< 10MB)
            if not thumbnail_triggered and first_chunk_buffer:                background_tasks.add_task(
                    generate_thumbnail_background,
                    video_id,
                    bytes(first_chunk_buffer),
                    file.filename or 'video.mp4'
                )
            
        except Exception as e:
            logger.error("Upload to storage failed", video_id=video_id, error=str(e))
            # Update status to failed
            try:
                await mongodb_client.update_video_status(video_id, VideoStatus.FAILED)
            except Exception:
                pass  # Don't fail if we can't update status
            raise HTTPException(500, "Upload failed")
        
        logger.info(
            "Video upload completed",
            video_id=video_id,
            file_size=total_size,
            filename=file.filename
        )
        
        return UploadResponse(
            video_id=video_id,
            status="uploaded",
            message="Video uploaded successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Video upload failed", error=str(e))
        raise HTTPException(500, "Upload failed")


@router.get("/", response_model=VideoListResponse)
async def list_videos(
    page: int = 1,
    per_page: int = 10,
    status: Optional[str] = None,
    mongodb_client: MongoDBClient = Depends(get_mongodb_client)
) -> VideoListResponse:
    """
    List videos with pagination and filtering.
    
    Args:
        page: Page number (1-based)
        per_page: Videos per page
        status: Filter by status
        
    Returns:
        Paginated video list
    """
    try:
        logger.info("list_videos called", page=page, per_page=per_page, status_filter=status)
        
        # Debug: Check raw database counts
        total_in_db = await mongodb_client.videos.count_documents({})
        anonymous_videos = await mongodb_client.videos.count_documents({"user_id": "anonymous"})
        uploading_videos = await mongodb_client.videos.count_documents({"user_id": "anonymous", "status": "uploading"})
        logger.info("Database debug counts", 
                   total_in_db=total_in_db, 
                   anonymous_videos=anonymous_videos,
                   uploading_videos=uploading_videos)
        
        # Get videos from database
        videos, total = await mongodb_client.list_videos(
            user_id="anonymous",  # No auth for now
            page=page,
            per_page=per_page,
            status_filter=status
        )
        
        logger.info("list_videos result", videos_count=len(videos), total=total)
        
        # Convert to response format
        video_infos = []
        for video in videos:
            # Handle upload_date - it might be datetime or string
            upload_date_str = ""
            if video.upload_date:
                if isinstance(video.upload_date, str):
                    upload_date_str = video.upload_date
                else:
                    upload_date_str = video.upload_date.isoformat()
            
            video_info = VideoInfo(
                video_id=video.video_id,
                filename=video.filename,
                upload_date=upload_date_str,
                status=video.status,
                upload_progress=video.upload_progress,
                file_size=video.file_size,
                duration_seconds=video.duration_seconds,
                thumbnail_available=getattr(video, 'thumbnail_available', False),
                thumbnail_url=f"/videos/{video.video_id}/thumbnail" if getattr(video, 'thumbnail_available', False) else None
            )
            video_infos.append(video_info)
        
        # Calculate pagination flags
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        has_next = end_index < total  # Are there more items after this page?
        has_prev = page > 1
        
        return VideoListResponse(
            videos=video_infos,
            total=total,
            page=page,
            per_page=per_page,
            has_next=has_next,
            has_prev=has_prev
        )
        
    except Exception as e:
        logger.error("Failed to list videos", error=str(e))
        raise HTTPException(500, "Failed to retrieve videos")


@router.get("/{video_id}/thumbnail")
async def get_thumbnail(
    video_id: str,
    storage_client: StorageClient = Depends(get_storage_client),
    mongodb_client: MongoDBClient = Depends(get_mongodb_client)
):
    """
    Get video thumbnail - returns 307 redirect to pre-signed URL or 404 if not available.
    
    Args:
        video_id: Video identifier
        
    Returns:
        307 redirect to pre-signed thumbnail URL or 404 if not available
    """
    try:
        # First check if video exists and is not deleted
        video = await mongodb_client.get_video_by_id(video_id)
        if not video:
            raise HTTPException(404, "Video not found")
            
        if getattr(video, 'deleted', False):
            raise HTTPException(404, "Video not found")
        
        # Check if thumbnail is marked as available in database
        if not getattr(video, 'thumbnail_available', False):
            raise HTTPException(404, "Thumbnail not yet available")
        
        # Verify thumbnail actually exists in storage
        thumbnail_key = f"thumbnails/{video_id}.jpg"
        try:
            # Use direct S3 head_object call to avoid method confusion
            bucket_name = storage_client.config.bucket_thumbnails
            
            def check_file():
                try:
                    storage_client.s3_client.head_object(Bucket=bucket_name, Key=thumbnail_key)
                    return True
                except Exception as e:
                    # Check if it's a 404 error (not found)
                    if hasattr(e, 'response') and e.response.get('Error', {}).get('Code') == '404':
                        return False
                    raise
            
            exists = await asyncio.get_event_loop().run_in_executor(None, check_file)
            
            if not exists:
                # Thumbnail marked as available but doesn't exist in storage
                await mongodb_client.update_video_thumbnail_status(video_id, False)
                raise HTTPException(404, "Thumbnail not yet available")
        except Exception:
            raise HTTPException(404, "Thumbnail not yet available")
        
        # Generate 10-minute pre-signed URL for direct browser access
        try:
            presigned_url = await asyncio.get_event_loop().run_in_executor(
                None,
                storage_client.generate_signed_url,
                thumbnail_key,
                600,  # 10 minutes validity
                storage_client.config.bucket_thumbnails
            )
            
            # Return JSON response with the pre-signed URL instead of redirect
            # This avoids CORS issues with manual redirect handling
            return JSONResponse({
                "thumbnail_url": presigned_url,
                "expires_in": 600
            }, headers={
                "Cache-Control": "public, max-age=300",  # Cache response for 5 minutes
                "X-Thumbnail-Expires": str(600)  # Inform frontend about URL validity
            })
            
        except Exception as storage_error:
            logger.error("Failed to generate pre-signed URL for thumbnail", 
                        video_id=video_id, error=str(storage_error))
            raise HTTPException(404, "Thumbnail not yet available")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get thumbnail", video_id=video_id, error=str(e))
        raise HTTPException(500, "Failed to retrieve thumbnail")


@router.get("/{video_id}/progress", response_model=ProgressResponse)
async def get_progress(
    video_id: str,
    mongodb_client: MongoDBClient = Depends(get_mongodb_client)
) -> ProgressResponse:
    """
    Get video processing progress.

    For videos being processed, returns real-time task progress (frames, ETA).
    For videos still uploading, returns upload progress percentage.

    Args:
        video_id: Video identifier

    Returns:
        Processing progress information
    """
    try:
        video = await mongodb_client.get_video_by_id(video_id)
        if not video:
            raise HTTPException(404, "Video not found")

        # For processing/queued videos, look up the active task for accurate frame-level progress
        from .models import VideoStatus as _VideoStatus
        processing_statuses = {_VideoStatus.PROCESSING, _VideoStatus.QUEUED, _VideoStatus.PROCESSING.value, _VideoStatus.QUEUED.value}
        if video.status in processing_statuses:
            task = await mongodb_client.get_active_task_by_video_id(video_id)
            if task:
                return ProgressResponse(
                    video_id=video_id,
                    status=video.status,
                    progress_percentage=task.progress_percentage,
                    current_frame=task.current_frame,
                    total_frames=task.total_frames,
                    estimated_time_remaining=task.estimated_time_remaining,
                )

        return ProgressResponse(
            video_id=video_id,
            status=video.status,
            progress_percentage=video.upload_progress,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get progress", video_id=video_id, error=str(e))
        raise HTTPException(500, "Failed to retrieve progress")


@router.delete("/{video_id}", response_model=DeleteResponse)
async def delete_video(
    video_id: str,
    mongodb_client: MongoDBClient = Depends(get_mongodb_client),
    storage_client: StorageClient = Depends(get_storage_client)
) -> DeleteResponse:
    """
    Delete video (soft delete from DB + remove files from storage).
    
    Args:
        video_id: Video identifier
        
    Returns:
        Deletion confirmation
    """
    try:
        # Get video document first
        video = await mongodb_client.get_video_by_id(video_id)
        if not video:
            raise HTTPException(404, "Video not found")
            
        if getattr(video, 'deleted', False):
            raise HTTPException(400, "Video already deleted")
        
        # Collect all file paths to delete.
        # raw_file_path / processed_file_path are stored with a virtual bucket-routing
        # prefix (e.g. "raw-videos/<id>.mp4") to allow workers to determine the
        # target bucket.  The actual MinIO object key is the part *after* that prefix,
        # so we must strip it before calling delete_file.
        files_to_delete = []

        # Add raw file if exists
        if video.raw_file_path:
            bucket = storage_client.config.bucket_raw
            raw_key = (
                video.raw_file_path[len("raw-videos/"):]
                if video.raw_file_path.startswith("raw-videos/")
                else video.raw_file_path
            )
            files_to_delete.append((bucket, raw_key))

        # Add processed file if exists
        if video.processed_file_path:
            bucket = storage_client.config.bucket_processed
            processed_key = (
                video.processed_file_path[len("processed-videos/"):]
                if video.processed_file_path.startswith("processed-videos/")
                else video.processed_file_path
            )
            files_to_delete.append((bucket, processed_key))
            
        # Add thumbnail if exists (use standard naming convention)
        # Thumbnails are always stored as "thumbnails/{video_id}.jpg"
        if getattr(video, 'thumbnail_available', False):
            bucket = storage_client.config.bucket_thumbnails
            thumbnail_key = f"thumbnails/{video_id}.jpg"
            files_to_delete.append((bucket, thumbnail_key))
        
        # Delete files from storage first
        # If this fails, we don't want to mark as deleted in DB
        for bucket, file_path in files_to_delete:
            try:
                await storage_client.delete_file(bucket, file_path)
                logger.info("Deleted file from storage", 
                           video_id=video_id, bucket=bucket, path=file_path)
            except Exception as e:
                logger.error("Failed to delete file from storage", 
                           video_id=video_id, bucket=bucket, path=file_path, error=str(e))
                raise HTTPException(500, f"Failed to delete file from storage: {file_path}")
        
        # Only mark as deleted in DB if storage deletion succeeded
        await mongodb_client.mark_video_as_deleted(video_id)
        
        return DeleteResponse(
            video_id=video_id,
            message="Video deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete video", video_id=video_id, error=str(e))
        raise HTTPException(500, "Failed to delete video")


@router.get("/{video_id}/download", response_model=DownloadResponse)
async def download_video(
    video_id: str,
    storage_client: StorageClient = Depends(get_storage_client),
    mongodb_client: MongoDBClient = Depends(get_mongodb_client)
) -> DownloadResponse:
    """
    Get a pre-signed download URL for a processed video.

    The URL is valid for 1 hour and points directly to the anonymised output file
    stored in the processed-videos bucket.

    Args:
        video_id: Video identifier

    Returns:
        Pre-signed download URL with expiry information
    """
    try:
        video = await mongodb_client.get_video_by_id(video_id)
        if not video:
            raise HTTPException(404, "Video not found")

        if getattr(video, 'deleted', False):
            raise HTTPException(404, "Video not found")

        if not video.processed_file_path:
            raise HTTPException(404, "Processed video not yet available")

        # processed_file_path is stored as "processed-videos/{filename}"
        # Extract the object key by stripping the bucket-prefix segment
        processed_key = video.processed_file_path
        if processed_key.startswith("processed-videos/"):
            processed_key = processed_key[len("processed-videos/"):]

        try:
            presigned_url = await asyncio.get_event_loop().run_in_executor(
                None,
                storage_client.generate_signed_url,
                processed_key,
                3600,  # 1 hour
                storage_client.config.bucket_processed
            )
        except Exception as e:
            logger.error("Failed to generate download pre-signed URL",
                         video_id=video_id, error=str(e))
            raise HTTPException(500, "Failed to generate download URL")

        return DownloadResponse(
            video_id=video_id,
            download_url=presigned_url,
            expires_in=3600
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get download URL", video_id=video_id, error=str(e))
        raise HTTPException(500, "Failed to retrieve download URL")
