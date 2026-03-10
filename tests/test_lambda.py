import json
from lambda_handler import lambda_handler

# Mock event for S3 object creation
mock_event = {
    "Records": [
        {
            "s3": {
                "bucket": {
                    "name": "project.v1"
                },
                "object": {
                    "key": "edgar-AlknQO5aHfM-unsplash.jpg"
                }
            }
        }
    ]
}

# Mock context
class MockContext:
    def __init__(self):
        self.aws_request_id = "test-request-id"
        self.function_name = "test-function"
        self.memory_limit_in_mb = 128

mock_context = MockContext()

# Set environment variables (dummy values for testing)
import os
os.environ['TARGET_BUCKET'] = 'project.v1'
os.environ['SNS_TOPIC_ARN'] = 'arn:aws:sns:ap-south-1:123456789012:test-topic'

# Run the lambda handler
try:
    result = lambda_handler(mock_event, mock_context)
    print("Lambda handler result:", result)
except Exception as e:
    print("Error:", str(e))