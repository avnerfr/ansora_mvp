# RAG Pipeline Prompts and Templates
# This file loads prompts from DynamoDB - no default prompts are provided.
# If prompts are not found in DynamoDB, errors will be raised.

import logging
from .dynamodb_prompts import get_asset_creation_rag_build_template, get_asset_creation_template

logger = logging.getLogger(__name__)


# Load prompts from DynamoDB - required, no fallbacks
def _load_prompts():
    """Load prompts from DynamoDB. Raises errors if prompts are not found."""
    global SYSTEM_PROMPT, VECTOR_DB_RETREIVAL_PROMPT
    
    # Load asset_creation_template -> SYSTEM_PROMPT
    try:
        system_prompt_body = get_asset_creation_template()
        if not system_prompt_body:
            error_msg = "Required prompt 'asset_creation_template' not found in DynamoDB"
            logger.error(f"✗ {error_msg}")
            raise ValueError(error_msg)
        SYSTEM_PROMPT = system_prompt_body
        logger.info("✓ Loaded SYSTEM_PROMPT from DynamoDB (asset_creation_template)")
    except Exception as e:
        error_msg = f"Failed to load SYSTEM_PROMPT from DynamoDB: {str(e)}"
        logger.error(f"✗ {error_msg}")
        raise ValueError(error_msg)
    
    # Load asset_creation_rag_build_template -> VECTOR_DB_RETREIVAL_PROMPT
    try:
        retrieval_prompt_body = get_asset_creation_rag_build_template()
        if not retrieval_prompt_body:
            error_msg = "Required prompt 'asset_creation_rag_build_template' not found in DynamoDB"
            logger.error(f"✗ {error_msg}")
            raise ValueError(error_msg)
        VECTOR_DB_RETREIVAL_PROMPT = retrieval_prompt_body
        logger.info("✓ Loaded VECTOR_DB_RETREIVAL_PROMPT from DynamoDB (asset_creation_rag_build_template)")
    except Exception as e:
        error_msg = f"Failed to load VECTOR_DB_RETREIVAL_PROMPT from DynamoDB: {str(e)}"
        logger.error(f"✗ {error_msg}")
        raise ValueError(error_msg)


# Initialize prompts on module import
# This will set prompts to None if loading fails, and errors will be raised when prompts are used
try:
    _load_prompts()
except ValueError as e:
    logger.error(f"Failed to load required prompts: {e}")
    # Set to None - errors will be raised when prompts are actually used
    SYSTEM_PROMPT = None
    VECTOR_DB_RETREIVAL_PROMPT = None

