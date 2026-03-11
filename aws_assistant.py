import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
import yaml

try:
    import questionary
except ImportError:  # pragma: no cover - optional dependency
    questionary = None

load_dotenv()

CONFIG_PATH = Path.home() / ".aws-assistant.yml"


def _load_assistant_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise RuntimeError(f"Failed to parse config {CONFIG_PATH}: {exc}")


def _resolved_region(explicit_region: str | None = None) -> str:
    if explicit_region:
        return explicit_region
    env_region = os.getenv("AWS_REGION")
    if env_region:
        return env_region
    cfg = _load_assistant_config()
    return cfg.get("defaults", {}).get("region", "ap-south-1")


def _boto3_session(service_region: str | None = None) -> boto3.session.Session:
    cfg = _load_assistant_config()
    defaults = cfg.get("defaults", {})

    region_name = _resolved_region(service_region)
    profile_name = os.getenv("AWS_PROFILE") or defaults.get("profile")

    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    session_token = os.getenv("AWS_SESSION_TOKEN")

    kwargs: dict[str, str] = {"region_name": region_name}
    if profile_name:
        kwargs["profile_name"] = profile_name

    # Explicit credentials from env take precedence over profile resolution.
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token

    return boto3.session.Session(**kwargs)


def _ec2_client():
    return _boto3_session().client("ec2")


def _s3_client():
    return _boto3_session().client("s3")


def _logs_client(region: str | None = None):
    return _boto3_session(region).client("logs")


def _ecs_client(region: str | None = None):
    return _boto3_session(region).client("ecs")


def _iam_client():
    return _boto3_session().client("iam")


def _elbv2_client(region: str | None = None):
    return _boto3_session(region).client("elbv2")


def _elb_client(region: str | None = None):
    return _boto3_session(region).client("elb")


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


def _confirm_action(prompt: str, assume_yes: bool = False) -> bool:
    if assume_yes:
        return True
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def ec2_terminate(instance_ids=None, name=None, tag=None, wait=False, assume_yes=False) -> None:
    ec2 = _ec2_client()
    instances = _resolve_instances(ec2, instance_ids=instance_ids, name=name, tag=tag)
    ids = [i["InstanceId"] for i in instances]

    _print_instances(instances)
    if not _confirm_action(f"Terminate {len(ids)} instance(s): {', '.join(ids)}?", assume_yes):
        print("Termination cancelled.")
        return

    try:
        ec2.terminate_instances(InstanceIds=ids)
        print(f"Termination requested: {', '.join(ids)}")
        if wait:
            _wait_for_state(ec2, ids, "instance_terminated")
            print("All instances are terminated.")
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"EC2 terminate failed: {e}")


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


def s3_delete_bucket(bucket: str, force_empty: bool = False, assume_yes: bool = False) -> None:
    s3 = _s3_client()

    if not _confirm_action(f"Delete bucket '{bucket}'? This is destructive.", assume_yes):
        print("Bucket delete cancelled.")
        return

    try:
        if force_empty:
            paginator = s3.get_paginator("list_object_versions")
            for page in paginator.paginate(Bucket=bucket):
                items = []
                for obj in page.get("Versions", []):
                    items.append({"Key": obj["Key"], "VersionId": obj["VersionId"]})
                for marker in page.get("DeleteMarkers", []):
                    items.append({"Key": marker["Key"], "VersionId": marker["VersionId"]})
                if items:
                    s3.delete_objects(Bucket=bucket, Delete={"Objects": items, "Quiet": True})

            paginator2 = s3.get_paginator("list_objects_v2")
            for page in paginator2.paginate(Bucket=bucket):
                objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
                if objects:
                    s3.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})

        s3.delete_bucket(Bucket=bucket)
        print(f"Bucket deleted: {bucket}")
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Delete bucket failed: {e}")


def _format_event_time(ms_epoch: int) -> str:
    return datetime.fromtimestamp(ms_epoch / 1000, tz=timezone.utc).isoformat()


def _tail_log_group(log_group: str, minutes: int, limit: int, filter_pattern: str | None = None) -> None:
    logs = _logs_client()
    start_ms = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000)
    paginator = logs.get_paginator("filter_log_events")

    shown = 0
    for page in paginator.paginate(
        logGroupName=log_group,
        startTime=start_ms,
        filterPattern=filter_pattern or "",
        interleaved=True,
    ):
        for event in page.get("events", []):
            print(f"[{_format_event_time(event['timestamp'])}] {event.get('message', '').rstrip()}")
            shown += 1
            if shown >= limit:
                return


