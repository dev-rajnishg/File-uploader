import json
import logging
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Simple demo Lambda function that echoes back the event and adds a timestamp.
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    response = {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Hello from AWS Lambda Demo!',
            'timestamp': datetime.utcnow().isoformat(),
            'event_received': event,
            'function_name': context.function_name if context else 'local',
        })
    }
    
    logger.info(f"Returning response: {response}")
    return response
