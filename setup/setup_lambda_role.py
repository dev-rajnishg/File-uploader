from dotenv import load_dotenv
import boto3
import json

load_dotenv()

account_id = "911167892844"
role_name = "lambda-demo-execution-role"

iam = boto3.client('iam')

# Check if role exists
try:
    response = iam.get_role(RoleName=role_name)
    role_arn = response['Role']['Arn']
    print(f"✓ Found existing role: {role_arn}")
except iam.exceptions.NoSuchEntityException:
    print(f"Role not found, attempting to create: {role_name}")
    
    # Create trust policy for Lambda
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    try:
        response = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Execution role for demo Lambda functions"
        )
        role_arn = response['Role']['Arn']
        print(f"✓ Created new role: {role_arn}")
        
        # Attach basic Lambda execution policy
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        )
        print("✓ Attached basic Lambda execution policy")
        
    except Exception as e:
        print(f"Error creating role: {e}")
        exit(1)

print(f"\nUse this role ARN for creating Lambda functions:")
print(f"  {role_arn}")
