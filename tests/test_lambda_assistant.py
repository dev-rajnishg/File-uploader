import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, mock_open

import pytest

# Add parent directory to path to import lambda_assistant
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import lambda_assistant


@pytest.fixture
def mock_env():
    """Fixture to mock environment variables."""
    with patch.dict(os.environ, {
        'AWS_ACCESS_KEY_ID': 'test_key',
        'AWS_SECRET_ACCESS_KEY': 'test_secret',
        'AWS_REGION': 'ap-south-1'
    }):
        yield


@pytest.fixture
def temp_dir():
    """Fixture to create temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestConfigLoader:
    """Test config file loading."""
    
    def test_load_json_config(self, temp_dir):
        """Test loading JSON config."""
        config_file = temp_dir / "config.json"
        config_data = {"functions": {"test": {"source_dir": "lambda_"}}}
        
        with open(config_file, "w") as f:
            json.dump(config_data, f)
        
        result = lambda_assistant._load_config(str(config_file))
        assert result == config_data
    
    def test_load_yaml_config(self, temp_dir):
        """Test loading YAML config."""
        config_file = temp_dir / "config.yaml"
        config_content = "functions:\n  test:\n    source_dir: lambda_\n"
        
        with open(config_file, "w") as f:
            f.write(config_content)
        
        result = lambda_assistant._load_config(str(config_file))
        assert "functions" in result
        assert result["functions"]["test"]["source_dir"] == "lambda_"
    
    def test_load_missing_config(self):
        """Test loading non-existent config."""
        with pytest.raises(FileNotFoundError):
            lambda_assistant._load_config("missing.json")


class TestDeploymentPackage:
    """Test deployment package creation."""
    
    def test_create_simple_package(self, temp_dir):
        """Test creating deployment package with source files only."""
        # Create source directory with test files
        source_dir = temp_dir / "source"
        source_dir.mkdir()
        
        (source_dir / "handler.py").write_text("def lambda_handler(event, context):\n    pass")
        (source_dir / "utils.py").write_text("def helper():\n    pass")
        
        # Create output location
        output_zip = temp_dir / "output.zip"
        
        # Create package
        result = lambda_assistant._create_deployment_package(
            source_dir=str(source_dir),
            output_zip=str(output_zip),
            requirements_file=None
        )
        
        assert result == str(output_zip)
        assert output_zip.exists()
        
        # Verify zip contents
        with zipfile.ZipFile(output_zip, 'r') as zf:
            names = zf.namelist()
            assert "handler.py" in names
            assert "utils.py" in names
    
    def test_exclude_patterns(self, temp_dir):
        """Test exclusion patterns in package creation."""
        # Create source directory with files to exclude
        source_dir = temp_dir / "source"
        source_dir.mkdir()
        
        (source_dir / "handler.py").write_text("def lambda_handler(event, context):\n    pass")
        (source_dir / "test_handler.py").write_text("def test():\n    pass")
        (source_dir / ".env").write_text("SECRET=value")
        
        pycache = source_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "handler.pyc").write_text("compiled")
        
        # Create output location
        output_zip = temp_dir / "output.zip"
        
        # Create package with default exclusions
        lambda_assistant._create_deployment_package(
            source_dir=str(source_dir),
            output_zip=str(output_zip),
            requirements_file=None
        )
        
        # Verify exclusions
        with zipfile.ZipFile(output_zip, 'r') as zf:
            names = zf.namelist()
            assert "handler.py" in names
            assert "test_handler.py" not in names  # test_ pattern excluded
            assert ".env" not in names  # .env excluded
            assert not any("__pycache__" in name for name in names)


class TestLambdaDeploy:
    """Test Lambda deployment functions."""
    
    @patch('lambda_assistant._lambda_client')
    @patch('lambda_assistant._create_deployment_package')
    def test_deploy_without_config(self, mock_package, mock_client, temp_dir):
        """Test deployment without config file."""
        mock_package.return_value = str(temp_dir / "test.zip")
        
        # Create mock zip file
        zip_path = temp_dir / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("handler.py", "def lambda_handler(event, context): pass")
        
        # Mock Lambda client
        mock_lambda = MagicMock()
        mock_lambda.update_function_code.return_value = {
            'FunctionArn': 'arn:aws:lambda:ap-south-1:123456789012:function:test',
            'Runtime': 'python3.11',
            'LastModified': '2026-03-10T10:00:00.000+0000'
        }
        mock_client.return_value = mock_lambda
        
        # Create source directory
        source_dir = temp_dir / "lambda_"
        source_dir.mkdir()
        (source_dir / "handler.py").write_text("def lambda_handler(event, context): pass")
        
        # Deploy
        lambda_assistant.lambda_package_deploy(
            function_name="test-function",
            source_dir=str(source_dir),
            output_zip=str(zip_path)
        )
        
        # Verify calls
        mock_package.assert_called_once()
        mock_lambda.update_function_code.assert_called_once()
    
    @patch('lambda_assistant._lambda_client')
    @patch('lambda_assistant._create_deployment_package')
    def test_deploy_not_found(self, mock_package, mock_client, temp_dir):
        """Test deployment when function doesn't exist."""
        from botocore.exceptions import ClientError
        
        mock_package.return_value = str(temp_dir / "test.zip")
        
        # Create mock zip file
        zip_path = temp_dir / "test.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("handler.py", "def lambda_handler(event, context): pass")
        
        # Mock Lambda client to raise ResourceNotFoundException
        mock_lambda = MagicMock()
        mock_lambda.update_function_code.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException'}},
            'UpdateFunctionCode'
        )
        mock_client.return_value = mock_lambda
        
        # Create source directory
        source_dir = temp_dir / "lambda_"
        source_dir.mkdir()
        (source_dir / "handler.py").write_text("def lambda_handler(event, context): pass")
        
        # Deploy should raise RuntimeError
        with pytest.raises(RuntimeError, match="not found"):
            lambda_assistant.lambda_package_deploy(
                function_name="missing-function",
                source_dir=str(source_dir),
                output_zip=str(zip_path)
            )


