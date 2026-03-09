import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "ap-south-1"),
)

MANAGED_LOG_EXPIRY_RULE_ID = "app-auto-expire-logs"
MANAGED_GLACIER_RULE_ID = "app-transition-glacier"


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


def generate_presigned_url(bucket: str, s3_key: str, expires_in: int = 3600) -> str:
    """Generate a temporary pre-signed URL for an object."""
    try:
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": s3_key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Pre-signed URL generation failed: {e}")


def _get_existing_lifecycle_rules(bucket: str) -> list:
    """Return existing lifecycle rules; empty when none are configured."""
    try:
        response = s3.get_bucket_lifecycle_configuration(Bucket=bucket)
        return response.get("Rules", [])
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code in {"NoSuchLifecycleConfiguration", "NoSuchLifecycleConfigurationError"}:
            return []
        raise RuntimeError(f"Lifecycle read failed: {e}")
    except BotoCoreError as e:
        raise RuntimeError(f"Lifecycle read failed: {e}")


def _build_log_expiry_rule(days: int) -> dict:
    return {
        "ID": MANAGED_LOG_EXPIRY_RULE_ID,
        "Status": "Enabled",
        "Filter": {"Prefix": "logs/"},
        "Expiration": {"Days": days},
    }


def _build_glacier_transition_rule(days: int) -> dict:
    return {
        "ID": MANAGED_GLACIER_RULE_ID,
        "Status": "Enabled",
        "Filter": {"Prefix": ""},
        "Transitions": [{"Days": days, "StorageClass": "GLACIER"}],
    }


def configure_lifecycle_rules(
    bucket: str,
    expire_logs_days: int | None,
    glacier_days: int | None,
    disable_expire_logs: bool,
    disable_glacier: bool,
) -> list:
    """Apply managed lifecycle toggles while preserving non-managed rules."""
    existing_rules = _get_existing_lifecycle_rules(bucket)

    preserved_rules = [
        rule
        for rule in existing_rules
        if rule.get("ID") not in {MANAGED_LOG_EXPIRY_RULE_ID, MANAGED_GLACIER_RULE_ID}
    ]

    if expire_logs_days is not None and disable_expire_logs:
        raise ValueError("Use either --expire-logs-days or --disable-expire-logs, not both.")
    if glacier_days is not None and disable_glacier:
        raise ValueError("Use either --glacier-days or --disable-glacier, not both.")

    if expire_logs_days is not None:
        preserved_rules.append(_build_log_expiry_rule(expire_logs_days))
    if glacier_days is not None:
        preserved_rules.append(_build_glacier_transition_rule(glacier_days))

    try:
        if preserved_rules:
            s3.put_bucket_lifecycle_configuration(
                Bucket=bucket,
                LifecycleConfiguration={"Rules": preserved_rules},
            )
        else:
            s3.delete_bucket_lifecycle(Bucket=bucket)
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Lifecycle update failed: {e}")

    return preserved_rules


def show_lifecycle_rules(bucket: str) -> list:
    """Get current bucket lifecycle rules."""
    rules = _get_existing_lifecycle_rules(bucket)
    if not rules:
        print("No lifecycle rules configured.")
        return []

    print(f"\nLifecycle rules for '{bucket}':")
    for idx, rule in enumerate(rules, 1):
        rule_id = rule.get("ID", "(no-id)")
        status = rule.get("Status", "Unknown")
        print(f"{idx}. ID={rule_id}, Status={status}, Filter={rule.get('Filter', {})}")
        if "Expiration" in rule:
            print(f"   Expiration: {rule['Expiration']}")
        if "Transitions" in rule:
            print(f"   Transitions: {rule['Transitions']}")
    return rules


