# Backend Service Specification

## Overview
The backend service is a unified API service and worker coordination system responsible for handling direct file uploads from frontend, coordinating video processing tasks with workers, and managing user authentication. It provides REST API endpoints for frontend communication while maintaining RabbitMQ-based coordination with worker services.

## Core Functionality

### What the Backend Must Do
- **Direct File Upload Handling**: Accept and process multipart video uploads from frontend with real-time progress tracking
- **REST API Services**: Provide HTTP endpoints for user management, video listing, and download operations
- **Task Orchestration**: Create and assign video processing tasks to workers based on capabilities and load
- **Worker Coordination**: Manage worker registration, heartbeat monitoring, and intelligent task assignment via RabbitMQ
- **Real-time Updates**: Deliver progress updates to frontend via WebSocket connections
- **User Management**: Handle user authentication, session management, and authorization via Google OAuth
- **File Management**: Direct file storage operations and generate signed URLs for processed videos
- **Payment Integration**: Optional credit-based payment system with Google Pay integration

### Performance Requirements
- **REST API Performance**: Handle thousands of concurrent HTTP requests with sub-second response times
- **File Upload Handling**: Support large file uploads (up to 2GB) with efficient streaming and progress tracking
- **Real-time Updates**: Provide real-time progress delivery to frontend via WebSocket connections
- **Worker Coordination**: Efficiently handle high-volume RabbitMQ message processing for worker communication
- **Database Efficiency**: Optimize database queries for fast response times

### Data Management Requirements
- **User Data**: Store user profiles, authentication data, and upload history
- **Video Metadata**: Track video information, processing status, and file locations
- **Task State**: Maintain processing task status, progress, and worker assignments
- **Worker Status**: Monitor worker health, capabilities, and current assignments
- **Payment Records**: Optional credit transactions and subscription management
- **Audit Logs**: Track all system activities for debugging and compliance

## Architecture and Technology Stack

### Hybrid API + Worker Coordination Architecture
The backend implements a **hybrid architecture** combining REST API services with message-driven worker coordination:
- **REST API Layer**: FastAPI-based HTTP endpoints for frontend communication, file uploads, and user management
- **WebSocket Layer**: Real-time progress updates and notifications to frontend clients
- **Worker Coordination Layer**: RabbitMQ message handlers for worker registration, task assignment, and progress tracking
- **Business Logic Layer**: Core application logic for task orchestration and user management
- **Data Access Layer**: MongoDB integration with optimized queries and indexing
- **Authentication Layer**: Google OAuth integration and session management
- **File Storage Layer**: Direct object storage operations for uploads and downloads

### Recommended Technology Stack
- **Language**: Python 3.12+
- **API Framework**: FastAPI for REST endpoints with automatic OpenAPI documentation
- **WebSocket Support**: FastAPI WebSocket for real-time progress updates
- **Message Queue Framework**: Pika for RabbitMQ communication with workers
- **Database**: MongoDB with Motor (async driver) for optimal performance
- **Object Storage**: boto3 for S3-compatible storage operations (MinIO/R2)
- **Authentication**: Google OAuth integration with session management
- **Validation**: Pydantic models for request/response validation
- **File Upload**: FastAPI multipart file handling with streaming support
- **Background Tasks**: asyncio for worker coordination and background operations
- **Monitoring**: Structured logging with correlation IDs for request tracing

### Worker Management System
- **Worker Registration**: Accept and validate worker capability announcements
- **Health Monitoring**: Track worker heartbeats and detect offline workers
- **Capability Tracking**: Maintain database of worker compute capabilities and availability
- **Smart Assignment**: Route tasks to optimal workers based on:
  - Current workload and queue depth
  - Hardware capabilities (GPU/CPU, memory)
  - Model size requirements
  - Task priority and user tier

## Configuration

### Environment Variables
The backend must support the following environment variables:
```bash
# API Server Configuration
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=["http://localhost:3000", "https://dashcam.example.com"]

# Database Configuration  
MONGODB_URI=mongodb://admin:dashcam123@localhost:27017/dashcam_db
DATABASE_NAME=dashcam_db

# Message Queue Configuration (Workers only)
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
STORAGE_BUCKET_THUMBNAILS=dashcam-thumbnails

# Authentication Configuration
GOOGLE_CLIENT_ID=required-google-oauth-client-id
GOOGLE_CLIENT_SECRET=required-google-oauth-client-secret
SESSION_SECRET_KEY=your-session-secret-key
SESSION_EXPIRES_HOURS=24

# Payment Configuration (Optional)
GOOGLE_PAY_ENABLED=false
GOOGLE_PAY_MERCHANT_ID=optional-merchant-id
CREDIT_PRICE_PER_MINUTE=0.10

# Application Configuration
MAX_UPLOAD_SIZE=2147483648  # 2GB in bytes
ALLOWED_VIDEO_FORMATS=["mp4", "avi", "mov", "mkv"]
DEFAULT_PROCESSING_SETTINGS={}
LOG_LEVEL=INFO
```

