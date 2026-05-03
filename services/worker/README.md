# Dashcam Worker

A high-performance video anonymization worker service that uses YOLO11 models to detect and blur objects in dashcam footage. The worker operates as a standalone microservice with RabbitMQ integration for distributed processing or can run locally for testing.

## Features

### 🎯 **Core Capabilities**
- **Multi-format Video Processing**: Supports MP4, AVI, MOV, MKV formats
- **AI-Powered Object Detection**: YOLO11 models with both bounding box and segmentation detection
- **Pixel-Perfect Anonymization**: Blur objects with rectangular regions or precise segmentation masks
- **Audio Preservation**: Original audio tracks preserved without modification
- **Metadata Preservation**: Maintains original video metadata, codec, bitrate, and quality

### ⚡ **Performance Features**
- **Multithreaded Pipeline**: 6-thread processing architecture for optimal performance
- **GPU Acceleration**: Automatic hardware detection and GPU utilization
- **Smart Frame Sampling**: Process every Nth frame with detection interpolation
- **Memory Efficient**: Configurable buffer management to handle large videos
- **Model Caching**: Local caching of AI models to avoid repeated downloads

### 🔧 **Technical Stack**
- **Video Processing**: FFmpeg for decoding/encoding with audio passthrough
- **Computer Vision**: OpenCV for frame scaling, blurring, and manipulation
- **AI Models**: YOLO11 via Ultralytics for object detection and segmentation
- **Message Queue**: RabbitMQ integration for distributed task processing
- **Storage**: S3-compatible object storage support

## Model Support

### Available Model Sizes
| Size | Model File | Size | Use Case |
|------|------------|------|----------|
| **Nano** | yolo11n.pt / yolo11n-seg.pt | 2.6MB | Ultra-lightweight, embedded devices |
| **Small** | yolo11s.pt / yolo11s-seg.pt | 9.4MB | CPU-optimized, limited GPU memory |
| **Medium** | yolo11m.pt / yolo11m-seg.pt | 20.1MB | Balanced performance |
| **Large** | yolo11l.pt / yolo11l-seg.pt | 25.3MB | High accuracy, powerful hardware |
| **XLarge** | yolo11x.pt / yolo11x-seg.pt | 56.9MB | Maximum accuracy, substantial resources |

### Detection Types
- **Bounding Box** (`bbox`): Rectangular regions around objects - faster processing
- **Segmentation** (`segmentation`): Pixel-perfect object masks - higher accuracy

## Installation

### Prerequisites
- Python 3.10+ (3.12+ recommended)
- FFmpeg (for video processing)
- CUDA-compatible GPU (optional, for acceleration)

### Setup
```bash
# Clone and navigate to project root
cd dashcam-anonymizer/

# Create shared virtual environment in project root (if not already created)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Navigate to worker directory and install dependencies
cd services/worker/
pip install -r requirements.txt

# Install worker package in development mode
pip install -e .

# Run setup script (optional, for additional configuration)
chmod +x setup.sh && ./setup.sh
```

### Testing 🧪

**IMPORTANT**: Always use the dedicated test runner for comprehensive testing:

```bash
# Run all tests (unit, integration, performance)
./run_tests.sh

# Never run pytest directly - use the test runner for proper environment setup
```

The test runner automatically:
- Uses the shared virtual environment from project root
- Sets up proper Python paths and environment variables
- Runs all test categories with detailed reporting
- Ensures all tests complete within performance requirements (<1s per unit test)

## Usage

### Local Testing Mode

Process a single video file without external dependencies:

```bash
# Basic usage
dashcam-worker --local-test \
  --input /path/to/input.mp4 \
  --output /path/to/output.mp4

# Advanced configuration
dashcam-worker --local-test \
  --input /path/to/input.mp4 \
  --output /path/to/output.mp4 \
  --yolo-classes "0,2,3,5,7" \
  --model-size medium \
  --detection-type segmentation \
  --blur-intensity 20 \
  --frame-sampling 2 \
  --processing-resolution 0.5 \
  --debug-mode
```

### Service Mode

Run as a distributed worker service:

```bash
# Set environment variables
export RABBITMQ_HOST=localhost
export RABBITMQ_PORT=5672
export STORAGE_ENDPOINT=http://localhost:9000
export GPU_ENABLED=auto

# Start worker service
dashcam-worker --service
```

### Python API

```python
from dashcam_worker.video_processor import VideoProcessor
from dashcam_worker.models import ProcessingSettings

# Initialize processor
processor = VideoProcessor(local_mode=True)

# Configure processing settings
settings = ProcessingSettings(
    yolo_classes=[0, 2, 3],  # person, car, motorcycle
    model_size="medium",
    detection_type="segmentation",
    blur_intensity=15,
    frame_sampling=1,
    processing_resolution=1.0
)

# Process video
success = processor.process_video_local(
    input_path="/path/to/input.mp4",
    output_path="/path/to/output.mp4",
    processing_settings=settings
)
```

## Configuration

### Environment Variables

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
MODEL_CACHE_DIR=./models
LOG_LEVEL=INFO
```

### COCO Class IDs

Common classes for dashcam anonymization:

```bash
# People and vehicles
--yolo-classes "0,2,3,5,7"  # person, car, motorcycle, bus, truck

