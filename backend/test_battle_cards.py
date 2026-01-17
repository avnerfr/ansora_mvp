"""
Test script for battle cards and dynamic asset types functionality.

This script tests:
1. Asset type loading from DynamoDB
2. Competitors loading from S3
3. Battle cards template existence

Run: python test_battle_cards.py
"""

import os
import sys
import boto3
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Key

# Load environment variables
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag.dynamodb_prompts import get_latest_prompt_template
from rag.s3_utils import get_company_data_manager

# DynamoDB setup
AWS_REGION = os.getenv('AWS_REGION', os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
PROMPTS_TABLE_NAME = 'prompts_templates_tbl'
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)

def load_asset_types_from_dynamodb():
    """
    Directly load asset types from DynamoDB without importing pipeline.
    This avoids the heavy dependencies in pipeline.py
    """
    try:
        table = dynamodb.Table(PROMPTS_TABLE_NAME)
        response = table.scan(
            FilterExpression='begins_with(template_name, :prefix)',
            ExpressionAttributeValues={':prefix': 'asset_template_'}
        )
        
        asset_rules = {}
        for item in response.get('Items', []):
            template_name = item['template_name']
            asset_type_key = template_name.replace('asset_template_', '').replace('_', '-')
            asset_rules[asset_type_key] = item['template_body']
        
        return asset_rules
    except Exception as e:
        print(f"Error loading asset types: {e}")
        return {}

def test_asset_types():
    """Test loading asset types from DynamoDB"""
    print("\n" + "="*80)
    print("TEST 1: Asset Types Loading")
    print("="*80)
    
    try:
        asset_rules = load_asset_types_from_dynamodb()
        
        if not asset_rules:
            print("❌ No asset types found in DynamoDB")
            return False
        
        print(f"✅ Loaded {len(asset_rules)} asset types from DynamoDB:")
        for asset_type in sorted(asset_rules.keys()):
            print(f"   - {asset_type}")
        
        # Check for battle-cards specifically
        if 'battle-cards' in asset_rules:
            print("\n✅ Battle-cards asset type found")
        else:
            print("\n⚠️  Battle-cards asset type NOT found")
            print("   Add 'asset_template_battle-cards' to DynamoDB")
        
        return True
    except Exception as e:
        print(f"❌ Error loading asset types: {e}")
        return False

def test_battle_cards_template():
    """Test that battle cards RAG build template exists"""
    print("\n" + "="*80)
    print("TEST 2: Battle Cards RAG Build Template")
    print("="*80)
    
    try:
        template_data = get_latest_prompt_template('battle_cards_rag_build_template')
        
        if not template_data:
            print("❌ battle_cards_rag_build_template NOT found in DynamoDB")
            print("   This template is required for battle cards to work")
            return False
        
        print("✅ battle_cards_rag_build_template found")
        print(f"   Edited by: {template_data.get('edited_by_sub', 'unknown')}")
        print(f"   Last edited: {template_data.get('edited_at_iso', 'unknown')}")
        
        template_body = template_data.get('template_body', '')
        print(f"\n   Template preview (first 200 chars):")
        print(f"   {template_body[:200]}...")
        
        # Check for expected placeholders
        placeholders = ['{competitor}', '{company_name}', '{icp}']
        missing = [p for p in placeholders if p not in template_body]
        
        if missing:
            print(f"\n⚠️  Missing placeholders: {missing}")
        else:
            print(f"\n✅ All expected placeholders present")
        
        return True
    except Exception as e:
        print(f"❌ Error loading battle cards template: {e}")
        return False

def test_competitors_loading(company_name='Algosec'):
    """Test loading competitors from S3"""
    print("\n" + "="*80)
    print(f"TEST 3: Competitors Loading for {company_name}")
    print("="*80)
    
    try:
        company_data_manager = get_company_data_manager()
        company_details = company_data_manager.get_company_data(company_name)
        
        if not company_details:
            print(f"❌ No company details found for {company_name}")
            return False
        
        competitors = company_details.company_context.known_competitors
        
        if not competitors:
            print(f"⚠️  No competitors found for {company_name}")
            print("   Company file exists but known_competitors is empty")
            return False
        
        print(f"✅ Found {len(competitors)} competitors for {company_name}:")
        for competitor in competitors:
            print(f"   - {competitor}")
        
        return True
    except Exception as e:
        print(f"❌ Error loading competitors: {e}")
        return False

def test_system_prompts():
    """Test that main system prompts are still working"""
    print("\n" + "="*80)
    print("TEST 4: System Prompts (Regression Test)")
    print("="*80)
    
    try:
        # Test main system prompts
        templates = [
            'asset_creation_template',
            'asset_creation_rag_build_template'
        ]
        
        results = {}
        for template_name in templates:
            template_data = get_latest_prompt_template(template_name)
            results[template_name] = template_data is not None
            
            if template_data:
                print(f"✅ {template_name} found")
            else:
                print(f"❌ {template_name} NOT found")
        
        return all(results.values())
    except Exception as e:
        print(f"❌ Error checking system prompts: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("BATTLE CARDS and DYNAMIC ASSET TYPES - TEST SUITE")
    print("="*80)
    
    results = {
        'Asset Types': test_asset_types(),
        'Battle Cards Template': test_battle_cards_template(),
        'Competitors Loading': test_competitors_loading(),
        'System Prompts': test_system_prompts(),
    }
    
    print("\n" + "="*80)
    print("TEST RESULTS SUMMARY")
    print("="*80)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10} - {test_name}")
    
    all_passed = all(results.values())
    
    print("\n" + "="*80)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
        print("\nReview the output above for details.")
        print("See BATTLE_CARDS_QUICK_START.md for setup instructions.")
    print("="*80 + "\n")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

