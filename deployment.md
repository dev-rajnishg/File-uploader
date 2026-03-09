# AWS Lambda Image Thumbnail Generator Deployment

## Prerequisites
- Python 3.12
- AWS CLI configured
- Virtual environment (optional but recommended)

## Deployment Steps

1. Create a deployment package directory:
   ```
   mkdir package
   cd package
   ```

2. Install dependencies into the package directory:
   ```
   pip install boto3 Pillow -t .
   ```

3. Copy the Lambda function code:
   ```
   copy ..\lambda_handler.py .
   ```

4. Create the deployment ZIP:
   ```
   powershell Compress-Archive -Path * -DestinationPath lambda_function.zip
   ```

5. Deploy to AWS Lambda:
   ```
   aws lambda create-function --function-name ImageThumbnailGenerator \
     --runtime python3.12 \
     --role arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-s3-role \
     --handler lambda_handler.lambda_handler \
     --environment Variables={TARGET_BUCKET=your-target-bucket,SNS_TOPIC_ARN=arn:aws:sns:region:account:topic} \
     --zip-file fileb://lambda_function.zip
   ```

## S3 Trigger Setup
Configure S3 event notification to trigger the Lambda on object creation for .jpg, .jpeg, .png files.

## IAM Permissions
Ensure the Lambda execution role has:
- s3:GetObject on source bucket
- s3:PutObject on target bucket
- sns:Publish on the SNS topic

## Environment Variables
- TARGET_BUCKET: Name of the S3 bucket for thumbnails
- SNS_TOPIC_ARN: ARN of the SNS topic for notifications