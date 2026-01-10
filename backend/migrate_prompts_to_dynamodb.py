"""
Migration Script: Copy Fallback Prompts to DynamoDB

This script copies the hardcoded fallback prompts from prompts.py to DynamoDB.
Run this once to initialize your DynamoDB table with the current prompts.

Usage:
    python migrate_prompts_to_dynamodb.py [--edited-by YOUR_USER_ID]
"""

import sys
import boto3
import time
import argparse
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from rag.prompts import _DEFAULT_SYSTEM_PROMPT, _DEFAULT_VECTOR_DB_RETREIVAL_PROMPT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# DynamoDB setup with region
AWS_REGION = os.getenv('AWS_REGION', os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
TABLE_NAME = 'prompts_templates_tbl'


def check_table_exists():
    """Check if the DynamoDB table exists."""
    try:
        table = dynamodb.Table(TABLE_NAME)
        table.load()
        logger.info(f"✓ Table '{TABLE_NAME}' exists")
        return True
    except Exception as e:
        logger.error(f"✗ Table '{TABLE_NAME}' does not exist or is not accessible: {e}")
        return False


def get_existing_items():
    """Get all existing items from the table."""
    try:
        table = dynamodb.Table(TABLE_NAME)
        response = table.scan()
        items = response.get('Items', [])
        logger.info(f"Found {len(items)} existing items in table")
        return items
    except Exception as e:
        logger.error(f"Error scanning table: {e}")
        return []


def migrate_prompt(template_name: str, template_body: str, edited_by: str, dry_run: bool = False):
    """
    Migrate a single prompt to DynamoDB.
    
    Args:
        template_name: The template name (primary key)
        template_body: The prompt text
        edited_by: User ID for audit trail
        dry_run: If True, only print what would be done
    """
    timestamp = int(time.time())
    
    item = {
        'template_name': template_name,
        'edited_at_iso': timestamp,
        'edited_by_sub': edited_by,
        'template_body': template_body
    }
    
    logger.info(f"\n{'[DRY RUN] ' if dry_run else ''}Migrating template: {template_name}")
    logger.info(f"  - edited_at_iso: {timestamp}")
    logger.info(f"  - edited_by_sub: {edited_by}")
    logger.info(f"  - template_body length: {len(template_body)} chars")
    logger.info(f"  - Preview: {template_body[:100]}...")
    
    if not dry_run:
        try:
            table = dynamodb.Table(TABLE_NAME)
            table.put_item(Item=item)
            logger.info(f"✓ Successfully migrated '{template_name}'")
        except Exception as e:
            logger.error(f"✗ Error migrating '{template_name}': {e}")
            return False
    else:
        logger.info(f"[DRY RUN] Would migrate '{template_name}'")
    
    return True


def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(
        description='Migrate fallback prompts to DynamoDB'
    )
    parser.add_argument(
        '--edited-by',
        default='migration-script',
        help='User ID for audit trail (default: migration-script)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without making changes'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing items without confirmation'
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("DynamoDB Prompt Migration Script")
    print("="*80 + "\n")
    
    # Check table exists
    if not check_table_exists():
        logger.error("Cannot proceed without table. Please create it first.")
        return 1
    
    # Check existing items
    existing_items = get_existing_items()
    existing_names = {item.get('template_name') for item in existing_items}
    
    templates_to_migrate = [
        ('asset_creation_rag_build_template', _DEFAULT_VECTOR_DB_RETREIVAL_PROMPT),
        ('asset_creation_template', _DEFAULT_SYSTEM_PROMPT)
    ]
    
    # Check for conflicts
    conflicts = [name for name, _ in templates_to_migrate if name in existing_names]
    
    if conflicts and not args.force and not args.dry_run:
        logger.warning(f"\n⚠ The following templates already exist in DynamoDB:")
        for name in conflicts:
            logger.warning(f"  - {name}")
        
        response = input("\nOverwrite existing items? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            logger.info("Migration cancelled by user")
            return 0
    
    # Perform migration
    logger.info("\nStarting migration...")
    success_count = 0
    
    for template_name, template_body in templates_to_migrate:
        if migrate_prompt(template_name, template_body, args.edited_by, args.dry_run):
            success_count += 1
    
    # Summary
    print("\n" + "="*80)
    if args.dry_run:
        logger.info(f"[DRY RUN] Would migrate {success_count}/{len(templates_to_migrate)} templates")
        logger.info("Run without --dry-run to perform actual migration")
    else:
        logger.info(f"✓ Successfully migrated {success_count}/{len(templates_to_migrate)} templates")
    print("="*80 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

