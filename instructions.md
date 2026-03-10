S3 helper commands (`uploader.py`)

Upload
python uploader.py upload <file_path> <bucket> [s3_key]

Legacy shorthand upload (still supported)
python uploader.py <file_path> <bucket> [s3_key]

List objects
python uploader.py list <bucket>

Delete object
python uploader.py delete <bucket> <s3_key>

Generate pre-signed URL (temporary object access)
python uploader.py presign <bucket> <s3_key> --expires-in 3600

Lifecycle rules
Show rules:
python uploader.py lifecycle <bucket> --show

Enable/Update toggles:
python uploader.py lifecycle <bucket> --expire-logs-days 30 --glacier-days 90

Disable toggles:
python uploader.py lifecycle <bucket> --disable-expire-logs --disable-glacier

Bulk sync local folder <-> S3
Upload local -> S3:
python uploader.py sync <local_folder> <bucket> --prefix data/ --direction up

Download S3 -> local:
python uploader.py sync <local_folder> <bucket> --prefix data/ --direction down

Two-way sync and delete destination-only files:
python uploader.py sync <local_folder> <bucket> --prefix data/ --direction both --delete

EC2 helper commands (`aws_assistant.py`)

Start/Stop/Reboot by name/tag (not only instance-id)
python aws_assistant.py ec2 start --name my-dev-box --wait
python aws_assistant.py ec2 stop --tag Environment=dev --wait
python aws_assistant.py ec2 reboot --instance-id i-0123456789abcdef0

Safe snapshot flow (pick instance -> inspect attached volumes -> create snapshots)
python aws_assistant.py ec2 snapshot --name my-dev-box --snapshot-tag Purpose=backup

Root volume consistency option (stop before snapshot, auto-start after)
python aws_assistant.py ec2 snapshot --name my-dev-box --stop-for-root-consistency --snapshot-tag Purpose=root-consistent

Snapshot only selected volumes
python aws_assistant.py ec2 snapshot --name my-dev-box --volume-id vol-0123 --volume-id vol-0456 --snapshot-tag Ticket=OPS-102

Quick launch by profile from JSON/YAML config
python aws_assistant.py ec2 launch --profile dev-web --config ec2_profiles.example.json --wait

`key=value` shorthand is also supported:
python aws_assistant.py ec2 launch profile=dev-web config=ec2_profiles.example.json

Windows command wrapper (same folder):
aws-assistant ec2 launch profile=dev-web config=ec2_profiles.example.json

Lambda helper commands (`lambda_assistant.py`)
Create a new Lambda function
python lambda_assistant.py create demo-lambda-function arn:aws:iam::123456789012:role/lambda-role
python lambda_assistant.py create my-function arn:aws:iam::123456789012:role/lambda-role --runtime python3.12 --memory 512 --timeout 60
Package and deploy Lambda function
python lambda_assistant.py deploy <function_name> --config lambda_config.json --update-env
python lambda_assistant.py deploy <function_name> --source-dir lambda_ --requirements requirements.txt

Test Lambda with event file
python lambda_assistant.py test <function_name> test_events/s3_upload_event.json
python lambda_assistant.py test <function_name> test_events/custom_event.json --tail

Create scheduled Lambda invocation (EventBridge)
Rate-based (every N time units):
python lambda_assistant.py schedule create cleanup-hourly s3-cleanup "rate(1 hour)" --description "Hourly cleanup"

Cron-based (specific times):
python lambda_assistant.py schedule create stop-ec2-nightly ec2-scheduler "cron(0 22 * * ? *)" --description "Stop idle EC2 at 10 PM"

With custom event payload:
python lambda_assistant.py schedule create cleanup s3-cleanup "rate(6 hours)" --event test_events/cleanup_event.json

List EventBridge schedules
python lambda_assistant.py schedule list
python lambda_assistant.py schedule list --function ec2-scheduler

Delete schedule
python lambda_assistant.py schedule delete <rule_name>

Container helper commands (`container_assistant.py`)

ECS: Register task definition from JSON template
python container_assistant.py ecs register ecs_task_definition.json

ECS: Update service with new task definition
python container_assistant.py ecs update-service my-cluster my-service --task-definition my-task:2
python container_assistant.py ecs update-service my-cluster my-service --desired-count 5 --force-deploy

ECS: Scale service (change desired task count)
python container_assistant.py ecs scale my-cluster my-service 10

ECS: List services in cluster
python container_assistant.py ecs list-services my-cluster

ECS: List tasks in cluster
python container_assistant.py ecs list-tasks my-cluster
python container_assistant.py ecs list-tasks my-cluster --service my-service

ECS: Stop a running task
python container_assistant.py ecs stop-task my-cluster abc123def456 --reason "Manual stop"

EKS: Connect to cluster (update kubeconfig)
python container_assistant.py eks connect my-cluster --region ap-south-1
python container_assistant.py eks connect my-cluster --region ap-south-1 --alias my-cluster-prod

EKS: Get cluster information
python container_assistant.py eks info my-cluster

EKS: Apply Kubernetes manifest
python container_assistant.py eks apply deployment.yaml
python container_assistant.py eks apply deployment.yaml --namespace production

EKS: Delete resources from manifest
python container_assistant.py eks delete deployment.yaml --namespace production

EKS: List pods
python container_assistant.py eks pods
python container_assistant.py eks pods --namespace production
python container_assistant.py eks pods --all-namespaces

Docker: Build image from Dockerfile
python container_assistant.py docker build Dockerfile my-app:v1.0
python container_assistant.py docker build Dockerfile my-app:latest --no-cache

Docker: Tag image
python container_assistant.py docker tag my-app:latest my-app:v1.0
python container_assistant.py docker tag my-app:latest 123456789012.dkr.ecr.ap-south-1.amazonaws.com/my-app:latest

Docker: Push image to registry
python container_assistant.py docker push my-app:latest
python container_assistant.py docker push 123456789012.dkr.ecr.ap-south-1.amazonaws.com/my-app:latest

ECR: Create repository
python container_assistant.py ecr create-repo my-app
python container_assistant.py ecr create-repo my-app --immutable --no-scan

ECR: Login to Amazon ECR
python container_assistant.py ecr login

ECR: List images in repository
python container_assistant.py ecr list-images my-app

ECR: Complete build-to-ECR push flow (build -> create repo -> login -> tag -> push)
python container_assistant.py ecr push-flow Dockerfile my-app --tag v1.0
python container_assistant.py ecr push-flow Dockerfile my-app --tag latest --repository my-app-prod