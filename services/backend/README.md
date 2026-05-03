# Dashcam Backend Service

The backend service is the central orchestrator for the Dashcam Anonymizer system, responsible for coordinating video processing tasks with workers, tracking progress, and handling user authentication.

## Architecture

This backend implements a **message-driven microservice architecture** using:
- **RabbitMQ** for all inter-service communication
- **MongoDB** for data persistence
- **S3-compatible storage** (MinIO/Cloudflare R2) for file management
- **Async/await** for high-performance message processing

## Features

### Core Functionality
- **Direct Video Upload**: Handle video uploads through the REST API
- **Task Orchestration**: Create and assign video processing tasks to workers
- **Worker Coordination**: Manage worker registration, heartbeat monitoring, and intelligent task assignment
- **Progress Tracking**: Real-time progress updates from workers and upload service
- **File Management**: Coordinate download operations and manage signed URLs

### Message-Driven Communication
- **Frontend Communication**: Upload requests, authentication, data queries via message queues
- **Upload Service Communication**: Token validation, upload completion notifications
- **Worker Communication**: Task assignment, progress reporting, worker coordination
- **Real-time Updates**: Progress broadcasts to frontend via message queues

## Quick Start

### Prerequisites
- Python 3.12+
- MongoDB running on localhost:27017
- RabbitMQ running on localhost:5672
- MinIO running on localhost:9000

### Installation
```bash
# Install dependencies
pip install -e .

# Or run the test script which sets up everything
./run_tests.sh
```

### Running the Service
```bash
# Using the main entry point
python -m dashcam_backend.main

# Or using the runner script
./run_backend.py

# Or in development with auto-reload
python src/dashcam_backend/main.py
```

### Configuration
Set environment variables or create a `.env` file:

```bash
# Database Configuration  
MONGODB_URI=mongodb://admin:dashcam123@localhost:27017/dashcam_db
DATABASE_NAME=dashcam_db

# Message Queue Configuration
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=dashcam
RABBITMQ_PASSWORD=dashcam123

# Storage Configuration
STORAGE_TYPE=minio  # or 'r2'
STORAGE_ENDPOINT=http://localhost:9000
STORAGE_ACCESS_KEY=AKIAADMIN87654321
STORAGE_SECRET_KEY=admin-secret-key-secure-dashcam-2024
STORAGE_BUCKET_RAW=dashcam-raw-videos
STORAGE_BUCKET_PROCESSED=dashcam-processed-videos
STORAGE_BUCKET_TEMP=dashcam-temp-uploads
STORAGE_BUCKET_THUMBNAILS=dashcam-thumbnails

# Application Configuration
LOG_LEVEL=INFO
```

## Development

### Running Tests

**IMPORTANT**: Always use the dedicated test runner for comprehensive testing:

```bash
# Run all tests (recommended approach)
./run_tests.sh
```

The test runner automatically:
- Uses the shared virtual environment from project root  
- Sets up proper Python paths and environment variables
- Runs all test categories with detailed reporting
- Ensures all tests complete within performance requirements (<1s per unit test)

For advanced debugging only (not recommended for regular development):
```bash
# Run specific test categories (only if needed for debugging)
pytest tests/test_config.py -v
pytest tests/test_models.py -v
pytest tests/test_mongodb_client.py -v
pytest tests/test_rabbitmq_client.py -v

# Run with coverage (only if needed for debugging)
pytest --cov=dashcam_backend tests/
```

### Test Strategy
- **Fast Unit Tests (<1s each)**: Test business logic with mocked dependencies
- **Integration Tests**: Test with real infrastructure (MongoDB, RabbitMQ, MinIO)
- **Comprehensive Mocking**: All I/O operations mocked for speed
- **Timeout Enforcement**: 1-second timeout per test to ensure fast execution

### Project Structure
```
services/backend/
├── src/
│   └── dashcam_backend/
│       ├── __init__.py
│       ├── main.py              # Application entry point
│       ├── config.py            # Configuration management
│       ├── models.py            # Data models and messages
│       ├── logging.py           # Structured logging
│       ├── rabbitmq_client.py   # RabbitMQ client
│       ├── mongodb_client.py    # MongoDB client
│       ├── storage_client.py    # S3-compatible storage
│       └── message_handlers.py  # Message processing logic
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_mongodb_client.py
│   └── test_rabbitmq_client.py
├── requirements.txt
├── pyproject.toml
├── run_tests.sh
└── README.md
```

## Message Queue Integration

### Queue Configuration
The backend manages these RabbitMQ queues:

