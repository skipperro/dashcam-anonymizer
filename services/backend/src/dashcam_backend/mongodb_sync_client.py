"""Synchronous MongoDB client for message handlers."""

import threading
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
import pymongo
from pymongo.errors import DuplicateKeyError, ConnectionFailure, ServerSelectionTimeoutError

from .config import get_config
from .logging import get_logger
from .models import (
    VideoDocument, TaskDocument, WorkerDocument, UserDocument,
    VideoStatus, TaskStatus, WorkerStatus, get_current_timestamp
)


logger = get_logger(__name__)

# Thread-local storage for sync MongoDB client
_thread_local = threading.local()


class SyncMongoDBClient:
    """Synchronous MongoDB client for message handlers."""
    
    def __init__(self):
        self.config = get_config().mongodb
        self.client: Optional[pymongo.MongoClient] = None
        self.database = None
        
        # Collection references
        self.users = None
        self.videos = None
        self.tasks = None
        self.workers = None
    
    def connect(self) -> None:
        """Connect to MongoDB and initialize collections."""
        try:
            self.client = pymongo.MongoClient(
                self.config.uri,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                connectTimeoutMS=5000,
                socketTimeoutMS=5000,
            )
            
            # Test connection
            self.client.admin.command('ping')
            
            # Get database
            self.database = self.client[self.config.database_name]
            
            # Get collection references
            self.users = self.database.users
            self.videos = self.database.videos
            self.tasks = self.database.tasks
            self.workers = self.database.workers
            
            # Create indexes
            self._create_indexes()
            
            logger.info("Connected to MongoDB (sync client)")
            
        except Exception as e:
            logger.error("Failed to connect to MongoDB (sync client)", error=str(e))
            raise
    
    def _create_indexes(self) -> None:
        """Create necessary indexes."""
        try:
            # Helper function to create index safely
            def create_index_safe(collection, *args, **kwargs):
                try:
                    collection.create_index(*args, **kwargs)
                except pymongo.errors.OperationFailure as e:
                    if e.code == 86:  # IndexKeySpecsConflict
                        logger.debug(f"Index already exists with different specs in {collection.name}, skipping")
                    else:
                        raise
            
            # User indexes
            create_index_safe(self.users, "user_id", unique=True)
            create_index_safe(self.users, "email", unique=True)
            
            # Video indexes
            create_index_safe(self.videos, "video_id", unique=True)
            create_index_safe(self.videos, "user_id")
            create_index_safe(self.videos, "status")
            
            # Task indexes
            create_index_safe(self.tasks, "task_id", unique=True)
            create_index_safe(self.tasks, "video_id")
            create_index_safe(self.tasks, "user_id")
            create_index_safe(self.tasks, "worker_id")
            create_index_safe(self.tasks, "status")
            
            # Worker indexes
            create_index_safe(self.workers, "worker_id", unique=True)
            create_index_safe(self.workers, "status")
            
            logger.info("MongoDB indexes created (sync client)")
            
        except Exception as e:
            logger.error("Failed to create MongoDB indexes (sync client)", error=str(e))
    
    def register_worker(self, worker: WorkerDocument) -> None:
        """Register a new worker."""
        try:
            worker_dict = {
                "worker_id": worker.worker_id,
                "hostname": worker.hostname,
                "status": worker.status,
                "capabilities": worker.capabilities,
                "current_task_id": worker.current_task_id,
                "resource_usage": worker.resource_usage,
                "last_heartbeat": get_current_timestamp(),
                "registered_at": get_current_timestamp()
            }
            
            # Use upsert to handle re-registration
            self.workers.replace_one(
                {"worker_id": worker.worker_id},
                worker_dict,
                upsert=True
            )
            
            logger.info("Worker registered (sync)", worker_id=worker.worker_id)
            
        except Exception as e:
            logger.error("Failed to register worker (sync)", worker_id=worker.worker_id, error=str(e))
            raise
    
    def update_worker_heartbeat(self, worker_id: str, status: WorkerStatus, resource_usage: Optional[Dict[str, Any]] = None) -> None:
        """Update worker heartbeat."""
        try:
            update_doc = {
                "status": status.value if isinstance(status, WorkerStatus) else status,
                "last_heartbeat": get_current_timestamp()
            }
            
            if resource_usage:
                update_doc["resource_usage"] = resource_usage
            
            result = self.workers.update_one(
                {"worker_id": worker_id},
                {"$set": update_doc}
            )
            
            if result.matched_count == 0:
                logger.warning("Worker not found for heartbeat update (sync)", worker_id=worker_id)
            else:
                logger.debug("Worker heartbeat updated (sync)", worker_id=worker_id)
                
        except Exception as e:
            logger.error("Failed to update worker heartbeat (sync)", worker_id=worker_id, error=str(e))
            raise
    
    def update_task_progress(self, task_id: str, progress_percentage: float, current_frame: Optional[int] = None,
                             total_frames: Optional[int] = None, fps: Optional[float] = None,
                             estimated_time_remaining: Optional[float] = None) -> None:
        """Update task progress. updated_at is used to detect stuck workers."""
        try:
            now = get_current_timestamp()
            update_doc = {
                "progress_percentage": progress_percentage,
                "status": TaskStatus.PROCESSING.value,
                "updated_at": now,
            }

            if current_frame is not None:
                update_doc["current_frame"] = current_frame
            if total_frames is not None:
                update_doc["total_frames"] = total_frames
            if fps is not None:
                update_doc["fps"] = fps
            if estimated_time_remaining is not None:
                update_doc["estimated_time_remaining"] = estimated_time_remaining

            result = self.tasks.update_one(
                {"task_id": task_id},
                {"$set": update_doc}
            )

            if result.matched_count == 0:
                logger.warning("Task not found for progress update (sync)", task_id=task_id)
            else:
                logger.debug("Task progress updated (sync)", task_id=task_id, progress=progress_percentage)

        except Exception as e:
            logger.error("Failed to update task progress (sync)", task_id=task_id, error=str(e))
            raise
    
    def update_task_status(self, task_id: str, status: TaskStatus) -> None:
        """Update task status."""
        try:
            update_doc = {
                "status": status.value if isinstance(status, TaskStatus) else status,
                "updated_at": get_current_timestamp()
            }
            
            if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                update_doc["completed_at"] = get_current_timestamp()
            
            result = self.tasks.update_one(
                {"task_id": task_id},
                {"$set": update_doc}
            )
            
            if result.matched_count == 0:
                logger.warning("Task not found for status update (sync)", task_id=task_id)
            else:
                logger.info("Task status updated (sync)", task_id=task_id, status=status.value)
                
        except Exception as e:
            logger.error("Failed to update task status (sync)", task_id=task_id, error=str(e))
            raise
    
    def update_video_processed_file_path(self, video_id: str, file_path: str) -> None:
        """Store the path of the processed (anonymised) video file."""
        try:
            result = self.videos.update_one(
                {"video_id": video_id},
                {"$set": {"processed_file_path": file_path, "updated_at": get_current_timestamp()}}
            )
            if result.matched_count == 0:
                logger.warning("Video not found for processed_file_path update (sync)", video_id=video_id)
            else:
                logger.info("Video processed_file_path updated (sync)", video_id=video_id, file_path=file_path)
        except Exception as e:
            logger.error("Failed to update video processed_file_path (sync)", video_id=video_id, error=str(e))
            raise

    def update_video_status(self, video_id: str, status: VideoStatus) -> None:
        """Update video status."""
        try:
            update_doc = {
                "status": status.value if isinstance(status, VideoStatus) else status,
                "updated_at": get_current_timestamp()
            }
            
            result = self.videos.update_one(
                {"video_id": video_id},
                {"$set": update_doc}
            )
            
            if result.matched_count == 0:
                logger.warning("Video not found for status update (sync)", video_id=video_id)
            else:
                logger.info("Video status updated (sync)", video_id=video_id, status=status.value)
                
        except Exception as e:
            logger.error("Failed to update video status (sync)", video_id=video_id, error=str(e))
            raise
    
    def get_task_by_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task by ID."""
        try:
            return self.tasks.find_one({"task_id": task_id})
        except Exception as e:
            logger.error("Failed to get task (sync)", task_id=task_id, error=str(e))
            return None
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        try:
            return self.users.find_one({"user_id": user_id})
        except Exception as e:
            logger.error("Failed to get user (sync)", user_id=user_id, error=str(e))
            return None
    
    def update_user_credits(self, user_id: str, new_credits: float) -> None:
        """Update user credits."""
        try:
            result = self.users.update_one(
                {"user_id": user_id},
                {"$set": {"credits": new_credits, "updated_at": get_current_timestamp()}}
            )
            
            if result.matched_count == 0:
                logger.warning("User not found for credits update (sync)", user_id=user_id)
            else:
                logger.info("User credits updated (sync)", user_id=user_id, credits=new_credits)
                
        except Exception as e:
            logger.error("Failed to update user credits (sync)", user_id=user_id, error=str(e))
            raise
    
    def create_task(self, task: TaskDocument) -> None:
        """Create a new task."""
        try:
            task_dict = {
                "task_id": task.task_id,
                "video_id": task.video_id,
                "user_id": task.user_id,
                "worker_id": task.worker_id,
                "status": task.status,
                "progress_percentage": task.progress_percentage,
                "current_frame": task.current_frame,
                "fps": task.fps,
                "estimated_time_remaining": task.estimated_time_remaining,
                "created_at": get_current_timestamp(),
                "updated_at": get_current_timestamp()
            }
            
            self.tasks.insert_one(task_dict)
            logger.info("Task created (sync)", task_id=task.task_id)
            
        except DuplicateKeyError:
            logger.warning("Task already exists (sync)", task_id=task.task_id)
        except Exception as e:
            logger.error("Failed to create task (sync)", task_id=task.task_id, error=str(e))
            raise
    
    def get_video_by_id(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Get video by ID."""
        try:
            return self.videos.find_one({"video_id": video_id})
        except Exception as e:
            logger.error("Failed to get video (sync)", video_id=video_id, error=str(e))
            return None
    
    def get_available_workers(self) -> List[Dict[str, Any]]:
        """Get list of available workers."""
        try:
            return list(self.workers.find({
                "status": WorkerStatus.READY.value,
                "current_task_id": None
            }))
        except Exception as e:
            logger.error("Failed to get available workers (sync)", error=str(e))
            return []

    def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Get all tasks in PENDING state that are waiting for a worker assignment."""
        try:
            return list(self.tasks.find(
                {"status": TaskStatus.PENDING.value},
                sort=[("created_at", 1)]  # oldest first
            ))
        except Exception as e:
            logger.error("Failed to get pending tasks (sync)", error=str(e))
            return []
    
    def get_videos_without_active_task(self) -> List[Dict[str, Any]]:
        """
        Find videos in UPLOADED or QUEUED status that have no active
        (PENDING / ASSIGNED / PROCESSING) task.

        These are videos whose upload_completion event was never processed —
        e.g. the backend was down when the message arrived, or it expired from the queue.
        """
        try:
            candidate_statuses = [VideoStatus.UPLOADED.value, VideoStatus.QUEUED.value]
            candidates = list(self.videos.find(
                {"status": {"$in": candidate_statuses}, "deleted": {"$ne": True}},
                sort=[("upload_date", 1)]  # oldest first
            ))
            if not candidates:
                return []

            candidate_ids = [v["video_id"] for v in candidates]
            active_statuses = [
                TaskStatus.PENDING.value,
                TaskStatus.ASSIGNED.value,
                TaskStatus.PROCESSING.value,
            ]
            active_tasks = list(self.tasks.find({
                "video_id": {"$in": candidate_ids},
                "status": {"$in": active_statuses}
            }))
            covered_video_ids = {t["video_id"] for t in active_tasks}

            return [v for v in candidates if v["video_id"] not in covered_video_ids]
        except Exception as e:
            logger.error("Failed to get videos without active task (sync)", error=str(e))
            return []
    def assign_task_to_worker(self, task_id: str, worker_id: str) -> None:
        """Assign task to worker and mark worker BUSY."""
        try:
            self.tasks.update_one(
                {"task_id": task_id},
                {"$set": {"worker_id": worker_id, "status": TaskStatus.ASSIGNED.value, "updated_at": get_current_timestamp()}}
            )
            self.workers.update_one(
                {"worker_id": worker_id},
                {"$set": {"current_task_id": task_id, "status": WorkerStatus.BUSY.value, "updated_at": get_current_timestamp()}}
            )
            logger.info("Task assigned to worker (sync)", task_id=task_id, worker_id=worker_id)
        except Exception as e:
            logger.error("Failed to assign task to worker (sync)", task_id=task_id, worker_id=worker_id, error=str(e))
            raise

    def mark_worker_ready(self, worker_id: str) -> None:
        """Reset worker to READY and clear its current task after a task finishes."""
        try:
            self.workers.update_one(
                {"worker_id": worker_id},
                {"$set": {"current_task_id": None, "status": WorkerStatus.READY.value,
                          "updated_at": get_current_timestamp()}}
            )
            logger.info("Worker marked ready (sync)", worker_id=worker_id)
        except Exception as e:
            logger.error("Failed to mark worker ready (sync)", worker_id=worker_id, error=str(e))
    
    def disconnect(self) -> None:
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB (sync client)")

    def reset_task_to_pending(self, task_id: str) -> None:
        """Reset a stuck task to PENDING and clear all progress fields."""
        try:
            self.tasks.update_one(
                {"task_id": task_id},
                {"$set": {
                    "status": TaskStatus.PENDING.value,
                    "worker_id": None,
                    "progress_percentage": 0.0,
                    "current_frame": 0,
                    "total_frames": 0,
                    "fps": None,
                    "estimated_time_remaining": None,
                    "updated_at": get_current_timestamp(),
                }}
            )
            logger.info("Task reset to pending (sync)", task_id=task_id)
        except Exception as e:
            logger.error("Failed to reset task to pending (sync)", task_id=task_id, error=str(e))

    def get_no_progress_tasks(self, stale_minutes: int = 2) -> List[Dict[str, Any]]:
        """
        Find tasks in ASSIGNED or PROCESSING state whose updated_at is older than
        stale_minutes. These are tasks where the worker stopped sending progress
        (crashed or restarted).
        """
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)).isoformat()
        try:
            return list(self.tasks.find({
                "status": {"$in": [TaskStatus.ASSIGNED.value, TaskStatus.PROCESSING.value]},
                "updated_at": {"$lt": cutoff},
            }))
        except Exception as e:
            logger.error("Failed to get no-progress tasks (sync)", error=str(e))
            return []

    def get_videos_older_than(self, max_age_days: int) -> List[Dict[str, Any]]:
        """Return all non-deleted videos whose upload_date is older than max_age_days."""
        from datetime import datetime, timezone, timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        try:
            return list(self.videos.find({
                "upload_date": {"$lt": cutoff},
                "deleted": {"$ne": True},
            }))
        except Exception as e:
            logger.error("Failed to get old videos (sync)", error=str(e))
            return []

    def delete_video_document(self, video_id: str) -> None:
        """Hard-delete a video document from MongoDB."""
        try:
            self.videos.delete_one({"video_id": video_id})
            logger.info("Video document deleted (sync)", video_id=video_id)
        except Exception as e:
            logger.error("Failed to delete video document (sync)", video_id=video_id, error=str(e))
            raise

    def delete_tasks_for_video(self, video_id: str) -> None:
        """Delete all task documents associated with a video."""
        try:
            result = self.tasks.delete_many({"video_id": video_id})
            logger.info("Tasks deleted for video (sync)", video_id=video_id, count=result.deleted_count)
        except Exception as e:
            logger.error("Failed to delete tasks for video (sync)", video_id=video_id, error=str(e))
            raise


def get_sync_mongodb_client() -> SyncMongoDBClient:
    """Get thread-local synchronous MongoDB client instance."""
    if not hasattr(_thread_local, 'sync_mongodb_client'):
        _thread_local.sync_mongodb_client = SyncMongoDBClient()
        _thread_local.sync_mongodb_client.connect()
    return _thread_local.sync_mongodb_client