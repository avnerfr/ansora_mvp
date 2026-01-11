#!/usr/bin/env python3
"""
Setup script for RAG reranking template.
Adds the results_rerank_and_filter_template to DynamoDB.
"""

import sys
import os
from datetime import datetime
from dotenv import load_dotenv

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mvp_marketing_app', 'backend'))

load_dotenv()

def setup_reranking_template():
    """Create the reranking template in DynamoDB."""
    import boto3
    from decimal import Decimal
    
    AWS_REGION = os.getenv('AWS_REGION', os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
    PROMPTS_TABLE_NAME = "prompts_templates_tbl"
    
    print("=" * 80)
    print("RAG RERANKING TEMPLATE SETUP")
    print("=" * 80)
    
    # Initialize DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    table = dynamodb.Table(PROMPTS_TABLE_NAME)
    
    # Template content
    template_body = """You are an intelligent document filter for a marketing content generation system.

Your task is to analyze RAG (Retrieval Augmented Generation) results and filter them to keep ONLY the most relevant documents for the current task.

## Context

**Company Name:**
{company_name}

**Company Domain:**
{company_domain}

**Known Competitors:**
{knwn_compatitors}

## For Asset Creation Pipeline:
**Queries sent to RAG:**
{retrieval_queries}

## For Battle Cards Pipeline:
**Target Competitor:**
{target_competitor}

**Target Audience/ICP:**
{icp}

## Candidates (Documents to Filter)

{candidates}

## Instructions

1. Analyze each document in the candidates list
2. Determine which documents are HIGHLY RELEVANT to:
   - The company's domain and market
   - The queries that were sent to RAG
   - Competitive intelligence if analyzing competitors
   - Genuine buyer language and pain points

3. Filter OUT documents that are:
   - Off-topic or tangentially related
   - About different industries/domains (unless relevant)
   - Duplicate or redundant information
   - Low quality or too vague
   - Not aligned with the retrieval queries
   - Generic content without specific insights

4. Keep documents that:
   - Directly address the topics in the retrieval queries
   - Contain buyer language and genuine pain points
   - Provide specific examples or use cases
   - Include competitive insights if relevant
   - Support the company's positioning
   - Have high information density

## Output Format

Return ONLY a JSON array of document IDs to KEEP.

Example:
[1, 3, 5, 7, 12, 15]

Rules:
- Include ONLY the IDs of documents you want to KEEP
- Typically keep 30-60% of documents (but use your judgment)
- Aim for 5-15 highly relevant documents
- Return valid JSON array of integers
- Do NOT include explanations, just the array

Begin filtering now."""

    # Create template item
    template_item = {
        'template_name': 'results_rerank_and_filter_template',
        'edited_at_iso': Decimal(str(int(datetime.now().timestamp()))),
        'edited_by_sub': 'system-setup-script',
        'edit_comment': 'Initial setup of RAG reranking template',
        'template_body': template_body
    }
    
    print("\n✓ Creating template: results_rerank_and_filter_template")
    print(f"✓ Template length: {len(template_body)} chars")
    print(f"✓ Timestamp: {template_item['edited_at_iso']}")
    
    try:
        table.put_item(Item=template_item)
        print("\n✅ SUCCESS! Template created in DynamoDB")
        
        # Also create battle cards specific template
        battle_cards_template_item = {
            'template_name': 'results_rerank_and_filter_battle_cards_template',
            'edited_at_iso': Decimal(str(int(datetime.now().timestamp()))),
            'edited_by_sub': 'system-setup-script',
            'edit_comment': 'Initial setup of battle cards reranking template (same as generic for now)',
            'template_body': template_body
        }
        table.put_item(Item=battle_cards_template_item)
        print("\n✅ SUCCESS! Battle cards template also created in DynamoDB")
        
        print("\nYou can now:")
        print("  1. Use the maintenance UI 'Prompts' tab to view/edit both templates:")
        print("     - results_rerank_and_filter_template (for asset creation)")
        print("     - results_rerank_and_filter_battle_cards_template (for battle cards)")
        print("  2. Test asset creation - it will use results_rerank_and_filter_template")
        print("  3. Test battle cards - it will use results_rerank_and_filter_battle_cards_template")
        print("\nMonitor logs for: 'Step 2.5. Reranking and filtering' messages")
        
    except Exception as e:
        print(f"\n❌ ERROR: Failed to create template: {e}")
        print("\nTroubleshooting:")
        print("  - Verify AWS credentials are configured")
        print("  - Check AWS_REGION environment variable")
        print("  - Verify DynamoDB table 'prompts_templates_tbl' exists")
        return False
    
    return True

if __name__ == "__main__":
    success = setup_reranking_template()
    sys.exit(0 if success else 1)

