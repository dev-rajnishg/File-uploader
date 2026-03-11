# GitHub Release Setup

This file explains how to release this package using GitHub Actions.

## Workflows Added

- .github/workflows/ci.yml
- .github/workflows/publish-python.yml
- .github/workflows/publish-container.yml

## 1) Configure Repository Secrets

Go to: Settings -> Secrets and variables -> Actions -> New repository secret

Add these secrets:

- PYPI_API_TOKEN
- TEST_PYPI_API_TOKEN

Token values should be API tokens from:

- https://pypi.org/manage/account/token/
- https://test.pypi.org/manage/account/token/

## 2) Validate CI

Push any commit or open a pull request.

The CI workflow will run tests, build package artifacts, and run twine checks.

## 3) Publish To TestPyPI

Go to Actions -> Publish Python Package -> Run workflow

Select:

- repository = testpypi

## 4) Publish To PyPI

Option A (manual):

Go to Actions -> Publish Python Package -> Run workflow

Select:

- repository = pypi

Option B (release-based):

Create a GitHub release. The workflow runs automatically and publishes to PyPI.

## 5) Publish Container (Optional)

Go to Actions -> Publish Container Image -> Run workflow

Requirements:

- Add a Dockerfile in repository root (not just Dockerfile.example)
- Choose image_name input

Image will be pushed to:

- ghcr.io/<owner>/<image_name>:latest
