# Dashcam Anonymizer 🚗📹

## See It in Action 🎬
Below is an example of what Dashcam Anonymizer can do:

**Original Footage**:
*(Insert image of unedited footage)*

**Anonymized Footage**:
*(Insert image of blurred people and cars)*

## What Is Dashcam Anonymizer? 🌟
Dashcam Anonymizer is a powerful tool that uses cutting-edge AI to protect privacy in dashcam videos. Whether you're sharing footage online or complying with GDPR regulations, this app automatically detects and blurs sensitive objects like people and vehicles, making your videos safe to share.

### Why Use Dashcam Anonymizer? ✨
- **AI-Powered Privacy**: Automatically detects and blurs individuals and vehicles using advanced YOLO models.
- **GDPR Compliance**: Share your videos confidently, knowing they meet privacy regulations.
- **Customizable Settings**: Choose what to blur, select model sizes, and configure detection options.
- **Flexible Deployment**: Run it locally or in the cloud with Docker Compose.

## How It Works 🎥
1. **Upload Your Video**: Drag and drop your dashcam footage into the app.
2. **Let the AI Work Its Magic**: The app processes your video, blurring sensitive objects.
3. **Download and Share**: Once processing is complete, download your anonymized video and share it worry-free.

## Key Features 🌐
- **AI-Powered Anonymization**: Automatically detects and blurs individuals and vehicles using advanced YOLO models, ensuring privacy and compliance with GDPR.
- **Customizable Processing**: Choose what to blur, select model sizes for performance or accuracy, and configure detection options like bounding boxes or segmentation.
- **Seamless Integration**: Works with self-hosted MinIO or Cloudflare R2 for video storage, and uses RabbitMQ for real-time task coordination.
- **Scalable and Flexible**: Supports GPU and non-GPU workers, allowing efficient processing on any infrastructure.

## Deployment Made Easy 🚀
### Prerequisites 📋
- Docker 🐳
- Docker Compose

### Quick Start 🛠️
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd dashcam-anonymizer
   ```
2. Start the application:
   ```bash
   docker-compose -f docker-compose.test.yml up --build
   ```
3. Open your browser and visit: `http://localhost:3000`

## Development Environment Setup 🛠️
For developers working on the project:

### Quick Setup (Recommended) ⚡
```bash
# Clone the repository
git clone <repository-url>
cd dashcam-anonymizer

# Run the automated setup script
./setup-dev-environment.sh

# Activate the shared virtual environment
source venv/bin/activate

# Start infrastructure for testing
docker-compose -f docker-compose.test.yml up -d

# Run tests
cd services/worker && ./run_tests.sh
cd ../backend && ./run_tests.sh
```

### Manual Setup 📚
```bash
# Create shared virtual environment
python3 -m venv venv
source venv/bin/activate

# Install worker dependencies
cd services/worker
pip3 install -r requirements.txt
pip3 install -e .

# Install backend dependencies
cd ../backend  
pip3 install -r requirements.txt
pip3 install -e .
```

### Architecture Notes 🏗️
- **Shared Virtual Environment**: All services use a consolidated virtual environment in the project root (`venv/`) to avoid confusion and save storage space.
- **Individual Test Runners**: Each service has its own `run_tests.sh` script that automatically uses the shared environment.
- **Consolidated Setup**: The root-level `setup-dev-environment.sh` script sets up dependencies for all services at once.

### Testing Guidelines 🧪
- **ALWAYS use `./run_tests.sh`** (never run `pytest` directly) for comprehensive testing
- Each service's test runner includes unit tests, integration tests, and performance validations
- Tests must complete in <1 second per unit test maximum
- All tests must pass before committing code changes
- Test runners automatically handle virtual environment activation and Python paths

1. **Quick Setup**: Run the automated setup script:
   ```bash
   ./setup-dev-environment.sh
   ```

2. **Manual Setup**:
   ```bash
   # Create shared virtual environment
   python3 -m venv venv
   source venv/bin/activate
   
   # Install dependencies for all services
   cd services/worker && pip install -r requirements.txt && pip install -e .
   cd ../backend && pip install -r requirements.txt && pip install -e .
   ```

3. **Running Tests**:
   ```bash
   # Worker tests
   cd services/worker && ./run_tests.sh
   
   # Backend tests  
   cd services/backend && ./run_tests.sh
   ```

The project uses a **shared virtual environment** in the root directory to avoid duplication and save storage space across all services.

## Optional Features 💡
- **Payment System**: Enable credits and subscriptions for video processing.
- **Storage Options**: Choose between self-hosted MinIO or Cloudflare R2 for storing videos.

## Who Is This For? 🤔
- **Content Creators**: Share your dashcam footage online without compromising privacy.
- **Fleet Managers**: Ensure compliance with privacy laws when sharing vehicle footage.
- **Tech Enthusiasts**: Deploy and customize the app to suit your needs.

## Get Involved 🤝
We'd love your feedback! If you encounter any issues or have feature suggestions, feel free to contribute or open an issue on our GitHub repository.

## License 📜
Dashcam Anonymizer is open-source and available under the MIT License. Use it, modify it, and make it your own!
