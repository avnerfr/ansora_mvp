# DynamoDB Prompt Templates Integration

## Overview

The RAG pipeline now dynamically loads prompt templates from DynamoDB, allowing for runtime updates without code deployments. This enables prompt engineers to update and version prompts independently from the application code.

## DynamoDB Table Structure

**Table Name:** `prompts_templates_tbl`

**Schema:**
- `template_name` (String, Primary Key): The template identifier
- `edited_at_iso` (Number, Sort Key): Unix timestamp for versioning
- `edited_by_sub` (String): User ID who last edited the template
- `template_body` (String): The actual prompt text

## Template Names

The system uses two prompt templates:

### 1. `asset_creation_rag_build_template`
- **Maps to:** `VECTOR_DB_RETREIVAL_PROMPT` in code
- **Purpose:** Used to build the retrieval query for vector database search
- **Used in:** Step 1 of RAG pipeline (query optimization)

### 2. `asset_creation_template`
- **Maps to:** `SYSTEM_PROMPT` in code  
- **Purpose:** System-level instructions for the LLM
- **Used in:** Throughout the pipeline for context and instructions

## How It Works

### 1. Automatic Loading on Startup

When the application starts, `prompts.py` automatically:
1. Queries DynamoDB for the latest version of each template
2. Loads the templates into memory
3. Falls back to hardcoded defaults if DynamoDB is unavailable
4. Logs which version is being used

```python
from rag.prompts import SYSTEM_PROMPT, VECTOR_DB_RETREIVAL_PROMPT
# These are automatically populated from DynamoDB on import
```

### 2. Version Selection

The system always retrieves the **latest** template based on `edited_at_iso`:
```python
latest_item = max(items, key=lambda x: x.get('edited_at_iso', 0))
```

### 3. Logging and Traceability

Every RAG pipeline execution logs:
- Which template version is being used
- Who edited it (`edited_by_sub`)
- When it was edited (`edited_at_iso`)

Example log output:
```
INFO - Prompt Templates:
INFO -   - Retrieval Prompt: edited by user123 at 1704672000
INFO -   - System Prompt: edited by user456 at 1704675600
```

## Fallback Mechanism

If DynamoDB is unavailable or returns no results:
1. The system automatically uses hardcoded fallback prompts
2. Logs a warning indicating fallback is being used
3. Continues normal operation

This ensures **zero downtime** even if DynamoDB is unavailable.

## API Reference

### Core Functions

#### `get_latest_prompt_template(template_name: str)`
Retrieves the latest version of a named template with full metadata.

**Returns:**
```python
{
    'template_body': str,      # The prompt text
    'edited_at_iso': int,      # Unix timestamp
    'edited_by_sub': str       # Editor user ID
}
```

#### `get_asset_creation_rag_build_template()`
Convenience function to get the retrieval prompt template body.

#### `get_asset_creation_template()`
Convenience function to get the system prompt template body.

#### `get_prompt_metadata_for_logging()`
Get metadata about currently loaded prompts for logging/audit purposes.

**Returns:**
```python
{
    'retrieval_prompt_edited_by': str,
    'retrieval_prompt_edited_at': int,
    'system_prompt_edited_by': str,
    'system_prompt_edited_at': int
}
```

## Testing

A test script is provided to verify the integration:

```bash
cd mvp_marketing_app/backend
python test_dynamodb_prompts.py
```

This will:
1. Test retrieval of both templates
2. Display template metadata
3. Verify the prompts module loads correctly
4. Check if DynamoDB values or fallbacks are being used

## Updating Prompts

### Via AWS Console

1. Go to DynamoDB → Tables → `prompts_templates_tbl`
2. Create a new item:
   ```json
   {
     "template_name": "asset_creation_rag_build_template",
     "edited_at_iso": 1704672000,  // Current Unix timestamp
     "edited_by_sub": "your-user-id",
     "template_body": "Your new prompt text..."
   }
   ```
3. The system will automatically pick up the newest version on next pipeline run

### Via AWS CLI