def logs_tail_lambda(function_name: str, minutes: int, limit: int, filter_pattern: str | None = None) -> None:
    log_group = f"/aws/lambda/{function_name}"
    print(f"Tailing Lambda log group: {log_group}")
    _tail_log_group(log_group=log_group, minutes=minutes, limit=limit, filter_pattern=filter_pattern)


def _resolve_ecs_log_targets(cluster: str, task: str, region: str | None = None) -> list[tuple[str, str]]:
    ecs = _ecs_client(region)
    response = ecs.describe_tasks(cluster=cluster, tasks=[task])
    tasks = response.get("tasks", [])
    if not tasks:
        raise RuntimeError(f"Task not found in cluster '{cluster}': {task}")

    task_obj = tasks[0]
    td_arn = task_obj["taskDefinitionArn"]
    task_id = task_obj["taskArn"].split("/")[-1]
    runtime_by_name = {c["name"]: c.get("runtimeId") for c in task_obj.get("containers", [])}

    td = ecs.describe_task_definition(taskDefinition=td_arn)["taskDefinition"]
    targets: list[tuple[str, str]] = []

    for container in td.get("containerDefinitions", []):
        log_cfg = container.get("logConfiguration", {})
        if log_cfg.get("logDriver") != "awslogs":
            continue
        options = log_cfg.get("options", {})
        group = options.get("awslogs-group")
        prefix = options.get("awslogs-stream-prefix")
        name = container.get("name")
        if not group:
            continue

        runtime_id = runtime_by_name.get(name)
        suffix = runtime_id or task_id
        if prefix and name:
            stream = f"{prefix}/{name}/{suffix}"
        else:
            stream = task_id
        targets.append((group, stream))

    if not targets:
        raise RuntimeError("No awslogs configuration found in task definition.")
    return targets


def logs_tail_ecs_task(cluster: str, task: str, minutes: int, limit: int, region: str | None = None) -> None:
    logs = _logs_client(region)
    start_ms = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000)
    shown = 0

    for group, stream in _resolve_ecs_log_targets(cluster=cluster, task=task, region=region):
        print(f"Tailing ECS logs: group={group}, stream={stream}")
        paginator = logs.get_paginator("filter_log_events")
        for page in paginator.paginate(
            logGroupName=group,
            logStreamNames=[stream],
            startTime=start_ms,
            interleaved=True,
        ):
            for event in page.get("events", []):
                print(f"[{_format_event_time(event['timestamp'])}] {event.get('message', '').rstrip()}")
                shown += 1
                if shown >= limit:
                    return


def logs_tail_eks_pod(
    pod: str,
    namespace: str,
    minutes: int,
    container: str | None = None,
    grep_terms: str | None = None,
) -> None:
    cmd = ["kubectl", "logs", pod, "-n", namespace, f"--since={minutes}m"]
    if container:
        cmd.extend(["-c", container])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        raise RuntimeError("kubectl not found. Install kubectl and connect to EKS first.")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"kubectl logs failed: {exc.stderr or exc.stdout}")

    terms = [term.strip().lower() for term in (grep_terms or "").split(",") if term.strip()]
    for line in result.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        if terms and not any(term in text.lower() for term in terms):
            continue
        print(text)


def logs_quick_search(target: str, minutes: int, limit: int, **kwargs) -> None:
    quick_terms = "ERROR,Timeout,Exception"

    if target == "lambda":
        logs_tail_lambda(
            function_name=kwargs["function_name"],
            minutes=minutes,
            limit=limit,
            filter_pattern='?ERROR ?Timeout ?Exception',
        )
        return

    if target == "ecs":
        # ECS quick search uses stream tail then local match by common error keywords.
        logs_tail_ecs_task(
            cluster=kwargs["cluster"],
            task=kwargs["task"],
            minutes=minutes,
            limit=limit,
            region=kwargs.get("region"),
        )
        return

    if target == "eks":
        logs_tail_eks_pod(
            pod=kwargs["pod"],
            namespace=kwargs["namespace"],
            minutes=minutes,
            container=kwargs.get("container"),
            grep_terms=quick_terms,
        )
        return

    raise ValueError(f"Unsupported logs quick-search target: {target}")


