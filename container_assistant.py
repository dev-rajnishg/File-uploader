#!/usr/bin/env python3
"""
AWS Container Assistant - ECS, EKS, and Docker operations
Simplifies container orchestration and management tasks
"""

import argparse
import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def get_aws_clients():
    """Initialize AWS clients with credentials from environment"""
    session_kwargs = {
        'aws_access_key_id': os.getenv('AWS_ACCESS_KEY_ID'),
        'aws_secret_access_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
        'region_name': os.getenv('AWS_REGION', 'ap-south-1')
    }
    
    ecs_client = boto3.client('ecs', **session_kwargs)
    eks_client = boto3.client('eks', **session_kwargs)
    ecr_client = boto3.client('ecr', **session_kwargs)
    sts_client = boto3.client('sts', **session_kwargs)
    
    return ecs_client, eks_client, ecr_client, sts_client


# ============================================================================
# ECS OPERATIONS
# ============================================================================

def ecs_register_task_definition(template_file):
    """Register a new ECS task definition from JSON template"""
    print(f"📝 Registering task definition from: {template_file}")
    
    if not os.path.exists(template_file):
        print(f"❌ Template file not found: {template_file}")
        return None
    
    with open(template_file, 'r') as f:
        task_def = json.load(f)
    
    ecs_client, _, _, _ = get_aws_clients()
    
    try:
        response = ecs_client.register_task_definition(**task_def)
        revision = response['taskDefinition']['revision']
        family = response['taskDefinition']['family']
        
        print(f"✅ Task definition registered: {family}:{revision}")
        print(f"   ARN: {response['taskDefinition']['taskDefinitionArn']}")
        return response['taskDefinition']
    
    except Exception as e:
        print(f"❌ Failed to register task definition: {e}")
        return None


def ecs_update_service(cluster, service, task_definition=None, desired_count=None, force_new_deployment=False):
    """Update ECS service with new task definition or desired count"""
    print(f"🔄 Updating service: {service} in cluster: {cluster}")
    
    ecs_client, _, _, _ = get_aws_clients()
    
    update_params = {
        'cluster': cluster,
        'service': service
    }
    
    if task_definition:
        update_params['taskDefinition'] = task_definition
        print(f"   Task definition: {task_definition}")
    
    if desired_count is not None:
        update_params['desiredCount'] = desired_count
        print(f"   Desired count: {desired_count}")
    
    if force_new_deployment:
        update_params['forceNewDeployment'] = True
        print(f"   Force new deployment: True")
    
    try:
        response = ecs_client.update_service(**update_params)
        
        print(f"✅ Service updated successfully")
        print(f"   Service ARN: {response['service']['serviceArn']}")
        print(f"   Desired count: {response['service']['desiredCount']}")
        print(f"   Running count: {response['service']['runningCount']}")
        
        return response['service']
    
    except Exception as e:
        print(f"❌ Failed to update service: {e}")
        return None


def ecs_scale_service(cluster, service, desired_count):
    """Scale ECS service to desired count"""
    return ecs_update_service(cluster, service, desired_count=desired_count)


def ecs_list_services(cluster):
    """List all ECS services in a cluster"""
    print(f"📋 Listing services in cluster: {cluster}")
    
    ecs_client, _, _, _ = get_aws_clients()
    
    try:
        # List service ARNs
        response = ecs_client.list_services(cluster=cluster)
        service_arns = response.get('serviceArns', [])
        
        if not service_arns:
            print("   No services found")
            return []
        
        # Describe services for details
        services_response = ecs_client.describe_services(
            cluster=cluster,
            services=service_arns
        )
        
        services = services_response.get('services', [])
        
        print(f"\n{'Service Name':<30} {'Status':<12} {'Desired':<10} {'Running':<10} {'Task Definition'}")
        print("-" * 100)
        
        for svc in services:
            name = svc['serviceName']
            status = svc['status']
            desired = svc['desiredCount']
            running = svc['runningCount']
            task_def = svc['taskDefinition'].split('/')[-1]
            
            print(f"{name:<30} {status:<12} {desired:<10} {running:<10} {task_def}")
        
        return services
    
    except Exception as e:
        print(f"❌ Failed to list services: {e}")
        return []


