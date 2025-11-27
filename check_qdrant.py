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

# 2. Check Cloud Qdrant (Reddit posts)
print("=== CLOUD QDRANT (REDDIT POSTS) ===")
cloud_client = QdrantClient(
    url="https://c4c03fda-2e4b-45d9-bf2f-e442ba883e0b.eu-west-1-0.aws.cloud.qdrant.io:6333",
    api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.s53XfrTWp0MHokNbtLSx2ikhLdi9Miru2Q99NxACFo8"
)

try:
    collections = cloud_client.get_collections()
    print(f"Collections: {len(collections.collections)}")
    for col in collections.collections:
        info = cloud_client.get_collection(col.name)
        print(f"  - {col.name}: {info.points_count} points, {info.config.params.vectors.size}D vectors")
except Exception as e:
    print(f"Error: {e}")