def _flatten_actions(action_field) -> list[str]:
    if isinstance(action_field, list):
        return [str(item) for item in action_field]
    if action_field is None:
        return []
    return [str(action_field)]


def _summarize_policy_document(document: dict) -> dict:
    statements = document.get("Statement", [])
    if isinstance(statements, dict):
        statements = [statements]

    allow_actions: set[str] = set()
    deny_actions: set[str] = set()
    for st in statements:
        actions = _flatten_actions(st.get("Action"))
        effect = str(st.get("Effect", "")).lower()
        if effect == "allow":
            allow_actions.update(actions)
        elif effect == "deny":
            deny_actions.update(actions)

    return {
        "statement_count": len(statements),
        "allow_action_count": len(allow_actions),
        "deny_action_count": len(deny_actions),
    }


def iam_permission_summary(principal_type: str, principal_name: str) -> None:
    iam = _iam_client()
    summaries = []

    if principal_type == "role":
        attached = iam.list_attached_role_policies(RoleName=principal_name).get("AttachedPolicies", [])
        inline = iam.list_role_policies(RoleName=principal_name).get("PolicyNames", [])

        for policy in attached:
            arn = policy["PolicyArn"]
            meta = iam.get_policy(PolicyArn=arn)["Policy"]
            default_version = meta["DefaultVersionId"]
            document = iam.get_policy_version(PolicyArn=arn, VersionId=default_version)["PolicyVersion"]["Document"]
            summaries.append((f"managed:{policy['PolicyName']}", _summarize_policy_document(document)))

        for policy_name in inline:
            document = iam.get_role_policy(RoleName=principal_name, PolicyName=policy_name)["PolicyDocument"]
            summaries.append((f"inline:{policy_name}", _summarize_policy_document(document)))

    elif principal_type == "user":
        attached = iam.list_attached_user_policies(UserName=principal_name).get("AttachedPolicies", [])
        inline = iam.list_user_policies(UserName=principal_name).get("PolicyNames", [])

        for policy in attached:
            arn = policy["PolicyArn"]
            meta = iam.get_policy(PolicyArn=arn)["Policy"]
            default_version = meta["DefaultVersionId"]
            document = iam.get_policy_version(PolicyArn=arn, VersionId=default_version)["PolicyVersion"]["Document"]
            summaries.append((f"managed:{policy['PolicyName']}", _summarize_policy_document(document)))

        for policy_name in inline:
            document = iam.get_user_policy(UserName=principal_name, PolicyName=policy_name)["PolicyDocument"]
            summaries.append((f"inline:{policy_name}", _summarize_policy_document(document)))
    else:
        raise ValueError("principal_type must be 'role' or 'user'")

    if not summaries:
        print("No attached or inline policies found.")
        return

    total_allow = sum(item[1]["allow_action_count"] for item in summaries)
    total_deny = sum(item[1]["deny_action_count"] for item in summaries)
    print(f"Principal: {principal_type}/{principal_name}")
    print(f"Policies: {len(summaries)} | allow-actions={total_allow} | deny-actions={total_deny}")
    print("-")
    for name, summary in summaries:
        print(
            f"{name}: statements={summary['statement_count']}, "
            f"allow-actions={summary['allow_action_count']}, deny-actions={summary['deny_action_count']}"
        )


def iam_policy_template(template_name: str, output_file: str | None = None) -> None:
    templates = {
        "s3-read-only": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:ListBucket"],
                    "Resource": ["arn:aws:s3:::*", "arn:aws:s3:::*/*"],
                }
            ],
        },
        "ec2-start-stop": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["ec2:DescribeInstances", "ec2:StartInstances", "ec2:StopInstances"],
                    "Resource": "*",
                }
            ],
        },
        "lambda-invoke-read-logs": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["lambda:InvokeFunction", "lambda:GetFunction"],
                    "Resource": "*",
                },
                {
                    "Effect": "Allow",
                    "Action": ["logs:FilterLogEvents", "logs:GetLogEvents", "logs:DescribeLogStreams"],
                    "Resource": "*",
                },
            ],
        },
    }

    if template_name not in templates:
        raise ValueError(f"Unknown template '{template_name}'. Options: {', '.join(sorted(templates.keys()))}")

    content = json.dumps(templates[template_name], indent=2)
    if output_file:
        Path(output_file).write_text(content + "\n", encoding="utf-8")
        print(f"Template written: {output_file}")
    else:
        print(content)


