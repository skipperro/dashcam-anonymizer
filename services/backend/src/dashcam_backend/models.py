"""Data models for the dashcam backend service."""

from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Dict, Any, List, Optional, Union
from enum import Enum
import uuid


class TaskStatus(str, Enum):
    """Task processing status."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkerStatus(str, Enum):
    """Worker status."""
    READY = "ready"
    BUSY = "busy"
    OFFLINE = "offline"
    ERROR = "error"


class VideoStatus(str, Enum):
    """Video processing status."""
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    PROCESSED = "processed"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadStatus(str, Enum):
    """Upload status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ChunkStatus(str, Enum):
    """Chunk upload status."""
    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"


# Message Models for RabbitMQ Communication

@dataclass
class ProcessingSettings:
    """Video processing configuration."""
    yolo_classes: List[int]  # COCO class IDs to blur
    model_size: str = "small"  # "small", "medium", "large"
    detection_type: str = "bbox"  # "bbox" or "segmentation"
    debug_mode: bool = False
    blur_intensity: int = 15
    frame_sampling: int = 1  # Process every Nth frame (1-10)
    processing_resolution: float = 1.0  # AI processing resolution scale
    # Hood detection settings
    enable_hood_detection: bool = False  # Enable simple hood detection filtering
    # Temporal stability settings
    temporal_stability_enabled: bool = True  # Enable temporal stability for smooth blurring
    temporal_stability_max_gap: int = 10  # Maximum frames to interpolate missing tracks
    temporal_stability_confidence_threshold: float = 0.4  # Minimum confidence for interpolation
    temporal_stability_spatial_threshold: float = 100.0  # Maximum pixel distance for spatial matching
    temporal_stability_max_velocity_change: float = 50.0  # Maximum velocity change per frame
    temporal_stability_max_spatial_drift: float = 150.0  # Maximum spatial drift for interpolation
    temporal_stability_class_consistency: bool = False  # Only interpolate within same class
    temporal_stability_duplicate_merge_threshold: float = 0.1  # IoU threshold for duplicate detection merging
    # Blur flickering prevention settings
    blur_minimum_track_duration: int = 8  # Minimum frames before applying blur to prevent flickering
    blur_duration_filtering_enabled: bool = True  # Enable/disable short-track filtering
    blur_large_object_threshold: float = 0.15  # Objects larger than 15% of frame bypass duration filter
    # Blur size filtering settings
    blur_minimum_object_height_ratio: float = 0.03  # Minimum object height as ratio of frame height (5%)
    blur_size_filtering_enabled: bool = True  # Enable/disable minimum size filtering for blur
    # Size-dependent blur settings
    blur_size_scaling_enabled: bool = True  # Enable/disable size-dependent blur intensity
    blur_size_scaling_max_height_ratio: float = 0.10  # Height ratio for full blur intensity (10% of frame height)
    # Debug visualization settings
    debug_show_trajectories: bool = True  # Show object movement trajectories in debug mode
    debug_trajectory_length: int = 30  # Maximum trajectory points to display
    debug_trajectory_fade: bool = True  # Fade older trajectory points


@dataclass
class TaskMessage:
    """Task assignment message sent to workers."""
    task_id: str
    video_id: str
    user_id: str
    input_file_path: str
    output_file_path: str
    processing_settings: ProcessingSettings
    created_at: str


@dataclass
class WorkerCapabilities:
    """Worker hardware capabilities."""
    compute_device: str  # cuda, cpu
    gpu_memory_gb: Optional[int] = None
    system_memory_gb: int = 8
    max_model_size: str = "medium"  # small, medium, large, xlarge
    supported_formats: List[str] = None
    
    def __post_init__(self):
        if self.supported_formats is None:
            self.supported_formats = ["mp4", "avi", "mov", "mkv"]


@dataclass
class ResourceUsage:
    """Current worker resource usage."""
    cpu_percent: float
    memory_percent: float
    gpu_percent: Optional[float] = None