- **frontend_requests**: Requests from frontend (video lists)
- **upload_progress**: Upload progress updates
- **upload_completed**: Upload completion notifications
- **worker_registration**: Worker registration messages
- **worker_heartbeat**: Worker heartbeat messages
- **processing_progress**: Task progress updates
- **processing_complete**: Task completion notifications
- **worker_assignments_{worker_id}**: Individual worker task queues

### Message Types
The backend handles these message types:

#### Frontend Messages
- `list_videos`: Get user's video list with pagination

#### Upload Service Messages
- `upload_progress`: Update upload progress
- `upload_completed`: Notify upload completion and move files

#### Worker Messages
- `worker_registration`: Register new worker
- `worker_heartbeat`: Update worker status and resource usage
- `processing_progress`: Update task progress
- `processing_complete`: Task completion notification

## Database Schema

### Collections
- **users**: User accounts, authentication, credits
- **videos**: Video metadata, upload status, processing settings
- **tasks**: Processing task status, progress, worker assignments
- **workers**: Worker capabilities, status, resource usage

### Key Indexes
- `videos.user_id + upload_date` (for user video lists)
- `tasks.worker_id + status` (for worker task assignment)
- `workers.status + last_heartbeat` (for available worker selection)

## API Workflows

### Direct Upload Workflow
1. Frontend uploads video directly to backend via REST API
2. Backend creates video record and stores file in MinIO
3. Backend automatically creates processing task
4. Task assigned to available worker for processing
5. Worker processes video and sends progress updates
6. Completion triggers video status update and worker release

### Task Assignment Workflow
1. File upload completion triggers task creation
2. Backend selects optimal worker based on capabilities and load
3. Task assigned to worker via individual worker queue
4. Worker processes video and sends progress updates
5. Completion triggers video status update and worker release

### Worker Management
1. Workers register via `worker_registration` with capabilities
2. Backend creates individual assignment queue for worker
3. Heartbeats maintain worker status via `worker_heartbeat` 
4. Offline workers trigger task reassignment
5. Smart assignment based on hardware capabilities and current load

## Monitoring and Logging

### Structured Logging
All logs include:
- Correlation IDs for request tracing
- Component names and operation context
- Error details with stack traces
- Performance metrics (request duration, database query time)

### Health Monitoring
- Database connectivity checks
- RabbitMQ connection and queue health  
- Storage service availability
- Worker status and capacity monitoring

### Error Handling
- Graceful degradation on component failures
- Automatic retry mechanisms for transient errors
- Circuit breaker patterns for external services
- Comprehensive error logging and alerting

## Security

### Authentication & Authorization
- Google OAuth integration for user authentication
- Session-based authentication with secure cookies
- User-level authorization for video access
- API request validation with Pydantic models

### Data Protection
- Input validation and sanitization
- SQL injection prevention (NoSQL parameterized queries)
- File upload security with type and size validation
- Secure storage with signed URLs for time-limited access

## Performance

### Optimization Features
- Async/await for high-concurrency message processing
- Database query optimization with proper indexing
- Connection pooling for database and storage clients
- Efficient message serialization with JSON

### Scalability
- Stateless design for horizontal scaling
- Message-driven architecture for natural load distribution
- Worker load balancing based on capabilities and current queue depth
- Database optimization for concurrent operations

## Implementation Status

### ✅ Completed Features
- **Configuration Management**: Environment-based configuration with validation
- **Data Models**: Complete message and database models for all service communication
- **Structured Logging**: JSON logging with correlation IDs and context
- **RabbitMQ Client**: Async message publishing and consumption with automatic reconnection
- **MongoDB Client**: Full database operations with async driver and proper indexing
- **Storage Client**: S3-compatible operations with signed URL generation
- **Message Handlers**: Complete message processing for all workflow types
- **Test Infrastructure**: Fast unit tests (<1s) with comprehensive mocking
- **Main Application**: Full service orchestration with signal handling and graceful shutdown

### 🚧 In Progress
- Integration testing with real infrastructure
- Authentication service integration
- Performance optimization and load testing

### 📋 Planned
- Google OAuth integration
- Payment system integration
- Advanced worker scheduling algorithms
- Monitoring and alerting dashboards

## Contributing

### Development Setup
1. Install Python 3.12+
2. Create shared virtual environment in project root: `cd ../../ && python -m venv venv`
3. Activate environment: `source ../../venv/bin/activate`
4. Install dependencies: `pip install -e .`
5. Run tests: `./run_tests.sh`

### Code Quality
- Type hints for all functions
- Comprehensive test coverage
- Fast test execution (<1s per test)
- Structured logging throughout
- Error handling with proper exception types

### Testing Guidelines
- Write fast unit tests with mocked dependencies
- Test business logic independently of infrastructure
- Use dataclasses for clean test data creation
- Maintain test isolation and independence