def ecs_list_tasks(cluster, service=None):
    """List tasks in cluster, optionally filtered by service"""
    print(f"📋 Listing tasks in cluster: {cluster}")
    if service:
        print(f"   Service filter: {service}")
    
    ecs_client, _, _, _ = get_aws_clients()
    
    try:
        list_params = {'cluster': cluster}
        if service:
            list_params['serviceName'] = service
        
        response = ecs_client.list_tasks(**list_params)
        task_arns = response.get('taskArns', [])
        
        if not task_arns:
            print("   No tasks found")
            return []
        
        # Describe tasks for details
        tasks_response = ecs_client.describe_tasks(
            cluster=cluster,
            tasks=task_arns
        )
        
        tasks = tasks_response.get('tasks', [])
        
        print(f"\n{'Task ID':<25} {'Status':<15} {'Health':<12} {'Task Definition'}")
        print("-" * 90)
        
        for task in tasks:
            task_id = task['taskArn'].split('/')[-1]
            status = task['lastStatus']
            health = task.get('healthStatus', 'N/A')
            task_def = task['taskDefinitionArn'].split('/')[-1]
            
            print(f"{task_id:<25} {status:<15} {health:<12} {task_def}")
        
        return tasks
    
    except Exception as e:
        print(f"❌ Failed to list tasks: {e}")
        return []


def ecs_stop_task(cluster, task, reason="Stopped via container assistant"):
    """Stop a running ECS task"""
    print(f"🛑 Stopping task: {task} in cluster: {cluster}")
    
    ecs_client, _, _, _ = get_aws_clients()
    
    try:
        response = ecs_client.stop_task(
            cluster=cluster,
            task=task,
            reason=reason
        )
        
        print(f"✅ Task stopped: {response['task']['taskArn']}")
        return response['task']
    
    except Exception as e:
        print(f"❌ Failed to stop task: {e}")
        return None


# ============================================================================
# EKS OPERATIONS
# ============================================================================

def eks_update_kubeconfig(cluster_name, region=None, alias=None):
    """Update kubeconfig to connect to EKS cluster"""
    print(f"🔐 Updating kubeconfig for EKS cluster: {cluster_name}")
    
    if not region:
        region = os.getenv('AWS_REGION', 'ap-south-1')
    
    cmd = [
        'aws', 'eks', 'update-kubeconfig',
        '--name', cluster_name,
        '--region', region
    ]
    
    if alias:
        cmd.extend(['--alias', alias])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ Kubeconfig updated successfully")
        print(result.stdout)
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to update kubeconfig: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"❌ AWS CLI not found. Please install AWS CLI first.")
        return False


def eks_get_cluster_info(cluster_name):
    """Get EKS cluster information"""
    print(f"ℹ️  Getting cluster info: {cluster_name}")
    
    _, eks_client, _, _ = get_aws_clients()
    
    try:
        response = eks_client.describe_cluster(name=cluster_name)
        cluster = response['cluster']
        
        print(f"\n{'Cluster Name':<20}: {cluster['name']}")
        print(f"{'Status':<20}: {cluster['status']}")
        print(f"{'Version':<20}: {cluster['version']}")
        print(f"{'Endpoint':<20}: {cluster['endpoint']}")
        print(f"{'Platform Version':<20}: {cluster.get('platformVersion', 'N/A')}")
        print(f"{'Created':<20}: {cluster['createdAt']}")
        
        return cluster
    
    except Exception as e:
        print(f"❌ Failed to get cluster info: {e}")
        return None


