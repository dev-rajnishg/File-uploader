from dotenv import load_dotenv
import boto3

load_dotenv()

lambda_client = boto3.client(
    'lambda',
    region_name='ap-south-1'
)

try:
    response = lambda_client.update_function_configuration(
        FunctionName='demo-function-test',
        Handler='handler.lambda_handler'
    )
    print(f"✓ Updated handler to: handler.lambda_handler")
except Exception as e:
    print(f"Error: {e}")
