# Worker Service Specification

## Overview
The worker service is a Python-based microservice responsible for processing videos using YOLO models. It operates as a standalone service that can be deployed on multiple machines (with or without GPUs) to handle video anonymization tasks.

## Core Functionality

### What the Worker Must Do
- **Video Processing**: Decode, process, and encode common video formats (MP4, AVI, MOV, MKV)
- **Audio Preservation**: Preserve original audio tracks without modification during video processing
- **AI Object Detection**: Support YOLO-based object detection models for identifying objects in video frames
- **Image Processing**: Scale, blur, and manipulate video frames
- **Message Queue Communication**: Communicate with RabbitMQ for task management and progress reporting
- **Object Storage Access**: Access S3-compatible storage for file upload/download

### Performance Requirements
- **Multithreading**: Support concurrent processing of video frames for optimal performance
- **Memory Management**: Efficiently handle large video files without excessive memory usage
- **GPU Support**: Automatically detect and utilize available GPU hardware when present
- **Model Caching**: Cache AI models locally to avoid repeated downloads

### Video Output Requirements
The output video must preserve all original video properties:
- **Resolution**: Maintain original video resolution regardless of AI processing resolution
- **Framerate**: Preserve original framerate and frame timing
- **Audio**: Copy original audio track without modification (audio passthrough)
- **Metadata**: Preserve video metadata (creation date, camera info, etc.)
- **Codec**: Preserve original codec and bitrate
- **Quality**: Apply blurring at original resolution to maintain visual quality

## Architecture and Technology Stack

### Hybrid Processing Approach
The worker should use a **hybrid processing approach** that combines the strengths of multiple video processing technologies:
- **Video Codec Operations**: Use FFmpeg or similar tools for video decoding/encoding and audio passthrough for maximum compatibility and performance
- **Computer Vision Processing**: Use OpenCV or equivalent libraries for frame scaling, blurring, and image manipulation with optimized algorithms
- **Efficient Data Handling**: Use NumPy or similar array processing libraries for seamless data transfer between video processing components

This hybrid approach ensures optimal performance, maintains video quality, and preserves audio/metadata while providing the flexibility needed for various video formats and processing requirements.

### Recommended Technology Stack
- **Language**: Python 3.12+
- **Video Processing**: FFmpeg (via ffmpeg-python or similar) for video decode/encode and audio preservation
- **AI Object Detection**: YOLO models (YOLO12 for detection, YOLO11 for segmentation via Ultralytics or equivalent) for object detection with support for both bounding box and segmentation models
- **Image Processing**: OpenCV for frame scaling, blurring, and manipulation
- **Array Operations**: NumPy for efficient data transfer between processing components
- **Message Queue Integration**: Pika or equivalent for RabbitMQ communication
- **Object Storage Access**: boto3 or equivalent for S3-compatible storage operations
- **Parallel Processing**: Threading or asyncio for multithreaded video processing pipeline

### Hardware Detection and Model Loading
- **Hardware Detection**: Automatically detect available hardware and announce capabilities
- **Model Sizes**: YOLO12 (detection) and YOLO11 (segmentation) support multiple model sizes for different performance requirements
- **Model Types**: Support for both detection types:
  - **Bounding Box Models**: Standard object detection with rectangular bounding boxes (yolo12n.pt, yolo12s.pt, yolo12m.pt, yolo12l.pt, yolo12x.pt)
  - **Segmentation Models**: Pixel-perfect object segmentation masks (yolo11n-seg.pt, yolo11s-seg.pt, yolo11m-seg.pt, yolo11l-seg.pt, yolo11x-seg.pt)
- **Model Management**: Download and cache AI models based on task requirements locally to ./models directory

### Detection Types and Model Selection
The worker supports two types of object detection models, each with different accuracy and performance characteristics:

#### Bounding Box Detection (`detection_type: "bbox"`)
- **Models**: yolo12n.pt, yolo12s.pt, yolo12m.pt, yolo12l.pt, yolo12x.pt
- **Output**: Rectangular bounding boxes around detected objects
- **Performance**: Faster processing, lower memory usage
- **Use Case**: General object detection where approximate object boundaries are sufficient
- **Blur Application**: Applies blur to the entire rectangular region around detected objects