def eks_apply_manifest(manifest_file, namespace=None):
    """Apply Kubernetes manifest to EKS cluster"""
    print(f"⚙️  Applying manifest: {manifest_file}")
    
    if not os.path.exists(manifest_file):
        print(f"❌ Manifest file not found: {manifest_file}")
        return False
    
    cmd = ['kubectl', 'apply', '-f', manifest_file]
    
    if namespace:
        cmd.extend(['-n', namespace])
        print(f"   Namespace: {namespace}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ Manifest applied successfully")
        print(result.stdout)
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to apply manifest: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"❌ kubectl not found. Please install kubectl first.")
        return False


def eks_delete_manifest(manifest_file, namespace=None):
    """Delete resources from Kubernetes manifest"""
    print(f"🗑️  Deleting resources from manifest: {manifest_file}")
    
    if not os.path.exists(manifest_file):
        print(f"❌ Manifest file not found: {manifest_file}")
        return False
    
    cmd = ['kubectl', 'delete', '-f', manifest_file]
    
    if namespace:
        cmd.extend(['-n', namespace])
        print(f"   Namespace: {namespace}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ Resources deleted successfully")
        print(result.stdout)
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to delete resources: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"❌ kubectl not found. Please install kubectl first.")
        return False


def eks_list_pods(namespace='default', all_namespaces=False):
    """List pods in EKS cluster"""
    print(f"📋 Listing pods")
    
    cmd = ['kubectl', 'get', 'pods']
    
    if all_namespaces:
        cmd.append('--all-namespaces')
        print(f"   All namespaces: True")
    else:
        cmd.extend(['-n', namespace])
        print(f"   Namespace: {namespace}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(result.stdout)
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to list pods: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"❌ kubectl not found. Please install kubectl first.")
        return False


# ============================================================================
# DOCKER & ECR OPERATIONS
# ============================================================================

def docker_build(dockerfile_path, image_tag, build_args=None, no_cache=False):
    """Build Docker image from Dockerfile"""
    print(f"🐳 Building Docker image: {image_tag}")
    print(f"   Dockerfile: {dockerfile_path}")
    
    dockerfile_dir = os.path.dirname(dockerfile_path) or '.'
    
    cmd = ['docker', 'build', '-t', image_tag, '-f', dockerfile_path, dockerfile_dir]
    
    if build_args:
        for key, value in build_args.items():
            cmd.extend(['--build-arg', f'{key}={value}'])
    
    if no_cache:
        cmd.append('--no-cache')
    
    try:
        result = subprocess.run(cmd, check=True)
        print(f"✅ Image built successfully: {image_tag}")
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to build image: {e}")
        return False
    except FileNotFoundError:
        print(f"❌ Docker not found. Please install Docker first.")
        return False


def docker_tag(source_image, target_image):
    """Tag Docker image"""
    print(f"🏷️  Tagging image: {source_image} -> {target_image}")
    
    cmd = ['docker', 'tag', source_image, target_image]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✅ Image tagged successfully")
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to tag image: {e}")
        return False


def docker_push(image_tag):
    """Push Docker image to registry"""
    print(f"⬆️  Pushing image: {image_tag}")
    
    cmd = ['docker', 'push', image_tag]
    
    try:
        result = subprocess.run(cmd, check=True)
        print(f"✅ Image pushed successfully: {image_tag}")
        return True
    
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to push image: {e}")
        return False


def ecr_create_repository(repository_name, image_tag_mutability='MUTABLE', scan_on_push=True):
    """Create ECR repository"""
    print(f"📦 Creating ECR repository: {repository_name}")
    
    _, _, ecr_client, _ = get_aws_clients()
    
    try:
        response = ecr_client.create_repository(
            repositoryName=repository_name,
            imageTagMutability=image_tag_mutability,
            imageScanningConfiguration={
                'scanOnPush': scan_on_push
            }
        )
        
        repo = response['repository']
        print(f"✅ Repository created: {repo['repositoryUri']}")
        return repo
    
    except ClientError as e:
        if e.response['Error']['Code'] == 'RepositoryAlreadyExistsException':
            print(f"ℹ️  Repository already exists: {repository_name}")
            # Get existing repository
            response = ecr_client.describe_repositories(repositoryNames=[repository_name])
            return response['repositories'][0]
        else:
            print(f"❌ Failed to create repository: {e}")
            return None
    
    except Exception as e:
        print(f"❌ Failed to create repository: {e}")
        return None


