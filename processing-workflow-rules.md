# Video Processing Workflow Rules

## Status Lifecycle

```
uploading → uploaded → processing → processed
                ↑           |
                └───────────┘  (if worker dies)
```

---

## Rule 1: Upload Completion

- Video status is set to **`uploaded`** when the **last chunk is assembled** into the final file in MinIO.
- No RabbitMQ message is sent or consumed for this transition.
- The `upload_completion` queue and its handler are **removed entirely**.

---

## Rule 2: Task Dispatch (Backend Polling)

- Every **30 seconds** the backend scans for all videos in **`uploaded`** status that have **no active task** (no task in `pending`, `assigned`, or `processing` state for that video).
- For each such video, a `TaskDocument` is created with status `pending`.
- The backend then tries to find an **idle worker** (registered and with a recent heartbeat).
- If a worker is available:
  - Task status → **`assigned`**
  - Video status → **`processing`**
  - Task message is sent to the worker's personal assignment queue.
- If no worker is available: task stays **`pending`**, video stays **`uploaded`**. Next 30-second cycle will retry.

---

## Rule 3: Processing Progress Updates

- After **each processed frame**, the worker publishes a progress message to the `progress_updates` queue containing:
  - `task_id`
  - `video_id`
  - `current_frame` — frame number just processed
  - `total_frames` — total frames in the video
  - `timestamp` — UTC timestamp of when this frame was processed
- Backend receives the message and updates the `TaskDocument` in MongoDB:
  - `current_frame`
  - `total_frames`
  - `progress_percentage` = `(current_frame / total_frames) * 100`
  - `last_updated` = timestamp from the message (or reception time if absent)

---

## Rule 4: Stuck Worker Detection

- If a task is in **`processing`** (or `assigned`) status and its `last_updated` field is older than **2 minutes**, the worker is assumed to be broken/crashed.
- Action:
  - Task status → **`pending`** (worker assignment cleared)
  - Video status → **`uploaded`**
  - Progress fields reset: `current_frame = 0`, `total_frames = 0`, `progress_percentage = 0.0`, `last_updated = null`
- The regular 30-second dispatch cycle will pick up the video on the next tick and reassign it.
- **No immediate reassignment** at detection time — rely on the dispatch cycle to keep logic in one place.

---

## Rule 5: Processing Completion

- When the worker finishes processing a video and uploads the result to the `dashcam-processed-videos` bucket, it publishes a completion message to `task_completion` containing:
  - `task_id`
  - `video_id`
  - `status`: `"completed"` or `"failed"`
  - `output_file_path`: path in the processed bucket
- Backend receives the message:
  - On **success**:
    - Task status → **`completed`**
    - Video status → **`processed`**
    - `processed_file_path` stored on the `VideoDocument`
  - On **failure**:
    - Task status → **`failed`**
    - Video status → **`uploaded`** (so it can be retried by the dispatch cycle)

---

## Summary Table

| Event                      | Trigger        | Video Status             | Task Status                     |
|----------------------------|----------------|--------------------------|---------------------------------|
| Last chunk assembled       | Upload API     | `uploaded`               | —                               |
| 30s poll finds idle worker | Backend daemon | `processing`             | `assigned` → `processing`       |
| No worker available        | Backend daemon | `uploaded` (unchanged)   | `pending`                       |
| Progress frame received    | Worker message | `processing` (unchanged) | `processing` (progress updated) |
| No progress for 2 min      | Backend daemon | `uploaded`               | `pending` (progress cleared)    |
| Worker reports success     | Worker message | `processed`              | `completed`                     |
| Worker reports failure     | Worker message | `uploaded`               | `failed`                        |

---

## What Is Removed

- `upload_completion` RabbitMQ queue and exchange binding.
- `_handle_upload_completion` message handler in backend.
- Any code that published an `upload_completion` event after the final chunk was assembled.
- Worker heartbeat-based offline detection (replaced by the simpler per-task `last_updated` check in Rule 4).