@dataclass
class WorkerRegistrationMessage:
    """Worker registration message."""
    worker_id: str
    hostname: str
    capabilities: WorkerCapabilities
    status: str
    timestamp: str
    message_type: str = "worker_registration"


@dataclass
class WorkerHeartbeatMessage:
    """Worker heartbeat message."""
    worker_id: str
    status: str
    resource_usage: ResourceUsage
    timestamp: str
    current_task_id: Optional[str] = None
    message_type: str = "worker_heartbeat"


@dataclass
class ProgressUpdateMessage:
    """Progress update from worker."""
    task_id: str
    video_id: str
    progress_percentage: int
    current_frame: int
    total_frames: int
    fps: float  # frames per second processing rate
    estimated_time_remaining: int  # seconds
    timestamp: str
    message_type: str = "processing_progress"


@dataclass
class CompletionMessage:
    """Task completion message from worker."""
    task_id: str
    video_id: str
    status: str  # "completed", "failed", "cancelled"
    output_file_path: Optional[str]
    processing_time: float  # seconds
    total_frames: int
    objects_detected: int
    timestamp: str
    error_message: Optional[str] = None
    message_type: str = "processing_complete"


# Frontend Communication Messages

@dataclass
class VideoListRequest:
    """Video list request from frontend."""
    session_id: str
    user_id: str
    page: int = 1
    per_page: int = 10
    message_type: str = "list_videos"


@dataclass
class VideoInfo:
    """Video information for frontend."""
    video_id: str
    filename: str
    upload_date: str
    status: str
    upload_progress: float
    processing_progress: float
    file_size: int
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None


@dataclass
class VideoListResponse:
    """Video list response to frontend."""
    videos: List[VideoInfo]
    total: int
    page: int
    per_page: int
    message_type: str = "video_list_response"


# Upload Service Communication Messages

@dataclass
class UploadProgressMessage:
    """Upload progress update from upload service."""
    video_id: str
    progress_percentage: float
    bytes_uploaded: int
    total_bytes: int
    timestamp: str
    message_type: str = "upload_progress"


@dataclass
class UploadCompletionMessage:
    """Upload completion notification from upload service."""
    video_id: str
    file_size: int
    format: str
    temp_file_path: str
    upload_time: float
    timestamp: str
    message_type: str = "upload_completed"
    duration_seconds: Optional[int] = None
    resolution: Optional[str] = None
    thumbnail_path: Optional[str] = None


# Database Document Models

@dataclass
class UploadSessionDocument:
    """Upload session document in MongoDB for chunked uploads."""
    session_id: str
    video_id: str
    user_id: str
    filename: str
    total_size: int
    chunk_size: int
    total_chunks: int
    uploaded_chunks: List[int]  # List of successfully uploaded chunk numbers
    multipart_upload_id: Optional[str] = None  # S3 multipart upload ID
    storage_key: str = ""  # S3 key for the file
    status: str = UploadStatus.PENDING
    created_at: datetime = None
    expires_at: datetime = None
    completed_at: Optional[datetime] = None
    last_chunk_uploaded_at: Optional[datetime] = None
    parts: Dict[str, Dict[str, Any]] = None  # S3 multipart upload parts {chunk_number: {ETag, PartNumber}}
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)
        if self.expires_at is None:
            # Sessions expire after 24 hours
            self.expires_at = datetime.now(UTC).replace(hour=23, minute=59, second=59, microsecond=999999)
        if self.parts is None:
            self.parts = {}


@dataclass
class UserDocument:
    """User document in MongoDB."""
    user_id: str
    email: str
    password_hash: Optional[str] = None
    google_id: Optional[str] = None
    credits: float = 0.0
    subscription_tier: str = "free"
    created_at: datetime = None
    last_login: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)


