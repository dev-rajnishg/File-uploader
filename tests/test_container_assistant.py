"""
Unit tests for container_assistant.py
Tests ECS, EKS, Docker, and ECR operations
"""

import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock, mock_open
import subprocess


# Mock AWS clients fixture
@pytest.fixture
def mock_aws_clients():
    """Mock AWS service clients"""
    with patch('container_assistant.get_aws_clients') as mock_get_clients:
        mock_ecs = Mock()
        mock_eks = Mock()
        mock_ecr = Mock()
        mock_sts = Mock()
        
        mock_get_clients.return_value = (mock_ecs, mock_eks, mock_ecr, mock_sts)
        
        yield {
            'ecs': mock_ecs,
            'eks': mock_eks,
            'ecr': mock_ecr,
            'sts': mock_sts
        }


# ============================================================================
# ECS TESTS
# ============================================================================

class TestECSOperations:
    """Test ECS task definition and service operations"""
    
    def test_register_task_definition_success(self, mock_aws_clients, tmp_path):
        """Test registering task definition from JSON template"""
        from container_assistant import ecs_register_task_definition
        
        # Create temporary task definition file
        task_def = {
            'family': 'test-task',
            'containerDefinitions': [{
                'name': 'test-container',
                'image': 'nginx:latest'
            }]
        }
        
        task_file = tmp_path / 'task.json'
        task_file.write_text(json.dumps(task_def))
        
        # Mock ECS response
        mock_aws_clients['ecs'].register_task_definition.return_value = {
            'taskDefinition': {
                'family': 'test-task',
                'revision': 1,
                'taskDefinitionArn': 'arn:aws:ecs:region:account:task-definition/test-task:1'
            }
        }
        
        # Execute
        result = ecs_register_task_definition(str(task_file))
        
        # Verify
        assert result is not None
        assert result['family'] == 'test-task'
        assert result['revision'] == 1
        mock_aws_clients['ecs'].register_task_definition.assert_called_once()
    
    def test_register_task_definition_file_not_found(self):
        """Test registering task definition with missing file"""
        from container_assistant import ecs_register_task_definition
        
        result = ecs_register_task_definition('nonexistent.json')
        
        assert result is None
    
    def test_update_service_with_task_definition(self, mock_aws_clients):
        """Test updating ECS service with new task definition"""
        from container_assistant import ecs_update_service
        
        # Mock ECS response
        mock_aws_clients['ecs'].update_service.return_value = {
            'service': {
                'serviceArn': 'arn:aws:ecs:region:account:service/my-cluster/my-service',
                'desiredCount': 2,
                'runningCount': 2
            }
        }
        
        # Execute
        result = ecs_update_service(
            'my-cluster',
            'my-service',
            task_definition='my-task:2'
        )
        
        # Verify
        assert result is not None
        assert result['desiredCount'] == 2
        mock_aws_clients['ecs'].update_service.assert_called_once()
        call_args = mock_aws_clients['ecs'].update_service.call_args[1]
        assert call_args['taskDefinition'] == 'my-task:2'
    
    def test_scale_service(self, mock_aws_clients):
        """Test scaling ECS service"""
        from container_assistant import ecs_scale_service
        
        # Mock ECS response
        mock_aws_clients['ecs'].update_service.return_value = {
            'service': {
                'serviceArn': 'arn:aws:ecs:region:account:service/my-cluster/my-service',
                'desiredCount': 5,
                'runningCount': 3
            }
        }
        
        # Execute
        result = ecs_scale_service('my-cluster', 'my-service', 5)
        
        # Verify
        assert result is not None
        assert result['desiredCount'] == 5
        call_args = mock_aws_clients['ecs'].update_service.call_args[1]
        assert call_args['desiredCount'] == 5
    
    def test_list_services(self, mock_aws_clients):
        """Test listing services in ECS cluster"""
        from container_assistant import ecs_list_services
        
        # Mock ECS responses
        mock_aws_clients['ecs'].list_services.return_value = {
            'serviceArns': ['arn:aws:ecs:region:account:service/my-cluster/service1']
        }
        
        mock_aws_clients['ecs'].describe_services.return_value = {
            'services': [{
                'serviceName': 'service1',
                'status': 'ACTIVE',
                'desiredCount': 2,
                'runningCount': 2,
                'taskDefinition': 'arn:aws:ecs:region:account:task-definition/my-task:1'
            }]
        }
        
        # Execute
        result = ecs_list_services('my-cluster')
        
        # Verify
        assert len(result) == 1
        assert result[0]['serviceName'] == 'service1'
    
    def test_stop_task(self, mock_aws_clients):
        """Test stopping ECS task"""
        from container_assistant import ecs_stop_task
        
        # Mock ECS response
        mock_aws_clients['ecs'].stop_task.return_value = {
            'task': {
                'taskArn': 'arn:aws:ecs:region:account:task/my-cluster/abc123'
            }
        }
        
        # Execute
        result = ecs_stop_task('my-cluster', 'abc123', reason='Test stop')
        
        # Verify
        assert result is not None
        mock_aws_clients['ecs'].stop_task.assert_called_once_with(
            cluster='my-cluster',
            task='abc123',
            reason='Test stop'
        )


