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