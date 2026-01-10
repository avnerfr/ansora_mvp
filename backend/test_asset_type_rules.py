"""
Test script to verify DynamoDB asset type rules loading.
Run this to test the new functionality.
"""

import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from rag.pipeline import _load_asset_type_rules_from_dynamodb, _get_asset_type_rules, asset_type_rules

def test_asset_type_rules():
    """Test asset type rules loading from DynamoDB."""
    print("\n" + "="*80)
    print("Testing Asset Type Rules Loading from DynamoDB")
    print("="*80 + "\n")
    
    # Test 1: Load from DynamoDB directly
    print("Test 1: Loading asset type rules from DynamoDB...")
    dynamodb_rules = _load_asset_type_rules_from_dynamodb()
    print(f"✓ Loaded {len(dynamodb_rules)} rules from DynamoDB:")
    for asset_type in sorted(dynamodb_rules.keys()):
        body_preview = dynamodb_rules[asset_type][:100].replace('\n', ' ')
        print(f"  - {asset_type}: {body_preview}...")
    
    print("\n" + "-"*80 + "\n")
    
    # Test 2: Get merged rules (DynamoDB + defaults)
    print("Test 2: Getting merged rules (DynamoDB + defaults)...")
    merged_rules = _get_asset_type_rules()
    print(f"✓ Total rules available: {len(merged_rules)}")
    print("Asset types:")
    for asset_type in sorted(merged_rules.keys()):
        source = "DynamoDB" if asset_type in dynamodb_rules else "Default"
        print(f"  - {asset_type} (from {source})")
    
    print("\n" + "-"*80 + "\n")
    
    # Test 3: Check module-level variable
    print("Test 3: Checking module-level asset_type_rules...")
    print(f"✓ Module has {len(asset_type_rules)} rules loaded")
    
    print("\n" + "-"*80 + "\n")
    
    # Test 4: Show examples of rules from DynamoDB
    print("Test 4: Sample rules from DynamoDB...")
    for asset_type in list(dynamodb_rules.keys())[:3]:  # Show first 3
        rule_body = dynamodb_rules[asset_type]
        print(f"\nAsset Type: {asset_type}")
        print(f"Length: {len(rule_body)} chars")
        print(f"Preview:\n{rule_body[:200]}...")
    
    print("\n" + "="*80)
    print("Tests completed!")
    print("="*80 + "\n")
    
    # Summary
    print("Summary:")
    print(f"  - DynamoDB rules: {len(dynamodb_rules)}")
    print(f"  - Default rules: {len([k for k in merged_rules if k not in dynamodb_rules])}")
    print(f"  - Total available: {len(merged_rules)}")
    print()
    print("Asset type naming convention:")
    print("  - DynamoDB template: 'asset_template_one-pager'")
    print("  - Becomes asset type: 'one-pager'")
    print("  - Multi-word types use hyphens: 'blog-post', 'landing-page', etc.")


if __name__ == "__main__":
    test_asset_type_rules()