# All vehicles
--yolo-classes "1,2,3,4,5,6,7,8"  # bicycle, car, motorcycle, airplane, bus, train, truck, boat

# People only
--yolo-classes "0"  # person
```

[Full COCO class reference (80 classes)](https://github.com/ultralytics/ultralytics/blob/main/ultralytics/cfg/datasets/coco.yaml)

## Architecture

### Multithreaded Processing Pipeline

```
[Input Video] → [Decoder] → [AI Thread] → [Blur Thread] → [Encoder] → [Output Video]
                     ↓           ↓            ↓              ↓
                [Frame Buffer] [Detection] [Processing] [Audio Passthrough]
                              [Interpolation] [Buffers]
```

**Thread Functions:**
- **Decoder**: FFmpeg video decoding to NumPy arrays
- **AI Thread**: YOLO11 inference on scaled frames
- **Blur Thread**: OpenCV blurring at original resolution
- **Encoder**: FFmpeg encoding with original audio/metadata preservation
- **Interpolation**: Detection tracking between sampled frames

### Key Features

- **Hybrid Processing**: FFmpeg + OpenCV + YOLO11 for optimal performance
- **Memory Management**: 30-frame buffer limit to prevent excessive RAM usage
- **Quality Preservation**: Output matches source codec, bitrate, and pixel format
- **Smart Scaling**: AI processing at reduced resolution, blurring at full resolution

## Performance

### Benchmark Results

| Resolution | Model Size | FPS (GPU) | FPS (CPU) | Memory Usage |
|------------|------------|-----------|-----------|--------------|
| 1080p | Small | ~25 FPS | ~8 FPS | 2-4 GB |
| 1080p | Medium | ~20 FPS | ~5 FPS | 3-6 GB |
| 1080p | Large | ~15 FPS | ~3 FPS | 4-8 GB |
| 4K | Small | ~8 FPS | ~2 FPS | 4-8 GB |
| 4K | Medium | ~6 FPS | ~1.5 FPS | 6-12 GB |

*Performance varies based on hardware, object density, and processing settings.*

### Optimization Tips

- **Frame Sampling**: Use `--frame-sampling 2` for 2x speed with minimal quality loss
- **Processing Resolution**: Use `--processing-resolution 0.5` for faster AI inference
- **Model Selection**: Choose the smallest model that meets your accuracy requirements
- **GPU Usage**: Ensure CUDA is properly installed for GPU acceleration

## Testing

### Run Test Suite
```bash
# All tests
./run_tests.sh

# Specific test categories
pytest tests/test_video_processor.py -v
pytest tests/test_model_manager.py -v
pytest tests/test_integration.py -v
```

### Integration Testing
```bash
# Process test video with different configurations
cd ../test-videos/
./process_video_bbox.sh      # Bounding box detection
./process_video_segmentation.sh  # Segmentation detection
```

## Health Monitoring

The worker provides a health check endpoint when running in service mode:

```bash
# Check worker health
curl http://localhost:8080/health

# Example response
{
  "status": "healthy",
  "worker_id": "worker-uuid",
  "hostname": "worker-node-01",
  "resource_usage": {
    "cpu_percent": 45,
    "memory_percent": 60,
    "gpu_percent": 80
  },
  "version": "1.0.0"
}
```

## Deployment

### Docker Container

```dockerfile
# Build container
docker build -t dashcam-worker .

# Run with GPU support
docker run --gpus all \
  -e RABBITMQ_HOST=rabbitmq \
  -e STORAGE_ENDPOINT=http://minio:9000 \
  -v ./models:/models \
  dashcam-worker

# Run CPU-only
docker run \
  -e GPU_ENABLED=false \
  -e RABBITMQ_HOST=rabbitmq \
  dashcam-worker
```

### Resource Requirements

| Worker Type | CPU | RAM | GPU | Storage |
|-------------|-----|-----|-----|---------|
| **CPU Worker** | 2+ cores | 4GB+ | None | 10GB temp |
| **GPU Worker** | 2+ cores | 8GB+ | 4GB+ VRAM | 20GB temp |
| **Production** | 4+ cores | 16GB+ | 8GB+ VRAM | 50GB temp |

## Troubleshooting

### Common Issues

**Model Download Failures:**
```bash
# Clear model cache and retry
rm -rf ./models/*
dashcam-worker --local-test --input test.mp4 --output out.mp4
```

**Memory Issues:**
```bash
# Reduce processing resolution
--processing-resolution 0.5

# Use smaller model
--model-size small

# Increase frame sampling
--frame-sampling 2
```

**GPU Not Detected:**
```bash
# Check CUDA installation
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"

# Force GPU usage
export GPU_ENABLED=true
```

### Logging

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Check logs in service mode
tail -f /var/log/dashcam-worker.log
```

## Contributing

### Development Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests before committing
./run_tests.sh

# Code formatting
black src/
isort src/

# Type checking
mypy src/
```

### Adding New Features

1. **Unit Tests**: Add tests in `tests/`
2. **Integration Tests**: Add end-to-end tests
3. **Documentation**: Update this README and docstrings
4. **Performance**: Benchmark new features

## License

MIT License - see LICENSE file for details.

## Support

- **Issues**: GitHub Issues
- **Documentation**: See `specifications/worker.md`
- **Performance**: See benchmark results in `tests/`
