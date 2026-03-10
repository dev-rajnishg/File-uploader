# AWS Assistant Toolkit (Version 1)

A practical Python toolkit for day-to-day AWS operations with a focus on speed, safety, and fewer manual console steps.

**Expanding to more AWS services** - currently includes:
- S3 operations (`uploader.py`)
- EC2 operations (`aws_assistant.py` + `aws-assistant.cmd`)

## Why This Exists
Managing common AWS tasks directly in the console is repetitive and error-prone, especially for:
- selecting the correct EC2 instance every time
- creating consistent snapshots with useful tags
- launching repeatable instances from standardized settings
- syncing local folders to S3 with clear behavior

Version 1 wraps these operations in simple commands that are easier to repeat, document, and automate.

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

## Project Layout
- `uploader.py`: S3 command-line utility
- `aws_assistant.py`: EC2 command-line utility
- `aws-assistant.cmd`: Windows wrapper for EC2 utility
- `ec2_profiles.example.json`: launch profile template reference
- `instructions.md`: quick command cookbook
- `requirements.txt`: Python dependencies

## Prerequisites
- Python 3.10+
- AWS IAM credentials with required permissions for S3/EC2 operations
- Network access to AWS APIs

## Setup
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

## How To Use
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

## Manual / Operational Notes
- Use least-privilege IAM permissions.
- Prefer `--name`/`--tag` selectors to reduce wrong-instance operations.
- For root volume snapshot consistency, use `--stop-for-root-consistency` on running instances.
- Keep local real profile configs private (`ec2_profiles.json`) and commit only examples.
- Always stop/terminate temporary EC2 test instances to avoid cost.

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

