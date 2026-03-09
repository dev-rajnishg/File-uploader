import boto3
import json
import logging
import os
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "ap-south-1")
)
sns_client = boto3.client(
    'sns',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "ap-south-1")
)

def lambda_handler(event, context):
    try:
        # Parse S3 event
        record = event['Records'][0]
        source_bucket = record['s3']['bucket']['name']
        source_key = record['s3']['object']['key']

        logger.info(f"Processing file: s3://{source_bucket}/{source_key}")

        # Check if file is JPEG or PNG
        if not (source_key.lower().endswith(('.jpg', '.jpeg', '.png'))):
            logger.warning(f"Unsupported file type: {source_key}")
            return {'statusCode': 400, 'body': 'Unsupported file type'}

        # Get target bucket and SNS topic from environment variables
        target_bucket = os.environ['TARGET_BUCKET']
        sns_topic_arn = os.environ['SNS_TOPIC_ARN']

        # Download the image from S3
        response = s3_client.get_object(Bucket=source_bucket, Key=source_key)
        image_data = response['Body'].read()

        # Check image size
        image_size = len(image_data)
        if image_size > 1 * 1024 * 1024:  # Greater than 1 MB
            # Process the image using BytesIO
            with BytesIO(image_data) as input_buffer:
                with Image.open(input_buffer) as image:
                    # Create thumbnail (larger size)
                    image.thumbnail((512, 512))

                    # Save as JPEG with quality 50
                    output_buffer = BytesIO()
                    image.convert('RGB').save(output_buffer, format='JPEG', quality=50)
                    output_data = output_buffer.getvalue()

            # Verify the processed image is not corrupt
            try:
                with BytesIO(output_data) as verify_buffer:
                    Image.open(verify_buffer).verify()
            except Exception as e:
                logger.error(f"Processed image is corrupt: {e}")
                raise e

            # Ensure target key ends with .jpg
            target_key = f"thumbs/{source_key}"
            if not target_key.lower().endswith('.jpg'):
                target_key = target_key.rsplit('.', 1)[0] + '.jpg'

            # Upload processed thumbnail
            s3_client.put_object(
                Bucket=target_bucket,
                Key=target_key,
                Body=output_data,
                ContentType='image/jpeg'
            )

            logger.info(f"Thumbnail uploaded to: s3://{target_bucket}/{target_key}")

            # Delete the original large file
            s3_client.delete_object(Bucket=source_bucket, Key=source_key)
            logger.info(f"Original file deleted: s3://{source_bucket}/{source_key}")

        else:
            # Image is <= 1 MB, upload as is to target
            target_key = f"thumbs/{source_key}"
            s3_client.put_object(
                Bucket=target_bucket,
                Key=target_key,
                Body=image_data,
                ContentType=response['ContentType']
            )
            logger.info(f"Small file copied to: s3://{target_bucket}/{target_key}")

        # Send SNS notification
        action = "processed and original deleted" if image_size > 1 * 1024 * 1024 else "copied as is"
        message = {
            'source_bucket': source_bucket,
            'source_key': source_key,
            'target_bucket': target_bucket,
            'target_key': target_key,
            'action': action,
            'message': f'Image {action} successfully'
        }

        sns_client.publish(
            TopicArn=sns_topic_arn,
            Message=json.dumps(message),
            Subject='Thumbnail Creation Notification'
        )

        logger.info("SNS notification sent")

        return {'statusCode': 200, 'body': 'Thumbnail created!'}

    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")
        # In production, you might want to send error notifications or handle retries
        raise e