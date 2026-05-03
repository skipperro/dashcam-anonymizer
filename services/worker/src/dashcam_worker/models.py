"""
Message models for RabbitMQ communication.

Defines the data structures for task messages, progress updates, and worker communication
as specified in the worker specification.
"""

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, UTC
import json


@dataclass
class ProcessingSettings:
    """Processing settings for video task."""
    yolo_classes: List[int]  # COCO class IDs to blur
    model_size: str  # "small", "medium", "large"
    detection_type: str  # "bbox" or "segmentation"
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
    # NOTE: No encoding parameters - codec, quality, and bitrate are automatically preserved from source


@dataclass
class TaskMessage:
    """Task assignment message from backend."""
    task_id: str
    video_id: str
    user_id: str
    input_file_path: str
    output_file_path: str
    processing_settings: ProcessingSettings
    created_at: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskMessage':
        """Create TaskMessage from dictionary."""
        settings = ProcessingSettings(**data['processing_settings'])
        return cls(
            task_id=data['task_id'],
            video_id=data['video_id'],
            user_id=data['user_id'],
            input_file_path=data['input_file_path'],
            output_file_path=data['output_file_path'],
            processing_settings=settings,
            created_at=data['created_at']
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert TaskMessage to dictionary."""
        return asdict(self)


@dataclass
class WorkerCapabilities:
    """Worker hardware capabilities."""
    compute_device: str  # "cuda", "mps", "cpu"
    gpu_memory_gb: Optional[int] = None
    system_memory_gb: int = 16
    max_model_size: str = "large"  # "small", "medium", "large"
    supported_formats: List[str] = None

    def __post_init__(self):
        if self.supported_formats is None:
            self.supported_formats = ["mp4", "avi", "mov", "mkv"]


@dataclass
class ResourceUsage:
    """Current resource usage statistics."""
    cpu_percent: float
    memory_percent: float
    gpu_percent: Optional[float] = None


@dataclass
class WorkerRegistrationMessage:
    """Worker registration message."""
    worker_id: str
    hostname: str
    capabilities: WorkerCapabilities
    status: str  # "ready", "busy", "offline"
    timestamp: str
    message_type: str = "worker_registration"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "message_type": self.message_type,
            "worker_id": self.worker_id,
            "hostname": self.hostname,
            "capabilities": asdict(self.capabilities),
            "status": self.status,
            "timestamp": self.timestamp
        }


@dataclass
class WorkerHeartbeatMessage:
    """Worker heartbeat message."""
    worker_id: str
    status: str  # "ready", "busy", "offline"
    current_task_id: Optional[str]
    resource_usage: ResourceUsage
    timestamp: str
    message_type: str = "worker_heartbeat"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "message_type": self.message_type,
            "worker_id": self.worker_id,
            "status": self.status,
            "current_task_id": self.current_task_id,
            "resource_usage": asdict(self.resource_usage),
            "timestamp": self.timestamp
        }


@dataclass
class ProgressUpdateMessage:
    """Progress update message."""
    task_id: str
    video_id: str
    progress_percentage: int
    current_frame: int
    total_frames: int
    fps: float  # frames per second processing rate
    estimated_time_remaining: int  # seconds
    timestamp: str
    message_type: str = "processing_progress"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result["message_type"] = self.message_type
        return result


@dataclass
class CompletionMessage:
    """Task completion message."""
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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result["message_type"] = self.message_type
        return result


def serialize_message(message: Union[WorkerRegistrationMessage, WorkerHeartbeatMessage, 
                                   ProgressUpdateMessage, CompletionMessage]) -> str:
    """Serialize message to JSON string."""
    return json.dumps(message.to_dict())


def get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
