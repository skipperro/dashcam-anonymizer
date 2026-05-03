# Infrastructure Specification

## Overview
The infrastructure is designed to support a modular and scalable architecture for the Dashcam Anonymizer application. It includes components for storage, communication, and fault tolerance.

## Components
### Main Database (MongoDB)
- **Deployment Options**:
  - Use a managed MongoDB service (e.g., MongoDB Atlas) for scalability.
  - Alternatively, deploy MongoDB as part of the `docker-compose` stack for local or self-hosted environments.
- **Configuration**:
  - Expose the MongoDB service with a secure connection string.
  - Use authentication and role-based access control to secure the database.

### Storage Solution (MinIO or Cloudflare R2)
- **Responsibilities**:
  - Serve as the central storage for video files.
  - Allow clients to upload raw videos and download processed videos.
  - Enable workers to fetch raw videos for processing and upload processed versions.

#### Option 1: Self-Hosted MinIO
- Deploy MinIO as part of the `docker-compose` stack.
- Use MinIO's S3-compatible API for seamless integration with existing tools and libraries.

#### Option 2: Cloudflare R2
- Use Cloudflare R2 as a managed storage solution.
- Leverage its S3-compatible API for integration with existing tools and libraries.

### Communication and Synchronization
- **Message Broker**:
  - Use RabbitMQ as the communication broker to implement a task queue.
  - The main module pushes tasks to RabbitMQ, and workers fetch tasks from it.
- **Worker Coordination**:
  - Workers fetch tasks from RabbitMQ one at a time, ensuring no two workers process the same task.
  - Use acknowledgment mechanisms provided by RabbitMQ to confirm task completion.

### Fault Tolerance and Scaling
- **Worker Failure Handling**:
  - Use RabbitMQ's built-in acknowledgment mechanism to detect worker failures.
  - If a worker goes offline or fails to acknowledge a task, RabbitMQ requeues the task automatically.
- **Horizontal Scaling**:
  - Add more worker instances to handle increased workloads.
- **Monitoring**:
  - Implement logging and monitoring for RabbitMQ, workers, and the main module to ensure smooth operation.
