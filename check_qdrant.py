"""
Quick script to check what's in your Qdrant databases
"""
from qdrant_client import QdrantClient

# 1. Check Docker Local Qdrant (MVP app)
print("=== DOCKER LOCAL QDRANT (MVP APP) ===")
local_client = QdrantClient(url="http://localhost:6333")

try:
    collections = local_client.get_collections()
    print(f"Collections: {len(collections.collections)}")
    for col in collections.collections:
        info = local_client.get_collection(col.name)
        print(f"  - {col.name}: {info.points_count} points, {info.config.params.vectors.size}D vectors")
except Exception as e:
    print(f"Error: {e}")

print()
from dotenv import load_dotenv
# Initialize clients
load_dotenv()
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# 2. Check Cloud Qdrant (Reddit posts)
print("=== CLOUD QDRANT (REDDIT POSTS) ===")
cloud_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)

try:
    collections = cloud_client.get_collections()
    print(f"Collections: {len(collections.collections)}")
    for col in collections.collections:
        info = cloud_client.get_collection(col.name)
        print(f"  - {col.name}: {info.points_count} points, {info.config.params.vectors.size}D vectors")
except Exception as e:
    print(f"Error: {e}")