class TestLambdaInvoke:
    """Test Lambda invocation functions."""
    
    @patch('lambda_assistant._lambda_client')
    @patch('lambda_assistant._fetch_recent_logs')
    def test_invoke_success(self, mock_logs, mock_client, temp_dir):
        """Test successful Lambda invocation."""
        # Create test event file
        event_file = temp_dir / "event.json"
        event_data = {"test": "data"}
        with open(event_file, "w") as f:
            json.dump(event_data, f)
        
        # Mock Lambda client
        mock_lambda = MagicMock()
        response_payload = json.dumps({"statusCode": 200, "body": "success"})
        mock_lambda.invoke.return_value = {
            'StatusCode': 200,
            'Payload': Mock(read=lambda: response_payload.encode('utf-8'))
        }
        mock_client.return_value = mock_lambda
        
        # Invoke
        lambda_assistant.lambda_test_invoke(
            function_name="test-function",
            event_file=str(event_file),
            show_logs=True
        )
        
        # Verify calls
        mock_lambda.invoke.assert_called_once()
        call_args = mock_lambda.invoke.call_args
        assert call_args[1]['FunctionName'] == 'test-function'
        
        # Verify event payload was passed correctly
        payload_arg = call_args[1]['Payload']
        assert json.loads(payload_arg) == event_data
    
    @patch('lambda_assistant._lambda_client')
    def test_invoke_missing_event_file(self, mock_client):
        """Test invocation with missing event file."""
        with pytest.raises(FileNotFoundError):
            lambda_assistant.lambda_test_invoke(
                function_name="test-function",
                event_file="missing.json",
                show_logs=False
            )


