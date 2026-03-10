# Changelog

All notable changes to this project will be documented in this file.

## [1.2.0] - 2026-03-10
### Added
- New `container_assistant.py` CLI for comprehensive container orchestration:
  - **ECS Operations**: Register task definitions, update/scale services, list services/tasks, stop tasks
  - **EKS Operations**: Update kubeconfig, get cluster info, apply/delete Kubernetes manifests, list pods
  - **Docker Operations**: Build images, tag images, push to registries
  - **ECR Operations**: Create repositories, login automation, list images, complete build-to-ECR push workflow
- Container example templates:
  - `ecs_task_definition.example.json` - ECS Fargate task definition
  - `Dockerfile.example` - Python application containerization
  - `k8s_deployment.example.yaml` - Kubernetes deployment and service
- Container test suite with 19 tests in `tests/test_container_assistant.py`.

### Changed
- Updated `README.md` with complete container workflows and command examples.
- Updated `instructions.md` with container command quick reference.
- Updated `.gitignore` for container artifacts (Dockerfiles, task definitions, k8s manifests).
- Total test count: 44 tests (5 EC2 + 20 Lambda + 19 Container).

### Verified
- Full test suite passes: 44 passed, 0 failed.
- ECS operations tested with mock boto3 clients.
- EKS/kubectl operations tested with subprocess mocking.
- Docker build/tag/push workflow tested.
- ECR repository and image management tested.

## [1.1.0] - 2026-03-10
### Added
- New `lambda_assistant.py` CLI for Lambda workflows:
  - Create functions (`create`)
  - Package and deploy code (`deploy`)
  - Test invoke with event payloads (`test`)
  - Manage EventBridge schedules (`schedule create|list|delete`)
- Lambda workflow test suite in `tests/test_lambda_assistant.py`.
- Organized test files under `tests/` and setup utilities under `setup/`.
- Demo Lambda source in `lambda_demo/handler.py`.
- Example Lambda config template in `lambda_config.example.json`.
- Workflow guide in `LAMBDA_WORKFLOW_DEMO.md`.

### Changed
- Updated `README.md` to reflect public developer usage and current feature set.
- Updated `instructions.md` with Lambda command coverage.
- Updated `requirements.txt` with test/runtime dependencies used by the toolkit.
- Updated `.gitignore` for public repo behavior:
  - Keep examples, tests, and setup scripts visible in git.
  - Ignore local secrets, local configs, caches, and build artifacts.

### Verified
- Full test suite passes from `tests/`:
  - 25 passed, 0 failed.
