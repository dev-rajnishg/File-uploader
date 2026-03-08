import os
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-1"),
)


def upload_file(file_path: str, bucket: str, s3_key: str = None) -> str:
    """Upload a local file to S3 and return the S3 URL."""
    s3_key = s3_key or os.path.basename(file_path)
    try:
        s3.upload_file(file_path, bucket, s3_key)
        return f"s3://{bucket}/{s3_key}"
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {file_path}")
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Upload failed: {e}")


def list_objects(bucket: str) -> list:
    """List all objects in an S3 bucket."""
    try:
        response = s3.list_objects_v2(Bucket=bucket)
        objects = response.get("Contents", [])
        if not objects:
            print("Bucket is empty.")
            return []
        print(f"\nObjects in '{bucket}':")
        print(f"{'#':<5} {'Key':<50} {'Size':>10}")
        print("-" * 67)
        for i, obj in enumerate(objects, 1):
            size_kb = round(obj["Size"] / 1024, 2)
            print(f"{i:<5} {obj['Key']:<50} {size_kb:>8} KB")
        return [obj["Key"] for obj in objects]
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"List failed: {e}")


def delete_object(bucket: str, s3_key: str) -> None:
    """Delete a single object from S3."""
    try:
        s3.delete_object(Bucket=bucket, Key=s3_key)
        print(f"Deleted: s3://{bucket}/{s3_key}")
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Delete failed: {e}")


if __name__ == "__main__":
    import sys

    usage = (
        "Usage:\n"
        "  python uploader.py <file_path> <bucket> [s3_key]  # upload\n"
        "  python uploader.py list <bucket>                   # list\n"
        "  python uploader.py delete <bucket> <s3_key>        # delete\n"
    )

    if len(sys.argv) < 2:
        print(usage)
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        if len(sys.argv) < 3:
            print(usage)
            sys.exit(1)
        list_objects(sys.argv[2])

    elif command == "delete":
        if len(sys.argv) < 4:
            print(usage)
            sys.exit(1)
        delete_object(sys.argv[2], sys.argv[3])

    else:
        # default: treat as upload
        if len(sys.argv) < 3:
            print(usage)
            sys.exit(1)
        file_path = sys.argv[1]
        bucket = sys.argv[2]
        s3_key = sys.argv[3] if len(sys.argv) > 3 else None
        url = upload_file(file_path, bucket, s3_key)
        print(f"Uploaded: {url}")