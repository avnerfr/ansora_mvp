#!/usr/bin/env python3
"""
Test script to verify battle cards search with minimal filtering.
Compares results between strict filtering and minimal filtering.
"""

import sys
import os
from dotenv import load_dotenv

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

def test_battle_cards_search():
    """Test battle cards search with minimal filtering."""
    print("=" * 80)
    print("BATTLE CARDS SEARCH TEST")
    print("=" * 80)
    
    from rag.vectorstore import vector_store
    
    # Test query about a competitor
    test_query = "Tufin's automation is too rigid and hard to customize"
    collection = "cybersecurity-summaries_1_0"
    k = 5
    
    print(f"\n📝 Test Query: {test_query}")
    print(f"🎯 Collection: {collection}")
    print(f"🔢 K: {k}")
    
    # Test 1: Minimal filter (battle cards approach)
    print("\n" + "=" * 80)
    print("TEST 1: MINIMAL FILTER (Battle Cards)")
    print("=" * 80)
    try:
        results_minimal = vector_store.search_reddit_posts_minimal_filter(
            query=test_query,
            k=k,
            collection_name=collection,
            doc_type='reddit_post'
        )
        print(f"\n✅ Retrieved {len(results_minimal)} documents with MINIMAL filter")
        
        if results_minimal:
            print("\nTop 3 Results:")
            for i, doc in enumerate(results_minimal[:3], 1):
                score = doc.metadata.get('score', 0.0)
                title = doc.metadata.get('title', 'Untitled')[:60]
                print(f"  {i}. {title}... (score: {score:.4f})")
        else:
            print("⚠️  No results with minimal filter")
            
    except Exception as e:
        print(f"❌ Error with minimal filter: {e}")
        import traceback
        traceback.print_exc()
    
    # Test 2: Strict filter (regular approach) - for comparison
    print("\n" + "=" * 80)
    print("TEST 2: STRICT FILTER (Regular RAG)")
    print("=" * 80)
    try:
        # Need company enumerations for strict filter
        company_enumerations = {
            "domain": ["algosec"],
            "operational_surface": [],
            "execution_surface": [],
            "failure_type": []
        }
        
        results_strict = vector_store.search_reddit_posts(
            query=test_query,
            k=k,
            company_enumerations=company_enumerations,
            collection_name=collection,
            company_name="algosec"
        )
        print(f"\n✅ Retrieved {len(results_strict)} documents with STRICT filter")
        
        if results_strict:
            print("\nTop 3 Results:")
            for i, doc in enumerate(results_strict[:3], 1):
                score = doc.metadata.get('score', 0.0)
                title = doc.metadata.get('title', 'Untitled')[:60]
                print(f"  {i}. {title}... (score: {score:.4f})")
        else:
            print("⚠️  No results with strict filter (expected for competitor queries)")
            
    except Exception as e:
        print(f"❌ Error with strict filter: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Minimal Filter: {len(results_minimal) if 'results_minimal' in locals() else 0} docs")
    print(f"Strict Filter:  {len(results_strict) if 'results_strict' in locals() else 0} docs")
    print("\n✅ For battle cards (competitor intel), minimal filter should return MORE results")
    print("✅ For company-specific insights, strict filter is more precise")
    
    # Verify embeddings are working
    print("\n" + "=" * 80)
    print("EMBEDDING VERIFICATION")
    print("=" * 80)
    try:
        from openai import OpenAI
        from core.config import settings
        
        openai_client = OpenAI(
            api_key=settings.DEEPINFRA_API_KEY, 
            base_url=settings.DEEPINFRA_API_BASE_URL
        )
        response = openai_client.embeddings.create(
            input=test_query,
            model=vector_store._model_name
        )
        embedding = response.data[0].embedding
        print(f"✅ Embedding model: {vector_store._model_name}")
        print(f"✅ Embedding dimensions: {len(embedding)}")
        print(f"✅ Sample values: [{embedding[0]:.4f}, {embedding[1]:.4f}, {embedding[2]:.4f}, ...]")
        print("\n✅ Embeddings are working correctly!")
        
    except Exception as e:
        print(f"❌ Error verifying embeddings: {e}")

if __name__ == "__main__":
    test_battle_cards_search()

