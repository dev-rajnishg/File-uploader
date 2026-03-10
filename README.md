# AWS Assistant Toolkit (Version 1.2)

A practical Python toolkit for day-to-day AWS operations, built for public developer use with a focus on speed, safety, and fewer manual console steps.

**Expanding to more AWS services** - currently includes:
- S3 operations (`uploader.py`)
- EC2 operations (`aws_assistant.py`)
- Lambda deployment & scheduling (`lambda_assistant.py`)
- Container orchestration - ECS, EKS, Docker, ECR (`container_assistant.py`)

**Cross-platform support:** Works on Windows, Linux, and macOS.

## Why This Exists
Managing common AWS tasks directly in the console is repetitive and error-prone, especially for:
- selecting the correct EC2 instance every time
- creating consistent snapshots with useful tags
- launching repeatable instances from standardized settings
- syncing local folders to S3 with clear behavior

Version 1.1 wraps these operations in simple commands that are easier to repeat, document, and automate, and now includes a full Lambda workflow (create, deploy, test, and schedule).

## Features
### S3 (`uploader.py`)
- Upload files
- List bucket objects
- Delete an object
- Generate pre-signed URLs
- Manage lifecycle rules (expire logs, transition to Glacier)
- Sync folder local <-> S3 (`up`, `down`, `both`) with optional delete

### EC2 (`aws_assistant.py`)
- Start/stop/reboot by `instance-id`, `Name` tag, or custom tag
- Safe EBS snapshot flow for one selected instance
- Optional stop/start for root-volume consistency during snapshot
- Launch instance from JSON/YAML profile templates
- `key=value` shorthand support for faster command entry
- Windows wrapper command: `aws-assistant ...`

### Lambda (`lambda_assistant.py`)
- Create new Lambda functions with custom runtime, memory, timeout
- Package Lambda code with dependencies into deployment zip
- Deploy code to existing Lambda functions
- Update environment variables from config file
- Test Lambda functions with saved JSON event files
- Display CloudWatch logs with test results
- Create EventBridge schedules for recurring Lambda invocations
- List and delete scheduled Lambda jobs

### Containers (`container_assistant.py`)
**ECS Operations:**
- Register task definitions from JSON templates
- Update services with zero-downtime deployments
- Scale services (adjust desired task count)
- List services and tasks in clusters
- Stop running tasks

**EKS Operations:**
- Update kubeconfig and connect to clusters in one command
- Get cluster information and status
- Apply/delete Kubernetes manifests
- List pods across namespaces

**Docker & ECR:**
- Build Docker images from Dockerfiles
- Tag and push images to registries
- Create and manage ECR repositories
- ECR login automation
- Complete build-tag-push workflow to ECR
- List images in ECR repositories

## Release Notes
### v1.2.0 (2026-03-10)
- Added `container_assistant.py` for comprehensive container orchestration:
  - ECS task definition registration and service management (update, scale, list)
  - EKS cluster connection and kubectl manifest operations (apply, delete, list pods)
  - Docker build/tag/push workflows with ECR integration
  - ECR repository creation and image management
- Added container example templates: `ecs_task_definition.example.json`, `Dockerfile.example`, `k8s_deployment.example.yaml`
- Added comprehensive container test suite in `tests/test_container_assistant.py`
- Updated `.gitignore` for container artifacts (Dockerfiles, task definitions, k8s manifests)
- Updated documentation with complete container workflows
### v1.1.0 (2026-03-10)
- Added `lambda_assistant.py` with end-to-end Lambda flows: create, package/deploy, test invoke, and schedule management.
- Added Lambda-focused test coverage in `tests/test_lambda_assistant.py` plus supporting test organization under `tests/`.
- Added `setup/` helper scripts for IAM role setup and Lambda handler/account utilities.
- Added `lambda_demo/handler.py` and `test_events/` examples for reproducible local demos.
- Updated docs (`README.md`, `instructions.md`, `LAMBDA_WORKFLOW_DEMO.md`) and dependencies (`requirements.txt`).
- Refined `.gitignore` for a public developer repository: keep examples/tests in git, ignore local secrets and build artifacts.