def ecr_get_login_password():
    """Get ECR login password and login to Docker"""
    print(f"🔐 Logging into ECR")
    
    _, _, ecr_client, sts_client = get_aws_clients()
    
    try:
        # Get account ID
        account_id = sts_client.get_caller_identity()['Account']
        region = os.getenv('AWS_REGION', 'ap-south-1')
        
        # Get authorization token
        response = ecr_client.get_authorization_token()
        auth_data = response['authorizationData'][0]
        
        # Extract password
        import base64
        token = base64.b64decode(auth_data['authorizationToken']).decode('utf-8')
        username, password = token.split(':')
        
        # Docker login
        registry_url = f"{account_id}.dkr.ecr.{region}.amazonaws.com"
        
        cmd = ['docker', 'login', '--username', username, '--password-stdin', registry_url]
        
        result = subprocess.run(
            cmd,
            input=password,
            text=True,
            capture_output=True,
            check=True
        )
        
        print(f"✅ Successfully logged into ECR: {registry_url}")
        return registry_url
    
    except Exception as e:
        print(f"❌ Failed to login to ECR: {e}")
        return None


def ecr_list_images(repository_name):
    """List images in ECR repository"""
    print(f"📋 Listing images in repository: {repository_name}")
    
    _, _, ecr_client, _ = get_aws_clients()
    
    try:
        response = ecr_client.list_images(
            repositoryName=repository_name,
            maxResults=100
        )
        
        images = response.get('imageIds', [])
        
        if not images:
            print("   No images found")
            return []
        
        print(f"\n{'Image Tag':<40} {'Image Digest'}")
        print("-" * 80)
        
        for img in images:
            tag = img.get('imageTag', 'untagged')
            digest = img.get('imageDigest', 'N/A')[:20] + '...'
            print(f"{tag:<40} {digest}")
        
        return images
    
    except Exception as e:
        print(f"❌ Failed to list images: {e}")
        return []


def docker_ecr_push_flow(dockerfile, image_name, image_tag='latest', repository_name=None):
    """Complete flow: build -> tag -> ECR login -> push"""
    print(f"🚀 Complete Docker to ECR push flow")
    print(f"   Dockerfile: {dockerfile}")
    print(f"   Image: {image_name}:{image_tag}")
    
    # Step 1: Build image
    local_tag = f"{image_name}:{image_tag}"
    if not docker_build(dockerfile, local_tag):
        return False
    
    # Step 2: Create ECR repository if needed
    if not repository_name:
        repository_name = image_name
    
    repo = ecr_create_repository(repository_name)
    if not repo:
        return False
    
    # Step 3: ECR login
    registry_url = ecr_get_login_password()
    if not registry_url:
        return False
    
    # Step 4: Tag for ECR
    ecr_tag = f"{registry_url}/{repository_name}:{image_tag}"
    if not docker_tag(local_tag, ecr_tag):
        return False
    
    # Step 5: Push to ECR
    if not docker_push(ecr_tag):
        return False
    
    print(f"\n✅ Complete flow finished successfully")
    print(f"   ECR Image: {ecr_tag}")
    
    return True


