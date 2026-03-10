import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv()


def _ec2_client():
    return boto3.client(
        "ec2",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "ap-south-1"),
    )


def _parse_key_value(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError(f"Expected KEY=VALUE format, got: {value}")
    key, val = value.split("=", 1)
    key = key.strip()
    val = val.strip()
    if not key:
        raise ValueError(f"Tag key cannot be empty: {value}")
    return key, val


def _resolve_instances(ec2, instance_ids=None, name=None, tag=None) -> list:
    instance_ids = instance_ids or []
    filters = []

    if name:
        filters.append({"Name": "tag:Name", "Values": [name]})
    if tag:
        k, v = _parse_key_value(tag)
        filters.append({"Name": f"tag:{k}", "Values": [v]})

    if not instance_ids and not filters:
        raise ValueError("Provide at least one selector: --instance-id, --name, or --tag KEY=VALUE")

    response = ec2.describe_instances(InstanceIds=instance_ids, Filters=filters)
    instances = [
        instance
        for reservation in response.get("Reservations", [])
        for instance in reservation.get("Instances", [])
    ]
    if not instances:
        raise RuntimeError("No instances matched the provided selector.")
    return instances


def _print_instances(instances: list) -> None:
    print("Matched instances:")
    for item in instances:
        name_tag = next((t["Value"] for t in item.get("Tags", []) if t["Key"] == "Name"), "")
        print(
            f"  - {item['InstanceId']} | state={item['State']['Name']} | "
            f"name={name_tag or '(none)'}"
        )


def _wait_for_state(ec2, instance_ids: list[str], waiter_name: str) -> None:
    ec2.get_waiter(waiter_name).wait(InstanceIds=instance_ids)


def ec2_power_action(action: str, instance_ids=None, name=None, tag=None, wait=False) -> None:
    ec2 = _ec2_client()
    instances = _resolve_instances(ec2, instance_ids=instance_ids, name=name, tag=tag)
    ids = [i["InstanceId"] for i in instances]

    _print_instances(instances)

    try:
        if action == "start":
            ec2.start_instances(InstanceIds=ids)
            print(f"Started: {', '.join(ids)}")
            if wait:
                _wait_for_state(ec2, ids, "instance_running")
                print("All instances are running.")
        elif action == "stop":
            ec2.stop_instances(InstanceIds=ids)
            print(f"Stopped: {', '.join(ids)}")
            if wait:
                _wait_for_state(ec2, ids, "instance_stopped")
                print("All instances are stopped.")
        elif action == "reboot":
            ec2.reboot_instances(InstanceIds=ids)
            print(f"Reboot requested: {', '.join(ids)}")
        else:
            raise ValueError(f"Unsupported action: {action}")
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"EC2 {action} failed: {e}")


def _instance_name(instance: dict) -> str:
    return next((t["Value"] for t in instance.get("Tags", []) if t["Key"] == "Name"), "unnamed")


def _collect_instance_volumes(instance: dict) -> tuple[list[str], str | None]:
    root_device = instance.get("RootDeviceName")
    volume_ids = []
    root_volume_id = None

    for mapping in instance.get("BlockDeviceMappings", []):
        ebs = mapping.get("Ebs")
        if not ebs:
            continue
        volume_id = ebs.get("VolumeId")
        if not volume_id:
            continue
        volume_ids.append(volume_id)
        if mapping.get("DeviceName") == root_device:
            root_volume_id = volume_id

    return volume_ids, root_volume_id


