from pathlib import Path
from unittest.mock import MagicMock

import pytest

import aws_assistant


def test_expand_equals_args_supports_shorthand() -> None:
    result = aws_assistant._expand_equals_args(
        ["ec2", "launch", "profile=dev-web", "config=ec2_profiles.example.json"]
    )
    assert result == [
        "ec2",
        "launch",
        "--profile",
        "dev-web",
        "--config",
        "ec2_profiles.example.json",
    ]


def test_ec2_start_by_name_waits_for_running(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_waiter = MagicMock()
    fake_ec2 = MagicMock()
    fake_ec2.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-12345",
                        "State": {"Name": "stopped"},
                        "Tags": [{"Key": "Name", "Value": "my-dev-box"}],
                    }
                ]
            }
        ]
    }
    fake_ec2.get_waiter.return_value = fake_waiter
    monkeypatch.setattr(aws_assistant, "_ec2_client", lambda: fake_ec2)

    aws_assistant.ec2_power_action("start", name="my-dev-box", wait=True)

    fake_ec2.describe_instances.assert_called_once_with(
        InstanceIds=[],
        Filters=[{"Name": "tag:Name", "Values": ["my-dev-box"]}],
    )
    fake_ec2.start_instances.assert_called_once_with(InstanceIds=["i-12345"])
    fake_ec2.get_waiter.assert_called_once_with("instance_running")
    fake_waiter.wait.assert_called_once_with(InstanceIds=["i-12345"])


def test_safe_snapshot_stops_and_restarts_for_root_consistency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_ec2 = MagicMock()
    fake_waiter = MagicMock()
    fake_ec2.get_waiter.return_value = fake_waiter
    fake_ec2.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-root",
                        "State": {"Name": "running"},
                        "RootDeviceName": "/dev/xvda",
                        "Tags": [{"Key": "Name", "Value": "root-box"}],
                        "BlockDeviceMappings": [
                            {"DeviceName": "/dev/xvda", "Ebs": {"VolumeId": "vol-root"}},
                            {"DeviceName": "/dev/xvdb", "Ebs": {"VolumeId": "vol-data"}},
                        ],
                    }
                ]
            }
        ]
    }
    fake_ec2.create_snapshot.side_effect = [
        {"SnapshotId": "snap-1"},
        {"SnapshotId": "snap-2"},
    ]
    monkeypatch.setattr(aws_assistant, "_ec2_client", lambda: fake_ec2)

    aws_assistant.ec2_safe_snapshot(
        name="root-box",
        stop_for_root_consistency=True,
        snapshot_tag=["Purpose=backup"],
    )

    fake_ec2.stop_instances.assert_called_once_with(InstanceIds=["i-root"])
    fake_ec2.start_instances.assert_called_once_with(InstanceIds=["i-root"])
    assert fake_ec2.create_snapshot.call_count == 2

    first_call = fake_ec2.create_snapshot.call_args_list[0].kwargs
    assert first_call["VolumeId"] == "vol-root"
    tags = first_call["TagSpecifications"][0]["Tags"]
    assert {"Key": "Purpose", "Value": "backup"} in tags


def test_safe_snapshot_requires_exactly_one_match(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_ec2 = MagicMock()
    fake_ec2.describe_instances.return_value = {
        "Reservations": [
            {"Instances": [{"InstanceId": "i-1", "State": {"Name": "running"}}]},
            {"Instances": [{"InstanceId": "i-2", "State": {"Name": "running"}}]},
        ]
    }
    monkeypatch.setattr(aws_assistant, "_ec2_client", lambda: fake_ec2)

    with pytest.raises(RuntimeError, match="exactly one"):
        aws_assistant.ec2_safe_snapshot(tag="Environment=dev")


def test_ec2_launch_profile_uses_sg_template_and_waits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "ec2_profiles.json"
    config_path.write_text(
        """
{
  "security_group_templates": {
    "web": ["sg-123", "sg-456"]
  },
  "profiles": {
    "dev-web": {
      "ami": "ami-abc",
      "instance_type": "t3.micro",
      "key_pair": "dev-key",
      "sg_template": "web",
      "tags": {
        "Environment": "dev"
      },
      "subnet_id": "subnet-1"
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    fake_ec2 = MagicMock()
    fake_waiter = MagicMock()
    fake_ec2.get_waiter.return_value = fake_waiter
    fake_ec2.run_instances.return_value = {"Instances": [{"InstanceId": "i-new"}]}
    monkeypatch.setattr(aws_assistant, "_ec2_client", lambda: fake_ec2)

    aws_assistant.ec2_launch_profile("dev-web", str(config_path), wait=True)

    run_kwargs = fake_ec2.run_instances.call_args.kwargs
    assert run_kwargs["ImageId"] == "ami-abc"
    assert run_kwargs["InstanceType"] == "t3.micro"
    assert run_kwargs["KeyName"] == "dev-key"
    assert run_kwargs["SubnetId"] == "subnet-1"
    assert run_kwargs["SecurityGroupIds"] == ["sg-123", "sg-456"]

    tags = run_kwargs["TagSpecifications"][0]["Tags"]
    assert {"Key": "Environment", "Value": "dev"} in tags
    assert {"Key": "Name", "Value": "dev-web"} in tags

    fake_ec2.get_waiter.assert_called_once_with("instance_running")
    fake_waiter.wait.assert_called_once_with(InstanceIds=["i-new"])