def _list_s3_objects_with_meta(bucket: str, prefix: str = "") -> dict:
    """Return object metadata keyed by key for all objects under prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    objects = {}
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            objects[item["Key"]] = {
                "size": item["Size"],
                "last_modified": item["LastModified"],
            }
    return objects


def _relative_s3_key(base_prefix: str, full_key: str) -> str:
    if not base_prefix:
        return full_key
    return full_key[len(base_prefix) :]


def _safe_prefix(prefix: str | None) -> str:
    if not prefix:
        return ""
    return prefix.strip("/") + "/"


def sync_local_and_s3(
    local_folder: str,
    bucket: str,
    prefix: str = "",
    direction: str = "up",
    delete: bool = False,
) -> dict:
    """Sync files between a local folder and S3 with summary stats."""
    local_root = Path(local_folder).resolve()
    if not local_root.exists() or not local_root.is_dir():
        raise FileNotFoundError(f"Local folder not found: {local_root}")

    normalized_prefix = _safe_prefix(prefix)
    s3_objects = _list_s3_objects_with_meta(bucket, normalized_prefix)
    local_files = {
        str(path.relative_to(local_root)).replace("\\", "/"): {
            "path": path,
            "size": path.stat().st_size,
            "last_modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
        }
        for path in local_root.rglob("*")
        if path.is_file()
    }

    uploaded = 0
    downloaded = 0
    deleted_local = 0
    deleted_s3 = 0

    if direction in {"up", "both"}:
        for rel_key, file_meta in local_files.items():
            s3_key = f"{normalized_prefix}{rel_key}"
            remote_meta = s3_objects.get(s3_key)
            should_upload = (
                remote_meta is None
                or remote_meta["size"] != file_meta["size"]
                or file_meta["last_modified"] > remote_meta["last_modified"]
            )
            if should_upload:
                s3.upload_file(str(file_meta["path"]), bucket, s3_key)
                uploaded += 1

        if delete:
            for s3_key in list(s3_objects.keys()):
                rel = _relative_s3_key(normalized_prefix, s3_key)
                if rel not in local_files:
                    s3.delete_object(Bucket=bucket, Key=s3_key)
                    deleted_s3 += 1

    if direction in {"down", "both"}:
        for s3_key, remote_meta in s3_objects.items():
            rel_key = _relative_s3_key(normalized_prefix, s3_key)
            local_meta = local_files.get(rel_key)
            local_path = local_root / rel_key
            should_download = (
                local_meta is None
                or local_meta["size"] != remote_meta["size"]
                or remote_meta["last_modified"] > local_meta["last_modified"]
            )
            if should_download:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(bucket, s3_key, str(local_path))
                downloaded += 1

        if delete:
            s3_rel_keys = {
                _relative_s3_key(normalized_prefix, s3_key): s3_key
                for s3_key in s3_objects.keys()
            }
            for rel_key, local_meta in local_files.items():
                if rel_key not in s3_rel_keys:
                    Path(local_meta["path"]).unlink(missing_ok=True)
                    deleted_local += 1

    return {
        "uploaded": uploaded,
        "downloaded": downloaded,
        "deleted_local": deleted_local,
        "deleted_s3": deleted_s3,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="S3 helper utilities")
    subparsers = parser.add_subparsers(dest="command")

    upload_parser = subparsers.add_parser("upload", help="Upload a file")
    upload_parser.add_argument("file_path")
    upload_parser.add_argument("bucket")
    upload_parser.add_argument("s3_key", nargs="?")

    list_parser = subparsers.add_parser("list", help="List bucket objects")
    list_parser.add_argument("bucket")

    delete_parser = subparsers.add_parser("delete", help="Delete one object")
    delete_parser.add_argument("bucket")
    delete_parser.add_argument("s3_key")

    presign_parser = subparsers.add_parser("presign", help="Generate pre-signed URL")
    presign_parser.add_argument("bucket")
    presign_parser.add_argument("s3_key")
    presign_parser.add_argument("--expires-in", type=int, default=3600)

    lifecycle_parser = subparsers.add_parser("lifecycle", help="Manage lifecycle rules")
    lifecycle_parser.add_argument("bucket")
    lifecycle_parser.add_argument("--show", action="store_true")
    lifecycle_parser.add_argument("--expire-logs-days", type=int)
    lifecycle_parser.add_argument("--glacier-days", type=int)
    lifecycle_parser.add_argument("--disable-expire-logs", action="store_true")
    lifecycle_parser.add_argument("--disable-glacier", action="store_true")

    sync_parser = subparsers.add_parser("sync", help="Sync local folder <-> S3")
    sync_parser.add_argument("local_folder")
    sync_parser.add_argument("bucket")
    sync_parser.add_argument("--prefix", default="")
    sync_parser.add_argument("--direction", choices=["up", "down", "both"], default="up")
    sync_parser.add_argument("--delete", action="store_true")

    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    # Backward-compatible shorthand: python uploader.py <file_path> <bucket> [s3_key]
    if args.command is None:
        import sys

        if len(sys.argv) >= 3:
            file_path = sys.argv[1]
            bucket = sys.argv[2]
            s3_key = sys.argv[3] if len(sys.argv) > 3 else None
            url = upload_file(file_path, bucket, s3_key)
            print(f"Uploaded: {url}")
            raise SystemExit(0)
        parser.print_help()
        raise SystemExit(1)

    if args.command == "upload":
        uploaded_url = upload_file(args.file_path, args.bucket, args.s3_key)
        print(f"Uploaded: {uploaded_url}")

    elif args.command == "list":
        list_objects(args.bucket)

    elif args.command == "delete":
        delete_object(args.bucket, args.s3_key)

    elif args.command == "presign":
        url = generate_presigned_url(args.bucket, args.s3_key, args.expires_in)
        print("Pre-signed URL:")
        print(url)

    elif args.command == "lifecycle":
        if args.show:
            show_lifecycle_rules(args.bucket)
        else:
            rules = configure_lifecycle_rules(
                bucket=args.bucket,
                expire_logs_days=args.expire_logs_days,
                glacier_days=args.glacier_days,
                disable_expire_logs=args.disable_expire_logs,
                disable_glacier=args.disable_glacier,
            )
            print(f"Lifecycle updated. Active rule count: {len(rules)}")

    elif args.command == "sync":
        summary = sync_local_and_s3(
            local_folder=args.local_folder,
            bucket=args.bucket,
            prefix=args.prefix,
            direction=args.direction,
            delete=args.delete,
        )
        print("Sync complete:")
        print(
            f"  uploaded={summary['uploaded']}, downloaded={summary['downloaded']}, "
            f"deleted_local={summary['deleted_local']}, deleted_s3={summary['deleted_s3']}"
        )



