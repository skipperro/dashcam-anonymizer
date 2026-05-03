# MinIO with bucket initialization
FROM minio/minio:latest

# Install MinIO client for bucket creation
RUN curl -L https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc && \
    chmod +x /usr/local/bin/mc

# Copy initialization script
COPY scripts/init-buckets.sh /usr/local/bin/init-buckets.sh
RUN chmod +x /usr/local/bin/init-buckets.sh

# Copy entrypoint script
COPY scripts/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:9000/minio/health/live || exit 1

# Expose ports
EXPOSE 9000 9001

# Use custom entrypoint
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