#### Segmentation Detection (`detection_type: "segmentation"`)
- **Models**: yolo11n-seg.pt, yolo11s-seg.pt, yolo11m-seg.pt, yolo11l-seg.pt, yolo11x-seg.pt
- **Output**: Pixel-perfect segmentation masks outlining the exact shape of detected objects
- **Performance**: Slower processing, higher memory usage, more accurate
- **Use Case**: High-precision anonymization where only the exact object pixels should be blurred
- **Blur Application**: Applies blur only to the pixels identified as part of the detected object

The model selection combines both the size (nano/small/medium/large/xlarge) and type (bbox/segmentation) to determine which specific YOLO12 (detection) or YOLO11 (segmentation) model file to download and use for inference.

## Configuration

### Environment Variables
The worker must support the following environment variables:
```bash
# Message Queue Configuration
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Storage Configuration
STORAGE_TYPE=minio  # or 'r2'
STORAGE_ENDPOINT=http://localhost:9000
STORAGE_ACCESS_KEY=minioadmin
STORAGE_SECRET_KEY=minioadmin
STORAGE_BUCKET_RAW=raw-videos
STORAGE_BUCKET_PROCESSED=processed-videos

# Processing Configuration
GPU_ENABLED=auto  # 'true', 'false', or 'auto'
MODEL_CACHE_DIR=/models  # or configurable path
LOG_LEVEL=INFO
WORKER_ID=worker-uuid  # Worker identifier (auto-generated UUID if not provided)
```

### COCO Dataset Class Reference
For reference, here are all COCO class IDs that can be used in `yolo_classes`:
```
0: person, 1: bicycle, 2: car, 3: motorcycle, 4: airplane, 5: bus, 6: train, 7: truck, 8: boat, 9: traffic light,
10: fire hydrant, 11: stop sign, 12: parking meter, 13: bench, 14: bird, 15: cat, 16: dog, 17: horse, 18: sheep, 19: cow,
20: elephant, 21: bear, 22: zebra, 23: giraffe, 24: backpack, 25: umbrella, 26: handbag, 27: tie, 28: suitcase, 29: frisbee,
30: skis, 31: snowboard, 32: sports ball, 33: kite, 34: baseball bat, 35: baseball glove, 36: skateboard, 37: surfboard, 38: tennis racket, 39: bottle,
40: wine glass, 41: cup, 42: fork, 43: knife, 44: spoon, 45: bowl, 46: banana, 47: apple, 48: sandwich, 49: orange,
50: broccoli, 51: carrot, 52: hot dog, 53: pizza, 54: donut, 55: cake, 56: chair, 57: couch, 58: potted plant, 59: bed,
60: dining table, 61: toilet, 62: tv, 63: laptop, 64: mouse, 65: remote, 66: keyboard, 67: cell phone, 68: microwave, 69: oven,
70: toaster, 71: sink, 72: refrigerator, 73: book, 74: clock, 75: vase, 76: scissors, 77: teddy bear, 78: hair drier, 79: toothbrush
```

## Task Processing Workflow