def _ec2_running_without_env_tag(ec2) -> list[dict]:
    response = ec2.describe_instances(Filters=[{"Name": "instance-state-name", "Values": ["running"]}])
    offenders = []
    for reservation in response.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            tags = {t["Key"].lower(): t["Value"] for t in instance.get("Tags", [])}
            if "env" not in tags and "environment" not in tags:
                offenders.append(instance)
    return offenders


def _unattached_ebs_volumes(ec2) -> list[dict]:
    response = ec2.describe_volumes(Filters=[{"Name": "status", "Values": ["available"]}])
    return response.get("Volumes", [])


def _idle_load_balancers(region: str | None = None) -> tuple[list[dict], list[dict]]:
    elbv2 = _elbv2_client(region)
    classic = _elb_client(region)

    idle_v2 = []
    for lb in elbv2.describe_load_balancers().get("LoadBalancers", []):
        tgs = elbv2.describe_target_groups(LoadBalancerArn=lb["LoadBalancerArn"]).get("TargetGroups", [])
        if not tgs:
            idle_v2.append(lb)
            continue

        has_healthy = False
        for tg in tgs:
            health = elbv2.describe_target_health(TargetGroupArn=tg["TargetGroupArn"]).get("TargetHealthDescriptions", [])
            if any(item.get("TargetHealth", {}).get("State") == "healthy" for item in health):
                has_healthy = True
                break
        if not has_healthy:
            idle_v2.append(lb)

    idle_classic = []
    for lb in classic.describe_load_balancers().get("LoadBalancerDescriptions", []):
        if not lb.get("Instances"):
            idle_classic.append(lb)

    return idle_v2, idle_classic


def safety_scan(region: str | None = None) -> None:
    ec2 = _ec2_client()
    running_untagged = _ec2_running_without_env_tag(ec2)
    unattached = _unattached_ebs_volumes(ec2)
    idle_v2, idle_classic = _idle_load_balancers(region=region)

    print("Suspicious resource scan")
    print(f"Running EC2 without env/environment tag: {len(running_untagged)}")
    for item in running_untagged:
        print(f"  - {item['InstanceId']}")

    print(f"Unattached EBS volumes: {len(unattached)}")
    for vol in unattached[:20]:
        print(f"  - {vol['VolumeId']} ({vol['Size']} GiB)")
    if len(unattached) > 20:
        print(f"  ... and {len(unattached) - 20} more")

    print(f"Idle ALB/NLB: {len(idle_v2)}")
    for lb in idle_v2:
        print(f"  - {lb['LoadBalancerName']} ({lb['Type']})")

    print(f"Idle Classic ELB: {len(idle_classic)}")
    for lb in idle_classic:
        print(f"  - {lb['LoadBalancerName']}")


def config_show() -> None:
    cfg = _load_assistant_config()
    print(json.dumps(cfg, indent=2))


def config_init(force: bool = False) -> None:
    if CONFIG_PATH.exists() and not force:
        raise RuntimeError(f"Config already exists at {CONFIG_PATH}. Use --force to overwrite.")

    sample = {
        "defaults": {
            "region": "ap-south-1",
            "profile": "default",
            "tag_filters": {"env": "dev"},
        },
        "safety": {"require_confirmation": True},
    }
    CONFIG_PATH.write_text(yaml.safe_dump(sample, sort_keys=False), encoding="utf-8")
    print(f"Created config: {CONFIG_PATH}")


def _forward_to_script(script_name: str, script_args: list[str]) -> int:
    script_path = Path(__file__).parent / script_name
    command = [sys.executable, str(script_path)] + script_args
    result = subprocess.run(command)
    return result.returncode