## Project Layout
- `uploader.py`: S3 command-line utility (all platforms)
- `aws_assistant.py`: EC2 command-line utility (all platforms)
- `lambda_assistant.py`: Lambda deployment & scheduling utility (all platforms)
- `container_assistant.py`: Container orchestration utility - ECS, EKS, Docker, ECR (all platforms)
- `aws-assistant.cmd`: Windows convenience wrapper
- `aws-assistant`: Linux/Mac convenience wrapper (requires `chmod +x`)
- `ec2_profiles.example.json`: launch profile template reference
- `lambda_config.example.json`: Lambda deployment config template
- `ecs_task_definition.example.json`: ECS task definition template
- `Dockerfile.example`: Docker containerization template
- `k8s_deployment.example.yaml`: Kubernetes deployment template
- `test_events/`: example Lambda test event files
- `instructions.md`: quick command cookbook
- `requirements.txt`: Python dependencies
- `tests/`: Unit test files
  - `test_lambda_assistant.py`: Lambda assistant unit tests (20 tests)
  - `test_aws_assistant_ec2.py`: EC2 assistant unit tests  
  - `test_lambda.py`: Legacy Lambda tests
  - `test_container_assistant.py`: Container assistant unit tests
- `setup/`: One-time AWS account setup scripts
  - `setup_lambda_role.py`: Creates IAM execution role for Lambda
  - `get_aws_info.py`: Retrieves AWS account and role information
  - `update_handler.py`: Updates Lambda handler configuration
## Prerequisites
- Python 3.10+ (or `python3` on Linux/Mac)
- AWS IAM credentials with required permissions for S3/EC2 operations
- Network access to AWS APIs

## Setup

### All Platforms
1. Create and activate a virtual environment.
2. Install dependencies:
```bash
pip install -r requirements.txt
```
3. Create `.env` in project root:
```env
AWS_ACCESS_KEY_ID=YOUR_KEY
AWS_SECRET_ACCESS_KEY=YOUR_SECRET
AWS_REGION=ap-south-1
```
4. (Optional) Validate credentials:
```bash
python validate_aws_credentials.py
```

### Linux/Mac Only: Enable Wrapper Script
```bash
chmod +x aws-assistant
```

After this, you can use `./aws-assistant` instead of `python aws_assistant.py`.

## How To Use

**Note:** All commands work cross-platform. Use:
- **Windows:** `python` or `aws-assistant.cmd`
- **Linux/Mac:** `python3` or `./aws-assistant` (after chmod)
### S3 Commands
Upload:
```bash
python uploader.py upload <file_path> <bucket> [s3_key]
```

Legacy shorthand upload:
```bash
python uploader.py <file_path> <bucket> [s3_key]
```

List objects:
```bash
python uploader.py list <bucket>
```

Delete object:
```bash
python uploader.py delete <bucket> <s3_key>
```

Pre-signed URL:
```bash
python uploader.py presign <bucket> <s3_key> --expires-in 3600
```

Lifecycle rules:
```bash
python uploader.py lifecycle <bucket> --show
python uploader.py lifecycle <bucket> --expire-logs-days 30 --glacier-days 90
python uploader.py lifecycle <bucket> --disable-expire-logs --disable-glacier
```

Folder sync:
```bash
python uploader.py sync <local_folder> <bucket> --prefix data/ --direction up
python uploader.py sync <local_folder> <bucket> --prefix data/ --direction down
python uploader.py sync <local_folder> <bucket> --prefix data/ --direction both --delete
```

### EC2 Commands
Start/stop/reboot by selector:
```bash
python aws_assistant.py ec2 start --name my-dev-box --wait
python aws_assistant.py ec2 stop --tag Environment=dev --wait
python aws_assistant.py ec2 reboot --instance-id i-0123456789abcdef0
```