# ============================================================================
# CLI ARGUMENT PARSER
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='AWS Container Assistant - ECS, EKS, and Docker operations',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # ========== ECS COMMANDS ==========
    ecs_parser = subparsers.add_parser('ecs', help='ECS operations')
    ecs_subparsers = ecs_parser.add_subparsers(dest='ecs_command', help='ECS command')
    
    # ECS Register Task Definition
    ecs_register = ecs_subparsers.add_parser('register', help='Register task definition from JSON template')
    ecs_register.add_argument('template', help='Path to task definition JSON template')
    
    # ECS Update Service
    ecs_update = ecs_subparsers.add_parser('update-service', help='Update ECS service')
    ecs_update.add_argument('cluster', help='Cluster name')
    ecs_update.add_argument('service', help='Service name')
    ecs_update.add_argument('--task-definition', help='New task definition (family:revision)')
    ecs_update.add_argument('--desired-count', type=int, help='Desired task count')
    ecs_update.add_argument('--force-deploy', action='store_true', help='Force new deployment')
    
    # ECS Scale Service
    ecs_scale = ecs_subparsers.add_parser('scale', help='Scale ECS service')
    ecs_scale.add_argument('cluster', help='Cluster name')
    ecs_scale.add_argument('service', help='Service name')
    ecs_scale.add_argument('count', type=int, help='Desired task count')
    
    # ECS List Services
    ecs_list_svc = ecs_subparsers.add_parser('list-services', help='List services in cluster')
    ecs_list_svc.add_argument('cluster', help='Cluster name')
    
    # ECS List Tasks
    ecs_list_tasks = ecs_subparsers.add_parser('list-tasks', help='List tasks in cluster')
    ecs_list_tasks.add_argument('cluster', help='Cluster name')
    ecs_list_tasks.add_argument('--service', help='Filter by service name')
    
    # ECS Stop Task
    ecs_stop = ecs_subparsers.add_parser('stop-task', help='Stop a running task')
    ecs_stop.add_argument('cluster', help='Cluster name')
    ecs_stop.add_argument('task', help='Task ID or ARN')
    ecs_stop.add_argument('--reason', default='Stopped via container assistant', help='Stop reason')
    
    # ========== EKS COMMANDS ==========
    eks_parser = subparsers.add_parser('eks', help='EKS operations')
    eks_subparsers = eks_parser.add_subparsers(dest='eks_command', help='EKS command')
    
    # EKS Update Kubeconfig
    eks_kubeconfig = eks_subparsers.add_parser('connect', help='Update kubeconfig for EKS cluster')
    eks_kubeconfig.add_argument('cluster', help='Cluster name')
    eks_kubeconfig.add_argument('--region', help='AWS region')
    eks_kubeconfig.add_argument('--alias', help='Kubeconfig context alias')
    
    # EKS Cluster Info
    eks_info = eks_subparsers.add_parser('info', help='Get cluster information')
    eks_info.add_argument('cluster', help='Cluster name')
    
    # EKS Apply Manifest
    eks_apply = eks_subparsers.add_parser('apply', help='Apply Kubernetes manifest')
    eks_apply.add_argument('manifest', help='Path to manifest file')
    eks_apply.add_argument('--namespace', '-n', help='Kubernetes namespace')
    
    # EKS Delete Manifest
    eks_delete = eks_subparsers.add_parser('delete', help='Delete resources from manifest')
    eks_delete.add_argument('manifest', help='Path to manifest file')
    eks_delete.add_argument('--namespace', '-n', help='Kubernetes namespace')
    
    # EKS List Pods
    eks_pods = eks_subparsers.add_parser('pods', help='List pods')
    eks_pods.add_argument('--namespace', '-n', default='default', help='Kubernetes namespace')
    eks_pods.add_argument('--all-namespaces', '-A', action='store_true', help='List pods from all namespaces')
    
    # ========== DOCKER COMMANDS ==========
    docker_parser = subparsers.add_parser('docker', help='Docker operations')
    docker_subparsers = docker_parser.add_subparsers(dest='docker_command', help='Docker command')
    
    # Docker Build
    docker_build_cmd = docker_subparsers.add_parser('build', help='Build Docker image')
    docker_build_cmd.add_argument('dockerfile', help='Path to Dockerfile')
    docker_build_cmd.add_argument('tag', help='Image tag (name:version)')
    docker_build_cmd.add_argument('--no-cache', action='store_true', help='Build without cache')
    
    # Docker Tag
    docker_tag_cmd = docker_subparsers.add_parser('tag', help='Tag Docker image')
    docker_tag_cmd.add_argument('source', help='Source image tag')
    docker_tag_cmd.add_argument('target', help='Target image tag')
    
    # Docker Push
    docker_push_cmd = docker_subparsers.add_parser('push', help='Push image to registry')
    docker_push_cmd.add_argument('tag', help='Image tag to push')
    
    # ========== ECR COMMANDS ==========
    ecr_parser = subparsers.add_parser('ecr', help='ECR operations')
    ecr_subparsers = ecr_parser.add_subparsers(dest='ecr_command', help='ECR command')
    
    # ECR Create Repository
    ecr_create = ecr_subparsers.add_parser('create-repo', help='Create ECR repository')
    ecr_create.add_argument('name', help='Repository name')
    ecr_create.add_argument('--immutable', action='store_true', help='Set image tag mutability to IMMUTABLE')
    ecr_create.add_argument('--no-scan', action='store_true', help='Disable scan on push')
    
    # ECR Login
    ecr_login = ecr_subparsers.add_parser('login', help='Login to ECR')
    
    # ECR List Images
    ecr_list = ecr_subparsers.add_parser('list-images', help='List images in repository')
    ecr_list.add_argument('repository', help='Repository name')
    
    # ECR Push Flow
    ecr_push_flow = ecr_subparsers.add_parser('push-flow', help='Complete build and push flow to ECR')
    ecr_push_flow.add_argument('dockerfile', help='Path to Dockerfile')
    ecr_push_flow.add_argument('image_name', help='Image name')
    ecr_push_flow.add_argument('--tag', default='latest', help='Image tag (default: latest)')
    ecr_push_flow.add_argument('--repository', help='ECR repository name (defaults to image_name)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Execute commands
    if args.command == 'ecs':
        if args.ecs_command == 'register':
            ecs_register_task_definition(args.template)
        
        elif args.ecs_command == 'update-service':
            ecs_update_service(
                args.cluster,
                args.service,
                task_definition=args.task_definition,
                desired_count=args.desired_count,
                force_new_deployment=args.force_deploy
            )
        
        elif args.ecs_command == 'scale':
            ecs_scale_service(args.cluster, args.service, args.count)
        
        elif args.ecs_command == 'list-services':
            ecs_list_services(args.cluster)
        
        elif args.ecs_command == 'list-tasks':
            ecs_list_tasks(args.cluster, service=args.service)
        
        elif args.ecs_command == 'stop-task':
            ecs_stop_task(args.cluster, args.task, reason=args.reason)
        
        else:
            ecs_parser.print_help()
    
    elif args.command == 'eks':
        if args.eks_command == 'connect':
            eks_update_kubeconfig(args.cluster, region=args.region, alias=args.alias)
        
        elif args.eks_command == 'info':
            eks_get_cluster_info(args.cluster)
        
        elif args.eks_command == 'apply':
            eks_apply_manifest(args.manifest, namespace=args.namespace)
        
        elif args.eks_command == 'delete':
            eks_delete_manifest(args.manifest, namespace=args.namespace)
        
        elif args.eks_command == 'pods':
            eks_list_pods(namespace=args.namespace, all_namespaces=args.all_namespaces)
        
        else:
            eks_parser.print_help()
    
    elif args.command == 'docker':
        if args.docker_command == 'build':
            docker_build(args.dockerfile, args.tag, no_cache=args.no_cache)
        
        elif args.docker_command == 'tag':
            docker_tag(args.source, args.target)
        
        elif args.docker_command == 'push':
            docker_push(args.tag)
        
        else:
            docker_parser.print_help()
    
    elif args.command == 'ecr':
        if args.ecr_command == 'create-repo':
            mutability = 'IMMUTABLE' if args.immutable else 'MUTABLE'
            scan_on_push = not args.no_scan
            ecr_create_repository(args.name, mutability, scan_on_push)
        
        elif args.ecr_command == 'login':
            ecr_get_login_password()
        
        elif args.ecr_command == 'list-images':
            ecr_list_images(args.repository)
        
        elif args.ecr_command == 'push-flow':
            docker_ecr_push_flow(
                args.dockerfile,
                args.image_name,
                args.tag,
                args.repository
            )
        
        else:
            ecr_parser.print_help()
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
