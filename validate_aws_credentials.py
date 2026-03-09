"""
AWS Credentials Validation Script

This script validates AWS credentials from the .env file and tests if boto3
can successfully authenticate with those credentials.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

print("=" * 70)
print("AWS CREDENTIALS VALIDATION SCRIPT")
print("=" * 70)

# Step 1: Check if .env file exists
print("\n[1/5] Checking .env file...")
if env_path.exists():
    print(f"✓ .env file found at: {env_path}")
else:
    print(f"✗ .env file NOT found at: {env_path}")
    print("   Please create a .env file with AWS credentials.")
    sys.exit(1)

# Step 2: Check if credentials are present
print("\n[2/5] Checking for AWS credentials in environment...")
aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
aws_region = os.getenv("AWS_REGION", "ap-south-1")

credentials_present = True

if aws_access_key:
    # Show first 8 chars to verify without exposing full key
    print(f"✓ AWS_ACCESS_KEY_ID found: {aws_access_key[:8]}***")
else:
    print("✗ AWS_ACCESS_KEY_ID not found in .env")
    credentials_present = False

if aws_secret_key:
    print(f"✓ AWS_SECRET_ACCESS_KEY found: {aws_secret_key[:8]}***")
else:
    print("✗ AWS_SECRET_ACCESS_KEY not found in .env")
    credentials_present = False

if aws_region:
    print(f"✓ AWS_REGION: {aws_region}")
else:
    print("✗ AWS_REGION not specified (using default: ap-south-1)")

if not credentials_present:
    print("\n✗ Missing required AWS credentials!")
    sys.exit(1)

# Step 3: Validate credential format
print("\n[3/5] Validating credential format...")

# AWS Access Key ID should be 20 characters alphanumeric
if len(aws_access_key) == 20 and aws_access_key.isalnum():
    print(f"✓ AWS_ACCESS_KEY_ID format looks valid (length: 20)")
else:
    print(f"⚠ AWS_ACCESS_KEY_ID format may be incorrect (length: {len(aws_access_key)})")
    print("  Expected: 20 alphanumeric characters")

# AWS Secret Access Key should be 40 characters alphanumeric including special chars
if len(aws_secret_key) == 40:
    print(f"✓ AWS_SECRET_ACCESS_KEY format looks valid (length: 40)")
else:
    print(f"⚠ AWS_SECRET_ACCESS_KEY format may be incorrect (length: {len(aws_secret_key)})")
    print("  Expected: 40 characters")

# Step 4: Test boto3 installation
print("\n[4/5] Checking boto3 installation...")
try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError
    print(f"✓ boto3 is installed (version: {boto3.__version__})")
except ImportError as e:
    print(f"✗ boto3 is not installed: {e}")
    print("  Run: pip install boto3")
    sys.exit(1)

# Step 5: Test AWS credentials with boto3
print("\n[5/5] Testing AWS credentials with boto3...")
try:
    # Create S3 client with explicit credentials
    s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        region_name=aws_region,
    )
    
    # Try to list S3 buckets (minimal operation that requires valid credentials)
    response = s3_client.list_buckets()
    buckets = response.get("Buckets", [])
    
    print("✓ Successfully connected to AWS S3!")
    print(f"✓ Found {len(buckets)} S3 bucket(s):")
    if buckets:
        for bucket in buckets:
            print(f"  - {bucket['Name']}")
    else:
        print("  (No buckets found, but credentials are valid)")
    
    print("\n" + "=" * 70)
    print("✓ ALL CHECKS PASSED - AWS CREDENTIALS ARE VALID AND WORKING!")
    print("=" * 70)
    sys.exit(0)

except ClientError as e:
    error_code = e.response.get("Error", {}).get("Code", "Unknown")
    error_msg = e.response.get("Error", {}).get("Message", str(e))
    print(f"✗ AWS Authentication Failed!")
    print(f"  Error: {error_code}")
    print(f"  Message: {error_msg}")
    
    if error_code == "InvalidAccessKeyId":
        print("  → The AWS_ACCESS_KEY_ID is invalid or doesn't exist")
    elif error_code == "SignatureDoesNotMatch":
        print("  → The AWS_SECRET_ACCESS_KEY doesn't match the Access Key ID")
    elif error_code == "AccessDenied":
        print("  → The credentials don't have permission to list S3 buckets")
    
    print("\n" + "=" * 70)
    print("✗ AWS CREDENTIALS VALIDATION FAILED")
    print("=" * 70)
    sys.exit(1)

except BotoCoreError as e:
    print(f"✗ Boto3 Configuration Error: {e}")
    print("  This may be a network issue or invalid region.")
    print("\n" + "=" * 70)
    print("✗ AWS CREDENTIALS VALIDATION FAILED")
    print("=" * 70)
    sys.exit(1)

except Exception as e:
    print(f"✗ Unexpected error: {e}")
    print("\n" + "=" * 70)
    print("✗ AWS CREDENTIALS VALIDATION FAILED")
    print("=" * 70)
    sys.exit(1)
