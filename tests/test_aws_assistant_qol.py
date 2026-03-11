import json
from pathlib import Path
from unittest.mock import MagicMock

import aws_assistant
import pytest


def test_expand_equals_args_still_supported() -> None:
    result = aws_assistant._expand_equals_args(["ec2", "terminate", "name=demo", "yes=true"])
    assert result == ["ec2", "terminate", "--name", "demo", "--yes", "true"]


def test_summarize_policy_document_counts_allow_and_deny() -> None:
    summary = aws_assistant._summarize_policy_document(
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"]},
                {"Effect": "Deny", "Action": "s3:DeleteObject"},
            ],
        }
    )

    assert summary["statement_count"] == 2
    assert summary["allow_action_count"] == 2
    assert summary["deny_action_count"] == 1


def test_iam_policy_template_writes_file(tmp_path: Path) -> None:
    output_file = tmp_path / "policy.json"
    aws_assistant.iam_policy_template("ec2-start-stop", output_file=str(output_file))

    payload = json.loads(output_file.read_text(encoding="utf-8"))
    actions = payload["Statement"][0]["Action"]
    assert "ec2:StartInstances" in actions
    assert "ec2:StopInstances" in actions


def test_config_init_creates_yaml(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / ".aws-assistant.yml"
    monkeypatch.setattr(aws_assistant, "CONFIG_PATH", config_path)

    aws_assistant.config_init()

    loaded = aws_assistant._load_assistant_config()
    assert loaded["defaults"]["region"] == "ap-south-1"
    assert loaded["safety"]["require_confirmation"] is True


def test_iam_permission_summary_role(monkeypatch, capsys) -> None:
    fake_iam = MagicMock()
    fake_iam.list_attached_role_policies.return_value = {
        "AttachedPolicies": [{"PolicyName": "ReadOnlyAccess", "PolicyArn": "arn:aws:iam::123:policy/ReadOnlyAccess"}]
    }
    fake_iam.list_role_policies.return_value = {"PolicyNames": ["InlineOps"]}
    fake_iam.get_policy.return_value = {"Policy": {"DefaultVersionId": "v1"}}
    fake_iam.get_policy_version.return_value = {
        "PolicyVersion": {
            "Document": {
                "Statement": [{"Effect": "Allow", "Action": ["ec2:DescribeInstances"]}]
            }
        }
    }
    fake_iam.get_role_policy.return_value = {
        "PolicyDocument": {
            "Statement": [{"Effect": "Deny", "Action": ["ec2:TerminateInstances"]}]
        }
    }

    monkeypatch.setattr(aws_assistant, "_iam_client", lambda: fake_iam)

    aws_assistant.iam_permission_summary("role", "demo-role")
    output = capsys.readouterr().out

    assert "Principal: role/demo-role" in output
    assert "managed:ReadOnlyAccess" in output
    assert "inline:InlineOps" in output


def test_parse_selection_valid_numeric() -> None:
    assert aws_assistant._parse_selection("2", 5) == 1


def test_parse_selection_back_commands() -> None:
    assert aws_assistant._parse_selection("q", 5) is None
    assert aws_assistant._parse_selection("back", 5) is None


def test_parse_selection_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        aws_assistant._parse_selection("x", 3)

    with pytest.raises(ValueError):
        aws_assistant._parse_selection("4", 3)


def test_parse_quick_action_tokenizes_quotes() -> None:
    tokens = aws_assistant._parse_quick_action('ec2 stop name "my dev box" --wait')
    assert tokens == ["ec2", "stop", "name", "my dev box", "--wait"]


def test_execute_quick_action_ec2_stop(monkeypatch) -> None:
    calls = []

    def fake_power_action(action, **kwargs):
        calls.append((action, kwargs))

    monkeypatch.setattr(aws_assistant, "ec2_power_action", fake_power_action)
    aws_assistant.execute_quick_action("ec2 stop name demo-box --wait")

    assert calls[0][0] == "stop"
    assert calls[0][1]["name"] == "demo-box"
    assert calls[0][1]["wait"] is True


def test_execute_quick_action_iam_summary(monkeypatch) -> None:
    calls = []

    def fake_summary(principal_type, principal_name):
        calls.append((principal_type, principal_name))

    monkeypatch.setattr(aws_assistant, "iam_permission_summary", fake_summary)
    aws_assistant.execute_quick_action("iam summary role app-role")

    assert calls == [("role", "app-role")]


def test_execute_quick_action_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        aws_assistant.execute_quick_action("unknown thing")


def test_execute_quick_action_alias_ec2_stop(monkeypatch) -> None:
    calls = []

    def fake_power_action(action, **kwargs):
        calls.append((action, kwargs))

    monkeypatch.setattr(aws_assistant, "ec2_power_action", fake_power_action)
    aws_assistant.execute_quick_action("ec2 sp name demo-box")

    assert calls[0][0] == "stop"
    assert calls[0][1]["name"] == "demo-box"


def test_execute_quick_action_alias_logs_lambda(monkeypatch) -> None:
    calls = []

    def fake_logs_quick_search(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(aws_assistant, "logs_quick_search", fake_logs_quick_search)
    aws_assistant.execute_quick_action("ls-lambda demo-fn 15")

    assert calls == [{"target": "lambda", "minutes": 15, "limit": 200, "function_name": "demo-fn"}]


def test_execute_quick_action_alias_scan(monkeypatch) -> None:
    called = {"ok": False}

    def fake_scan():
        called["ok"] = True

    monkeypatch.setattr(aws_assistant, "safety_scan", fake_scan)
    aws_assistant.execute_quick_action("scan")
    assert called["ok"] is True
