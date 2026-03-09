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