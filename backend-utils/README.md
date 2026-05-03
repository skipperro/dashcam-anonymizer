# Backend Utilities

This directory contains utility modules that were designed for the backend service but are not needed by the worker.

## Database Client

The `database_client.py` module provides MongoDB connectivity for checkpointing and task state management. This was originally designed for the worker but has been moved here because:

1. **Worker Design Change**: The worker is now stateless and communicates only via RabbitMQ
2. **Backend Responsibility**: Task tracking, checkpointing, and persistent state should be managed by the backend service
3. **Simplified Architecture**: Removes database dependency from workers, making them easier to deploy and scale

## Usage

If you're building the backend service, you can use this database client for:

- Task state management
- Progress checkpointing  
- Worker registration tracking
- Historical processing data

## MongoDB Collections

The database client is designed to work with these collections:

- `tasks` - Task definitions and status
- `checkpoints` - Processing progress checkpoints
- `workers` - Worker registration and capabilities

## Integration

To use in your backend service:

```python
from backend_utils.database_client import DatabaseClient

# Initialize
db_client = DatabaseClient()

# Use for task management
db_client.save_checkpoint(task_id, current_frame, total_frames)
db_client.get_incomplete_tasks()
```

The database client was fully implemented and tested, so it's ready to be integrated into your backend service.