class TestScheduleCreate:
    """Test EventBridge schedule creation."""
    
    @patch('lambda_assistant._events_client')
    @patch('lambda_assistant._lambda_client')
    def test_create_schedule_basic(self, mock_lambda_client, mock_events_client):
        """Test basic schedule creation."""
        # Mock Lambda client
        mock_lambda = MagicMock()
        mock_lambda.get_function.return_value = {
            'Configuration': {
                'FunctionArn': 'arn:aws:lambda:ap-south-1:123456789012:function:test'
            }
        }
        mock_lambda.add_permission.return_value = {}
        mock_lambda_client.return_value = mock_lambda
        
        # Mock Events client
        mock_events = MagicMock()
        mock_events.put_rule.return_value = {
            'RuleArn': 'arn:aws:events:ap-south-1:123456789012:rule/test-rule'
        }
        mock_events.put_targets.return_value = {}
        mock_events_client.return_value = mock_events
        
        # Create schedule
        lambda_assistant.lambda_schedule_create(
            rule_name="test-rule",
            function_name="test-function",
            schedule_expression="rate(1 hour)",
            description="Test schedule"
        )
        
        # Verify calls
        mock_events.put_rule.assert_called_once()
        mock_events.put_targets.assert_called_once()
        mock_lambda.add_permission.assert_called_once()
        
        # Verify rule parameters
        rule_call = mock_events.put_rule.call_args[1]
        assert rule_call['Name'] == 'test-rule'
        assert rule_call['ScheduleExpression'] == 'rate(1 hour)'
        assert rule_call['State'] == 'ENABLED'
    
    @patch('lambda_assistant._events_client')
    @patch('lambda_assistant._lambda_client')
    def test_create_schedule_with_event_payload(self, mock_lambda_client, mock_events_client, temp_dir):
        """Test schedule creation with event payload."""
        # Create event file
        event_file = temp_dir / "event.json"
        event_data = {"action": "cleanup"}
        with open(event_file, "w") as f:
            json.dump(event_data, f)
        
        # Mock Lambda client
        mock_lambda = MagicMock()
        mock_lambda.get_function.return_value = {
            'Configuration': {
                'FunctionArn': 'arn:aws:lambda:ap-south-1:123456789012:function:test'
            }
        }
        mock_lambda.add_permission.return_value = {}
        mock_lambda_client.return_value = mock_lambda
        
        # Mock Events client
        mock_events = MagicMock()
        mock_events.put_rule.return_value = {
            'RuleArn': 'arn:aws:events:ap-south-1:123456789012:rule/test-rule'
        }
        mock_events.put_targets.return_value = {}
        mock_events_client.return_value = mock_events
        
        # Create schedule with event
        lambda_assistant.lambda_schedule_create(
            rule_name="test-rule",
            function_name="test-function",
            schedule_expression="cron(0 22 * * ? *)",
            event_payload=str(event_file)
        )
        
        # Verify targets include event input
        targets_call = mock_events.put_targets.call_args[1]
        assert 'Targets' in targets_call
        assert 'Input' in targets_call['Targets'][0]


class TestScheduleList:
    """Test EventBridge schedule listing."""
    
    @patch('lambda_assistant._events_client')
    def test_list_all_schedules(self, mock_events_client):
        """Test listing all schedules."""
        mock_events = MagicMock()
        mock_events.list_rules.return_value = {
            'Rules': [
                {
                    'Name': 'rule1',
                    'State': 'ENABLED',
                    'ScheduleExpression': 'rate(1 hour)'
                },
                {
                    'Name': 'rule2',
                    'State': 'DISABLED',
                    'ScheduleExpression': 'cron(0 22 * * ? *)'
                }
            ]
        }
        mock_events.list_targets_by_rule.return_value = {'Targets': []}
        mock_events_client.return_value = mock_events
        
        # List schedules
        lambda_assistant.lambda_schedule_list()
        
        # Verify calls
        mock_events.list_rules.assert_called_once()