Safe snapshot:
```bash
python aws_assistant.py ec2 snapshot --name my-dev-box --snapshot-tag Purpose=backup
python aws_assistant.py ec2 snapshot --name my-dev-box --stop-for-root-consistency --snapshot-tag Purpose=root-consistent
python aws_assistant.py ec2 snapshot --name my-dev-box --volume-id vol-0123 --volume-id vol-0456 --snapshot-tag Ticket=OPS-102
```

Launch from profile config:
```bash
python aws_assistant.py ec2 launch --profile dev-web --config ec2_profiles.example.json --wait
```

Shorthand (`key=value`):
```bash
python aws_assistant.py ec2 launch profile=dev-web config=ec2_profiles.example.json
```

Windows wrapper:
```bash
aws-assistant ec2 launch profile=dev-web config=ec2_profiles.example.json
```

### Lambda Commands
Create new Lambda function:
```bash
python lambda_assistant.py create <function_name> <role_arn>
python lambda_assistant.py create my-function arn:aws:iam::123456789012:role/lambda-role --runtime python3.12 --memory 512 --timeout 60
```

Package and deploy:
```bash
python lambda_assistant.py deploy <function_name> --config lambda_config.json
python lambda_assistant.py deploy <function_name> --source-dir lambda_ --requirements requirements.txt
python lambda_assistant.py deploy <function_name> --config lambda_config.json --update-env
```

Test with event file:
```bash
python lambda_assistant.py test <function_name> test_events/s3_upload_event.json
python lambda_assistant.py test <function_name> test_events/custom_event.json --tail
python lambda_assistant.py test <function_name> test_events/custom_event.json --no-logs
```

Create scheduled Lambda:
```bash
python lambda_assistant.py schedule create <rule_name> <function_name> "rate(1 hour)"
python lambda_assistant.py schedule create <rule_name> <function_name> "cron(0 22 * * ? *)" --description "Nightly cleanup"
python lambda_assistant.py schedule create <rule_name> <function_name> "rate(1 day)" --event test_events/event.json
```

List and delete schedules:
```bash
python lambda_assistant.py schedule list
python lambda_assistant.py schedule list --function <function_name>
python lambda_assistant.py schedule delete <rule_name>
```

### Container Commands

**ECS Operations:**

Register task definition:
```bash
python container_assistant.py ecs register ecs_task_definition.json
```

Update service:
```bash
python container_assistant.py ecs update-service my-cluster my-service --task-definition my-task:2
python container_assistant.py ecs update-service my-cluster my-service --desired-count 5 --force-deploy
```

Scale service:
```bash
python container_assistant.py ecs scale my-cluster my-service 10
```

List services and tasks:
```bash
python container_assistant.py ecs list-services my-cluster
python container_assistant.py ecs list-tasks my-cluster --service my-service
```

Stop task:
```bash
python container_assistant.py ecs stop-task my-cluster abc123def456 --reason "Manual stop"
```

**EKS Operations:**

Connect to cluster:
```bash
python container_assistant.py eks connect my-cluster --region ap-south-1 --alias my-cluster-prod
```

Get cluster info:
```bash
python container_assistant.py eks info my-cluster
```

Apply/delete manifests:
```bash
python container_assistant.py eks apply deployment.yaml --namespace production
python container_assistant.py eks delete deployment.yaml --namespace production
```

List pods:
```bash
python container_assistant.py eks pods --namespace default
python container_assistant.py eks pods --all-namespaces
```

**Docker Operations:**

Build image:
```bash
python container_assistant.py docker build Dockerfile my-app:v1.0
python container_assistant.py docker build Dockerfile my-app:latest --no-cache
```

Tag image:
```bash
python container_assistant.py docker tag my-app:latest my-app:v1.0
```

Push image:
```bash
python container_assistant.py docker push my-app:latest
```

**ECR Operations:**

Create repository:
```bash
python container_assistant.py ecr create-repo my-app
python container_assistant.py ecr create-repo my-app --immutable --no-scan
```

ECR login:
```bash
python container_assistant.py ecr login
```

List images:
```bash
python container_assistant.py ecr list-images my-app
```