@dataclass
class VideoDocument:
    """Video document in MongoDB."""
    video_id: str
    user_id: str
    filename: str
    file_size: int
    duration_seconds: Optional[int] = None
    resolution: Optional[str] = None
    format: str = ""
    upload_date: datetime = None
    status: str = VideoStatus.UPLOADING
    upload_status: str = UploadStatus.PENDING
    upload_progress: float = 0.0
    bytes_uploaded: Optional[int] = None  # Bytes uploaded so far during upload
    upload_started_at: Optional[datetime] = None
    upload_completed_at: Optional[datetime] = None
    upload_expires_at: Optional[datetime] = None
    upload_session_id: Optional[str] = None  # Link to upload session for chunked uploads
    chunks_uploaded: List[int] = None  # List of uploaded chunks
    total_chunks: Optional[int] = None  # Total number of chunks
    raw_file_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    thumbnail_available: bool = False
    processed_file_path: Optional[str] = None  # Link to latest processed version
    deleted: bool = False  # Soft delete flag
    
    def __post_init__(self):
        if self.upload_date is None:
            self.upload_date = datetime.now(UTC)
        if self.chunks_uploaded is None:
            self.chunks_uploaded = []


@dataclass
class TaskDocument:
    """Task document in MongoDB."""
    task_id: str
    video_id: str
    user_id: str
    worker_id: Optional[str] = None
    status: str = TaskStatus.PENDING
    progress_percentage: float = 0.0
    current_frame: int = 0
    total_frames: int = 0
    fps: Optional[float] = None  # frames per second processing rate
    estimated_time_remaining: Optional[int] = None
    created_at: datetime = None
    started_at: Optional[datetime] = None
    last_updated: datetime = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    priority: int = 0
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)
        if self.last_updated is None:
            self.last_updated = datetime.now(UTC)


@dataclass
class ProcessingTaskDocument:
    """Processing task document in MongoDB - separate from video upload."""
    processing_task_id: str
    video_id: str
    user_id: str
    worker_id: Optional[str] = None
    status: str = TaskStatus.PENDING
    progress_percentage: float = 0.0
    processing_settings: ProcessingSettings = None
    processed_file_path: Optional[str] = None
    processing_stats: Optional[Dict[str, Any]] = None
    created_at: datetime = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(UTC)
        if self.processing_settings is None:
            self.processing_settings = ProcessingSettings()


@dataclass
class WorkerDocument:
    """Worker document in MongoDB."""
    worker_id: str
    hostname: str
    status: str = WorkerStatus.OFFLINE
    capabilities: WorkerCapabilities = None
    current_task_id: Optional[str] = None
    resource_usage: Optional[ResourceUsage] = None
    registered_at: datetime = None
    last_heartbeat: Optional[datetime] = None
    
    def __post_init__(self):
        if self.registered_at is None:
            self.registered_at = datetime.now(UTC)
        if self.capabilities is None:
            self.capabilities = WorkerCapabilities(compute_device="cpu")


# Utility functions for message handling

def generate_task_id() -> str:
    """Generate a unique task ID."""
    return str(uuid.uuid4())


def generate_video_id() -> str:
    """Generate a unique video ID."""
    return str(uuid.uuid4())


def generate_user_id() -> str:
    """Generate a unique user ID."""
    return str(uuid.uuid4())


def get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def serialize_message(message: Any) -> str:
    """Serialize a message to JSON string."""
    import json
    from dataclasses import asdict
    
    if hasattr(message, '__dict__'):
        data = asdict(message) if hasattr(message, '__dataclass_fields__') else message.__dict__
    else:
        data = message
    
    return json.dumps(data, default=str)


def deserialize_message(message_str: str, message_class: type) -> Any:
    """Deserialize a JSON string to a message object."""
    import json
    
    data = json.loads(message_str)
    
    # Handle dataclass deserialization
    if hasattr(message_class, '__dataclass_fields__'):
        return message_class(**data)
    else:
        return message_class(data)
