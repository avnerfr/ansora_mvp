"""
DynamoDB Prompt Templates Manager

This module handles retrieval and management of prompt templates from DynamoDB.
Table: prompts_templates_tbl

Items structure:
- template_name (String): Primary key
- edited_at_iso (Number): Timestamp for version tracking
- edited_by_sub: User ID who edited
- template_body: The actual prompt text
"""

import boto3
from typing import Optional, Dict, Any
import logging
from decimal import Decimal
import os

logger = logging.getLogger(__name__)

# Get AWS region from environment or use default
AWS_REGION = os.getenv('AWS_REGION', os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))

# Initialize DynamoDB resource with region
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
prompts_table = dynamodb.Table('prompts_templates_tbl')


def _convert_decimal(obj):
    """Convert DynamoDB Decimal types to Python native types."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


def get_latest_prompt_template(template_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the latest version of a prompt template from DynamoDB.
    
    Args:
        template_name: The name of the template to retrieve
                      (e.g., 'asset_creation_rag_build_template' or 'asset_creation_template')
    
    Returns:
        Dict containing template_body, edited_at_iso, and edited_by_sub, or None if not found
    """
    try:
        logger.info(f"Retrieving prompt template: {template_name}")
        
        # Query all items with this template_name
        response = prompts_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('template_name').eq(template_name)
        )
        
        items = response.get('Items', [])
        
        if not items:
            logger.warning(f"No template found with name: {template_name}")
            return None
        
        # Sort by edited_at_iso to get the latest
        latest_item = max(items, key=lambda x: _convert_decimal(x.get('edited_at_iso', 0)))
        
        result = {
            'template_body': latest_item.get('template_body', ''),
            'edited_at_iso': _convert_decimal(latest_item.get('edited_at_iso')),
            'edited_by_sub': latest_item.get('edited_by_sub', 'unknown')
        }
        
        logger.info(
            f"✓ Retrieved template '{template_name}' "
            f"(edited_at: {result['edited_at_iso']}, edited_by: {result['edited_by_sub']})"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error retrieving prompt template '{template_name}': {e}", exc_info=True)
        return None


def get_asset_creation_rag_build_template() -> Optional[str]:
    """
    Get the VECTOR_DB_RETREIVAL_PROMPT template.
    
    Returns:
        The template body string, or None if not found
    """
    template = get_latest_prompt_template('asset_creation_rag_build_template')
    if template:
        logger.info(
            f"Using asset_creation_rag_build_template from DynamoDB "
            f"(edited by: {template['edited_by_sub']})"
        )
        return template['template_body']
    return None


def get_asset_creation_template() -> Optional[str]:
    """
    Get the SYSTEM_PROMPT template.
    
    Returns:
        The template body string, or None if not found
    """
    logger.info(f"++++++++++++++++++++Getting asset_creation_template from DynamoDB")
    template = get_latest_prompt_template('asset_creation_template')
    if template:
        logger.info(
            f"Using asset_creation_template from DynamoDB "
            f"(edited by: {template['edited_by_sub']} on {template['edited_at_iso']})"
            f"(template: {template['template_body'][0:100]}...)"
        )
        return template['template_body']
    return None


# Cache for loaded templates (optional, for performance)
_template_cache: Dict[str, Dict[str, Any]] = {}


def get_cached_template(template_name: str, cache_duration_seconds: int = 300) -> Optional[Dict[str, Any]]:
    """
    Get a template with caching support (5 minutes by default).
    
    Args:
        template_name: The name of the template
        cache_duration_seconds: How long to cache the template
    
    Returns:
        Template dict or None
    """
    import time
    
    cache_key = template_name
    cached_entry = _template_cache.get(cache_key)
    
    if cached_entry:
        cache_time = cached_entry.get('_cached_at', 0)
        if time.time() - cache_time < cache_duration_seconds:
            logger.debug(f"Using cached template: {template_name}")
            return cached_entry
    
    # Not cached or expired, fetch fresh
    template = get_latest_prompt_template(template_name)
    if template:
        template['_cached_at'] = time.time()
        _template_cache[cache_key] = template
    
    return template


def clear_template_cache():
    """Clear the template cache (useful for testing or after updates)."""
    global _template_cache
    _template_cache = {}
    logger.info("Template cache cleared")


def get_prompt_metadata_for_logging() -> Dict[str, str]:
    """
    Get metadata about currently loaded prompts for logging purposes.
    
    Returns:
        Dict with metadata about template versions and editors
    """
    metadata = {}
    
    try:
        # Get metadata for both templates
        rag_build = get_latest_prompt_template('asset_creation_rag_build_template')
        if rag_build:
            metadata['retrieval_prompt_edited_by'] = rag_build.get('edited_by_sub', 'unknown')
            metadata['retrieval_prompt_edited_at'] = rag_build.get('edited_at_iso', 'unknown')
        else:
            metadata['retrieval_prompt_edited_by'] = 'FALLBACK'
            metadata['retrieval_prompt_edited_at'] = 'N/A'
        
        asset_creation = get_latest_prompt_template('asset_creation_template')
        if asset_creation:
            metadata['system_prompt_edited_by'] = asset_creation.get('edited_by_sub', 'unknown')
            metadata['system_prompt_edited_at'] = asset_creation.get('edited_at_iso', 'unknown')
        else:
            metadata['system_prompt_edited_by'] = 'FALLBACK'
            metadata['system_prompt_edited_at'] = 'N/A'
            
    except Exception as e:
        logger.error(f"Error getting prompt metadata: {e}")
        metadata = {
            'retrieval_prompt_edited_by': 'ERROR',
            'retrieval_prompt_edited_at': 'ERROR',
            'system_prompt_edited_by': 'ERROR',
            'system_prompt_edited_at': 'ERROR'
        }
    
    return metadata

