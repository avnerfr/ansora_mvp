"""
Test script to verify DynamoDB prompt template retrieval.
Run this to test the integration before deploying.
"""

import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path to import rag module
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from rag.dynamodb_prompts import (
    get_latest_prompt_template,
    get_asset_creation_rag_build_template,
    get_asset_creation_template
)

def test_dynamodb_prompts():
    """Test DynamoDB prompt template retrieval."""
    print("\n" + "="*80)
    print("Testing DynamoDB Prompt Template Retrieval")
    print("="*80 + "\n")
    
    # Test 1: Get asset_creation_rag_build_template
    print("Test 1: Retrieving 'asset_creation_rag_build_template'...")
    template1 = get_asset_creation_rag_build_template()
    if template1:
        print(f"✓ Success! Retrieved template ({len(template1)} chars)")
        print(f"Preview: {template1[:200]}...")
    else:
        print("✗ Failed to retrieve template")
    
    print("\n" + "-"*80 + "\n")
    
    # Test 2: Get asset_creation_template
    print("Test 2: Retrieving 'asset_creation_template'...")
    template2 = get_asset_creation_template()
    if template2:
        print(f"✓ Success! Retrieved template ({len(template2)} chars)")
        print(f"Preview: {template2[:200]}...")
    else:
        print("✗ Failed to retrieve template")
    
    print("\n" + "-"*80 + "\n")
    
    # Test 3: Get detailed info
    print("Test 3: Getting detailed template info...")
    detailed = get_latest_prompt_template('asset_creation_rag_build_template')
    if detailed:
        print(f"✓ Success!")
        print(f"  - Edited at (ISO): {detailed.get('edited_at_iso')}")
        print(f"  - Edited by: {detailed.get('edited_by_sub')}")
        print(f"  - Template length: {len(detailed.get('template_body', ''))} chars")
    else:
        print("✗ Failed to retrieve detailed info")
    
    print("\n" + "="*80 + "\n")
    
    # Test 4: Verify prompts module loads correctly
    print("Test 4: Importing prompts module to verify auto-loading...")
    try:
        from rag.prompts import SYSTEM_PROMPT, VECTOR_DB_RETREIVAL_PROMPT
        print(f"✓ SYSTEM_PROMPT loaded ({len(SYSTEM_PROMPT)} chars)")
        print(f"✓ VECTOR_DB_RETREIVAL_PROMPT loaded ({len(VECTOR_DB_RETREIVAL_PROMPT)} chars)")
        
        # Check if they're using DynamoDB values or fallbacks
        print("\nChecking if prompts are from DynamoDB...")
        if template2 and SYSTEM_PROMPT == template2:
            print("✓ SYSTEM_PROMPT is using DynamoDB value")
        else:
            print("⚠ SYSTEM_PROMPT is using fallback (DynamoDB unavailable or returned None)")
        
        if template1 and VECTOR_DB_RETREIVAL_PROMPT == template1:
            print("✓ VECTOR_DB_RETREIVAL_PROMPT is using DynamoDB value")
        else:
            print("⚠ VECTOR_DB_RETREIVAL_PROMPT is using fallback (DynamoDB unavailable or returned None)")
            
    except Exception as e:
        print(f"✗ Error importing prompts: {e}")
    
    print("\n" + "="*80)
    print("Tests completed!")
    print("="*80 + "\n")


if __name__ == "__main__":
    test_dynamodb_prompts()

