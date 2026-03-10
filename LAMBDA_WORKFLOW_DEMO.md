# Lambda Creation & Deployment Workflow - Demo

## Prerequisites:
1. AWS Credentials configured in `.env`
2. IAM role ARN with Lambda execution permissions

## Complete Workflow:

### Step 1: Create a new Lambda function
```powershell
# Get your role ARN first (from IAM console)
# Format: arn:aws:iam::ACCOUNT_ID:role/ROLE_NAME

.venv\Scripts\python.exe lambda_assistant.py create demo-lambda-function `
  arn:aws:iam::123456789012:role/lambda-execution-role `
  --runtime python3.11 `
  --memory 256 `
  --timeout 60 `
  --description "Demo Lambda function"
```

**What this does:**
- Creates new Lambda function in AWS
- Sets runtime to Python 3.11
- Allocates 256 MB memory
- Sets 60-second timeout
- Initializes with basic "hello" handler

**Expected output:**
```
Creating Lambda function: demo-lambda-function
  Role: arn:aws:iam::123456789012:role/lambda-execution-role
  Runtime: python3.11
  Handler: index.handler
  Memory: 256 MB
  Timeout: 60s

✓ Function created successfully!
  Function ARN: arn:aws:lambda:ap-south-1:123456789012:function:demo-lambda-function
  Function Name: demo-lambda-function
  Runtime: python3.11
  CodeSha256: abc123def456...
```

---

### Step 2: Deploy your code
```powershell
# Deploy the demo code we created
.venv\Scripts\python.exe lambda_assistant.py deploy demo-lambda-function `
  --source-dir lambda_demo `
  --output dist/demo.zip
```

**What this does:**
- Packages your Python code from `lambda_demo/`
- Creates a zip file
- Uploads to the Lambda function
- Updates the function code

**Expected output:**
```
Copying source files from lambda_demo...
Creating deployment package: dist/demo.zip
Package created: dist/demo.zip (478 bytes)
Deploying to Lambda function: demo-lambda-function
✓ Code updated successfully
  Function ARN: arn:aws:lambda:ap-south-1:123456789012:function:demo-lambda-function
  Runtime: python3.11
  Last Modified: 2026-03-10T14:30:00.000000+00:00
```

---

### Step 3: Test your Lambda
```powershell
# Test with the demo event
.venv\Scripts\python.exe lambda_assistant.py test demo-lambda-function `
  test_events/demo_test_event.json
```

**Expected output:**
```
Invoking Lambda function: demo-lambda-function
Event file: test_events/demo_test_event.json
------------------------------------------------------------

✓ Invocation Status: 200

Response Payload:
------------------------------------------------------------
{
  "statusCode": 200,
  "body": "{\"message\": \"Hello from AWS Lambda Demo!\", ...}"
}

Fetching CloudWatch Logs...
------------------------------------------------------------
[14:30:01] [INFO] Received event: {...}
[14:30:01] [INFO] Returning response: {...}
```

---

### Step 4: Schedule it (Optional)
```powershell
# Make it run every hour
.venv\Scripts\python.exe lambda_assistant.py schedule create `
  demo-hourly `
  demo-lambda-function `
  "rate(1 hour)" `
  --description "Demo Lambda running every hour" `
  --event test_events/demo_test_event.json
```

**What this does:**
- Creates EventBridge rule
- Schedules to run every hour
- Automatically passes the test event as input
- Lambda will execute automatically

---

## Where to see everything in AWS Console:

### 1. Lambda Function
```
AWS Console → Lambda → Functions → demo-lambda-function
```
- View code
- Check logs
- Update settings
- View metrics

### 2. CloudWatch Logs
```
AWS Console → CloudWatch → Log Groups → /aws/lambda/demo-lambda-function
```
- See every execution
- Debug errors
- Check performance

### 3. Scheduled Runs (EventBridge)
```
AWS Console → EventBridge → Rules → demo-hourly
```
- Verify schedule is active
- See execution history
- Modify schedule

---

## Troubleshooting:

**"Function already exists"**
- The function name is taken. Choose a different name.

**"Role not found"**
- Get the correct role ARN from IAM console
- Role must have basic Lambda execution permissions

**"Code deployment failed"**
- Check that handler name matches your code
- Verify syntax of Python files

**"Invocation fails"**
- Check CloudWatch Logs for error details
- Update code and redeploy

---

## What's the difference from manual AWS Console?

### Manual (Old way):
1. Console → Create function → Fill form → Create
2. Console → Zip code locally → Upload via console
3. Console → Test tab → Copy-paste event → Run
4. Console → EventBridge → Create rule → Attach target → Configure

### With our tool (New way):
```bash
create demo-lambda-function ...
deploy demo-lambda-function ...
test demo-lambda-function ...
schedule create demo-hourly demo-lambda-function ...
```

**Advantage:** Automated, repeatable, scriptable, version-controllable!
