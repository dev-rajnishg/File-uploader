# AWS Assistant Command Sheet (Single Page)

This is the one-file command reference for daily usage.

## 1) Install And Run

Install from GitHub:

pip install "git+https://github.com/dev-rajnishg/File-uploader.git"
pip install "git+https://github.com/dev-rajnishg/File-uploader.git#egg=aws-assistant-toolkit[tui]"

Run help:

aws-assistant --help

If running from source folder:

python aws_assistant.py --help

## 2) First-Time Setup

Create assistant config:

aws-assistant config init
aws-assistant config show

Validate AWS credentials (optional):

python validate_aws_credentials.py

## 3) Unified Assistant Commands

EC2:

aws-assistant ec2 start --name my-dev-box --wait
aws-assistant ec2 stop --tag Environment=dev --wait
aws-assistant ec2 reboot --instance-id i-0123456789abcdef0
aws-assistant ec2 terminate --instance-id i-0123456789abcdef0
aws-assistant ec2 snapshot --name my-dev-box --snapshot-tag Purpose=backup
aws-assistant ec2 snapshot --name my-dev-box --stop-for-root-consistency --snapshot-tag Purpose=root-consistent
aws-assistant ec2 launch --profile dev-web --config ec2_profiles.example.json --wait

S3 via unified CLI:

aws-assistant s3 list my-bucket
aws-assistant s3 delete-bucket my-temp-bucket --force-empty

Lambda via unified CLI forwarding:

aws-assistant lambda create my-function arn:aws:iam::123456789012:role/lambda-role
aws-assistant lambda deploy my-function --config lambda_config.json
aws-assistant lambda test my-function test_events/s3_upload_event.json --tail
aws-assistant lambda schedule list

Container via unified CLI forwarding:

aws-assistant ecs list-services my-cluster
aws-assistant ecs list-tasks my-cluster --service my-service
aws-assistant eks connect my-cluster --region ap-south-1
aws-assistant eks pods --all-namespaces

Logs:

aws-assistant logs lambda my-function --minutes 30 --quick-errors
aws-assistant logs ecs my-cluster abc123def456 --minutes 30 --quick-errors
aws-assistant logs eks my-pod --namespace production --minutes 30 --quick-errors

IAM:

aws-assistant iam summary role my-app-role
aws-assistant iam summary user my-user
aws-assistant iam policy-template s3-read-only --output s3_read_only_policy.json
aws-assistant iam policy-template ec2-start-stop

Cost safety:

aws-assistant safety scan

## 4) TUI Mode

Start TUI:

aws-assistant tui

Fallback plain menu:

aws-assistant tui --plain

Quick Action Palette examples inside TUI:

ec2 stop name my-dev-box
ec2 terminate id i-0123456789abcdef0
logs lambda my-function 30
iam summary role my-app-role
iam template s3-read-only my_policy.json
safety scan

Quick aliases inside TUI palette:

ec2 sp name my-dev-box
ec2 term id i-0123456789abcdef0
ls-lambda my-function 30
iam-sum role my-app-role
iam-tpl s3-read-only my_policy.json
scan

## 5) Legacy Direct Script Commands (Still Supported)

S3:

python uploader.py upload <file_path> <bucket> [s3_key]
python uploader.py list <bucket>
python uploader.py delete <bucket> <s3_key>
python uploader.py presign <bucket> <s3_key> --expires-in 3600
python uploader.py lifecycle <bucket> --show
python uploader.py sync <local_folder> <bucket> --prefix data/ --direction both --delete

Lambda:

python lambda_assistant.py create <function_name> <role_arn>
python lambda_assistant.py deploy <function_name> --config lambda_config.json --update-env
python lambda_assistant.py test <function_name> test_events/custom_event.json --tail
python lambda_assistant.py schedule create <rule_name> <function_name> "rate(1 hour)"
python lambda_assistant.py schedule list
python lambda_assistant.py schedule delete <rule_name>

Containers:

python container_assistant.py ecs register ecs_task_definition.json
python container_assistant.py ecs update-service my-cluster my-service --task-definition my-task:2
python container_assistant.py ecs scale my-cluster my-service 10
python container_assistant.py eks apply k8s_deployment.yaml --namespace production
python container_assistant.py docker build Dockerfile my-app:latest
python container_assistant.py ecr push-flow Dockerfile my-app --tag v1.0 --repository my-app-repo

## 6) Release Build Commands

python -m pip install build twine
python -m build
python -m twine check dist/aws_assistant_toolkit-1.3.0-py3-none-any.whl dist/aws_assistant_toolkit-1.3.0.tar.gz
