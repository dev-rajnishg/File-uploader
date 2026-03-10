# Changelog

All notable changes to this project will be documented in this file.

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