# ============================================================================
# EKS TESTS
# ============================================================================

class TestEKSOperations:
    """Test EKS cluster and kubectl operations"""
    
    @patch('subprocess.run')
    def test_update_kubeconfig_success(self, mock_run):
        """Test updating kubeconfig for EKS cluster"""
        from container_assistant import eks_update_kubeconfig
        
        # Mock successful subprocess run
        mock_run.return_value = Mock(
            stdout='Added new context',
            returncode=0
        )
        
        # Execute
        result = eks_update_kubeconfig('my-cluster')
        
        # Verify
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'aws' in call_args
        assert 'eks' in call_args
        assert 'update-kubeconfig' in call_args
        assert 'my-cluster' in call_args
    
    @patch('subprocess.run')
    def test_update_kubeconfig_failure(self, mock_run):
        """Test kubeconfig update failure"""
        from container_assistant import eks_update_kubeconfig
        
        # Mock failed subprocess run
        mock_run.side_effect = subprocess.CalledProcessError(1, 'aws', stderr='Error')
        
        # Execute
        result = eks_update_kubeconfig('my-cluster')
        
        # Verify
        assert result is False
    
    def test_get_cluster_info(self, mock_aws_clients):
        """Test getting EKS cluster information"""
        from container_assistant import eks_get_cluster_info
        
        # Mock EKS response
        mock_aws_clients['eks'].describe_cluster.return_value = {
            'cluster': {
                'name': 'my-cluster',
                'status': 'ACTIVE',
                'version': '1.28',
                'endpoint': 'https://abc123.eks.amazonaws.com',
                'createdAt': '2024-01-01T00:00:00Z'
            }
        }
        
        # Execute
        result = eks_get_cluster_info('my-cluster')
        
        # Verify
        assert result is not None
        assert result['name'] == 'my-cluster'
        assert result['status'] == 'ACTIVE'
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_apply_manifest_success(self, mock_exists, mock_run):
        """Test applying Kubernetes manifest"""
        from container_assistant import eks_apply_manifest
        
        # Mock file exists
        mock_exists.return_value = True
        
        # Mock successful kubectl apply
        mock_run.return_value = Mock(
            stdout='deployment.apps/my-app created',
            returncode=0
        )
        
        # Execute
        result = eks_apply_manifest('deployment.yaml')
        
        # Verify
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'kubectl' in call_args
        assert 'apply' in call_args
    
    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_delete_manifest_success(self, mock_exists, mock_run):
        """Test deleting resources from manifest"""
        from container_assistant import eks_delete_manifest
        
        # Mock file exists
        mock_exists.return_value = True
        
        # Mock successful kubectl delete
        mock_run.return_value = Mock(
            stdout='deployment.apps/my-app deleted',
            returncode=0
        )
        
        # Execute
        result = eks_delete_manifest('deployment.yaml', namespace='default')
        
        # Verify
        assert result is True
        call_args = mock_run.call_args[0][0]
        assert 'kubectl' in call_args
        assert 'delete' in call_args
        assert '-n' in call_args
        assert 'default' in call_args


# ============================================================================
# DOCKER TESTS
# ============================================================================

class TestDockerOperations:
    """Test Docker build, tag, and push operations"""
    
    @patch('subprocess.run')
    @patch('os.path.dirname')
    def test_docker_build_success(self, mock_dirname, mock_run):
        """Test Docker image build"""
        from container_assistant import docker_build
        
        # Mock directory
        mock_dirname.return_value = '/app'
        
        # Mock successful docker build
        mock_run.return_value = Mock(returncode=0)
        
        # Execute
        result = docker_build('Dockerfile', 'my-app:latest')
        
        # Verify
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'docker' in call_args
        assert 'build' in call_args
        assert 'my-app:latest' in call_args
    
    @patch('subprocess.run')
    def test_docker_tag_success(self, mock_run):
        """Test Docker image tagging"""
        from container_assistant import docker_tag
        
        # Mock successful docker tag
        mock_run.return_value = Mock(returncode=0)
        
        # Execute
        result = docker_tag('my-app:latest', 'my-app:v1.0')
        
        # Verify
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'docker' in call_args
        assert 'tag' in call_args
        assert 'my-app:latest' in call_args
        assert 'my-app:v1.0' in call_args
    
    @patch('subprocess.run')
    def test_docker_push_success(self, mock_run):
        """Test Docker image push"""
        from container_assistant import docker_push
        
        # Mock successful docker push
        mock_run.return_value = Mock(returncode=0)
        
        # Execute
        result = docker_push('my-app:latest')
        
        # Verify
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'docker' in call_args
        assert 'push' in call_args
        assert 'my-app:latest' in call_args