```bash
aws dynamodb put-item \
  --table-name prompts_templates_tbl \
  --item '{
    "template_name": {"S": "asset_creation_rag_build_template"},
    "edited_at_iso": {"N": "1704672000"},
    "edited_by_sub": {"S": "user123"},
    "template_body": {"S": "Your prompt text here..."}
  }'
```

### Via Boto3

```python
import boto3
import time

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('prompts_templates_tbl')

table.put_item(Item={
    'template_name': 'asset_creation_rag_build_template',
    'edited_at_iso': int(time.time()),
    'edited_by_sub': 'user123',
    'template_body': 'Your prompt text here...'
})
```

## Cache Management

The system includes optional caching for performance:

```python
from rag.dynamodb_prompts import clear_template_cache

# Clear cache to force reload on next access
clear_template_cache()
```

Default cache duration: 5 minutes

## Permissions Required

The application's IAM role needs:
```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:Query",
    "dynamodb:GetItem",
    "dynamodb:Scan"
  ],
  "Resource": "arn:aws:dynamodb:*:*:table/prompts_templates_tbl"
}
```

## Troubleshooting

### Template Not Loading

**Symptom:** Logs show "Using fallback SYSTEM_PROMPT"

**Possible causes:**
1. DynamoDB table doesn't exist
2. No items with that `template_name`
3. IAM permissions missing
4. AWS credentials not configured

**Solution:**
1. Check table exists: `aws dynamodb describe-table --table-name prompts_templates_tbl`
2. Verify items exist: `aws dynamodb scan --table-name prompts_templates_tbl`
3. Check IAM role permissions
4. Verify AWS credentials: `aws sts get-caller-identity`

### Wrong Version Loading

**Symptom:** Old prompt version is being used

**Possible causes:**
1. Cache not cleared
2. New item has older `edited_at_iso` timestamp

**Solution:**
1. Clear cache: `clear_template_cache()`
2. Verify timestamps: Ensure new item has largest `edited_at_iso`

## Migration from Hardcoded Prompts

The existing hardcoded prompts in `prompts.py` now serve as **fallbacks only**. To migrate:

1. Copy existing prompts to DynamoDB:
   ```python
   from rag.prompts import _DEFAULT_SYSTEM_PROMPT, _DEFAULT_VECTOR_DB_RETREIVAL_PROMPT
   import boto3
   import time
   
   dynamodb = boto3.resource('dynamodb')
   table = dynamodb.Table('prompts_templates_tbl')
   
   # Migrate system prompt
   table.put_item(Item={
       'template_name': 'asset_creation_template',
       'edited_at_iso': int(time.time()),
       'edited_by_sub': 'migration-script',
       'template_body': _DEFAULT_SYSTEM_PROMPT
   })
   
   # Migrate retrieval prompt
   table.put_item(Item={
       'template_name': 'asset_creation_rag_build_template',
       'edited_at_iso': int(time.time()),
       'edited_by_sub': 'migration-script',
       'template_body': _DEFAULT_VECTOR_DB_RETREIVAL_PROMPT
   })
   ```

2. Verify prompts loaded from DynamoDB
3. Keep fallbacks in code for disaster recovery

## Best Practices

1. **Version Control:** Include `edited_by_sub` for audit trail
2. **Testing:** Test new prompts in dev environment first
3. **Timestamps:** Use millisecond precision for `edited_at_iso` if making rapid updates
4. **Backup:** Keep copies of working prompts before updates
5. **Monitoring:** Watch logs for "Using fallback" warnings
6. **Documentation:** Document significant prompt changes

## Example: Updating a Prompt

```python
import boto3
import time

# Connect to DynamoDB
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('prompts_templates_tbl')

# Updated prompt
new_prompt = """
You are an AI assistant specialized in cybersecurity.
[... your new prompt text ...]
"""

# Save new version
table.put_item(Item={
    'template_name': 'asset_creation_rag_build_template',
    'edited_at_iso': int(time.time() * 1000),  # millisecond precision
    'edited_by_sub': 'john.doe@company.com',
    'template_body': new_prompt
})

print("✓ New prompt version saved!")
```

The system will automatically use this new version on the next pipeline execution.

