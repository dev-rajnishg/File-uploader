from dotenv import load_dotenv
import boto3

load_dotenv()

try:
    sts = boto3.client('sts', region_name='ap-south-1')
    result = sts.get_caller_identity()
    account_id = result['Account']
    user_id = result['UserId']
    arn = result['Arn']
    
    print(f"Account ID: {account_id}")
    print(f"User ID: {user_id}")
    print(f"ARN: {arn}")
    
    # Now check for roles
    iam = boto3.client('iam')
    roles_response = iam.list_roles()
    roles = roles_response.get('Roles', [])
    
    print(f"\nAvailable Roles:")
    for role in roles[:5]:  # Show first 5
        print(f"  - {role['RoleName']}: {role['Arn']}")
    
    if len(roles) > 5:
        print(f"  ... and {len(roles) - 5} more roles")
        
except Exception as e:
    print(f"Error: {e}")