def _render_menu(title: str, options: list[str]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    for idx, label in enumerate(options, start=1):
        print(f"{idx}. {label}")


def _parse_selection(raw: str, max_index: int) -> int | None:
    value = raw.strip().lower()
    if value in {"q", "quit", "exit", "back", "b"}:
        return None
    if not value.isdigit():
        raise ValueError("Enter a number from the menu.")

    choice = int(value)
    if choice < 1 or choice > max_index:
        raise ValueError(f"Choose a number between 1 and {max_index}.")
    return choice - 1


def _choose_option(
    title: str,
    options: list[str],
    prompt: str = "Select",
    fancy: bool = False,
    searchable: bool = False,
) -> int | None:
    if fancy and questionary and sys.stdin.isatty():
        choice = None
        if searchable:
            choice = questionary.autocomplete(
                f"{title} - {prompt}",
                choices=options,
                ignore_case=True,
                match_middle=True,
                validate=lambda text: True if text in options else "Pick one of the listed options.",
            ).ask()
        else:
            choice = questionary.select(
                f"{title} - {prompt}",
                choices=options + ["[Back]"],
                use_shortcuts=True,
            ).ask()
            if choice == "[Back]":
                return None

        if not choice:
            return None
        return options.index(choice)

    while True:
        _render_menu(title, options)
        raw = input(f"{prompt} (or 'q' to go back): ")
        try:
            return _parse_selection(raw, len(options))
        except ValueError as exc:
            print(f"Invalid selection: {exc}")


def _list_ec2_instances_for_tui() -> list[dict]:
    ec2 = _ec2_client()
    response = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}]
    )
    instances = [
        item
        for reservation in response.get("Reservations", [])
        for item in reservation.get("Instances", [])
    ]
    return instances


def _ec2_tui(fancy: bool = False) -> None:
    instances = _list_ec2_instances_for_tui()
    if not instances:
        print("No EC2 instances found.")
        return

    labels = []
    for item in instances:
        name = next((t["Value"] for t in item.get("Tags", []) if t["Key"] == "Name"), "(none)")
        labels.append(f"{item['InstanceId']} | {item['State']['Name']} | {name}")

    idx = _choose_option(
        "EC2 Instances",
        labels,
        prompt="Pick an instance",
        fancy=fancy,
        searchable=len(labels) > 8,
    )
    if idx is None:
        return

    target_id = instances[idx]["InstanceId"]
    action_idx = _choose_option(
        "EC2 Actions",
        ["start", "stop", "reboot", "terminate", "snapshot(root-consistent)", "cancel"],
        prompt="Pick action",
        fancy=fancy,
    )
    if action_idx is None or action_idx == 5:
        return

    if action_idx == 0:
        ec2_power_action("start", instance_ids=[target_id], wait=True)
    elif action_idx == 1:
        ec2_power_action("stop", instance_ids=[target_id], wait=True)
    elif action_idx == 2:
        ec2_power_action("reboot", instance_ids=[target_id], wait=False)
    elif action_idx == 3:
        ec2_terminate(instance_ids=[target_id], wait=False, assume_yes=False)
    elif action_idx == 4:
        ec2_safe_snapshot(
            instance_ids=[target_id],
            stop_for_root_consistency=True,
            snapshot_tag=["CreatedBy=tui"],
        )


def _logs_tui(fancy: bool = False) -> None:
    source_idx = _choose_option(
        "Logs Source",
        ["Lambda quick errors", "ECS task quick errors", "EKS pod quick errors", "back"],
        prompt="Pick source",
        fancy=fancy,
    )
    if source_idx is None or source_idx == 3:
        return

    if source_idx == 0:
        fn = input("Lambda function name: ").strip()
        minutes = int(input("Minutes to search [30]: ").strip() or "30")
        logs_quick_search(target="lambda", minutes=minutes, limit=200, function_name=fn)
        return

    if source_idx == 1:
        cluster = input("ECS cluster: ").strip()
        task = input("ECS task id/arn: ").strip()
        minutes = int(input("Minutes to search [30]: ").strip() or "30")
        logs_quick_search(target="ecs", minutes=minutes, limit=200, cluster=cluster, task=task)
        return

    pod = input("EKS pod name: ").strip()
    namespace = input("Namespace [default]: ").strip() or "default"
    minutes = int(input("Minutes to search [30]: ").strip() or "30")
    logs_quick_search(target="eks", minutes=minutes, limit=0, pod=pod, namespace=namespace)


def _iam_tui(fancy: bool = False) -> None:
    action_idx = _choose_option(
        "IAM Menu",
        ["Permission summary", "Generate policy template", "back"],
        prompt="Pick action",
        fancy=fancy,
    )
    if action_idx is None or action_idx == 2:
        return

    if action_idx == 0:
        p_type = input("Principal type (role/user): ").strip().lower()
        p_name = input("Principal name: ").strip()
        iam_permission_summary(p_type, p_name)
        return

    tpl_idx = _choose_option(
        "Policy Templates",
        ["s3-read-only", "ec2-start-stop", "lambda-invoke-read-logs", "back"],
        prompt="Pick template",
        fancy=fancy,
    )
    if tpl_idx is None or tpl_idx == 3:
        return
    selected = ["s3-read-only", "ec2-start-stop", "lambda-invoke-read-logs"][tpl_idx]
    out = input("Output file (leave empty to print): ").strip()
    iam_policy_template(selected, output_file=out or None)


