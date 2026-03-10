import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import boto3
import yaml
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv()


def _lambda_client():
    return boto3.client(
        "lambda",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "ap-south-1"),
    )


def _events_client():
    return boto3.client(
        "events",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "ap-south-1"),
    )


def _logs_client():
    return boto3.client(
        "logs",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION", "ap-south-1"),
    )


def _load_config(config_path: str) -> dict:
    """Load Lambda deployment config from JSON or YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path, "r", encoding="utf-8") as f:
        if path.suffix in [".yaml", ".yml"]:
            return yaml.safe_load(f)
        else:
            return json.load(f)


def _create_deployment_package(
    source_dir: str,
    output_zip: str,
    requirements_file: str = None,
    exclude_patterns: list = None
) -> str:
    """
    Create a Lambda deployment package with code and dependencies.
    
    Args:
        source_dir: Directory containing Lambda code
        output_zip: Output zip file path
        requirements_file: Optional requirements.txt for dependencies
        exclude_patterns: Optional list of patterns to exclude
    
    Returns:
        Path to created zip file
    """
    exclude_patterns = exclude_patterns or [
        "__pycache__",
        "*.pyc",
        ".venv",
        "venv",
        ".env",
        ".git",
        "*.log",
        "test_*.py",
        "*_test.py"
    ]
    
    source_path = Path(source_dir)
    if not source_path.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")
    
    output_path = Path(output_zip)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create temp directory for building package
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Install dependencies if requirements.txt provided
        if requirements_file and Path(requirements_file).exists():
            print(f"Installing dependencies from {requirements_file}...")
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    requirements_file,
                    "-t",
                    str(temp_path),
                    "--upgrade",
                ],
                check=True,
                capture_output=True,
            )
        
        # Copy source files to temp directory
        print(f"Copying source files from {source_dir}...")
        for item in source_path.rglob("*"):
            if item.is_file():
                # Check exclusion patterns
                relative = item.relative_to(source_path)
                should_exclude = False
                
                for pattern in exclude_patterns:
                    if "*" in pattern:
                        import fnmatch
                        if fnmatch.fnmatch(str(relative), pattern):
                            should_exclude = True
                            break
                    elif pattern in str(relative):
                        should_exclude = True
                        break
                
                if not should_exclude:
                    dest = temp_path / relative
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)
        
        # Create zip file
        print(f"Creating deployment package: {output_zip}")
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for item in temp_path.rglob("*"):
                if item.is_file():
                    arcname = item.relative_to(temp_path)
                    zipf.write(item, arcname)
        
        zip_size = output_path.stat().st_size
        print(f"Package created: {output_zip} ({zip_size:,} bytes)")
    
    return str(output_path)


def lambda_package_deploy(
    function_name: str,
    config_path: str = None,
    source_dir: str = None,
    requirements_file: str = None,
    output_zip: str = None,
    update_env: bool = False,
) -> None:
    """
    Package Lambda code and dependencies, then deploy to AWS.
    
    Args:
        function_name: Name of Lambda function
        config_path: Optional config file with deployment settings
        source_dir: Directory containing Lambda code
        requirements_file: Optional requirements.txt
        output_zip: Output zip file path
        update_env: Whether to update environment variables from config
    """
    config = {}
    if config_path:
        config = _load_config(config_path)
        function_config = config.get("functions", {}).get(function_name, {})
        
        # Override with config values if not provided
        source_dir = source_dir or function_config.get("source_dir", "lambda_")
        requirements_file = requirements_file or function_config.get("requirements", "requirements.txt")
        output_zip = output_zip or function_config.get("output_zip", f"dist/{function_name}.zip")
    
    # Set defaults
    source_dir = source_dir or "lambda_"
    output_zip = output_zip or f"dist/{function_name}.zip"
    
    # Create deployment package
    zip_path = _create_deployment_package(
        source_dir=source_dir,
        output_zip=output_zip,
        requirements_file=requirements_file if requirements_file and Path(requirements_file).exists() else None,
    )
    
    # Deploy to Lambda
    lambda_client = _lambda_client()
    
    try:
        print(f"Deploying to Lambda function: {function_name}")
        with open(zip_path, "rb") as f:
            zip_bytes = f.read()
        
        response = lambda_client.update_function_code(
            FunctionName=function_name,
            ZipFile=zip_bytes,
        )
        
        print(f"✓ Code updated successfully")
        print(f"  Function ARN: {response['FunctionArn']}")
        print(f"  Runtime: {response['Runtime']}")
        print(f"  Last Modified: {response['LastModified']}")
        
        # Update environment variables if requested
        if update_env and config_path:
            function_config = config.get("functions", {}).get(function_name, {})
            env_vars = function_config.get("environment", {})
            
            if env_vars:
                print(f"Updating environment variables...")
                lambda_client.update_function_configuration(
                    FunctionName=function_name,
                    Environment={"Variables": env_vars}
                )
                print(f"✓ Environment variables updated")
        
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            raise RuntimeError(
                f"Lambda function '{function_name}' not found. Create it first via AWS Console or IaC."
            )
        else:
            raise RuntimeError(f"Deployment failed: {e}")


def lambda_test_invoke(
    function_name: str,
    event_file: str,
    show_logs: bool = True,
    tail_logs: bool = False,
) -> None:
    """
    Invoke Lambda function with a test event and display results.
    
    Args:
        function_name: Name of Lambda function to invoke
        event_file: Path to JSON file containing test event
        show_logs: Whether to fetch and display CloudWatch logs
        tail_logs: Whether to include tail logs in response
    """
    # Load event payload
    event_path = Path(event_file)
    if not event_path.exists():
        raise FileNotFoundError(f"Event file not found: {event_file}")
    
    with open(event_path, "r", encoding="utf-8") as f:
        event_payload = json.load(f)
    
    print(f"Invoking Lambda function: {function_name}")
    print(f"Event file: {event_file}")
    print("-" * 60)
    
    # Invoke Lambda
    lambda_client = _lambda_client()
    
    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            LogType="Tail" if tail_logs else "None",
            Payload=json.dumps(event_payload),
        )
        
        # Parse response
        status_code = response["StatusCode"]
        payload = response["Payload"].read().decode("utf-8")
        
        print(f"\n✓ Invocation Status: {status_code}")
        
        # Display function error if present
        if "FunctionError" in response:
            print(f"⚠ Function Error: {response['FunctionError']}")
        
        # Display response payload
        print("\nResponse Payload:")
        print("-" * 60)
        try:
            payload_json = json.loads(payload)
            print(json.dumps(payload_json, indent=2))
        except json.JSONDecodeError:
            print(payload)
        
        # Display tail logs if requested
        if tail_logs and "LogResult" in response:
            print("\nExecution Logs (tail):")
            print("-" * 60)
            log_data = base64.b64decode(response["LogResult"]).decode("utf-8")
            print(log_data)
        
        # Fetch CloudWatch logs if requested
        if show_logs and not tail_logs:
            print("\nFetching CloudWatch Logs...")
            print("-" * 60)
            _fetch_recent_logs(function_name)
        
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            raise RuntimeError(f"Lambda function '{function_name}' not found")
        else:
            raise RuntimeError(f"Invocation failed: {e}")


def _fetch_recent_logs(function_name: str, minutes: int = 5) -> None:
    """Fetch recent CloudWatch logs for a Lambda function."""
    logs_client = _logs_client()
    log_group_name = f"/aws/lambda/{function_name}"
    
    try:
        # Get recent log streams
        response = logs_client.describe_log_streams(
            logGroupName=log_group_name,
            orderBy="LastEventTime",
            descending=True,
            limit=3,
        )
        
        if not response.get("logStreams"):
            print("No log streams found")
            return
        
        # Fetch log events from most recent stream
        log_stream = response["logStreams"][0]
        log_stream_name = log_stream["logStreamName"]
        
        events_response = logs_client.get_log_events(
            logGroupName=log_group_name,
            logStreamName=log_stream_name,
            startFromHead=False,
            limit=50,
        )
        
        events = events_response.get("events", [])
        if events:
            for event in reversed(events[-20:]):  # Show last 20 events
                timestamp = datetime.fromtimestamp(event["timestamp"] / 1000)
                message = event["message"].rstrip()
                print(f"[{timestamp.strftime('%H:%M:%S')}] {message}")
        else:
            print("No log events found")
            
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            print(f"Log group not found: {log_group_name}")
        else:
            print(f"Failed to fetch logs: {e}")


def lambda_schedule_create(
    rule_name: str,
    function_name: str,
    schedule_expression: str,
    description: str = None,
    event_payload: str = None,
) -> None:
    """
    Create an EventBridge rule to run a Lambda on a schedule.
    
    Args:
        rule_name: Name for the EventBridge rule
        function_name: Name of Lambda function to invoke
        schedule_expression: Cron or rate expression (e.g., 'rate(1 hour)', 'cron(0 22 * * ? *)')
        description: Optional description for the rule
        event_payload: Optional JSON string or file path for event input
    """
    events_client = _events_client()
    lambda_client = _lambda_client()
    
    # Get Lambda function ARN
    try:
        lambda_response = lambda_client.get_function(FunctionName=function_name)
        function_arn = lambda_response["Configuration"]["FunctionArn"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            raise RuntimeError(f"Lambda function '{function_name}' not found")
        raise
    
    # Parse event payload
    event_input = None
    if event_payload:
        event_path = Path(event_payload)
        if event_path.exists():
            with open(event_path, "r", encoding="utf-8") as f:
                event_input = f.read()
        else:
            event_input = event_payload
    
    # Create EventBridge rule
    try:
        print(f"Creating EventBridge rule: {rule_name}")
        
        rule_params = {
            "Name": rule_name,
            "ScheduleExpression": schedule_expression,
            "State": "ENABLED",
        }
        
        if description:
            rule_params["Description"] = description
        
        rule_response = events_client.put_rule(**rule_params)
        rule_arn = rule_response["RuleArn"]
        
        print(f"✓ Rule created: {rule_arn}")
        
        # Add Lambda as target
        print(f"Adding Lambda function as target...")
        
        target_params = {
            "Rule": rule_name,
            "Targets": [
                {
                    "Id": "1",
                    "Arn": function_arn,
                }
            ],
        }
        
        if event_input:
            target_params["Targets"][0]["Input"] = event_input
        
        events_client.put_targets(**target_params)
        
        print(f"✓ Target added: {function_name}")
        
        # Add Lambda permission for EventBridge to invoke
        print(f"Adding Lambda permission for EventBridge...")
        
        statement_id = f"{rule_name}-invoke-permission"
        
        try:
            lambda_client.add_permission(
                FunctionName=function_name,
                StatementId=statement_id,
                Action="lambda:InvokeFunction",
                Principal="events.amazonaws.com",
                SourceArn=rule_arn,
            )
            print(f"✓ Permission granted")
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceConflictException":
                print(f"⚠ Permission already exists")
            else:
                raise
        
        print(f"\nSchedule created successfully!")
        print(f"  Rule: {rule_name}")
        print(f"  Function: {function_name}")
        print(f"  Schedule: {schedule_expression}")
        
    except ClientError as e:
        raise RuntimeError(f"Failed to create schedule: {e}")


def lambda_schedule_list(function_name: str = None) -> None:
    """
    List EventBridge rules, optionally filtered by Lambda function target.
    
    Args:
        function_name: Optional Lambda function name to filter rules
    """
    events_client = _events_client()
    lambda_client = _lambda_client()
    
    try:
        # List all rules
        response = events_client.list_rules()
        rules = response.get("Rules", [])
        
        if not rules:
            print("No EventBridge rules found")
            return
        
        # Filter by function name if provided
        if function_name:
            # Get function ARN
            lambda_response = lambda_client.get_function(FunctionName=function_name)
            function_arn = lambda_response["Configuration"]["FunctionArn"]
            
            # Filter rules by target
            filtered_rules = []
            for rule in rules:
                targets_response = events_client.list_targets_by_rule(Rule=rule["Name"])
                targets = targets_response.get("Targets", [])
                
                if any(target.get("Arn") == function_arn for target in targets):
                    filtered_rules.append(rule)
            
            rules = filtered_rules
        
        if not rules:
            print(f"No rules found for function: {function_name}")
            return
        
        print(f"EventBridge Rules{' for ' + function_name if function_name else ''}:")
        print("-" * 80)
        
        for rule in rules:
            state_icon = "✓" if rule["State"] == "ENABLED" else "✗"
            print(f"{state_icon} {rule['Name']}")
            print(f"  Schedule: {rule.get('ScheduleExpression', 'N/A')}")
            print(f"  State: {rule['State']}")
            
            if "Description" in rule:
                print(f"  Description: {rule['Description']}")
            
            # Get targets
            targets_response = events_client.list_targets_by_rule(Rule=rule["Name"])
            targets = targets_response.get("Targets", [])
            
            if targets:
                print(f"  Targets:")
                for target in targets:
                    arn = target.get("Arn", "")
                    target_name = arn.split(":")[-1] if ":" in arn else arn
                    print(f"    - {target_name}")
            
            print()
        
    except ClientError as e:
        raise RuntimeError(f"Failed to list rules: {e}")


def lambda_schedule_delete(rule_name: str) -> None:
    """
    Delete an EventBridge rule and remove targets.
    
    Args:
        rule_name: Name of the EventBridge rule to delete
    """
    events_client = _events_client()
    
    try:
        print(f"Deleting EventBridge rule: {rule_name}")
        
        # Remove all targets first
        targets_response = events_client.list_targets_by_rule(Rule=rule_name)
        target_ids = [target["Id"] for target in targets_response.get("Targets", [])]
        
        if target_ids:
            print(f"Removing {len(target_ids)} target(s)...")
            events_client.remove_targets(Rule=rule_name, Ids=target_ids)
            print(f"✓ Targets removed")
        
        # Delete the rule
        events_client.delete_rule(Name=rule_name)
        print(f"✓ Rule deleted: {rule_name}")
        
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            raise RuntimeError(f"Rule '{rule_name}' not found")
        else:
            raise RuntimeError(f"Failed to delete rule: {e}")


def lambda_create_function(
    function_name: str,
    role_arn: str,
    runtime: str = "python3.11",
    handler: str = "index.handler",
    timeout: int = 30,
    memory: int = 128,
    description: str = None,
    environment: dict = None,
    vpc_config: dict = None,
) -> None:
    """
    Create a new Lambda function.
    
    Args:
        function_name: Name of the Lambda function
        role_arn: ARN of IAM role for Lambda execution
        runtime: Lambda runtime (e.g., python3.11, python3.12, nodejs18.x)
        handler: Handler for the function (e.g., index.handler, handler.lambda_handler)
        timeout: Timeout in seconds (default: 30)
        memory: Memory in MB (128-10240, default: 128)
        description: Optional description
        environment: Optional dict of environment variables
        vpc_config: Optional VPC configuration dict
    """
    lambda_client = _lambda_client()
    
    # Validate memory
    if not (128 <= memory <= 10240):
        raise ValueError("Memory must be between 128 and 10240 MB")
    
    # Validate timeout
    if not (1 <= timeout <= 900):
        raise ValueError("Timeout must be between 1 and 900 seconds")
    
    try:
        print(f"Creating Lambda function: {function_name}")
        print(f"  Role: {role_arn}")
        print(f"  Runtime: {runtime}")
        print(f"  Handler: {handler}")
        print(f"  Memory: {memory} MB")
        print(f"  Timeout: {timeout}s")
        
        # Create a minimal valid zip file with basic handler code
        import io
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            handler_code = '''def handler(event, context):
    """Basic Lambda handler function."""
    return {
        'statusCode': 200,
        'body': 'Hello from Lambda!'
    }
'''
            zf.writestr('index.py', handler_code)
        zip_bytes = zip_buffer.getvalue()
        
        create_params = {
            "FunctionName": function_name,
            "Role": role_arn,
            "Code": {"ZipFile": zip_bytes},
            "Handler": handler,
            "Runtime": runtime,
            "Timeout": timeout,
            "MemorySize": memory,
        }
        
        if description:
            create_params["Description"] = description
        
        if environment:
            create_params["Environment"] = {"Variables": environment}
        
        if vpc_config:
            create_params["VpcConfig"] = vpc_config
        
        response = lambda_client.create_function(**create_params)
        
        print(f"\n✓ Function created successfully!")
        print(f"  Function ARN: {response['FunctionArn']}")
        print(f"  Function Name: {response['FunctionName']}")
        print(f"  Runtime: {response['Runtime']}")
        print(f"  CodeSha256: {response['CodeSha256']}")
        
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceConflictException":
            raise RuntimeError(f"Function '{function_name}' already exists")
        elif error_code == "InvalidParameterValueException":
            raise RuntimeError(f"Invalid parameter: {e.response['Error']['Message']}")
        else:
            raise RuntimeError(f"Failed to create function: {e}")


def _build_parser() -> argparse.ArgumentParser:
    """Build argument parser for Lambda assistant CLI."""
    parser = argparse.ArgumentParser(
        description="AWS Lambda Assistant - deployment, testing, and scheduling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create function command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new Lambda function",
    )
    create_parser.add_argument("function_name", help="Lambda function name")
    create_parser.add_argument("role_arn", help="IAM role ARN for Lambda execution")
    create_parser.add_argument(
        "--runtime",
        default="python3.11",
        help="Lambda runtime (default: python3.11)",
    )
    create_parser.add_argument(
        "--handler",
        default="index.handler",
        help="Handler name (default: index.handler)",
    )
    create_parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds (1-900, default: 30)",
    )
    create_parser.add_argument(
        "--memory",
        type=int,
        default=128,
        help="Memory in MB (128-10240, default: 128)",
    )
    create_parser.add_argument(
        "--description",
        help="Function description",
    )
    
    # Package & Deploy command
    deploy_parser = subparsers.add_parser(
        "deploy",
        help="Package and deploy Lambda function",
    )
    deploy_parser.add_argument("function_name", help="Lambda function name")
    deploy_parser.add_argument(
        "--config",
        help="Config file with deployment settings (JSON/YAML)",
    )
    deploy_parser.add_argument(
        "--source-dir",
        help="Directory containing Lambda code (default: lambda_)",
    )
    deploy_parser.add_argument(
        "--requirements",
        help="Requirements file for dependencies (default: requirements.txt)",
    )
    deploy_parser.add_argument(
        "--output",
        help="Output zip file path (default: dist/<function_name>.zip)",
    )
    deploy_parser.add_argument(
        "--update-env",
        action="store_true",
        help="Update environment variables from config file",
    )
    
    # Test invoke command
    test_parser = subparsers.add_parser(
        "test",
        help="Invoke Lambda with test event",
    )
    test_parser.add_argument("function_name", help="Lambda function name")
    test_parser.add_argument("event_file", help="JSON file with test event")
    test_parser.add_argument(
        "--no-logs",
        action="store_true",
        help="Skip CloudWatch logs fetch",
    )
    test_parser.add_argument(
        "--tail",
        action="store_true",
        help="Include tail logs in response (instead of CloudWatch)",
    )
    
    # Schedule commands
    schedule_parser = subparsers.add_parser(
        "schedule",
        help="Manage Lambda schedules (EventBridge rules)",
    )
    schedule_subparsers = schedule_parser.add_subparsers(
        dest="schedule_command",
        help="Schedule sub-command",
    )
    
    # Schedule create
    schedule_create_parser = schedule_subparsers.add_parser(
        "create",
        help="Create scheduled Lambda invocation",
    )
    schedule_create_parser.add_argument("rule_name", help="EventBridge rule name")
    schedule_create_parser.add_argument("function_name", help="Lambda function name")
    schedule_create_parser.add_argument(
        "schedule_expression",
        help="Schedule expression (e.g., 'rate(1 hour)', 'cron(0 22 * * ? *)')",
    )
    schedule_create_parser.add_argument(
        "--description",
        help="Description for the rule",
    )
    schedule_create_parser.add_argument(
        "--event",
        help="Event payload (JSON string or file path)",
    )
    
    # Schedule list
    schedule_list_parser = schedule_subparsers.add_parser(
        "list",
        help="List EventBridge rules",
    )
    schedule_list_parser.add_argument(
        "--function",
        help="Filter by Lambda function name",
    )
    
    # Schedule delete
    schedule_delete_parser = schedule_subparsers.add_parser(
        "delete",
        help="Delete EventBridge rule",
    )
    schedule_delete_parser.add_argument("rule_name", help="EventBridge rule name")
    
    return parser


def main():
    """Main entry point for Lambda assistant CLI."""
    parser = _build_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == "create":
            lambda_create_function(
                function_name=args.function_name,
                role_arn=args.role_arn,
                runtime=args.runtime,
                handler=args.handler,
                timeout=args.timeout,
                memory=args.memory,
                description=args.description,
            )
        
        elif args.command == "deploy":
            lambda_package_deploy(
                function_name=args.function_name,
                config_path=args.config,
                source_dir=args.source_dir,
                requirements_file=args.requirements,
                output_zip=args.output,
                update_env=args.update_env,
            )
        
        elif args.command == "test":
            lambda_test_invoke(
                function_name=args.function_name,
                event_file=args.event_file,
                show_logs=not args.no_logs,
                tail_logs=args.tail,
            )
        
        elif args.command == "schedule":
            if not args.schedule_command:
                parser.parse_args(["schedule", "--help"])
                sys.exit(1)
            
            if args.schedule_command == "create":
                lambda_schedule_create(
                    rule_name=args.rule_name,
                    function_name=args.function_name,
                    schedule_expression=args.schedule_expression,
                    description=args.description,
                    event_payload=args.event,
                )
            
            elif args.schedule_command == "list":
                lambda_schedule_list(function_name=args.function)
            
            elif args.schedule_command == "delete":
                lambda_schedule_delete(rule_name=args.rule_name)
        
        else:
            parser.print_help()
            sys.exit(1)
    
    except (ValueError, RuntimeError, FileNotFoundError, BotoCoreError, ClientError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
