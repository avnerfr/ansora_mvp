"""
Setup script for battle cards templates in DynamoDB.

This script creates:
1. battle_cards_rag_build_template
2. asset_template_battle-cards

Run: python setup_battle_cards_templates.py
"""

import boto3
import os
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# DynamoDB configuration
AWS_REGION = os.getenv('AWS_REGION', os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
PROMPTS_TABLE_NAME = 'prompts_templates_tbl'

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table(PROMPTS_TABLE_NAME)

def create_battle_cards_rag_template():
    """Create the battle_cards_rag_build_template"""
    print("\n" + "="*80)
    print("Creating: battle_cards_rag_build_template")
    print("="*80)
    
    template_body = """You are a competitive intelligence analyst creating battle card content.

**Company Information:**
- Our Company: {company_name}
- Domain: {company_domain}
- Positioning: {self_described_positioning}

**Competitor:** {competitor}

**Target Audience:** {icp}

**Campaign Context:**
{user_provided_text}

**Task:**
Analyze our company vs the competitor and provide:

1. **Key Differentiators** (3-5 points)
   - Specific features, capabilities, or approaches where we differ
   - Focus on meaningful differences that matter to {icp}

2. **Competitive Advantages** (3-5 points)
   - Clear advantages we have over the competitor
   - Quantifiable benefits when possible
   - Customer value propositions

3. **Common Objections & Responses** (3-5 objections)
   - Typical objections prospects raise about our solution
   - Strong, evidence-based responses
   - Focus on {icp} concerns

4. **Pricing Positioning**
   - How our pricing compares (without specific numbers)
   - Value justification
   - TCO considerations

**Requirements:**
- Be factual and specific
- Focus on customer value
- Use language appropriate for {icp}
- Avoid hyperbole
- Support claims with reasoning

Provide a comprehensive analysis that sales teams can use to effectively position our solution against {competitor}.
"""
    
    try:
        table.put_item(Item={
            'template_name': 'battle_cards_rag_build_template',
            'edited_at_iso': int(time.time()),
            'edited_by_sub': 'system-setup',
            'edit_comment': 'Initial battle cards RAG build template - created by setup script',
            'template_body': template_body
        })
        print("✅ Successfully created battle_cards_rag_build_template")
        return True
    except Exception as e:
        print(f"❌ Error creating template: {e}")
        return False

def create_battle_cards_asset_template():
    """Create the asset_template_battle-cards"""
    print("\n" + "="*80)
    print("Creating: asset_template_battle-cards")
    print("="*80)
    
    template_body = """Format the battle card as a clear, scannable document:

# Battle Card: [Our Company] vs [Competitor]

## Quick Overview
*2-3 sentence executive summary of the competitive landscape*

---

## Key Differentiators

### Feature/Capability 1
**Us:** [Our approach]
**Them:** [Their approach]
**Why it matters:** [Customer value]

### Feature/Capability 2
**Us:** [Our approach]
**Them:** [Their approach]
**Why it matters:** [Customer value]

*(Continue for 3-5 differentiators)*

---

## Our Competitive Advantages

1. **[Advantage Title]**
   - Specific capability or benefit
   - Customer impact
   - Supporting evidence/metrics if available

2. **[Advantage Title]**
   - Specific capability or benefit
   - Customer impact
   - Supporting evidence/metrics if available

*(Continue for 3-5 advantages)*

---

## Common Objections & How to Respond

### Objection 1: "[Common prospect concern]"
**Response:** [Clear, confident response with reasoning]
**Supporting Points:**
- Point 1
- Point 2

### Objection 2: "[Common prospect concern]"
**Response:** [Clear, confident response with reasoning]
**Supporting Points:**
- Point 1
- Point 2

*(Continue for 3-5 objections)*

---

## Pricing Positioning

**Overall Positioning:** [How we position our pricing vs competitor]

**Value Justification:**
- TCO consideration 1
- TCO consideration 2
- ROI factor 1
- ROI factor 2

**When to Use:**
- Scenario 1: [When this positioning is most effective]
- Scenario 2: [When this positioning is most effective]

---

## Win Themes

*(3-5 key messages to emphasize in competitive situations)*

1. **[Theme]:** [Explanation]
2. **[Theme]:** [Explanation]
3. **[Theme]:** [Explanation]

---

## Resources & Next Steps

- Link to detailed comparison sheet
- Customer testimonials vs this competitor
- Technical documentation
- Case studies

---

**Last Updated:** [Date]
**Prepared For:** [Target Audience]
"""
    
    try:
        table.put_item(Item={
            'template_name': 'asset_template_battle-cards',
            'edited_at_iso': int(time.time()),
            'edited_by_sub': 'system-setup',
            'edit_comment': 'Initial battle cards asset template - created by setup script',
            'template_body': template_body
        })
        print("✅ Successfully created asset_template_battle-cards")
        return True
    except Exception as e:
        print(f"❌ Error creating template: {e}")
        return False

def verify_templates():
    """Verify that templates were created successfully"""
    print("\n" + "="*80)
    print("Verifying Templates")
    print("="*80)
    
    templates_to_check = [
        'battle_cards_rag_build_template',
        'asset_template_battle-cards'
    ]
    
    all_ok = True
    for template_name in templates_to_check:
        try:
            response = table.get_item(
                Key={
                    'template_name': template_name,
                    'edited_at_iso': 0  # We need to query, not get_item
                }
            )
            # This won't work properly - need to query instead
            # Let's just scan for the template_name
            from boto3.dynamodb.conditions import Key
            response = table.query(
                KeyConditionExpression=Key('template_name').eq(template_name),
                ScanIndexForward=False,
                Limit=1
            )
            
            if response.get('Items'):
                item = response['Items'][0]
                print(f"✅ {template_name}")
                print(f"   Edited by: {item.get('edited_by_sub')}")
                print(f"   Timestamp: {item.get('edited_at_iso')}")
            else:
                print(f"❌ {template_name} - NOT FOUND")
                all_ok = False
        except Exception as e:
            print(f"❌ {template_name} - Error: {e}")
            all_ok = False
    
    return all_ok

def main():
    """Main setup function"""
    print("\n" + "="*80)
    print("BATTLE CARDS TEMPLATES SETUP")
    print("="*80)
    print(f"Region: {AWS_REGION}")
    print(f"Table: {PROMPTS_TABLE_NAME}")
    
    # Create templates
    rag_ok = create_battle_cards_rag_template()
    asset_ok = create_battle_cards_asset_template()
    
    # Verify
    verify_ok = verify_templates()
    
    # Summary
    print("\n" + "="*80)
    print("SETUP SUMMARY")
    print("="*80)
    
    if rag_ok and asset_ok and verify_ok:
        print("✅ All templates created successfully!")
        print("\nNext steps:")
        print("1. Run: python test_battle_cards.py")
        print("2. Test battle cards in the UI")
        print("3. Customize templates via Maintenance → Prompts UI")
        return True
    else:
        print("❌ Some templates failed to create")
        print("\nCheck the errors above and:")
        print("1. Verify AWS credentials")
        print("2. Verify DynamoDB table exists")
        print("3. Verify table name is correct")
        return False

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)

