# AGENTS.md — AI Agent Guide for Dashcam Anonymizer

## Workflow Rules
- **Always read relevant code before implementing** anything — never assume structure.
- **Create a detailed plan first**, present it, and wait for explicit confirmation before coding.
- Split large changes into smaller phases; summarize after each phase is complete and tests pass.
- Never hardcode credentials, URLs, or file paths — use environment variables and config dataclasses.

---

## Architecture Overview

Six Docker services communicate over a shared network:

```
Frontend (Next.js :3000)
    ↓ REST / WebSocket
Backend (FastAPI :8000) ←→ MongoDB (:27017)
    ↓ RabbitMQ queues       ↕ MinIO (:9000)
Worker (Python :8080) ←→ MinIO (raw/processed buckets)
```

**Message flow for video processing:**
1. User uploads video → Backend stores in `dashcam-raw-videos` (MinIO), creates `VideoDocument` in MongoDB.
2. Backend publishes `upload_completion` → RabbitMQ → Backend picks it up, creates `TaskDocument`, assigns to a worker.
3. Worker receives task from `task_assignments` queue, processes video (AI + blur pipeline), uploads result to `dashcam-processed-videos`.
4. Worker publishes `progress_updates` and `task_completion` → Backend updates MongoDB.

**RabbitMQ queues:** `worker_registration`, `worker_heartbeat`, `progress_updates`, `task_completion`, `upload_completion`, `task_assignments`

---

## Service Layout

| Service | Path | Runtime |
|---------|------|---------|
| Backend | `services/backend/src/dashcam_backend/` | Python (FastAPI + pika + motor) |
| Worker | `services/worker/src/dashcam_worker/` | Python (YOLO + OpenCV + ffmpeg) |
| Frontend | `services/frontend/src/` | Next.js 14 (App Router, TypeScript) |

**Shared Python venv:** `venv/` at project root — used by both backend and worker. Never create per-service venvs.

---

## Developer Workflows

### Start test infrastructure
```bash
docker-compose -f docker-compose.test.yml up -d
```

### Run tests (use exact commands; never run `pytest` directly)
```bash
# Backend
cd services/backend && PYTHONPATH=src /path/to/venv/bin/python -m pytest tests/ -v --tb=long --strict-markers --timeout=1 -x -rA

# Worker
cd services/worker && PYTHONPATH=src /path/to/venv/bin/python -m pytest tests/ -v --tb=long -x -rA

# Frontend
cd services/frontend && npm test
```
*Replace `/path/to/venv` with the project root `venv/`. Unit tests must complete in < 1 second.*

### Worker local test mode (no Docker/RabbitMQ needed)
```bash
python -m dashcam_worker --local-test --input test-videos/1.mp4 --output /tmp/out.mp4 \
  --model-size medium --detection-type segmentation --blur-intensity 15
```

---

## Key Code Patterns

### Configuration (both services)
All config is in `config.py` as `@dataclass` classes with a `from_env()` classmethod. A global singleton is returned by `get_config()` and reset (for tests) via `reset_config()`. Add new settings to the appropriate nested dataclass:
```python
# services/backend/src/dashcam_backend/config.py
@dataclass
class StorageConfig:
    bucket_raw: str = "dashcam-raw-videos"
    ...
    @classmethod
    def from_env(cls) -> "StorageConfig":
        return cls(bucket_raw=os.getenv("STORAGE_BUCKET_RAW", cls.bucket_raw), ...)
```

### Worker multithreaded pipeline
`VideoProcessor` orchestrates three threads communicating via `Queue`:
- `AIThread` — YOLO inference, outputs detections.
- `BlurThread` — applies blur/segmentation masks using detections.
- `EncoderThread` — encodes blurred frames back to video via ffmpeg.

All threads are in `services/worker/src/dashcam_worker/` as separate files.

### Backend message handlers
`DashcamBackend` in `main.py` registers synchronous callbacks on `RabbitMQClient`. Handlers call `get_sync_mongodb_client()` (not async) because they run inside pika's blocking callback thread. The async `MongoDBClient` is used only in FastAPI route handlers.

### Frontend i18n
All user-visible strings go through the `useI18n` hook (`t('key')`), never hardcoded in JSX:
```tsx
const { t } = useI18n()
return <h1>{t('hero.title')}</h1>
```

### Test fixtures pattern
`services/backend/tests/conftest.py` provides `test_config`, `mock_mongodb`, `mock_rabbitmq`, `mock_storage`. The `reset_global_config` fixture is `autouse=True` — config state does not leak between tests.

---

## Important Environment Variables