### Task Message Format
The worker receives task assignments from the backend via its individual RabbitMQ queue (`worker_assignments_{worker_id}`) with the following JSON structure:
```json
{
  "task_id": "uuid-string",
  "video_id": "uuid-string",
  "user_id": "user-uuid",
  "input_file_path": "raw-videos/user-uuid/video-uuid.mp4",
  "output_file_path": "processed-videos/user-uuid/video-uuid/task-uuid/output.mp4",
  "processing_settings": {
    "yolo_classes": [0, 2, 3, 5, 7],  // COCO class IDs to blur: 0=person, 2=car, 3=motorcycle, 5=bus, 7=truck
    "model_size": "medium",  # "nano", "small", "medium", "large", "xlarge"
    "detection_type": "bbox",  # "bbox" or "segmentation"
    "debug_mode": false,
    "blur_intensity": 15,
    "frame_sampling": 1,  # Process every Nth frame (1=all frames, 2=every 2nd, up to 10=every 10th)
    "processing_resolution": 1.0,  # AI processing resolution scale (1.0=full, 0.5=half, 0.25=quarter)
    "enable_hood_detection": false,  # Enable simple hood detection filtering
    # Temporal stability settings
    "temporal_stability_enabled": true,  # Enable temporal stability for smooth blurring
    "temporal_stability_max_gap": 10,  # Maximum frames to interpolate missing tracks
    "temporal_stability_confidence_threshold": 0.4,  # Minimum confidence for interpolation
    "temporal_stability_spatial_threshold": 100.0,  # Maximum pixel distance for spatial matching
    "temporal_stability_max_velocity_change": 50.0,  # Maximum velocity change per frame
    "temporal_stability_max_spatial_drift": 150.0,  # Maximum spatial drift for interpolation
    "temporal_stability_class_consistency": false,  # Only interpolate within same class
    "temporal_stability_duplicate_merge_threshold": 0.1,  # IoU threshold for duplicate detection merging
    # Blur flickering prevention settings
    "blur_minimum_track_duration": 8,  # Minimum frames before applying blur to prevent flickering
    "blur_duration_filtering_enabled": true,  # Enable/disable short-track filtering
    "blur_large_object_threshold": 0.15,  # Objects larger than 15% of frame bypass duration filter
    # Blur size filtering settings
    "blur_minimum_object_height_ratio": 0.03,  # Minimum object height as ratio of frame height (3%)
    "blur_size_filtering_enabled": true,  # Enable/disable minimum size filtering for blur
    # Size-dependent blur settings
    "blur_size_scaling_enabled": true,  # Enable/disable size-dependent blur intensity
    "blur_size_scaling_max_height_ratio": 0.10,  # Height ratio for full blur intensity (10% of frame height)
    # Debug visualization settings
    "debug_show_trajectories": true,  # Show object movement trajectories in debug mode
    "debug_trajectory_length": 30,  # Maximum trajectory points to display
    "debug_trajectory_fade": true  # Fade older trajectory points
  },
  "created_at": "2025-01-15T10:30:00Z"
}
```

### Processing Steps
1. **Task Assignment Reception**: Receive task assignment from backend via individual worker queue
2. **Task Acknowledgment**: Acknowledge the assignment and update status to "busy"
3. **File Download**: Download video file from storage using the input_file_path
4. **Model Loading**: Load appropriate YOLO model based on processing_settings
5. **Video Processing**: Process video frame by frame using hybrid pipeline
6. **Progress Updates**: Send progress updates every 10% completion to backend
7. **File Upload**: Upload processed video to storage
8. **Task Completion**: Send completion message and update status back to "ready"