Complete build and push flow:
```bash
python container_assistant.py ecr push-flow Dockerfile my-app --tag v1.0 --repository my-app-repo
```

## Lambda Config Example
Use `lambda_config.example.json` as a base:
```json
{
  "functions": {
    "my-function": {
      "source_dir": "lambda_",
      "requirements": "requirements.txt",
      "output_zip": "dist/my-function.zip",
      "environment": {
        "TARGET_BUCKET": "my-bucket",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

## EC2 Profile Config Example
Use `ec2_profiles.example.json` as a base:
```json
{
  "security_group_templates": {
    "web": ["sg-0123456789abcdef0"]
  },
  "profiles": {
    "dev-web": {
      "ami": "ami-0123456789abcdef0",
      "instance_type": "t3.micro",
      "key_pair": "my-keypair",
      "subnet_id": "subnet-0123456789abcdef0",
      "sg_template": "web",
      "tags": {
        "Name": "dev-web",
        "Environment": "dev"
      }
    }
  }
}
```

## Container Config Examples

### ECS Task Definition Template
Use `ecs_task_definition.example.json` as a base:
```json
{
  "family": "my-app-task",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "256",
  "memory": "512",
  "containerDefinitions": [{
    "name": "my-app-container",
    "image": "<ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/my-app:latest",
    "portMappings": [{"containerPort": 8080, "protocol": "tcp"}],
    "environment": [
      {"name": "ENV", "value": "production"}
    ],
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group": "/ecs/my-app",
        "awslogs-region": "ap-south-1"
      }
    },
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"]
    }
  }]
}
```

### Kubernetes Deployment Template
Use `k8s_deployment.example.yaml` as a base:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app-deployment
spec:
  replicas: 3
  selector:
    matchLabels:
      app: my-app
  template:
    spec:
      containers:
      - name: my-app
        image: <ACCOUNT_ID>.dkr.ecr.ap-south-1.amazonaws.com/my-app:latest
        ports:
        - containerPort: 8080
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
---
apiVersion: v1
kind: Service
metadata:
  name: my-app-service
spec:
  selector:
    app: my-app
  ports:
    - port: 80
      targetPort: 8080
  type: LoadBalancer
```

## Manual / Operational Notes
- Use least-privilege IAM permissions.
- Prefer `--name`/`--tag` selectors to reduce wrong-instance operations.
- For root volume snapshot consistency, use `--stop-for-root-consistency` on running instances.
- Keep local real profile configs private (`ec2_profiles.json`, `lambda_config.json`, `ecs_task_definition.json`, `Dockerfile`, `k8s_deployment.yaml`) and commit only examples.
- Always stop/terminate temporary EC2 test instances to avoid cost.
- Test Lambda functions with sample events before creating schedules.
- Keep test event files with sensitive data in gitignore.
- For ECS/EKS: Ensure proper IAM roles (ecsTaskExecutionRole, ecsTaskRole) exist before deploying.
- For ECR: Login expires after 12 hours; re-run `ecr login` if push fails.
- For EKS: Requires kubectl and AWS CLI installed; run `eks connect` before using kubectl commands.
- For Docker: Ensure Docker daemon is running locally before build/tag/push operations.

## Comparison: Version 1 vs Previous Workflow
### Previous workflow (manual console + ad-hoc commands)
- Repeated clicking in AWS Console for common tasks
- Harder to standardize launch settings between environments
- Snapshot tagging inconsistent across team members
- Instance targeting often done via instance-id lookup each time
- Sync behavior between local and S3 not centralized

### Version 1 (this toolkit)
- Single command layer for routine S3 + EC2 workflows
- Launch profiles provide repeatable infrastructure parameters
- Snapshot flow auto-applies useful source tags
- Instance actions can target by name/tag, not only ID
- Sync behavior is explicit (`up`/`down`/`both`, optional delete)
- Easier onboarding due to codified commands and examples

## Limitations (Current V1 Scope)
- Credentials currently read from `.env` (no advanced profile/STS workflow yet)
- No dry-run mode for EC2 actions yet
- No built-in automated snapshot retention cleanup yet