## Communication Architecture

### Hybrid Communication Model
The backend uses different communication protocols optimized for each service type:

**Frontend Communication** (REST API + WebSocket):
- **REST API**: HTTP endpoints for uploads, authentication, video management
- **WebSocket**: Real-time progress updates and notifications
- **Session Management**: HTTP cookies and session storage

**Worker Communication** (RabbitMQ):
- **Worker Registration**: Worker capability announcements via message queues
- **Task Assignment**: Direct task assignment to individual worker queues
- **Progress Reporting**: Workers send progress updates via dedicated queues
- **Heartbeat Monitoring**: Worker health status via periodic messages

### Benefits of Hybrid Architecture:
1. **Standard Frontend Protocol**: REST API follows web standards and best practices
2. **Efficient Worker Coordination**: RabbitMQ provides reliable async communication with workers
3. **Real-time Updates**: WebSocket enables instant progress delivery to frontend
4. **Simplified Development**: Standard HTTP tools and frameworks for frontend integration

## REST API Specification

### Authentication Endpoints
- `POST /auth/google` - Google OAuth authentication
- `POST /auth/logout` - User logout
- `GET /auth/user` - Get current user information

### Video Management Endpoints
- `POST /videos/upload` - Direct video upload with multipart form
- `GET /videos` - List user's videos with pagination
- `GET /videos/{video_id}` - Get specific video details
- `GET /videos/{video_id}/download` - Get signed download URL
- `DELETE /videos/{video_id}` - Delete video and associated files

### Processing Endpoints
- `GET /videos/{video_id}/progress` - Get processing progress
- `POST /videos/{video_id}/reprocess` - Restart processing with new settings

### System Endpoints
- `GET /health` - Service health check
- `GET /workers` - List active workers (admin only)

## Worker Coordination via RabbitMQ

### RabbitMQ Queue Configuration
```python
# Worker communication queues only
queues = {
    # Worker ↔ Backend Communication
    "worker_registration": {"durable": True, "routing_key": "worker.register"},
    "worker_heartbeat": {"durable": True, "routing_key": "worker.heartbeat"}, 
    "processing_progress": {"durable": True, "routing_key": "task.progress"},
    "processing_complete": {"durable": True, "routing_key": "task.complete"},
    "processing_errors": {"durable": True, "routing_key": "task.error"},
    
    # Dynamic queues per worker
    "worker_assignments_{worker_id}": {"durable": True, "auto_delete": False}
}
```

### Worker Message Protocols

#### Worker Registration
```json
{
  "message_type": "worker_registration",
  "worker_id": "worker-uuid",
  "hostname": "worker-node-01",
  "capabilities": {
    "compute_device": "cuda",
    "gpu_memory_gb": 8,
    "max_model_size": "large"
  }
}
```

#### Task Assignment (Backend → Worker)
```json
{
  "message_type": "process_video",
  "task_id": "task-uuid",
  "video_id": "video-uuid",
  "input_path": "dashcam-raw-videos/user-uuid/video-uuid.mp4",
  "output_path": "dashcam-processed-videos/user-uuid/video-uuid/",
  "processing_settings": {
    "yolo_classes": [0, 2, 3],
    "model_size": "medium"
  }
}
```

#### Progress Update (Worker → Backend)
```json
{
  "message_type": "processing_progress",
  "task_id": "task-uuid",
  "progress_percentage": 45,
  "current_frame": 2430,
  "total_frames": 5400,
  "estimated_time_remaining": 155
}
```

## Database Schema

### Collections and Document Structure

#### users
```json
{
  "_id": "ObjectId",
  "user_id": "uuid-string",
  "email": "user@example.com",
  "password_hash": "bcrypt-hash",
  "google_id": "google-user-id-string",
  "credits": 10.50,
  "subscription_tier": "free",
  "created_at": "2025-01-15T10:30:00Z",
  "last_login": "2025-01-15T10:30:00Z"
}
```

