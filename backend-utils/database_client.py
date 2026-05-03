"""
Database client for MongoDB checkpoint operations.

Handles progress tracking and checkpoint saving/restoration for fault tolerance
as specified in the worker specification.
"""

from pymongo import MongoClient
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import structlog

from .config import get_config


class DatabaseClient:
    """
    MongoDB client for checkpoint and progress tracking operations.
    
    Handles saving processing progress every 30 seconds and restoration
    on worker restart for fault tolerance.
    """
    
    def __init__(self):
        self.config = get_config()
        self.logger = structlog.get_logger("database_client")
        self.client: Optional[MongoClient] = None
        self.db = None
        self.checkpoints_collection = None
        self._connect()
    
    def _connect(self) -> None:
        """Establish connection to MongoDB."""
        try:
            self.client = MongoClient(self.config.database.uri)
            self.db = self.client[self.config.database.database]
            self.checkpoints_collection = self.db.checkpoints
            
            # Test connection
            self.client.admin.command('ping')
            
            self.logger.info("Connected to MongoDB", 
                           database=self.config.database.database)
            
        except Exception as e:
            self.logger.error("Failed to connect to MongoDB", error=str(e))
            raise
    
    def save_checkpoint(self, task_id: str, current_frame: int, 
                       processed_frames_count: int, total_frames: int = None,
                       additional_data: Dict[str, Any] = None) -> bool:
        """
        Save processing checkpoint to database.
        
        Args:
            task_id: Task identifier
            current_frame: Current frame being processed
            processed_frames_count: Number of frames processed so far
            total_frames: Total number of frames (optional)
            additional_data: Additional checkpoint data (optional)
        
        Returns:
            True if checkpoint saved successfully, False otherwise
        """
        try:
            checkpoint_data = {
                "task_id": task_id,
                "worker_id": self.config.worker_id,
                "current_frame": current_frame,
                "processed_frames_count": processed_frames_count,
                "timestamp": datetime.utcnow(),
                "status": "in_progress"
            }
            
            if total_frames is not None:
                checkpoint_data["total_frames"] = total_frames
            
            if additional_data:
                checkpoint_data.update(additional_data)
            
            # Upsert checkpoint (update if exists, insert if not)
            result = self.checkpoints_collection.update_one(
                {"task_id": task_id},
                {"$set": checkpoint_data},
                upsert=True
            )
            
            self.logger.debug("Checkpoint saved", 
                            task_id=task_id,
                            current_frame=current_frame,
                            processed_frames=processed_frames_count)
            
            return True
            
        except Exception as e:
            self.logger.error("Error saving checkpoint", 
                            task_id=task_id, error=str(e))
            return False
    
    def get_checkpoint(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve checkpoint for a task.
        
        Args:
            task_id: Task identifier
        
        Returns:
            Checkpoint data if found, None otherwise
        """
        try:
            checkpoint = self.checkpoints_collection.find_one({"task_id": task_id})
            
            if checkpoint:
                self.logger.info("Checkpoint retrieved", 
                               task_id=task_id,
                               current_frame=checkpoint.get("current_frame"),
                               processed_frames=checkpoint.get("processed_frames_count"))
            
            return checkpoint
            
        except Exception as e:
            self.logger.error("Error retrieving checkpoint", 
                            task_id=task_id, error=str(e))
            return None
    
    def delete_checkpoint(self, task_id: str) -> bool:
        """
        Delete checkpoint after task completion.
        
        Args:
            task_id: Task identifier
        
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            result = self.checkpoints_collection.delete_one({"task_id": task_id})
            
            if result.deleted_count > 0:
                self.logger.info("Checkpoint deleted", task_id=task_id)
                return True
            else:
                self.logger.warning("No checkpoint found to delete", task_id=task_id)
                return False
                
        except Exception as e:
            self.logger.error("Error deleting checkpoint", 
                            task_id=task_id, error=str(e))
            return False
    
    def mark_checkpoint_completed(self, task_id: str, status: str = "completed") -> bool:
        """
        Mark checkpoint as completed.
        
        Args:
            task_id: Task identifier
            status: Final status ("completed", "failed", "cancelled")
        
        Returns:
            True if updated successfully, False otherwise
        """
        try:
            result = self.checkpoints_collection.update_one(
                {"task_id": task_id},
                {
                    "$set": {
                        "status": status,
                        "completed_at": datetime.utcnow()
                    }
                }
            )
            
            if result.modified_count > 0:
                self.logger.info("Checkpoint marked as completed", 
                               task_id=task_id, status=status)
                return True
            else:
                self.logger.warning("No checkpoint found to update", task_id=task_id)
                return False
                
        except Exception as e:
            self.logger.error("Error marking checkpoint completed", 
                            task_id=task_id, error=str(e))
            return False
    
    def get_incomplete_tasks(self, worker_id: str = None) -> List[Dict[str, Any]]:
        """
        Get list of incomplete tasks for this worker.
        
        Args:
            worker_id: Worker ID to filter by (defaults to current worker)
        
        Returns:
            List of incomplete task checkpoints
        """
        try:
            if worker_id is None:
                worker_id = self.config.worker_id
            
            incomplete_tasks = list(self.checkpoints_collection.find({
                "worker_id": worker_id,
                "status": "in_progress"
            }))
            
            self.logger.info("Retrieved incomplete tasks", 
                           worker_id=worker_id,
                           count=len(incomplete_tasks))
            
            return incomplete_tasks
            
        except Exception as e:
            self.logger.error("Error retrieving incomplete tasks", 
                            worker_id=worker_id, error=str(e))
            return []
    
    def cleanup_old_checkpoints(self, days_old: int = 7) -> int:
        """
        Clean up old checkpoints.
        
        Args:
            days_old: Delete checkpoints older than this many days
        
        Returns:
            Number of checkpoints deleted
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days_old)
            
            result = self.checkpoints_collection.delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            
            deleted_count = result.deleted_count
            
            self.logger.info("Old checkpoints cleaned up", 
                           deleted_count=deleted_count,
                           days_old=days_old)
            
            return deleted_count
            
        except Exception as e:
            self.logger.error("Error cleaning up old checkpoints", error=str(e))
            return 0
    
    def close(self) -> None:
        """Close database connection."""
        try:
            if self.client:
                self.client.close()
                self.logger.info("Database connection closed")
        except Exception as e:
            self.logger.error("Error closing database connection", error=str(e))