def _parse_quick_action(action_text: str) -> list[str]:
    tokens = shlex.split(action_text.strip())
    if not tokens:
        raise ValueError("Quick action cannot be empty.")
    return [token.strip() for token in tokens if token.strip()]


def _selector_from_quick_tokens(selector_kind: str, selector_value: str) -> dict:
    if selector_kind in {"id", "instance-id", "instance"}:
        return {"instance_ids": [selector_value]}
    if selector_kind == "name":
        return {"name": selector_value}
    if selector_kind == "tag":
        return {"tag": selector_value}
    raise ValueError("Selector must be one of: id, name, tag")


def _normalize_quick_tokens(tokens: list[str]) -> list[str]:
    aliases = {
        "st": "start",
        "sp": "stop",
        "rb": "reboot",
        "term": "terminate",
        "ls-lambda": "logs-lambda",
        "iam-sum": "iam-summary",
        "iam-tpl": "iam-template",
        "scan": "safety-scan",
    }
    normalized = []
    for token in tokens:
        key = token.lower()
        normalized.append(aliases.get(key, token))
    return normalized


def execute_quick_action(action_text: str) -> None:
    tokens = _normalize_quick_tokens(_parse_quick_action(action_text))
    root = tokens[0].lower()

    if root == "safety-scan":
        safety_scan()
        return

    if root == "logs-lambda" and len(tokens) >= 2:
        minutes = int(tokens[2]) if len(tokens) >= 3 else 30
        logs_quick_search(target="lambda", minutes=minutes, limit=200, function_name=tokens[1])
        return

    if root == "iam-summary" and len(tokens) >= 3:
        iam_permission_summary(tokens[1].lower(), tokens[2])
        return

    if root == "iam-template" and len(tokens) >= 2:
        output_file = tokens[2] if len(tokens) >= 3 else None
        iam_policy_template(tokens[1], output_file=output_file)
        return

    if root == "safety" and len(tokens) >= 2 and tokens[1].lower() == "scan":
        safety_scan()
        return

    if root == "iam" and len(tokens) >= 4 and tokens[1].lower() == "summary":
        iam_permission_summary(tokens[2].lower(), tokens[3])
        return

    if root == "iam" and len(tokens) >= 3 and tokens[1].lower() in {"template", "policy-template"}:
        output_file = tokens[3] if len(tokens) >= 4 else None
        iam_policy_template(tokens[2], output_file=output_file)
        return

    if root == "logs" and len(tokens) >= 3 and tokens[1].lower() == "lambda":
        minutes = int(tokens[3]) if len(tokens) >= 4 else 30
        logs_quick_search(target="lambda", minutes=minutes, limit=200, function_name=tokens[2])
        return

    if root == "ec2" and len(tokens) >= 4:
        action = tokens[1].lower()
        selector_kind = tokens[2].lower()
        selector_value = tokens[3]
        selector = _selector_from_quick_tokens(selector_kind, selector_value)

        wait = "--wait" in tokens
        if action in {"start", "stop", "reboot"}:
            ec2_power_action(action=action, wait=wait, **selector)
            return
        if action == "terminate":
            ec2_terminate(wait=wait, assume_yes=False, **selector)
            return

    raise ValueError(
        "Unsupported quick action. Examples: "
        "ec2 stop name my-dev-box | ec2 terminate id i-123 | logs lambda my-fn 30 | iam summary role my-role | safety scan"
    )


def _quick_palette_tui(fancy: bool = False) -> None:
    print("Quick action examples:")
    print("  ec2 stop name my-dev-box")
    print("  ec2 terminate id i-0123456789abcdef0")
    print("  logs lambda my-function 30")
    print("  iam summary role my-role")
    print("  iam template s3-read-only my_policy.json")
    print("  safety scan")
    print("Alias examples:")
    print("  ec2 sp name my-dev-box")
    print("  ec2 term id i-0123456789abcdef0")
    print("  ls-lambda my-function 30")
    print("  iam-sum role my-role")
    print("  iam-tpl s3-read-only my_policy.json")
    print("  scan")

    if fancy and questionary and sys.stdin.isatty():
        action_text = questionary.text("Enter quick action (blank to cancel):").ask()
        if not action_text:
            return
    else:
        action_text = input("Enter quick action (or empty to cancel): ").strip()
        if not action_text:
            return

    execute_quick_action(action_text)