def ec2_safe_snapshot(
    instance_ids=None,
    name=None,
    tag=None,
    volume_ids=None,
    snapshot_tag=None,
    stop_for_root_consistency=False,
    no_restart=False,
) -> None:
    ec2 = _ec2_client()
    matches = _resolve_instances(ec2, instance_ids=instance_ids, name=name, tag=tag)
    if len(matches) != 1:
        raise RuntimeError("Snapshot expects exactly one matched instance; refine selector.")

    instance = matches[0]
    instance_id = instance["InstanceId"]
    instance_name = _instance_name(instance)
    all_volume_ids, root_volume_id = _collect_instance_volumes(instance)

    if not all_volume_ids:
        raise RuntimeError("No EBS volumes attached to selected instance.")

    selected = volume_ids or all_volume_ids
    invalid = [vid for vid in selected if vid not in all_volume_ids]
    if invalid:
        raise RuntimeError(f"Volume(s) not attached to instance {instance_id}: {', '.join(invalid)}")

    print(f"Selected instance: {instance_id} (Name={instance_name})")
    print(f"Attached volumes: {', '.join(all_volume_ids)}")
    print(f"Target snapshot volumes: {', '.join(selected)}")

    state = instance.get("State", {}).get("Name")
    was_running = state == "running"
    stopped_for_consistency = False

    should_stop = bool(stop_for_root_consistency and root_volume_id and root_volume_id in selected and was_running)
    if should_stop:
        ec2.stop_instances(InstanceIds=[instance_id])
        _wait_for_state(ec2, [instance_id], "instance_stopped")
        stopped_for_consistency = True
        print("Instance stopped for root-volume-consistent snapshot.")

    extra_tags = []
    for item in snapshot_tag or []:
        key, value = _parse_key_value(item)
        extra_tags.append({"Key": key, "Value": value})

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    created = []

    try:
        for volume_id in selected:
            description = f"Safe snapshot {instance_id}:{volume_id} at {timestamp}"
            tags = [
                {"Key": "Name", "Value": f"snap-{instance_name}-{volume_id}-{timestamp}"},
                {"Key": "CreatedBy", "Value": "aws-assistant"},
                {"Key": "SourceInstanceId", "Value": instance_id},
                {"Key": "SourceVolumeId", "Value": volume_id},
            ] + extra_tags

            response = ec2.create_snapshot(
                VolumeId=volume_id,
                Description=description,
                TagSpecifications=[{"ResourceType": "snapshot", "Tags": tags}],
            )
            snapshot_id = response["SnapshotId"]
            created.append(snapshot_id)
            print(f"Created snapshot {snapshot_id} for volume {volume_id}")
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Snapshot creation failed: {e}")
    finally:
        if stopped_for_consistency and not no_restart:
            ec2.start_instances(InstanceIds=[instance_id])
            _wait_for_state(ec2, [instance_id], "instance_running")
            print("Instance restarted after snapshot.")

    print(f"Snapshot operation complete. Created: {', '.join(created)}")


def _load_profile_config(config_path: str) -> dict:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")

    if suffix == ".json":
        return json.loads(text)

    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError:
            raise RuntimeError("YAML config requires PyYAML. Install with: pip install pyyaml")
        return yaml.safe_load(text)

    raise ValueError("Config must be .json, .yaml, or .yml")


def ec2_launch_profile(profile: str, config_path: str, wait: bool = False) -> None:
    config = _load_profile_config(config_path)
    profiles = config.get("profiles", {})
    sg_templates = config.get("security_group_templates", {})

    if profile not in profiles:
        raise RuntimeError(f"Profile '{profile}' not found in {config_path}")

    selected = profiles[profile]

    image_id = selected.get("ami") or selected.get("image_id") or selected.get("ImageId")
    instance_type = selected.get("instance_type") or selected.get("InstanceType")
    key_name = selected.get("key_pair") or selected.get("key_name") or selected.get("KeyName")

    if not image_id or not instance_type:
        raise RuntimeError("Profile must include AMI and instance type.")

    security_group_ids = (
        selected.get("security_group_ids")
        or selected.get("sg_ids")
        or selected.get("SecurityGroupIds")
        or []
    )

    if not security_group_ids and selected.get("sg_template"):
        template_name = selected["sg_template"]
        security_group_ids = sg_templates.get(template_name, [])
        if not security_group_ids:
            raise RuntimeError(f"Security group template '{template_name}' not found or empty")

    tags_dict = selected.get("tags", {})
    tags = [{"Key": k, "Value": str(v)} for k, v in tags_dict.items()]
    if not any(t["Key"] == "Name" for t in tags):
        tags.append({"Key": "Name", "Value": profile})

    params = {
        "ImageId": image_id,
        "InstanceType": instance_type,
        "MinCount": 1,
        "MaxCount": 1,
        "TagSpecifications": [{"ResourceType": "instance", "Tags": tags}],
    }

    if key_name:
        params["KeyName"] = key_name
    if security_group_ids:
        params["SecurityGroupIds"] = security_group_ids
    if selected.get("subnet_id"):
        params["SubnetId"] = selected["subnet_id"]
    if selected.get("iam_instance_profile"):
        iip = selected["iam_instance_profile"]
        params["IamInstanceProfile"] = {"Arn": iip} if str(iip).startswith("arn:") else {"Name": iip}
    if selected.get("user_data"):
        params["UserData"] = selected["user_data"]
    if selected.get("block_device_mappings"):
        params["BlockDeviceMappings"] = selected["block_device_mappings"]
    if selected.get("metadata_options"):
        params["MetadataOptions"] = selected["metadata_options"]

    ec2 = _ec2_client()
    try:
        response = ec2.run_instances(**params)
        instance = response["Instances"][0]
        instance_id = instance["InstanceId"]
        print(f"Launched instance: {instance_id} (profile={profile})")
        if wait:
            _wait_for_state(ec2, [instance_id], "instance_running")
            print(f"Instance {instance_id} is running.")
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Launch failed: {e}")