### Frame Processing Steps
1. **Frame Sampling**: Process only every Nth frame based on `frame_sampling` setting (1-10)
2. **Resolution Scaling**: Scale frames for AI processing based on `processing_resolution` (1.0, 0.5, or 0.25)
3. **YOLO Inference**: Run YOLO model inference on the scaled frames
4. **Detection Filtering**: Filter detections by configured YOLO classes
5. **Detection Upscaling**: Scale detection coordinates back to original resolution
6. **Object Tracking**: Assign track IDs and maintain object histories for interpolation and hood filtering
7. **Detection Interpolation**: For skipped frames, interpolate detections between processed frames
8. **Hood Detection Filtering**: Remove stationary large objects in bottom frame region (vehicle's own hood)
9. **Blur Application**: Apply blurring to all frames at original resolution based on detection type
10. **Debug Annotations**: Add debug annotations if enabled in settings

### Multithreaded Processing Pipeline
The worker should implement a multithreaded processing pipeline using the recommended technology stack for optimal performance:

#### Threading Architecture:
- **Decoder Thread**: Use FFmpeg to continuously decode frames from input video into NumPy arrays
- **Scaler Thread**: Use OpenCV to scale NumPy arrays to AI processing resolution as needed
- **AI Thread**: Run YOLO inference on scaled frames from OpenCV
- **Tracking Thread**: Manage object tracking, assign track IDs, and perform hood detection filtering
- **Interpolation Thread**: Use NumPy for efficient detection position calculations on skipped frames
- **Blur Thread**: Use OpenCV to apply blurring to frames at original resolution based on detections
- **Encoder Thread**: Use FFmpeg to encode processed frames while preserving original audio and metadata
- **Buffer Management**: Maintain NumPy array buffers between threads (max 30 frames per buffer to prevent excessive RAM usage)

#### Data Flow Design:
1. **FFmpeg → NumPy**: Video frames decoded directly into NumPy arrays for memory efficiency
2. **NumPy → OpenCV**: Arrays passed to OpenCV for scaling and blurring operations
3. **OpenCV → NumPy**: Processed frames returned as NumPy arrays
4. **NumPy → YOLO**: AI inference performed on NumPy arrays
5. **YOLO → Tracker**: Detection results passed to object tracking system
6. **Tracker → NumPy**: Filtered detections (excluding hood) with track IDs
7. **NumPy ↔ NumPy**: Detection interpolation using efficient NumPy array operations
8. **NumPy → FFmpeg**: Final frames encoded with original audio stream preservation

This design minimizes memory copies and maximizes processing throughput while maintaining video quality.

### Detection Interpolation Algorithm
When `frame_sampling` > 1, the worker must interpolate object positions for frames that were not processed:
- **Object Tracking**: Match detected objects between processed frames based on position and class
- **Position Interpolation**: Calculate intermediate positions using linear interpolation
- **Bounding Box Scaling**: Interpolate bounding box dimensions between keyframes
- **Confidence Decay**: Apply confidence decay for interpolated detections (optional)

### Object Tracking and Hood Detection Filtering
The worker must implement object tracking to solve common dashcam processing issues:

#### Object Tracking System
- **YOLO Built-in Tracking**: Use YOLO's built-in tracking capabilities (ByteTrack, BoT-SORT) for both bbox and segmentation models
- **Tracking Algorithm Selection**: YOLO automatically selects the best tracking algorithm (ByteTrack is default, BoT-SORT for higher accuracy)
- **Track Identification**: YOLO automatically assigns unique track IDs to detected objects and maintains them across frames
- **Track Persistence**: YOLO tracking handles object matching, interpolation, and lifecycle management automatically
- **Track History**: Maintain track history for each object (position, size, class, track_id) for hood detection analysis
- **Cross-frame Consistency**: YOLO tracking provides robust object matching across frames, handling occlusions and temporary disappearances
- **Implementation**: Use `model.track()` method instead of `model.predict()` to enable tracking with minimal code changes

#### Hood Detection Filtering
Dashcam footage often includes the vehicle's own hood, which should not be anonymized:
- **Track-based Analysis**: Use YOLO track IDs to analyze object behavior over time for hood detection
- **Temporal Consistency Analysis**: Identify tracked objects that remain stationary in the same position across multiple frames
- **Position-based Filtering**: Focus on tracked objects detected in the bottom portion of the frame (configurable threshold)
- **Size-based Filtering**: Consider tracked objects that are unusually large relative to the frame size
- **Hood Detection Logic**: Filter out car-class detections with consistent track IDs that meet all criteria:
  - Same track ID stationary for 5+ consecutive frames
  - Located in bottom 30% of frame (configurable)
  - Width > 40% of frame width OR height > 30% of frame height (configurable)
- **Smart Filtering**: Ensure legitimate vehicles in the scene are not excluded by leveraging track ID persistence and movement patterns

#### Technical Implementation Notes
**YOLO Tracking Integration:**
- Replace `model.predict(frame)` calls with `model.track(frame)` in the video processing pipeline
- Track results include both detection data and track IDs in the same format as standard predictions
- Track IDs are automatically assigned and maintained by YOLO across frames
- For segmentation models, masks are returned alongside track IDs (track IDs are assigned to bounding boxes)
- Tracking state is maintained internally by YOLO - no external state management required

**Hood Detection Implementation:**
- Store track history dictionary: `{track_id: [(frame_num, bbox, class), ...]}`
- Analyze track consistency for car-class objects in the bottom frame region
- Filter detections before applying blur based on hood detection criteria
- Preserve track ID information in processing results for debugging and analysis

**Processing Pipeline Changes:**
1. Initialize YOLO model with tracking enabled (automatically handled by `.track()` method)
2. Process frames with `results = model.track(frame)` instead of `model.predict(frame)`
3. Extract track IDs from results: `track_id = result.boxes.id` (for both bbox and segmentation)
4. Store track history and apply hood detection filtering logic
5. Continue with existing blur and encoding pipeline using filtered detections
```

## Communication Protocols

### Task Assignment Workflow
The worker operates in a **push-based assignment model** where the backend intelligently assigns tasks:

1. **Worker Registration**: Worker announces capabilities on startup
2. **Capability-Based Assignment**: Backend assigns tasks based on worker capabilities, current load, and task priority
3. **Individual Queues**: Each worker listens to its own assignment queue (`worker_assignments_{worker_id}`)
4. **Status Updates**: Workers continuously update their status via heartbeat messages
5. **Smart Routing**: Backend routes tasks to the most suitable available worker

This design ensures optimal resource utilization and prevents task conflicts between workers.

### RabbitMQ Queue Configuration
- **Worker Assignment Queue**: `worker_assignments_{worker_id}` (individual queues per worker)
- **Worker Registration Queue**: `worker_registration` (workers announce capabilities)
- **Worker Heartbeat Queue**: `worker_heartbeat` (workers send status updates)
- **Progress Queue**: `processing_progress` (workers send progress updates)
- **Completion Queue**: `processing_complete` (workers send completion notifications)
- **Error Queue**: `processing_errors` (workers send error notifications)

### Message Formats

#### Worker Registration Message
When a worker starts up, it must register with the backend by publishing its capabilities to the `worker_registration` queue:
```json
{
  "worker_id": "worker-uuid",
  "hostname": "worker-node-01",
  "capabilities": {
    "compute_device": "cuda",  // "cuda", "mps", "cpu"
    "gpu_memory_gb": 8,
    "system_memory_gb": 16,
    "max_model_size": "large",  // "nano", "small", "medium", "large", "xlarge"
    "supported_formats": ["mp4", "avi", "mov", "mkv"]
  },
  "status": "ready",  // "ready", "busy", "offline"
  "timestamp": "2025-01-15T10:30:00Z"
}
```

#### Worker Heartbeat
Workers must send heartbeat messages every 30 seconds to the `worker_heartbeat` queue:
```json
{
  "worker_id": "worker-uuid",
  "status": "ready",  // "ready", "busy", "offline"
  "current_task_id": null,  // or task UUID if processing
  "resource_usage": {
    "cpu_percent": 45,
    "memory_percent": 60,
    "gpu_percent": 80  // null if no GPU
  },
  "timestamp": "2025-01-15T10:35:00Z"
}
```

#### Progress Updates
```json
{
  "task_id": "uuid-string",
  "video_id": "uuid-string",
  "progress_percentage": 45,
  "current_frame": 1350,
  "total_frames": 3000,
  "estimated_time_remaining": 120,  // seconds
  "timestamp": "2025-01-15T10:35:00Z"
}
```

#### Completion Message
```json
{
  "task_id": "uuid-string",
  "video_id": "uuid-string",
  "status": "completed",  // "completed", "failed", "cancelled"
  "output_file_path": "processed-videos/user-uuid/video-uuid/task-uuid/output.mp4",
  "processing_time": 300,  // seconds
  "total_frames": 3000,
  "objects_detected": 45,
  "timestamp": "2025-01-15T10:40:00Z",
  "error_message": null  // only if status is "failed"
}
```

## Error Handling and Fault Tolerance

### Progress Tracking
- Report processing progress via RabbitMQ progress messages every 5 seconds
- Include: task_id, current_frame, processed_frames_count, timestamp
- Progress is stateless - no persistent storage needed

### Error Recovery
1. **Network Errors**: Retry download/upload operations up to 3 times with exponential backoff
2. **Processing Errors**: Log error details and send failure message to error queue
3. **Memory Errors**: Reduce batch size and retry processing
4. **Model Loading Errors**: Fall back to smaller model if available

### Monitoring and Logging
Required log events:
- Worker startup/shutdown
- Task start/completion
- Progress milestones (every 25%)
- Error occurrences
- Resource usage (CPU/GPU/Memory)

## Local Testing Mode

### Standalone Processing Function
The worker must provide a local testing mode that operates independently of external services:

**Command Interface:**
```bash
# Local testing command interface
worker --local-test \
  --input [input_video_path] \
  --output [output_video_path] \
  --yolo-classes [comma_separated_class_ids] \
  --model-size [nano|small|medium|large|xlarge] \
  --detection-type [bbox|segmentation] \
  --blur-intensity [blur_strength] \
  --frame-sampling [sampling_rate] \
  --processing-resolution [resolution_scale] \
  --enable-hood-detection \
  --blur-minimum-track-duration [minimum_frames] \
  --blur-large-object-threshold [threshold_ratio] \
  --no-blur-duration-filtering \
  --debug-mode \
  --debug-show-trajectories \
  --debug-trajectory-length [max_points] \
  --debug-trajectory-fade
```

### Local Test Configuration
When running in local test mode, the worker must:
- Operate without external service dependencies (RabbitMQ)
- Cache or download AI models as needed
- Process video files using the complete processing pipeline
- Provide console-based progress reporting
- Generate processing statistics report

### Local Test Output
```json
{
  "input_file": "/path/to/input.mp4",
  "output_file": "/path/to/output.mp4",
  "processing_time": 120.5,
  "total_frames": 1800,
  "processed_frames": 900,
  "objects_detected": 245,
  "audio_preserved": true,
  "original_resolution": "1920x1080",
  "processing_resolution": "960x540",
  "settings_used": {
    "yolo_classes": [0, 2, 3, 5, 7],
    "model_size": "medium",
    "detection_type": "bbox",
    "frame_sampling": 2,
    "processing_resolution": 0.5,
    "enable_hood_detection": false,
    "temporal_stability_enabled": true,
    "blur_minimum_track_duration": 8,
    "blur_duration_filtering_enabled": true,
    "blur_large_object_threshold": 0.15
  }
}
```

## Testing Requirements

### Unit Tests
- Frame processing functions (scaling and blurring operations)
- YOLO model loading and inference capabilities
- Video decode/encode operations
- Storage upload/download operations
- Message parsing and validation
- Data transfer operations between processing components

### Integration Tests
- End-to-end task processing with complete video pipeline
- RabbitMQ message handling
- Progress reporting via RabbitMQ
- Error recovery scenarios
- Audio passthrough verification

### Performance Tests
- Processing speed benchmarks for different model sizes
- Memory usage profiling with multithreaded processing
- Audio passthrough quality verification

## Deployment and Scaling

### Container Deployment
The worker must be deployable as a Docker container with the following specifications:

#### Container Specifications
- **Runtime Environment**: Python 3.12+ compatible environment
- **Application Directory**: Consistent application structure
- **Model Storage**: Dedicated directory for AI model caching
- **Health Check**: Health monitoring endpoint on port 8080
- **Service Interface**: Standard application entry point

### Horizontal Scaling
- Each worker instance should be stateless
- Workers wait for task assignments from the backend based on their capabilities and priority
- The backend intelligently assigns tasks to the most suitable available workers
- Scale by increasing the number of worker containers
- No coordination required between workers (assignment handled by backend)

### Resource Requirements
- **CPU Worker**: 2 CPU cores, 4GB RAM minimum
- **GPU Worker**: 1 GPU, 4GB GPU memory, 8GB RAM minimum
- **Storage**: Temporary space for 2x largest expected video file size