def run_tui(fancy: bool = True) -> int:
    print("AWS Assistant TUI")
    print("Type 'q' at any menu prompt to go back.")
    if fancy and questionary:
        print("Interactive mode: arrow keys enabled.")
    elif fancy and not questionary:
        print("Tip: install 'questionary' for arrow-key and searchable menus.")

    while True:
        selection = _choose_option(
            "Main Menu",
            [
                "Quick action palette",
                "EC2 quick actions",
                "Logs quick search",
                "IAM helper",
                "Cost safety scan",
                "Exit",
            ],
            prompt="Choose workflow",
            fancy=fancy,
        )

        if selection is None or selection == 5:
            print("Exiting TUI.")
            return 0

        if selection == 0:
            _quick_palette_tui(fancy=fancy)
        elif selection == 1:
            _ec2_tui(fancy=fancy)
        elif selection == 2:
            _logs_tui(fancy=fancy)
        elif selection == 3:
            _iam_tui(fancy=fancy)
        elif selection == 4:
            safety_scan()


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

    terminate = ec2_sub.add_parser("terminate", help="Terminate instances by selector")
    terminate.add_argument("--instance-id", action="append", dest="instance_ids")
    terminate.add_argument("--name")
    terminate.add_argument("--tag", help="Tag selector in KEY=VALUE form")
    terminate.add_argument("--wait", action="store_true")
    terminate.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

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

    logs_parser = services.add_parser("logs", help="CloudWatch/Kubernetes log helpers")
    logs_sub = logs_parser.add_subparsers(dest="logs_command")

    logs_lambda = logs_sub.add_parser("lambda", help="Tail Lambda logs")
    logs_lambda.add_argument("function_name")
    logs_lambda.add_argument("--minutes", type=int, default=15)
    logs_lambda.add_argument("--limit", type=int, default=200)
    logs_lambda.add_argument("--filter", dest="filter_pattern")
    logs_lambda.add_argument("--quick-errors", action="store_true")

    logs_ecs = logs_sub.add_parser("ecs", help="Tail ECS task logs")
    logs_ecs.add_argument("cluster")
    logs_ecs.add_argument("task")
    logs_ecs.add_argument("--minutes", type=int, default=15)
    logs_ecs.add_argument("--limit", type=int, default=200)
    logs_ecs.add_argument("--region")
    logs_ecs.add_argument("--quick-errors", action="store_true")

    logs_eks = logs_sub.add_parser("eks", help="Tail EKS pod logs")
    logs_eks.add_argument("pod")
    logs_eks.add_argument("--namespace", default="default")
    logs_eks.add_argument("--container")
    logs_eks.add_argument("--minutes", type=int, default=15)
    logs_eks.add_argument("--grep", help="Comma-separated terms filter")
    logs_eks.add_argument("--quick-errors", action="store_true")

    iam_parser = services.add_parser("iam", help="IAM quality-of-life helpers")
    iam_sub = iam_parser.add_subparsers(dest="iam_command")

    iam_summary = iam_sub.add_parser("summary", help="Show effective permission summary")
    iam_summary.add_argument("principal_type", choices=["role", "user"])
    iam_summary.add_argument("principal_name")

    iam_tpl = iam_sub.add_parser("policy-template", help="Generate starter IAM policy templates")
    iam_tpl.add_argument("template_name", choices=["s3-read-only", "ec2-start-stop", "lambda-invoke-read-logs"])
    iam_tpl.add_argument("--output")

    safety_parser = services.add_parser("safety", help="Cost-safety and destructive-op helpers")
    safety_sub = safety_parser.add_subparsers(dest="safety_command")

    safety_scan_parser = safety_sub.add_parser("scan", help="Scan suspicious cost/leak resources")
    safety_scan_parser.add_argument("--region")

    s3_parser = services.add_parser("s3", help="S3 helper commands")
    s3_sub = s3_parser.add_subparsers(dest="s3_command")
    s3_delete_bucket_cmd = s3_sub.add_parser("delete-bucket", help="Delete bucket with confirmation")
    s3_delete_bucket_cmd.add_argument("bucket")
    s3_delete_bucket_cmd.add_argument("--force-empty", action="store_true")
    s3_delete_bucket_cmd.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    config_parser = services.add_parser("config", help="Assistant defaults in ~/.aws-assistant.yml")
    config_sub = config_parser.add_subparsers(dest="config_command")
    config_sub.add_parser("show", help="Show current assistant config")
    config_init_parser = config_sub.add_parser("init", help="Create starter config")
    config_init_parser.add_argument("--force", action="store_true")

    tui_parser = services.add_parser("tui", help="Interactive text UI for common workflows")
    tui_parser.add_argument("--plain", action="store_true", help="Force plain numeric menus")

    lambda_parser = services.add_parser("lambda", help="Forward to lambda_assistant.py")
    lambda_parser.add_argument("lambda_args", nargs=argparse.REMAINDER)

    container_parser = services.add_parser("container", help="Forward to container_assistant.py")
    container_parser.add_argument("container_args", nargs=argparse.REMAINDER)

    ecs_passthrough = services.add_parser("ecs", help="Shorthand forward to container_assistant.py ecs")
    ecs_passthrough.add_argument("ecs_args", nargs=argparse.REMAINDER)

    eks_passthrough = services.add_parser("eks", help="Shorthand forward to container_assistant.py eks")
    eks_passthrough.add_argument("eks_args", nargs=argparse.REMAINDER)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args(_expand_equals_args(sys.argv[1:]))

    if args.service == "lambda":
        return _forward_to_script("lambda_assistant.py", list(args.lambda_args or []))

    if args.service == "container":
        return _forward_to_script("container_assistant.py", list(args.container_args or []))

    if args.service == "ecs":
        return _forward_to_script("container_assistant.py", ["ecs"] + list(args.ecs_args or []))

    if args.service == "eks":
        return _forward_to_script("container_assistant.py", ["eks"] + list(args.eks_args or []))

    if args.service == "s3":
        if args.s3_command == "delete-bucket":
            s3_delete_bucket(bucket=args.bucket, force_empty=args.force_empty, assume_yes=args.yes)
            return 0
        return _forward_to_script("uploader.py", sys.argv[2:])

    if args.service == "iam":
        if args.iam_command == "summary":
            iam_permission_summary(args.principal_type, args.principal_name)
            return 0
        if args.iam_command == "policy-template":
            iam_policy_template(args.template_name, output_file=args.output)
            return 0
        parser.print_help()
        return 1

    if args.service == "logs":
        if args.logs_command == "lambda":
            if args.quick_errors:
                logs_quick_search(
                    target="lambda",
                    minutes=args.minutes,
                    limit=args.limit,
                    function_name=args.function_name,
                )
            else:
                logs_tail_lambda(
                    function_name=args.function_name,
                    minutes=args.minutes,
                    limit=args.limit,
                    filter_pattern=args.filter_pattern,
                )
            return 0

        if args.logs_command == "ecs":
            if args.quick_errors:
                logs_quick_search(
                    target="ecs",
                    minutes=args.minutes,
                    limit=args.limit,
                    cluster=args.cluster,
                    task=args.task,
                    region=args.region,
                )
            else:
                logs_tail_ecs_task(
                    cluster=args.cluster,
                    task=args.task,
                    minutes=args.minutes,
                    limit=args.limit,
                    region=args.region,
                )
            return 0

        if args.logs_command == "eks":
            if args.quick_errors:
                logs_quick_search(
                    target="eks",
                    minutes=args.minutes,
                    limit=0,
                    pod=args.pod,
                    namespace=args.namespace,
                    container=args.container,
                )
            else:
                logs_tail_eks_pod(
                    pod=args.pod,
                    namespace=args.namespace,
                    minutes=args.minutes,
                    container=args.container,
                    grep_terms=args.grep,
                )
            return 0

        parser.print_help()
        return 1

    if args.service == "safety":
        if args.safety_command == "scan":
            safety_scan(region=args.region)
            return 0
        parser.print_help()
        return 1

    if args.service == "config":
        if args.config_command == "show":
            config_show()
            return 0
        if args.config_command == "init":
            config_init(force=args.force)
            return 0
        parser.print_help()
        return 1

    if args.service == "tui":
        return run_tui(fancy=not args.plain)

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

    if args.ec2_command == "terminate":
        ec2_terminate(
            instance_ids=args.instance_ids,
            name=args.name,
            tag=args.tag,
            wait=args.wait,
            assume_yes=args.yes,
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
