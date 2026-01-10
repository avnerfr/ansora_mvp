"""
Example: Update Prompt Template in DynamoDB

This script demonstrates how to update a prompt template in DynamoDB.
Modify this for your specific use case.
"""

import boto3
import time
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize DynamoDB with region
AWS_REGION = os.getenv('AWS_REGION', os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table('prompts_templates_tbl')

# Example 1: Update the retrieval prompt (VECTOR_DB_RETREIVAL_PROMPT)
def update_retrieval_prompt(edited_by: str):
    """Update the retrieval prompt template."""
    
    new_prompt = """
You are a retrieval query condenser for a RAG system.
Your task is to translate the user's inputs into 3-5 concrete, retrieval-optimized sentences.

[YOUR UPDATED PROMPT TEXT HERE]

Instructions:
- Focus on operational scenarios
- Use practitioner language
- Avoid vendor branding

Output:
3 to 5 standalone sentences describing operational angles.

Company domain: {company_domain}
Company value proposition: {company_value_proposition}
Campaign context: {user_provided_text}
Operational pain points: {backgrounds}
"""
    
    timestamp = int(time.time())
    
    item = {
        'template_name': 'asset_creation_rag_build_template',
        'edited_at_iso': timestamp,
        'edited_by_sub': edited_by,
        'template_body': new_prompt.strip()
    }
    
    print(f"Updating retrieval prompt...")
    print(f"  Timestamp: {timestamp} ({datetime.fromtimestamp(timestamp)})")
    print(f"  Editor: {edited_by}")
    print(f"  Length: {len(new_prompt)} chars")
    
    table.put_item(Item=item)
    print("✓ Successfully updated retrieval prompt!")


# Example 2: Update the system prompt (SYSTEM_PROMPT)
def update_system_prompt(edited_by: str):
    """Update the system prompt template."""
    
    new_prompt = """
You are a senior enterprise B2B Product Marketing Writer.

[YOUR UPDATED PROMPT TEXT HERE]

Focus on:
- Operational failure and friction
- Practitioner language
- Decision fatigue

Rules:
- Avoid marketing buzzwords
- Stay in operational reality
- Combine technical specifics
"""
    
    timestamp = int(time.time())
    
    item = {
        'template_name': 'asset_creation_template',
        'edited_at_iso': timestamp,
        'edited_by_sub': edited_by,
        'template_body': new_prompt.strip()
    }
    
    print(f"Updating system prompt...")
    print(f"  Timestamp: {timestamp} ({datetime.fromtimestamp(timestamp)})")
    print(f"  Editor: {edited_by}")
    print(f"  Length: {len(new_prompt)} chars")
    
    table.put_item(Item=item)
    print("✓ Successfully updated system prompt!")


# Example 3: View current version
def view_current_prompt(template_name: str):
    """View the current version of a prompt."""
    
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('template_name').eq(template_name)
    )
    
    items = response.get('Items', [])
    
    if not items:
        print(f"No items found for template: {template_name}")
        return
    
    # Get latest
    latest = max(items, key=lambda x: x.get('edited_at_iso', 0))
    
    timestamp = int(latest.get('edited_at_iso', 0))
    
    print(f"\nCurrent version of '{template_name}':")
    print(f"  Edited by: {latest.get('edited_by_sub')}")
    print(f"  Edited at: {timestamp} ({datetime.fromtimestamp(timestamp)})")
    print(f"  Length: {len(latest.get('template_body', ''))} chars")
    print(f"\nPreview:")
    print("-" * 80)
    print(latest.get('template_body', '')[:300] + "...")
    print("-" * 80)


# Example 4: List all versions (history)
def list_all_versions(template_name: str):
    """List all versions of a prompt template."""
    
    response = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('template_name').eq(template_name)
    )
    
    items = response.get('Items', [])
    
    if not items:
        print(f"No items found for template: {template_name}")
        return
    
    # Sort by timestamp descending
    items_sorted = sorted(items, key=lambda x: x.get('edited_at_iso', 0), reverse=True)
    
    print(f"\nVersion history for '{template_name}':")
    print("-" * 80)
    for i, item in enumerate(items_sorted, 1):
        timestamp = int(item.get('edited_at_iso', 0))
        print(f"{i}. {datetime.fromtimestamp(timestamp)} by {item.get('edited_by_sub')} ({len(item.get('template_body', ''))} chars)")
    print("-" * 80)


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  View current prompts:")
        print("    python update_prompt_example.py view")
        print()
        print("  Update retrieval prompt:")
        print("    python update_prompt_example.py update-retrieval your@email.com")
        print()
        print("  Update system prompt:")
        print("    python update_prompt_example.py update-system your@email.com")
        print()
        print("  List version history:")
        print("    python update_prompt_example.py history asset_creation_rag_build_template")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "view":
        print("\n" + "="*80)
        view_current_prompt('asset_creation_rag_build_template')
        print("\n" + "="*80)
        view_current_prompt('asset_creation_template')
        print("="*80 + "\n")
    
    elif command == "update-retrieval":
        if len(sys.argv) < 3:
            print("Error: Please provide editor ID (email)")
            sys.exit(1)
        editor = sys.argv[2]
        update_retrieval_prompt(editor)
    
    elif command == "update-system":
        if len(sys.argv) < 3:
            print("Error: Please provide editor ID (email)")
            sys.exit(1)
        editor = sys.argv[2]
        update_system_prompt(editor)
    
    elif command == "history":
        if len(sys.argv) < 3:
            print("Error: Please provide template name")
            sys.exit(1)
        template_name = sys.argv[2]
        list_all_versions(template_name)
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

