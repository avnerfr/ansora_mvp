"""
Test script to verify cloud Qdrant connection and Reddit posts search.
Run this to diagnose issues with remote Qdrant database.
"""
from qdrant_client import QdrantClient
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Qdrant
import os
from dotenv import load_dotenv

print("=" * 60)
print("Testing Cloud Qdrant Connection")
print("=" * 60)

# Initialize clients - load from root .env file
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("❌ OPENAI_API_KEY not set!")
    print("Set it with: export OPENAI_API_KEY='your-key'")
    exit(1)

print(f"\n✓ OpenAI API Key: {'*' * 20}{OPENAI_API_KEY[-10:]}")

# Step 1: Test connection
print("\n1. Testing Qdrant connection...")
try:
    client = QdrantClient(url=CLOUD_URL, api_key=CLOUD_API_KEY)
    print("✓ Connected to cloud Qdrant")
except Exception as e:
    print(f"❌ Connection failed: {e}")
    exit(1)

# Step 2: List collections
print("\n2. Listing collections...")
try:
    collections = client.get_collections()
    print(f"✓ Found {len(collections.collections)} collections:")
    for col in collections.collections:
        info = client.get_collection(col.name)
        print(f"   - {col.name}: {info.points_count} points, {info.config.params.vectors.size}D vectors")
except Exception as e:
    print(f"❌ Failed to list collections: {e}")
    exit(1)

# Step 3: Check reddit_posts collection
print("\n3. Checking reddit_posts collection...")
collection_names = [c.name for c in collections.collections]
if "reddit_posts" not in collection_names:
    print("❌ reddit_posts collection NOT FOUND!")
    print(f"Available collections: {collection_names}")
    exit(1)
else:
    print("✓ reddit_posts collection exists")
    info = client.get_collection("reddit_posts")
    print(f"   Points: {info.points_count}")
    print(f"   Vector size: {info.config.params.vectors.size}")
    print(f"   Distance: {info.config.params.vectors.distance}")

# Step 4: Test embeddings
print("\n4. Testing OpenAI embeddings...")
try:
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    test_vector = embeddings.embed_query("test")
    print(f"✓ Embeddings working, vector size: {len(test_vector)}")
except Exception as e:
    print(f"❌ Embeddings failed: {e}")
    exit(1)

# Step 5: Create vector store
print("\n5. Creating LangChain Qdrant wrapper...")
try:
    vector_store = Qdrant(
        client=client,
        collection_name="reddit_posts",
        embeddings=embeddings,
    )
    print("✓ Vector store created")
except Exception as e:
    print(f"❌ Vector store creation failed: {e}")
    exit(1)

# Step 6: Test search
print("\n6. Testing similarity search...")
test_queries = [
    "cybersecurity best practices",
    "network security",
    "firewall configuration",
]

for query in test_queries:
    print(f"\n   Query: '{query}'")
    try:
        results = vector_store.similarity_search(query, k=3)
        print(f"   ✓ Found {len(results)} results")
        
        for i, doc in enumerate(results, 1):
            metadata = doc.metadata if hasattr(doc, 'metadata') else {}
            print(f"      Result {i}:")
            print(f"         Author: {metadata.get('author', 'N/A')}")
            print(f"         Text: {doc.page_content[:100]}...")
            print(f"         Metadata keys: {list(metadata.keys())}")
    except Exception as e:
        print(f"   ❌ Search failed: {e}")

# Step 7: Test with score
print("\n7. Testing search with scores...")
try:
    results_with_scores = vector_store.similarity_search_with_score("cybersecurity", k=3)
    print(f"✓ Found {len(results_with_scores)} results with scores:")
    for i, (doc, score) in enumerate(results_with_scores, 1):
        print(f"   {i}. Score: {score:.4f}, Author: {doc.metadata.get('author', 'N/A')}")
except Exception as e:
    print(f"❌ Search with scores failed: {e}")

print("\n" + "=" * 60)
print("Test completed!")
print("=" * 60)