#### videos
```json
{
  "_id": "ObjectId",
  "video_id": "uuid-string",
  "user_id": "uuid-string",
  "filename": "dashcam_footage.mp4",
  "file_size": 157286400,
  "duration_seconds": 180,
  "resolution": "1920x1080",
  "format": "mp4",
  "upload_date": "2025-01-15T10:30:00Z",
  "status": "completed",
  "raw_file_path": "dashcam-raw-videos/user-uuid/video-uuid.mp4",
  "thumbnail_path": "dashcam-thumbnails/user-uuid/video-uuid.jpg",
  "processed_file_path": "dashcam-processed-videos/user-uuid/video-uuid/output.mp4",
  "processing_settings": {
    "yolo_classes": [0, 2, 3],
    "model_size": "medium",
    "detection_type": "bbox"
  },
  "processing_stats": {
    "processing_time": 285,
    "total_frames": 5400,
    "objects_detected": 127
  }
}
```

#### tasks
```json
{
  "_id": "ObjectId", 
  "task_id": "uuid-string",
  "video_id": "uuid-string",
  "user_id": "uuid-string",
  "worker_id": "uuid-string",
  "status": "processing",
  "progress_percentage": 45,
  "current_frame": 2430,
  "total_frames": 5400,
  "estimated_time_remaining": 155,
  "created_at": "2025-01-15T10:30:00Z",
  "started_at": "2025-01-15T10:31:00Z",
  "last_updated": "2025-01-15T10:35:00Z",
  "completed_at": null,
  "error_message": null
}
```

#### workers
```json
{
  "_id": "ObjectId",
  "worker_id": "uuid-string", 
  "hostname": "worker-node-01",
  "status": "ready",
  "capabilities": {
    "compute_device": "cuda",
    "gpu_memory_gb": 8,
    "system_memory_gb": 16,
    "max_model_size": "large",
    "supported_formats": ["mp4", "avi", "mov", "mkv"]
  },
  "current_task_id": null,
  "resource_usage": {
    "cpu_percent": 45,
    "memory_percent": 60,
    "gpu_percent": 80
  },
  "registered_at": "2025-01-15T10:00:00Z",
  "last_heartbeat": "2025-01-15T10:35:00Z"
}
```

#### payment_transactions (Optional)
```json
{
  "_id": "ObjectId",
  "transaction_id": "uuid-string",
  "user_id": "uuid-string", 
  "amount": 5.00,
  "credits_purchased": 50,
  "payment_method": "google_pay",
  "google_pay_transaction_id": "google-transaction-id",
  "status": "completed",
  "created_at": "2025-01-15T10:30:00Z"
}
```

### Database Indexes
Required indexes for optimal performance:
```javascript
// users collection
db.users.createIndex({"email": 1}, {unique: true})
db.users.createIndex({"user_id": 1}, {unique: true})

// videos collection  
db.videos.createIndex({"user_id": 1, "upload_date": -1})
db.videos.createIndex({"video_id": 1}, {unique: true})
db.videos.createIndex({"status": 1})

// tasks collection
db.tasks.createIndex({"task_id": 1}, {unique: true})
db.tasks.createIndex({"user_id": 1, "created_at": -1})
db.tasks.createIndex({"worker_id": 1, "status": 1})
db.tasks.createIndex({"status": 1})

// workers collection
db.workers.createIndex({"worker_id": 1}, {unique: true})
db.workers.createIndex({"status": 1})
db.workers.createIndex({"last_heartbeat": 1})
```

## Workflow Processes

### Worker Registration Workflow
1. **Worker Startup**: Worker sends registration message to `worker_registration` queue
2. **Capability Storage**: Backend stores worker capabilities in `workers` collection
3. **Queue Creation**: Backend creates individual assignment queue `worker_assignments_{worker_id}`
4. **Registration Confirmation**: Backend confirms successful registration

### File Upload and Processing Workflow
1. **Direct Upload**: Frontend uploads video directly to backend via REST API
2. **File Storage**: Backend streams file to object storage and creates database record
3. **Task Creation**: Backend creates processing task with video metadata
4. **Worker Selection**: Backend selects optimal worker based on capabilities and load
5. **Task Assignment**: Backend sends task message to worker's individual queue
6. **Progress Tracking**: Worker sends progress updates via RabbitMQ, backend broadcasts via WebSocket