class TestLambdaCreate:
    """Test Lambda function creation."""
    
    @patch('lambda_assistant._lambda_client')
    def test_create_function_success(self, mock_client):
        """Test successful Lambda function creation."""
        mock_lambda = MagicMock()
        mock_lambda.create_function.return_value = {
            'FunctionArn': 'arn:aws:lambda:ap-south-1:123456789012:function:test',
            'FunctionName': 'test',
            'Runtime': 'python3.11',
            'CodeSha256': 'abc123def456',
        }
        mock_client.return_value = mock_lambda
        
        # Create function
        lambda_assistant.lambda_create_function(
            function_name='test',
            role_arn='arn:aws:iam::123456789012:role/lambda-role',
            runtime='python3.11',
            handler='index.handler',
            timeout=30,
            memory=128,
            description='Test function'
        )
        
        # Verify calls
        mock_lambda.create_function.assert_called_once()
        call_args = mock_lambda.create_function.call_args[1]
        assert call_args['FunctionName'] == 'test'
        assert call_args['Runtime'] == 'python3.11'
        assert call_args['Handler'] == 'index.handler'
        assert call_args['Timeout'] == 30
        assert call_args['MemorySize'] == 128
        assert call_args['Description'] == 'Test function'
    
    @patch('lambda_assistant._lambda_client')
    def test_create_function_already_exists(self, mock_client):
        """Test creating function that already exists."""
        from botocore.exceptions import ClientError
        
        mock_lambda = MagicMock()
        mock_lambda.create_function.side_effect = ClientError(
            {'Error': {'Code': 'ResourceConflictException'}},
            'CreateFunction'
        )
        mock_client.return_value = mock_lambda
        
        # Create should raise RuntimeError
        with pytest.raises(RuntimeError, match="already exists"):
            lambda_assistant.lambda_create_function(
                function_name='test',
                role_arn='arn:aws:iam::123456789012:role/lambda-role'
            )
    
    def test_create_invalid_memory(self):
        """Test create with invalid memory."""
        with pytest.raises(ValueError, match="Memory must be between"):
            lambda_assistant.lambda_create_function(
                function_name='test',
                role_arn='arn:aws:iam::123456789012:role/lambda-role',
                memory=64  # Too low
            )
    
    def test_create_invalid_timeout(self):
        """Test create with invalid timeout."""
        with pytest.raises(ValueError, match="Timeout must be between"):
            lambda_assistant.lambda_create_function(
                function_name='test',
                role_arn='arn:aws:iam::123456789012:role/lambda-role',
                timeout=1000  # Too high
            )


class TestArgumentParser:
    """Test argument parser."""
    
    def test_deploy_command_parser(self):
        """Test deploy command parsing."""
        parser = lambda_assistant._build_parser()
        args = parser.parse_args([
            'deploy', 'test-function',
            '--config', 'config.json',
            '--update-env'
        ])
        
        assert args.command == 'deploy'
        assert args.function_name == 'test-function'
        assert args.config == 'config.json'
        assert args.update_env is True
    
    def test_create_command_parser(self):
        """Test create command parsing."""
        parser = lambda_assistant._build_parser()
        args = parser.parse_args([
            'create', 'test-function', 'arn:aws:iam::123456789012:role/lambda-role',
            '--runtime', 'python3.12',
            '--timeout', '60',
            '--memory', '256',
            '--description', 'Test function'
        ])
        
        assert args.command == 'create'
        assert args.function_name == 'test-function'
        assert args.role_arn == 'arn:aws:iam::123456789012:role/lambda-role'
        assert args.runtime == 'python3.12'
        assert args.timeout == 60
        assert args.memory == 256
        assert args.description == 'Test function'
    
    def test_test_command_parser(self):
        """Test test command parsing."""
        parser = lambda_assistant._build_parser()
        args = parser.parse_args([
            'test', 'test-function', 'event.json',
            '--tail'
        ])
        
        assert args.command == 'test'
        assert args.function_name == 'test-function'
        assert args.event_file == 'event.json'
        assert args.tail is True
    
    def test_schedule_create_parser(self):
        """Test schedule create command parsing."""
        parser = lambda_assistant._build_parser()
        args = parser.parse_args([
            'schedule', 'create',
            'test-rule', 'test-function', 'rate(1 hour)',
            '--description', 'Test schedule',
            '--event', 'event.json'
        ])
        
        assert args.command == 'schedule'
        assert args.schedule_command == 'create'
        assert args.rule_name == 'test-rule'
        assert args.function_name == 'test-function'
        assert args.schedule_expression == 'rate(1 hour)'
        assert args.description == 'Test schedule'
        assert args.event == 'event.json'