# ============================================================================
# ECR TESTS
# ============================================================================

class TestECROperations:
    """Test ECR repository and image operations"""
    
    def test_create_repository_success(self, mock_aws_clients):
        """Test creating ECR repository"""
        from container_assistant import ecr_create_repository
        
        # Mock ECR response
        mock_aws_clients['ecr'].create_repository.return_value = {
            'repository': {
                'repositoryUri': '123456789012.dkr.ecr.ap-south-1.amazonaws.com/my-app',
                'repositoryName': 'my-app'
            }
        }
        
        # Execute
        result = ecr_create_repository('my-app')
        
        # Verify
        assert result is not None
        assert result['repositoryName'] == 'my-app'
        mock_aws_clients['ecr'].create_repository.assert_called_once()
    
    def test_create_repository_already_exists(self, mock_aws_clients):
        """Test creating repository that already exists"""
        from container_assistant import ecr_create_repository
        from botocore.exceptions import ClientError
        
        # Mock ECR exception for existing repo
        mock_aws_clients['ecr'].create_repository.side_effect = ClientError(
            {'Error': {'Code': 'RepositoryAlreadyExistsException', 'Message': 'Repository already exists'}},
            'create_repository'
        )
        
        # Create a proper exception class for the mock
        class RepositoryAlreadyExistsException(Exception):
            pass
        
        mock_aws_clients['ecr'].exceptions.RepositoryAlreadyExistsException = RepositoryAlreadyExistsException
        
        # Mock describe to return existing repo
        mock_aws_clients['ecr'].describe_repositories.return_value = {
            'repositories': [{
                'repositoryUri': '123456789012.dkr.ecr.ap-south-1.amazonaws.com/my-app',
                'repositoryName': 'my-app'
            }]
        }
        
        # Execute
        result = ecr_create_repository('my-app')
        
        # Verify
        assert result is not None
        assert result['repositoryName'] == 'my-app'
    
    def test_list_images(self, mock_aws_clients):
        """Test listing images in ECR repository"""
        from container_assistant import ecr_list_images
        
        # Mock ECR response
        mock_aws_clients['ecr'].list_images.return_value = {
            'imageIds': [
                {'imageTag': 'latest', 'imageDigest': 'sha256:abc123'},
                {'imageTag': 'v1.0', 'imageDigest': 'sha256:def456'}
            ]
        }
        
        # Execute
        result = ecr_list_images('my-app')
        
        # Verify
        assert len(result) == 2
        assert result[0]['imageTag'] == 'latest'
        assert result[1]['imageTag'] == 'v1.0'
    
    @patch('subprocess.run')
    @patch('base64.b64decode')
    def test_ecr_login_success(self, mock_b64decode, mock_run, mock_aws_clients):
        """Test ECR login flow"""
        from container_assistant import ecr_get_login_password
        
        # Mock STS response
        mock_aws_clients['sts'].get_caller_identity.return_value = {
            'Account': '123456789012'
        }
        
        # Mock ECR authorization response
        mock_aws_clients['ecr'].get_authorization_token.return_value = {
            'authorizationData': [{
                'authorizationToken': 'base64token'
            }]
        }
        
        # Mock base64 decode
        mock_b64decode.return_value = b'AWS:password123'
        
        # Mock successful docker login
        mock_run.return_value = Mock(returncode=0)
        
        # Execute
        result = ecr_get_login_password()
        
        # Verify
        assert result is not None
        assert '123456789012.dkr.ecr' in result
        mock_run.assert_called_once()


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegrationFlows:
    """Test complete integration workflows"""
    
    @patch('container_assistant.docker_build')
    @patch('container_assistant.ecr_create_repository')
    @patch('container_assistant.ecr_get_login_password')
    @patch('container_assistant.docker_tag')
    @patch('container_assistant.docker_push')
    def test_docker_ecr_push_flow(self, mock_push, mock_tag, mock_login, mock_create, mock_build):
        """Test complete Docker build and ECR push flow"""
        from container_assistant import docker_ecr_push_flow
        
        # Mock all steps to succeed
        mock_build.return_value = True
        mock_create.return_value = {'repositoryUri': '123456789012.dkr.ecr.ap-south-1.amazonaws.com/my-app'}
        mock_login.return_value = '123456789012.dkr.ecr.ap-south-1.amazonaws.com'
        mock_tag.return_value = True
        mock_push.return_value = True
        
        # Execute
        result = docker_ecr_push_flow('Dockerfile', 'my-app', 'v1.0')
        
        # Verify all steps were called
        assert result is True
        mock_build.assert_called_once()
        mock_create.assert_called_once()
        mock_login.assert_called_once()
        mock_tag.assert_called_once()
        mock_push.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