def _expand_equals_args(argv: list[str]) -> list[str]:
    expanded = []
    for arg in argv:
        if "=" in arg and not arg.startswith("-"):
            key, value = arg.split("=", 1)
            key = key.strip().replace("_", "-")
            expanded.append(f"--{key}")
            expanded.append(value)
        else:
            expanded.append(arg)
    return expanded


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aws-assistant", description="AWS helper CLI")
    services = parser.add_subparsers(dest="service")

    ec2_parser = services.add_parser("ec2", help="EC2 operations")
    ec2_sub = ec2_parser.add_subparsers(dest="ec2_command")

    for action in ["start", "stop", "reboot"]:
        cmd = ec2_sub.add_parser(action, help=f"{action.capitalize()} instances by selector")
        cmd.add_argument("--instance-id", action="append", dest="instance_ids")
        cmd.add_argument("--name")
        cmd.add_argument("--tag", help="Tag selector in KEY=VALUE form")
        cmd.add_argument("--wait", action="store_true")

    snap = ec2_sub.add_parser("snapshot", help="Safe EBS snapshot flow for one instance")
    snap.add_argument("--instance-id", action="append", dest="instance_ids")
    snap.add_argument("--name")
    snap.add_argument("--tag", help="Tag selector in KEY=VALUE form")
    snap.add_argument("--volume-id", action="append", dest="volume_ids")
    snap.add_argument("--snapshot-tag", action="append", help="Add snapshot tag KEY=VALUE")
    snap.add_argument("--stop-for-root-consistency", action="store_true")
    snap.add_argument("--no-restart", action="store_true")

    launch = ec2_sub.add_parser("launch", help="Launch instance from profile config")
    launch.add_argument("--profile", required=True)
    launch.add_argument("--config", default="ec2_profiles.json")
    launch.add_argument("--wait", action="store_true")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args(_expand_equals_args(sys.argv[1:]))

    if args.service != "ec2" or not args.ec2_command:
        parser.print_help()
        return 1

    if args.ec2_command in {"start", "stop", "reboot"}:
        ec2_power_action(
            action=args.ec2_command,
            instance_ids=args.instance_ids,
            name=args.name,
            tag=args.tag,
            wait=args.wait,
        )
        return 0

    if args.ec2_command == "snapshot":
        ec2_safe_snapshot(
            instance_ids=args.instance_ids,
            name=args.name,
            tag=args.tag,
            volume_ids=args.volume_ids,
            snapshot_tag=args.snapshot_tag,
            stop_for_root_consistency=args.stop_for_root_consistency,
            no_restart=args.no_restart,
        )
        return 0

    if args.ec2_command == "launch":
        ec2_launch_profile(profile=args.profile, config_path=args.config, wait=args.wait)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        print(f"Error: {e}")
        raise SystemExit(1)