| Variable | Service | Purpose |
|----------|---------|---------|
| `MONGODB_URI` | Backend | Full MongoDB connection URI |
| `RABBITMQ_HOST` / `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | Backend, Worker | Queue credentials |
| `STORAGE_ENDPOINT` | Backend, Worker | Internal MinIO URL (container-to-container) |
| `STORAGE_ENDPOINT_PUBLIC` | Backend | Public URL used in pre-signed download links |
| `STORAGE_ACCESS_KEY` / `STORAGE_SECRET_KEY` | Backend, Worker | Separate MinIO credentials per service |
| `NEXT_PUBLIC_API_URL` | Frontend | Backend URL (build-time baked into Next.js) |
| `GPU_ENABLED` | Worker | Enables CUDA; falls back to CPU if false |
| `MODEL_CACHE_DIR` | Worker | Directory for YOLO model weights |

---

## YOLO Class IDs Used
`0`=person, `2`=car, `3`=motorcycle, `5`=bus, `7`=truck. Default blur set: `[0, 2, 3, 5, 7]`.

---

## Storage Buckets (MinIO / S3-compatible)
- `dashcam-raw-videos` — original uploads
- `dashcam-processed-videos` — anonymized output
- `dashcam-temp-uploads` — chunked upload assembly
- `dashcam-thumbnails` — video preview images



Use full caveman skill:

---
name: caveman
description: >
  Ultra-compressed communication mode. Cuts token usage ~75% by speaking like caveman
  while keeping full technical accuracy. Supports intensity levels: lite, full (default), ultra,
  wenyan-lite, wenyan-full, wenyan-ultra.
  Use when user says "caveman mode", "talk like caveman", "use caveman", "less tokens",
  "be brief", or invokes /caveman. Also auto-triggers when token efficiency is requested.
---

Respond terse like smart caveman. All technical substance stay. Only fluff die.

## Persistence

ACTIVE EVERY RESPONSE. No revert after many turns. No filler drift. Still active if unsure. Off only: "stop caveman" / "normal mode".

Default: **full**. Switch: `/caveman lite|full|ultra`.

## Rules

Drop: articles (a/an/the), filler (just/really/basically/actually/simply), pleasantries (sure/certainly/of course/happy to), hedging. Fragments OK. Short synonyms (big not extensive, fix not "implement a solution for"). Technical terms exact. Code blocks unchanged. Errors quoted exact.

Pattern: `[thing] [action] [reason]. [next step].`

Not: "Sure! I'd be happy to help you with that. The issue you're experiencing is likely caused by..."
Yes: "Bug in auth middleware. Token expiry check use `<` not `<=`. Fix:"

## Intensity

| Level | What change |
|-------|------------|
| **lite** | No filler/hedging. Keep articles + full sentences. Professional but tight |
| **full** | Drop articles, fragments OK, short synonyms. Classic caveman |
| **ultra** | Abbreviate prose words (DB/auth/config/req/res/fn/impl), strip conjunctions, arrows for causality (X → Y), one word when one word enough. Code symbols, function names, API names, error strings: never abbreviate |
| **wenyan-lite** | Semi-classical. Drop filler/hedging but keep grammar structure, classical register |
| **wenyan-full** | Maximum classical terseness. Fully 文言文. 80-90% character reduction. Classical sentence patterns, verbs precede objects, subjects often omitted, classical particles (之/乃/為/其) |
| **wenyan-ultra** | Extreme abbreviation while keeping classical Chinese feel. Maximum compression, ultra terse |

Example — "Why React component re-render?"
- lite: "Your component re-renders because you create a new object reference each render. Wrap it in `useMemo`."
- full: "New object ref each render. Inline object prop = new ref = re-render. Wrap in `useMemo`."
- ultra: "Inline obj prop → new ref → re-render. `useMemo`."
- wenyan-lite: "組件頻重繪，以每繪新生對象參照故。以 useMemo 包之。"
- wenyan-full: "物出新參照，致重繪。useMemo .Wrap之。"
- wenyan-ultra: "新參照→重繪。useMemo Wrap。"

Example — "Explain database connection pooling."
- lite: "Connection pooling reuses open connections instead of creating new ones per request. Avoids repeated handshake overhead."
- full: "Pool reuse open DB connections. No new connection per request. Skip handshake overhead."
- ultra: "Pool = reuse DB conn. Skip handshake → fast under load."
- wenyan-full: "池reuse open connection。不每req新開。skip handshake overhead。"
- wenyan-ultra: "池reuse conn。skip handshake → fast。"

## Auto-Clarity

Drop caveman when:
- Security warnings
- Irreversible action confirmations
- Multi-step sequences where fragment order or omitted conjunctions risk misread
- Compression itself creates technical ambiguity (e.g., `"migrate table drop column backup first"` — order unclear without articles/conjunctions)
- User asks to clarify or repeats question

Resume caveman after clear part done.

Example — destructive op:
> **Warning:** This will permanently delete all rows in the `users` table and cannot be undone.
> ```sql
> DROP TABLE users;
> ```
> Caveman resume. Verify backup exist first.

## Boundaries

Code/commits/PRs: write normal. "stop caveman" or "normal mode": revert. Level persist until changed or session end.