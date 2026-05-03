"""MongoDB client for database operations."""

import asyncio
import time
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo.errors import DuplicateKeyError, ConnectionFailure, ServerSelectionTimeoutError

from .config import get_config
from .logging import get_logger
from .models import (
    VideoDocument, TaskDocument, WorkerDocument, UserDocument, UploadSessionDocument,
    VideoStatus, TaskStatus, WorkerStatus, UploadStatus, get_current_timestamp
)


logger = get_logger(__name__)


class MongoDBClient:
    """MongoDB client with async operations and automatic reconnection."""
    
    def __init__(self):
        self.config = get_config().mongodb
        self.app_config = get_config().app
        self.client: Optional[AsyncIOMotorClient] = None
        self.database: Optional[AsyncIOMotorDatabase] = None
        self.monitoring_task: Optional[asyncio.Task] = None
        self.shutdown_event = asyncio.Event()
        
        # Collection references
        self.users: Optional[AsyncIOMotorCollection] = None
        self.videos: Optional[AsyncIOMotorCollection] = None
        self.tasks: Optional[AsyncIOMotorCollection] = None
        self.workers: Optional[AsyncIOMotorCollection] = None
        self.upload_sessions: Optional[AsyncIOMotorCollection] = None
    
    @staticmethod
    def _convert_string_dates_to_datetime(document: dict) -> dict:
        """Convert string date fields to datetime objects."""
        datetime_fields = [
            'upload_date', 'upload_started_at', 'upload_completed_at', 
            'upload_expires_at', 'created_at', 'updated_at', 'started_at', 
            'completed_at', 'expires_at', 'last_heartbeat'
        ]
        
        for field in datetime_fields:
            if field in document and isinstance(document[field], str):
                try:
                    # Parse ISO format date string
                    date_str = document[field]
                    if date_str.endswith('Z'):
                        date_str = date_str.replace('Z', '+00:00')
                    document[field] = datetime.fromisoformat(date_str)
                except (ValueError, AttributeError):
                    # If parsing fails, set to None
                    document[field] = None
        
        return document
    
    async def connect(self) -> None:
        """Connect to MongoDB and initialize collections with retry logic."""
        max_attempts = self.app_config.connection_retry_max_attempts
        base_delay = self.app_config.connection_retry_base_delay
        max_delay = self.app_config.connection_retry_max_delay
        
        for attempt in range(max_attempts):
            try:
                self.client = AsyncIOMotorClient(
                    self.config.uri,
                    serverSelectionTimeoutMS=5000,  # 5 second timeout
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000,
                    maxPoolSize=10,
                    retryWrites=True
                )
                
                # Test connection
                await self.client.admin.command('ping')
                
                # Get database
                self.database = self.client[self.config.database_name]
                
                # Initialize collection references
                self.users = self.database.users
                self.videos = self.database.videos
                self.tasks = self.database.tasks
                self.workers = self.database.workers
                self.upload_sessions = self.database.upload_sessions
                
                # Initialize collection references
                self.users = self.database.users
                self.videos = self.database.videos
                self.tasks = self.database.tasks
                self.workers = self.database.workers
                self.upload_sessions = self.database.upload_sessions
                
                # Create indexes
                await self._create_indexes()
                
                logger.info(
                    "Connected to MongoDB",
                    database=self.config.database_name,
                    uri=self.config.uri.split('@')[-1],  # Hide credentials
                    attempt=attempt + 1
                )
                
                # Start connection monitoring
                if not self.monitoring_task or self.monitoring_task.done():
                    self.monitoring_task = asyncio.create_task(self._monitor_connection())
                
                return
                
            except Exception as e:
                logger.warning(
                    "MongoDB connection attempt failed",
                    error=str(e),
                    attempt=attempt + 1,
                    max_attempts=max_attempts
                )
                
                if attempt < max_attempts - 1:
                    # Exponential backoff
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    await asyncio.sleep(delay)
                else:
                    logger.error("Max MongoDB connection attempts reached")
                    raise
    
    async def _monitor_connection(self) -> None:
        """Monitor MongoDB connection health and reconnect if needed."""
        check_interval = self.app_config.connection_health_check_interval
        
        while not self.shutdown_event.is_set():
            try:
                await asyncio.sleep(check_interval)
                
                if self.shutdown_event.is_set():
                    break
                    
                # Test connection
                if self.client:
                    await self.client.admin.command('ping')
                else:
                    logger.warning("MongoDB client is None, attempting to reconnect")
                    await self._reconnect()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("MongoDB connection check failed, attempting to reconnect", error=str(e))
                await self._reconnect()
                
    async def _reconnect(self) -> None:
        """Attempt to reconnect to MongoDB."""
        try:
            # Clean up old connection
            if self.client:
                self.client.close()
            
            self.client = None
            self.database = None
            self.users = None
            self.videos = None
            self.tasks = None
            self.workers = None
            
            # Reconnect
            await self.connect()
            
            logger.info("MongoDB reconnection successful")
            
        except Exception as e:
            logger.error("MongoDB reconnection failed", error=str(e))
    
    async def disconnect(self) -> None:
        """Close MongoDB connection and stop monitoring."""
        try:
            # Signal shutdown to monitoring task
            self.shutdown_event.set()
            
            if self.monitoring_task and not self.monitoring_task.done():
                self.monitoring_task.cancel()
                try:
                    await self.monitoring_task
                except asyncio.CancelledError:
                    pass
            
            if self.client:
                self.client.close()
                logger.info("Disconnected from MongoDB")
                
        except Exception as e:
            logger.error("Error disconnecting from MongoDB", error=str(e))
    
    async def _resilient_operation(self, operation) -> Any:
        """Execute a MongoDB operation with automatic reconnection on failure."""
        max_attempts = 3
        base_delay = 1.0
        
        for attempt in range(max_attempts):
            try:
                return await operation()
                
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                logger.warning(
                    "MongoDB operation failed, connection issue detected",
                    error=str(e),
                    attempt=attempt + 1
                )
                
                if attempt < max_attempts - 1:
                    # Try to reconnect
                    try:
                        await self._reconnect()
                    except Exception as reconnect_error:
                        logger.error("MongoDB reconnection failed", error=str(reconnect_error))
                    
                    # Wait before retry
                    await asyncio.sleep(base_delay * (2 ** attempt))
                else:
                    logger.error("Max MongoDB operation attempts reached")
                    raise
                    
            except Exception as e:
                # Non-connection related error, don't retry
                logger.error("MongoDB operation failed with non-connection error", error=str(e))
                raise
    
    async def _create_indexes(self) -> None:
        """Create database indexes for optimal performance."""
        try:
            # Users collection indexes
            await self.users.create_index("email", unique=True)
            await self.users.create_index("user_id", unique=True)
            
            # Videos collection indexes
            await self.videos.create_index([("user_id", 1), ("upload_date", -1)])
            await self.videos.create_index("video_id", unique=True)
            await self.videos.create_index("status")
            await self.videos.create_index("upload_status")
            await self.videos.create_index("upload_expires_at")
            
            # Tasks collection indexes
            await self.tasks.create_index("task_id", unique=True)
            await self.tasks.create_index([("user_id", 1), ("created_at", -1)])
            await self.tasks.create_index([("worker_id", 1), ("status", 1)])
            await self.tasks.create_index("status")
            
            # Workers collection indexes
            await self.workers.create_index("worker_id", unique=True)
            await self.workers.create_index("status")
            await self.workers.create_index("last_heartbeat")
            
            logger.info("Database indexes created")
            
        except Exception as e:
            logger.error("Failed to create indexes", error=str(e))
            raise
    
    # User operations
    async def create_user(self, user: UserDocument) -> str:
        """Create a new user."""
        try:
            user_dict = user.__dict__.copy()
            user_dict['created_at'] = get_current_timestamp()
            user_dict['last_login'] = get_current_timestamp()
            
            result = await self.users.insert_one(user_dict)
            
            logger.info("Created user", user_id=user.user_id, email=user.email)
            return str(result.inserted_id)
            
        except DuplicateKeyError:
            logger.warning("User already exists", user_id=user.user_id, email=user.email)
            raise ValueError("User already exists")
        except Exception as e:
            logger.error("Failed to create user", error=str(e))
            raise
    
    async def get_user_by_id(self, user_id: str) -> Optional[UserDocument]:
        """Get user by ID."""
        try:
            user_dict = await self.users.find_one({"user_id": user_id})
            if user_dict:
                return UserDocument(**user_dict)
            return None
            
        except Exception as e:
            logger.error("Failed to get user by ID", user_id=user_id, error=str(e))
            raise
    
    async def get_user_by_email(self, email: str) -> Optional[UserDocument]:
        """Get user by email."""
        try:
            user_dict = await self.users.find_one({"email": email})
            if user_dict:
                return UserDocument(**user_dict)
            return None
            
        except Exception as e:
            logger.error("Failed to get user by email", email=email, error=str(e))
            raise
    
    async def update_user_last_login(self, user_id: str) -> None:
        """Update user's last login timestamp."""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_login": get_current_timestamp()}}
            )
            
            logger.debug("Updated user last login", user_id=user_id)
            
        except Exception as e:
            logger.error("Failed to update user last login", user_id=user_id, error=str(e))
            raise
    
    async def update_user_credits(self, user_id: str, credits: float) -> None:
        """Update user's credit balance."""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"credits": credits}}
            )
            
            logger.info("Updated user credits", user_id=user_id, credits=credits)
            
        except Exception as e:
            logger.error("Failed to update user credits", user_id=user_id, error=str(e))
            raise
    
    async def update_user_subscription(self, user_id: str, tier: str) -> None:
        """Update user's subscription tier."""
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"subscription_tier": tier}}
            )
            
            logger.info("Updated user subscription", user_id=user_id, tier=tier)
            
        except Exception as e:
            logger.error("Failed to update user subscription", user_id=user_id, error=str(e))
            raise
    
    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user's usage statistics."""
        try:
            # Get user basic info
            user = await self.get_user_by_id(user_id)
            if not user:
                return {}
            
            # Count videos by status
            video_stats = await self.videos.aggregate([
                {"$match": {"user_id": user_id}},
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "total_size": {"$sum": "$file_size"}
                }}
            ]).to_list(None)
            
            # Count tasks by status
            task_stats = await self.tasks.aggregate([
                {"$match": {"user_id": user_id}},
                {"$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }}
            ]).to_list(None)
            
            return {
                "user_id": user_id,
                "credits": user.credits,
                "subscription_tier": user.subscription_tier,
                "member_since": user.created_at,
                "last_login": user.last_login,
                "video_stats": video_stats,
                "task_stats": task_stats
            }
            
        except Exception as e:
            logger.error("Failed to get user stats", user_id=user_id, error=str(e))
            raise

    # Video operations
    async def create_video(self, video: VideoDocument) -> str:
        """Create a new video record."""
        try:
            video_dict = video.__dict__.copy()
            video_dict['upload_date'] = get_current_timestamp()
            
            result = await self.videos.insert_one(video_dict)
            
            logger.info(
                "Created video record",
                video_id=video.video_id,
                user_id=video.user_id,
                filename=video.filename,
                status=video.status,
                upload_progress=getattr(video, 'upload_progress', 0.0)
            )
            return str(result.inserted_id)
            
        except DuplicateKeyError:
            logger.warning("Video already exists", video_id=video.video_id)
            raise ValueError("Video already exists")
        except Exception as e:
            logger.error("Failed to create video", error=str(e))
            raise
    
    async def get_video_by_id(self, video_id: str) -> Optional[VideoDocument]:
        """Get video by ID."""
        try:
            video_dict = await self.videos.find_one({"video_id": video_id})
            if video_dict:
                # Remove MongoDB's _id field before creating VideoDocument
                video_dict.pop('_id', None)
                # Convert string dates to datetime objects
                video_dict = self._convert_string_dates_to_datetime(video_dict)
                # Strip fields not in VideoDocument (e.g. updated_at from sync client)
                known_fields = set(VideoDocument.__dataclass_fields__.keys())
                video_dict = {k: v for k, v in video_dict.items() if k in known_fields}
                return VideoDocument(**video_dict)
            return None
            
        except Exception as e:
            logger.error("Failed to get video by ID", video_id=video_id, error=str(e))
            raise
    
    async def get_videos_by_user(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 10
    ) -> Dict[str, Any]:
        """Get videos for a user with pagination."""
        try:
            skip = (page - 1) * per_page
            
            # Get total count
            total = await self.videos.count_documents({"user_id": user_id})
            
            # Get videos
            cursor = self.videos.find({"user_id": user_id}) \
                .sort("upload_date", -1) \
                .skip(skip) \
                .limit(per_page)
            
            videos = []
            async for video_dict in cursor:
                # Remove MongoDB's _id field before creating VideoDocument
                video_dict.pop('_id', None)
                # Convert string dates to datetime objects
                video_dict = self._convert_string_dates_to_datetime(video_dict)
                # Strip fields not in VideoDocument (e.g. updated_at from sync client)
                known_fields = set(VideoDocument.__dataclass_fields__.keys())
                video_dict = {k: v for k, v in video_dict.items() if k in known_fields}
                videos.append(VideoDocument(**video_dict))
            
            return {
                "videos": videos,
                "total": total,
                "page": page,
                "per_page": per_page
            }
            
        except Exception as e:
            logger.error("Failed to get videos by user", user_id=user_id, error=str(e))
            raise
    
    async def update_video_status(self, video_id: str, status: VideoStatus) -> None:
        """Update video status."""
        try:
            await self.videos.update_one(
                {"video_id": video_id},
                {"$set": {"status": status.value}}
            )
            
            logger.debug("Updated video status", video_id=video_id, status=status.value)
            
        except Exception as e:
            logger.error("Failed to update video status", video_id=video_id, error=str(e))
            raise
    
    async def update_video_upload_progress(
        self,
        video_id: str,
        progress: int,
        bytes_uploaded: Optional[int] = None
    ) -> None:
        """Update video upload progress."""
        try:
            update_data = {"upload_progress": progress}
            if bytes_uploaded is not None:
                update_data["bytes_uploaded"] = bytes_uploaded
            
            await self.videos.update_one(
                {"video_id": video_id},
                {"$set": update_data}
            )
            
            logger.debug(
                "Updated video upload progress",
                video_id=video_id,
                progress=progress
            )
            
        except Exception as e:
            logger.error("Failed to update upload progress", video_id=video_id, error=str(e))
            raise

    async def update_video_thumbnail_status(self, video_id: str, thumbnail_available: bool) -> None:
        """Update video thumbnail availability status."""
        try:
            await self.videos.update_one(
                {"video_id": video_id},
                {"$set": {"thumbnail_available": thumbnail_available}}
            )
            
            logger.debug(
                "Updated video thumbnail status",
                video_id=video_id,
                thumbnail_available=thumbnail_available
            )
            
        except Exception as e:
            logger.error("Failed to update thumbnail status", video_id=video_id, error=str(e))
            raise

    async def mark_video_as_deleted(self, video_id: str) -> None:
        """Mark video as deleted (soft delete)."""
        try:
            result = await self.videos.update_one(
                {"video_id": video_id},
                {"$set": {"deleted": True}}
            )
            
            if result.matched_count == 0:
                raise ValueError(f"Video {video_id} not found")
            
            logger.info("Marked video as deleted", video_id=video_id)
            
        except Exception as e:
            logger.error("Failed to mark video as deleted", video_id=video_id, error=str(e))
            raise

    async def list_videos(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 10,
        status_filter: Optional[str] = None
    ) -> tuple[List[VideoDocument], int]:
        """List videos with pagination and optional status filtering."""
        try:
            skip = (page - 1) * per_page
            
            # Build query - always exclude deleted videos
            # Use $or to handle cases where deleted field might not exist
            query = {
                "user_id": user_id, 
                "$or": [
                    {"deleted": {"$exists": False}},  # Include docs without deleted field
                    {"deleted": False}                # Include docs with deleted=False
                ]
            }
            if status_filter:
                query["status"] = status_filter
            
            # Get total count
            total = await self.videos.count_documents(query)
            
            # Get videos with custom sorting - uploading videos first, then by upload date
            # We'll use aggregation pipeline to achieve custom sorting
            pipeline = [
                {"$match": query},
                {"$addFields": {
                    "sort_priority": {
                        "$cond": {
                            "if": {"$eq": ["$status", "uploading"]},
                            "then": 0,  # uploading videos get priority 0 (highest)
                            "else": 1   # all other videos get priority 1
                        }
                    }
                }},
                {"$sort": {
                    "sort_priority": 1,    # uploading videos first
                    "upload_date": -1      # then by upload date descending
                }},
                {"$skip": skip},
                {"$limit": per_page},
                {"$unset": "sort_priority"}  # remove the helper field
            ]
            
            cursor = self.videos.aggregate(pipeline)
            
            videos = []
            video_count = 0
            uploading_count = 0
            async for video_dict in cursor:
                video_count += 1
                status = video_dict.get('status', 'unknown')
                if status == 'uploading':
                    uploading_count += 1
                    logger.info("Found uploading video in list_videos", 
                              video_id=video_dict.get('video_id', 'unknown'),
                              filename=video_dict.get('filename', 'unknown'),
                              status=status,
                              upload_progress=video_dict.get('upload_progress', 'unknown'))
                
                # Remove MongoDB's _id field before creating VideoDocument
                video_dict.pop('_id', None)
                # Convert string dates to datetime objects
                video_dict = self._convert_string_dates_to_datetime(video_dict)
                # Strip any extra fields not defined in VideoDocument (e.g. updated_at added by sync updates)
                known_fields = set(VideoDocument.__dataclass_fields__.keys())
                video_dict = {k: v for k, v in video_dict.items() if k in known_fields}
                videos.append(VideoDocument(**video_dict))
            
            logger.info("list_videos completed", 
                       user_id=user_id, 
                       total_videos=video_count, 
                       uploading_videos=uploading_count,
                       page=page,
                       per_page=per_page)
            
            return videos, total
            
        except Exception as e:
            logger.error("Failed to list videos", user_id=user_id, error=str(e))
            raise
    
    # Task operations
    async def create_task(self, task: TaskDocument) -> str:
        """Create a new task."""
        try:
            task_dict = task.__dict__.copy()
            task_dict['created_at'] = get_current_timestamp()
            task_dict['last_updated'] = get_current_timestamp()
            
            result = await self.tasks.insert_one(task_dict)
            
            logger.info(
                "Created task",
                task_id=task.task_id,
                video_id=task.video_id,
                user_id=task.user_id
            )
            return str(result.inserted_id)
            
        except DuplicateKeyError:
            logger.warning("Task already exists", task_id=task.task_id)
            raise ValueError("Task already exists")
        except Exception as e:
            logger.error("Failed to create task", error=str(e))
            raise
    
    async def get_task_by_id(self, task_id: str) -> Optional[TaskDocument]:
        """Get task by ID."""
        try:
            task_dict = await self.tasks.find_one({"task_id": task_id})
            if task_dict:
                return TaskDocument(**task_dict)
            return None
            
        except Exception as e:
            logger.error("Failed to get task by ID", task_id=task_id, error=str(e))
            raise

    async def get_active_task_by_video_id(self, video_id: str) -> Optional[TaskDocument]:
        """Get the most recent active (assigned or processing) task for a video."""
        try:
            active_statuses = [TaskStatus.ASSIGNED.value, TaskStatus.PROCESSING.value, TaskStatus.PENDING.value]
            task_dict = await self.tasks.find_one(
                {"video_id": video_id, "status": {"$in": active_statuses}},
                sort=[("created_at", -1)]
            )
            if task_dict:
                task_dict.pop('_id', None)
                known_fields = set(TaskDocument.__dataclass_fields__.keys())
                task_dict = {k: v for k, v in task_dict.items() if k in known_fields}
                return TaskDocument(**task_dict)
            return None

        except Exception as e:
            logger.error("Failed to get active task by video ID", video_id=video_id, error=str(e))
            raise
    
    async def update_task_progress(
        self,
        task_id: str,
        progress: int,
        current_frame: Optional[int] = None,
        fps: Optional[float] = None,
        estimated_time_remaining: Optional[int] = None
    ) -> None:
        """Update task progress."""
        try:
            update_data = {
                "progress_percentage": progress,
                "last_updated": get_current_timestamp()
            }
            
            if current_frame is not None:
                update_data["current_frame"] = current_frame
            if fps is not None:
                update_data["fps"] = fps
            if estimated_time_remaining is not None:
                update_data["estimated_time_remaining"] = estimated_time_remaining
            
            await self.tasks.update_one(
                {"task_id": task_id},
                {"$set": update_data}
            )
            
            logger.debug("Updated task progress", task_id=task_id, progress=progress)
            
        except Exception as e:
            logger.error("Failed to update task progress", task_id=task_id, error=str(e))
            raise
    
    async def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        """Update task status."""
        try:
            update_data = {
                "status": status.value,
                "last_updated": get_current_timestamp()
            }
            
            if status == TaskStatus.PROCESSING:
                update_data["started_at"] = get_current_timestamp()
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                update_data["completed_at"] = get_current_timestamp()
            
            await self.tasks.update_one(
                {"task_id": task_id},
                {"$set": update_data}
            )
            
            logger.info("Updated task status", task_id=task_id, status=status.value)
            
        except Exception as e:
            logger.error("Failed to update task status", task_id=task_id, error=str(e))
            raise
    
    # Worker operations
    async def register_worker(self, worker: WorkerDocument) -> str:
        """Register a new worker or update existing one."""
        try:
            worker_dict = worker.__dict__.copy()
            worker_dict['registered_at'] = get_current_timestamp()
            worker_dict['last_heartbeat'] = get_current_timestamp()
            
            # Upsert worker (insert if new, update if exists)
            result = await self.workers.replace_one(
                {"worker_id": worker.worker_id},
                worker_dict,
                upsert=True
            )
            
            logger.info(
                "Registered worker",
                worker_id=worker.worker_id,
                hostname=worker.hostname,
                compute_device=worker.capabilities.get('compute_device', 'unknown')
            )
            
            return str(result.upserted_id) if result.upserted_id else worker.worker_id
            
        except Exception as e:
            logger.error("Failed to register worker", error=str(e))
            raise
    
    async def update_worker_heartbeat(
        self,
        worker_id: str,
        status: WorkerStatus,
        resource_usage: Optional[Dict] = None
    ) -> None:
        """Update worker heartbeat and status."""
        try:
            update_data = {
                "status": status.value,
                "last_heartbeat": get_current_timestamp()
            }
            
            if resource_usage:
                update_data["resource_usage"] = resource_usage
            
            await self.workers.update_one(
                {"worker_id": worker_id},
                {"$set": update_data}
            )
            
            logger.debug("Updated worker heartbeat", worker_id=worker_id, status=status.value)
            
        except Exception as e:
            logger.error("Failed to update worker heartbeat", worker_id=worker_id, error=str(e))
            raise
    
    async def get_available_workers(self) -> List[WorkerDocument]:
        """Get list of available workers."""
        try:
            # Workers are considered available if they're ready and had heartbeat within 60 seconds
            from datetime import datetime, timezone, timedelta
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=60)
            cutoff_str = cutoff_time.isoformat().replace("+00:00", "Z")
            
            cursor = self.workers.find({
                "status": WorkerStatus.READY.value,
                "last_heartbeat": {"$gte": cutoff_str}
            })
            
            workers = []
            async for worker_dict in cursor:
                workers.append(WorkerDocument(**worker_dict))
            
            return workers
            
        except Exception as e:
            logger.error("Failed to get available workers", error=str(e))
            raise
    
    async def assign_task_to_worker(self, task_id: str, worker_id: str) -> None:
        """Assign a task to a worker."""
        try:
            # Update task with worker assignment
            await self.tasks.update_one(
                {"task_id": task_id},
                {"$set": {
                    "worker_id": worker_id,
                    "status": TaskStatus.ASSIGNED.value,
                    "last_updated": get_current_timestamp()
                }}
            )
            
            # Update worker with current task
            await self.workers.update_one(
                {"worker_id": worker_id},
                {"$set": {
                    "current_task_id": task_id,
                    "status": WorkerStatus.BUSY.value,
                    "last_heartbeat": get_current_timestamp()
                }}
            )
            
            logger.info("Assigned task to worker", task_id=task_id, worker_id=worker_id)
            
        except Exception as e:
            logger.error("Failed to assign task to worker", task_id=task_id, worker_id=worker_id, error=str(e))
            raise

    # Upload session operations
    async def create_upload_session(self, upload_session: UploadSessionDocument) -> str:
        """Create a new upload session record."""
        try:
            session_dict = upload_session.__dict__.copy()
            session_dict['created_at'] = get_current_timestamp()
            if upload_session.expires_at:
                session_dict['expires_at'] = upload_session.expires_at.isoformat()
            
            result = await self.upload_sessions.insert_one(session_dict)
            
            logger.info("Created upload session record", 
                       session_id=upload_session.session_id,
                       video_id=upload_session.video_id)
            return str(result.inserted_id)
            
        except DuplicateKeyError:
            logger.warning("Upload session already exists", session_id=upload_session.session_id)
            raise ValueError("Upload session already exists")
        except Exception as e:
            logger.error("Failed to create upload session", error=str(e))
            raise

    async def get_upload_session(self, session_id: str) -> Optional[UploadSessionDocument]:
        """Get upload session by ID."""
        try:
            session_dict = await self.upload_sessions.find_one({"session_id": session_id})
            if session_dict:
                # Remove MongoDB's _id field
                session_dict.pop('_id', None)
                # Convert string dates to datetime objects
                session_dict = self._convert_string_dates_to_datetime(session_dict)
                # Handle uploaded_chunks - ensure it's a list
                if 'uploaded_chunks' not in session_dict:
                    session_dict['uploaded_chunks'] = []
                return UploadSessionDocument(**session_dict)
            return None
            
        except Exception as e:
            logger.error("Failed to get upload session", session_id=session_id, error=str(e))
            raise

    async def update_upload_session_chunk(self, session_id: str, chunk_number: int, etag: str) -> None:
        """Update upload session with completed chunk."""
        try:
            # Add chunk to uploaded_chunks list and store etag for S3 completion
            await self.upload_sessions.update_one(
                {"session_id": session_id},
                {
                    "$addToSet": {"uploaded_chunks": chunk_number},
                    "$set": {
                        f"parts.{chunk_number}": {"ETag": etag, "PartNumber": chunk_number + 1},
                        "last_chunk_uploaded_at": get_current_timestamp()
                    }
                }
            )
            
            logger.debug("Updated upload session with chunk", 
                        session_id=session_id, chunk_number=chunk_number)
            
        except Exception as e:
            logger.error("Failed to update upload session chunk", 
                        session_id=session_id, chunk_number=chunk_number, error=str(e))
            raise

    async def update_upload_session_status(self, session_id: str, status: str) -> None:
        """Update upload session status."""
        try:
            update_data = {"status": status}
            if status == UploadStatus.COMPLETED:
                update_data["completed_at"] = get_current_timestamp()
            
            await self.upload_sessions.update_one(
                {"session_id": session_id},
                {"$set": update_data}
            )
            
            logger.info("Updated upload session status", 
                       session_id=session_id, status=status)
            
        except Exception as e:
            logger.error("Failed to update upload session status", 
                        session_id=session_id, status=status, error=str(e))
            raise

    async def get_upload_session_parts(self, session_id: str) -> List[Dict[str, Any]]:
        """Get parts list for S3 multipart upload completion."""
        try:
            session_dict = await self.upload_sessions.find_one({"session_id": session_id})
            if not session_dict:
                raise ValueError("Upload session not found")
            
            parts = session_dict.get('parts', {})
            # Convert to list sorted by part number
            parts_list = []
            for chunk_num_str, part_data in parts.items():
                parts_list.append(part_data)
            
            # Sort by PartNumber
            parts_list.sort(key=lambda x: x['PartNumber'])
            
            logger.debug("Retrieved upload session parts", 
                        session_id=session_id, parts_count=len(parts_list))
            
            return parts_list
            
        except Exception as e:
            logger.error("Failed to get upload session parts", 
                        session_id=session_id, error=str(e))
            raise


# Global client instance
_mongodb_client: Optional[MongoDBClient] = None


def get_mongodb_client() -> MongoDBClient:
    """Get global MongoDB client instance."""
    global _mongodb_client
    if _mongodb_client is None:
        _mongodb_client = MongoDBClient()
    return _mongodb_client


async def ensure_connected() -> MongoDBClient:
    """Ensure MongoDB client is connected."""
    client = get_mongodb_client()
    if client.database is None:
        await client.connect()
    return client