### Task Assignment Logic
Backend selects optimal worker based on:
- Current status (ready/busy)
- Hardware capabilities vs task requirements
- Current queue depth and workload
- Task priority and user tier

### Worker Health Monitoring
1. **Heartbeat Reception**: Backend receives worker heartbeats every 30 seconds
2. **Status Update**: Update worker status and resource usage in database
3. **Health Check**: Mark workers as offline if no heartbeat for 60 seconds
4. **Task Reassignment**: Reassign tasks from offline workers to available workers

## File Storage Integration

### Direct Upload Workflow
1. **Upload Validation**: Validate file format, size, and user authentication
2. **Streaming Upload**: Stream uploaded file directly to object storage
3. **Database Record**: Create video record with storage path and metadata
4. **Task Creation**: Create processing task and assign to optimal worker

### Storage Path Structure
```
dashcam-raw-videos/
  {user_id}/
    {video_id}.{extension}
    
dashcam-processed-videos/
  {user_id}/
    {video_id}/
      output.{extension}
      metadata.json
```

### Download Workflow
1. **Authorization**: Verify user owns the video via session
2. **Signed URL**: Generate time-limited signed URL for direct download
3. **Access Logging**: Log download access for audit

## Security and Authentication

### Session-Based Authentication
- **Session Creation**: Create secure server-side sessions after Google OAuth
- **Session Validation**: Validate session cookies on protected endpoints  
- **Session Storage**: Store session data in MongoDB or Redis
- **Session Renewal**: Automatic session refresh before expiration

### Authorization Levels
- **User**: Access own videos and tasks (default for Google sign-in users)
- **Admin**: Access all system data and worker management (manually assigned)
- **Guest**: No access (all operations require Google authentication)

### Data Protection
- **Google OAuth Security**: Validate OAuth tokens and implement CSRF protection
- **Session Security**: HTTP-only, secure cookies with SameSite protection
- **Input Validation**: Pydantic models for all API requests
- **NoSQL Injection Prevention**: Use parameterized queries with MongoDB
- **File Upload Security**: Validate file types, size limits, and scan for malware
- **Rate Limiting**: Implement request rate limiting per user session

## Error Handling and Monitoring

### Error Categories
1. **Client Errors (4xx)**: Invalid requests, authentication failures
2. **Server Errors (5xx)**: Database failures, worker communication errors
3. **Processing Errors**: Worker failures, video processing errors
4. **Storage Errors**: Upload/download failures, storage unavailability

### Monitoring and Logging
Required log events:
- API request/response with correlation IDs
- Worker registration/deregistration
- Task creation/completion/failure
- File upload/download events
- Authentication events
- Error occurrences with stack traces
- Performance metrics (request duration, database query time)

### Health Checks
- **Database Connectivity**: MongoDB connection health
- **Message Queue**: RabbitMQ connection and queue health
- **Storage**: Object storage connectivity test
- **Worker Status**: Number of active/offline workers

## Testing Requirements

### Unit Tests (Fast Execution - <1 second each)
- **REST API endpoints** with FastAPI TestClient
- **WebSocket communication** with mocked connections
- **Worker coordination logic** with mocked RabbitMQ operations
- **Database operations** with in-memory mock databases
- **Authentication logic** with mocked Google OAuth responses
- **File upload handling** with synthetic file data
- **Worker assignment algorithms** with synthetic worker data

### Integration Tests
- **End-to-end API workflows** with real database
- **Worker communication** with real RabbitMQ
- **File storage operations** with test storage buckets
- **WebSocket real-time updates** with multiple clients

### Test Execution
```bash
# Fast unit tests (development)
pytest tests/unit/ --timeout=1 -v

# Integration tests (CI/CD)
pytest tests/integration/ -v
```

## Deployment and Scaling

### Container Deployment
- **Runtime Environment**: Python 3.12+ with FastAPI and async worker coordination
- **Health Check**: HTTP health endpoints and RabbitMQ connection monitoring
- **Configuration**: Environment variable based configuration
- **Logging**: Structured JSON logs to stdout
- **Security**: Non-root user execution

### Scaling Considerations
- **Stateless Design**: No local state storage, all state in MongoDB
- **Load Balancing**: Support multiple backend instances behind load balancer
- **Database Scaling**: MongoDB replica set support
- **Resource Requirements**: 2 CPU cores, 4GB RAM minimum for production
