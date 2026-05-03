# Dashcam Anonymizer - Complete Tech Stack

## 🏗️ Directory Structure

```
dashcam-anonymizer/
├── README.md                          # This file
├── .env.example                       # Environment template
├── .dockerignore                      # Global Docker ignore
├── docker-compose.yml                 # All-in-one development
├── docker-compose.core.yml           # Backend infrastructure
├── docker-compose.frontend.yml       # Frontend service only
├── docker-compose.worker.yml         # Worker deployment
├── docker-compose.nginx.yml          # Nginx proxy (optional)
├── docker-compose.production.yml     # Production overrides
│
├── services/                          # All microservices
│   ├── backend/                       # Python REST API
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── src/                       # Backend application code
│   │
│   ├── frontend/                      # Next.js 14 (React/TypeScript)
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   ├── src/                       # Next.js application (App Router)
│   │   │   ├── app/                   # Routes and layouts
│   │   │   ├── components/            # React components
│   │   │   └── hooks/                 # Custom React hooks
│   │
│   ├── worker/                        # Video processing service ✅
│   │   ├── Dockerfile                 # Already implemented
│   │   ├── requirements.txt
│   │   ├── src/dashcam_worker/
│   │   └── ...
│   │
│   ├── nginx/                         # Reverse proxy
│   │   ├── Dockerfile
│   │   └── config/                    # Nginx configurations
│   │
│   ├── rabbitmq/                      # Message broker
│   │   ├── Dockerfile
│   │   └── config/                    # RabbitMQ configurations
│   │
│   ├── mongodb/                       # Database
│   │   ├── Dockerfile
│   │   └── init/                      # Database initialization scripts
│   │
│   ├── minio/                         # Object storage
│   │   ├── Dockerfile
│   │   └── config/                    # MinIO configurations
│   │
│   └── payment/                       # Payment service (optional)
│       ├── Dockerfile
│       ├── requirements.txt
│       └── src/                       # Payment service code
│
├── scripts/                           # Deployment scripts
│   ├── deploy-all.sh                  # All-in-one deployment
│   ├── deploy-core.sh                 # Backend infrastructure
│   ├── deploy-frontend.sh             # Frontend deployment
│   ├── deploy-workers.sh              # GPU worker deployment
│   ├── scale-workers.sh               # Auto-scale to GPU count
│   └── stop-workers.sh                # Stop all workers
│
├── config/                            # Environment configurations
│   ├── development/                   # Development settings
│   └── production/                    # Production settings
│
├── backend-utils/                     # Shared utilities ✅
├── specifications/                    # Project specifications ✅
└── test-videos/                       # Test video files ✅
```

## 🚀 Deployment Scenarios

### 1. All-in-One Development
```bash
docker-compose up
```
Runs all services on a single machine for development and testing.

### 2. Production Split Architecture
```bash
# Server 1: Backend Infrastructure
docker-compose -f docker-compose.core.yml up

# Server 2: Frontend
docker-compose -f docker-compose.frontend.yml up  

# Server 3+: GPU Workers (auto-detects GPUs)
./scripts/deploy-workers.sh
```

### 3. Custom Deployment
Mix and match services using different compose files as needed.

## 🔧 Service Overview

| Service | Purpose | Port | Dependencies |
|---------|---------|------|--------------|
| **Backend** | REST API, task coordination | 8000 | MongoDB, RabbitMQ, MinIO |
| **Frontend** | Web interface, Next.js server | 3000 | Backend API |
| **Worker** | Video processing | 8080 | RabbitMQ, MinIO |
| **RabbitMQ** | Message broker | 5672, 15672 | None |
| **MongoDB** | Database | 27017 | None |
| **MinIO** | Object storage | 9000, 9001 | None |
| **Nginx** | Reverse proxy | 80, 443 | Frontend, Backend |
| **Payment** | Payment processing | 8001 | MongoDB |

## 📋 Next Steps

1. ✅ **Directory structure created**
2. 🔄 **Create service Dockerfiles**
3. 🔄 **Create docker-compose files**
4. 🔄 **Create deployment scripts**
5. 🔄 **Implement services**

## 🎯 GPU Worker Deployment

Workers are deployed with GPU isolation:
- **Naming**: `[server-name]-gpu[index]` (e.g., `gpu-server-01-gpu0`)
- **GPU Assignment**: One GPU per worker container
- **Memory Limit**: 8GB per worker
- **Auto-scaling**: Detects GPU count and deploys accordingly

```bash
# Example: 4 GPU server deployment
./scripts/deploy-workers.sh gpu-server-01
# Creates: gpu-server-01-gpu0, gpu-server-01-gpu1, gpu-server-01-gpu2, gpu-server-01-gpu3
```
