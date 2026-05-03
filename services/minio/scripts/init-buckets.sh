#!/bin/bash
# Secure MinIO initialization script with access keys and IAM policies

echo "Initializing MinIO with secure configuration..."

# Wait for MinIO to be available
while ! curl -f http://localhost:9000/minio/health/live > /dev/null 2>&1; do
    echo "Waiting for MinIO..."
    sleep 2
done

echo "MinIO is ready, configuring secure access..."

# Configure MinIO client with admin credentials
mc alias set local http://localhost:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD

# Create required buckets (all private by default)
echo "Creating private buckets..."
mc mb local/dashcam-raw-videos 2>/dev/null || echo "Bucket dashcam-raw-videos already exists"
mc mb local/dashcam-processed-videos 2>/dev/null || echo "Bucket dashcam-processed-videos already exists"  
mc mb local/dashcam-thumbnails 2>/dev/null || echo "Bucket dashcam-thumbnails already exists"
mc mb local/dashcam-temp-uploads 2>/dev/null || echo "Bucket dashcam-temp-uploads already exists"

# Remove any public access (ensure all buckets are private)
echo "Ensuring all buckets are private..."
mc anonymous set none local/dashcam-raw-videos 2>/dev/null || true
mc anonymous set none local/dashcam-processed-videos 2>/dev/null || true
mc anonymous set none local/dashcam-thumbnails 2>/dev/null || true
mc anonymous set none local/dashcam-temp-uploads 2>/dev/null || true

# Create IAM policy for worker (restricted access)
echo "Creating worker IAM policy..."
cat > /tmp/worker-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::dashcam-raw-videos",
        "arn:aws:s3:::dashcam-raw-videos/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::dashcam-processed-videos",
        "arn:aws:s3:::dashcam-processed-videos/*"
      ]
    }
  ]
}
EOF

# Create the IAM policy
mc admin policy create local worker-policy /tmp/worker-policy.json || echo "Worker policy already exists"

# Create IAM policy for upload service (temp uploads and thumbnails only)
echo "Creating upload service IAM policy..."
cat > /tmp/upload-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::dashcam-thumbnails",
        "arn:aws:s3:::dashcam-thumbnails/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::dashcam-temp-uploads",
        "arn:aws:s3:::dashcam-temp-uploads/*"
      ]
    }
  ]
}
EOF

# Create the upload IAM policy
mc admin policy create local upload-policy /tmp/upload-policy.json || echo "Upload policy already exists"

# Create IAM policy for backend (full access to all buckets)
echo "Creating backend IAM policy..."
cat > /tmp/backend-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": [
        "arn:aws:s3:::dashcam-raw-videos",
        "arn:aws:s3:::dashcam-raw-videos/*",
        "arn:aws:s3:::dashcam-processed-videos",
        "arn:aws:s3:::dashcam-processed-videos/*",
        "arn:aws:s3:::dashcam-thumbnails",
        "arn:aws:s3:::dashcam-thumbnails/*",
        "arn:aws:s3:::dashcam-temp-uploads",
        "arn:aws:s3:::dashcam-temp-uploads/*"
      ]
    }
  ]
}
EOF

# Create the backend IAM policy
mc admin policy create local backend-policy /tmp/backend-policy.json || echo "Backend policy already exists"

# Create service account for worker with restricted policy
echo "Creating worker service account..."
WORKER_ACCESS_KEY="AKIAWORKER12345678"
WORKER_SECRET_KEY="worker-secret-key-secure-dashcam-2024"

# Create service account without policy first
mc admin user svcacct add local $MINIO_ROOT_USER --access-key "$WORKER_ACCESS_KEY" --secret-key "$WORKER_SECRET_KEY" || echo "Worker service account may already exist"

# Attach the policy to the service account
echo "Attaching worker policy to service account..."
mc admin policy attach local worker-policy --user "$WORKER_ACCESS_KEY" || echo "Policy may already be attached"

# Store the generated keys for reference (in logs)
echo "=== WORKER CREDENTIALS ==="
echo "Access Key: $WORKER_ACCESS_KEY"
echo "Secret Key: $WORKER_SECRET_KEY"
echo "=========================="

# Create upload service credentials  
echo "Creating upload service account..."
UPLOAD_ACCESS_KEY="AKIAUPLOAD24681357"
UPLOAD_SECRET_KEY="upload-secret-key-secure-dashcam-2024"

# Create upload service account
mc admin user svcacct add local $MINIO_ROOT_USER --access-key "$UPLOAD_ACCESS_KEY" --secret-key "$UPLOAD_SECRET_KEY" || echo "Upload service account may already exist"

# Attach the upload policy to the service account
echo "Attaching upload policy to service account..."
mc admin policy attach local upload-policy --user "$UPLOAD_ACCESS_KEY" || echo "Upload policy may already be attached"

# Store the generated keys for reference (in logs)
echo "=== UPLOAD SERVICE CREDENTIALS ==="
echo "Access Key: $UPLOAD_ACCESS_KEY"
echo "Secret Key: $UPLOAD_SECRET_KEY"
echo "================================="

# Create admin access keys for backend
echo "Creating admin access keys for backend..."
ADMIN_ACCESS_KEY="AKIABACKEND12345678"
ADMIN_SECRET_KEY="backend-secret-key-secure-dashcam-2024"

# Create admin service account
mc admin user svcacct add local $MINIO_ROOT_USER --access-key "$ADMIN_ACCESS_KEY" --secret-key "$ADMIN_SECRET_KEY" || echo "Admin service account may already exist"

# Attach the backend policy to the service account
echo "Attaching backend policy to service account..."
mc admin policy attach local backend-policy --user "$ADMIN_ACCESS_KEY" || echo "Backend policy may already be attached"

echo "=== BACKEND CREDENTIALS ==="
echo "Access Key: $ADMIN_ACCESS_KEY" 
echo "Secret Key: $ADMIN_SECRET_KEY"
echo "========================="

# Clean up temporary files
rm -f /tmp/worker-policy.json /tmp/upload-policy.json /tmp/backend-policy.json

echo "Secure MinIO initialization completed!"
echo "All buckets are private - access only through authentication"
echo "Worker has restricted access to raw (read) and processed (read/write) buckets only"
echo "Upload service has restricted access to temp-uploads and thumbnails buckets only"
echo "Backend has full admin access and handles moving files from temp to raw buckets"
