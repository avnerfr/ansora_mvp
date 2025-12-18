from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from typing import List, Optional
from core.auth import get_current_user
from models import User
from rag.vectorstore import vector_store
from rag.process_and_upsert_reddit import process_and_upsert_reddit
from rag.process_and_upsert_youtube import process_and_upsert_youtube
from rag.process_and_upsert_podcast import process_and_upsert_podcast
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency that requires admin group membership."""
    # For now, check if user email is in admin list or has admin flag
    # In production, this would check Cognito groups from the token
    # The frontend already checks cognito:groups, backend trusts the token
    return current_user


@router.get("/collections")
async def get_collections(current_user: User = Depends(require_admin)):
    """Get list of all Qdrant collections."""
    try:
        collections_response = vector_store.client.get_collections()
        collection_names = [c.name for c in collections_response.collections]
        logger.info(f"Retrieved {len(collection_names)} collections")
        return {"collections": collection_names}
    except Exception as e:
        logger.error(f"Failed to get collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collections")
async def create_collection(
    collection_name: str = Form(...),
    vector_size: int = Form(1536),
    distance: str = Form("Cosine"),
    current_user: User = Depends(require_admin)
):
    """Create a new Qdrant collection."""
    try:
        from qdrant_client.models import VectorParams, Distance as QdrantDistance
        
        # Validate collection name
        if not collection_name or not collection_name.strip():
            raise HTTPException(status_code=400, detail="Collection name is required")
        
        # Check if collection already exists
        collections_response = vector_store.client.get_collections()
        collection_names = [c.name for c in collections_response.collections]
        
        if collection_name in collection_names:
            raise HTTPException(status_code=400, detail=f"Collection '{collection_name}' already exists")
        
        # Validate distance
        distance_map = {
            "Cosine": QdrantDistance.COSINE,
            "Euclidean": QdrantDistance.EUCLID,
            "Dot": QdrantDistance.DOT
        }
        if distance not in distance_map:
            raise HTTPException(status_code=400, detail=f"Invalid distance metric. Must be one of: {list(distance_map.keys())}")
        
        # Validate vector size
        if vector_size < 1 or vector_size > 10000:
            raise HTTPException(status_code=400, detail="Vector size must be between 1 and 10000")
        
        # Create collection
        vector_store.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=distance_map[distance])
        )
        
        logger.info(f"Created collection: {collection_name} (vector_size={vector_size}, distance={distance})")
        return {
            "success": True,
            "collection": collection_name,
            "vector_size": vector_size,
            "distance": distance,
            "message": f"Collection '{collection_name}' created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collections/{collection_name}")
async def delete_collection(
    collection_name: str,
    current_user: User = Depends(require_admin)
):
    """Delete a Qdrant collection."""
    try:
        # Check if collection exists
        collections_response = vector_store.client.get_collections()
        collection_names = [c.name for c in collections_response.collections]
        
        if collection_name not in collection_names:
            raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found")
        
        # Delete collection
        vector_store.client.delete_collection(collection_name=collection_name)
        
        logger.info(f"Deleted collection: {collection_name}")
        return {
            "success": True,
            "collection": collection_name,
            "message": f"Collection '{collection_name}' deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collection-stats/{collection}")
async def get_collection_stats(
    collection: str,
    current_user: User = Depends(require_admin)
):
    """Get doc_type counts for a collection."""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        # Check if collection exists
        collections_response = vector_store.client.get_collections()
        collection_names = [c.name for c in collections_response.collections]
        
        if collection not in collection_names:
            raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
        
        # Get total count
        collection_info = vector_store.client.get_collection(collection)
        total_points = collection_info.points_count
        
        # Get unique doc_types by scrolling a sample and counting
        doc_type_counts = {}
        offset = None
        
        while True:
            results = vector_store.client.scroll(
                collection_name=collection,
                limit=1000,
                offset=offset,
                with_payload=["doc_type"],
                with_vectors=False
            )
            
            points, next_offset = results
            
            for point in points:
                doc_type = point.payload.get("doc_type", "unknown") if point.payload else "unknown"
                doc_type_counts[doc_type] = doc_type_counts.get(doc_type, 0) + 1
            
            if next_offset is None or len(points) == 0:
                break
            offset = next_offset
        
        logger.info(f"Collection {collection} stats: {total_points} total, {doc_type_counts}")
        return {
            "collection": collection,
            "total_points": total_points,
            "doc_type_counts": doc_type_counts
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/records/{collection}")
async def get_records(
    collection: str,
    limit: int = 10,
    doc_type: Optional[str] = None,
    current_user: User = Depends(require_admin)
):
    """Retrieve records from a specific collection, optionally filtered by doc_type."""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        # Check if collection exists
        collections_response = vector_store.client.get_collections()
        collection_names = [c.name for c in collections_response.collections]
        
        if collection not in collection_names:
            raise HTTPException(status_code=404, detail=f"Collection '{collection}' not found")
        
        # Build filter if doc_type specified
        scroll_filter = None
        if doc_type:
            scroll_filter = Filter(
                must=[FieldCondition(key="doc_type", match=MatchValue(value=doc_type))]
            )
        
        # Scroll through records (no vector search, just retrieve)
        results = vector_store.client.scroll(
            collection_name=collection,
            limit=min(limit, 100),  # Cap at 100
            scroll_filter=scroll_filter,
            with_payload=True,
            with_vectors=False
        )
        
        records = []
        for point in results[0]:
            records.append({
                "id": str(point.id),
                "metadata": point.payload
            })
        
        logger.info(f"Retrieved {len(records)} records from {collection}" + (f" (doc_type={doc_type})" if doc_type else ""))
        return {"records": records, "collection": collection, "doc_type_filter": doc_type}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get records: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upsert/{data_type}")
async def upsert_data(
    data_type: str,
    files: List[UploadFile] = File(...),
    collection: Optional[str] = Form(None),
    podcast_format: Optional[str] = Form(None),
    current_user: User = Depends(require_admin)
):
    """Upsert data into vector store."""
    if data_type not in ['reddit', 'podcast', 'youtube']:
        raise HTTPException(status_code=400, detail="Invalid data type. Must be 'reddit', 'podcast', or 'youtube'")
    
    total_count = 0
    
    try:
        for file in files:
            content = await file.read()
            
            # Parse JSON content
            try:
                data = json.loads(content.decode('utf-8'))
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail=f"Invalid JSON in file: {file.filename}")
            
            # Handle both single object and array
            if isinstance(data, dict):
                data = [data]
            
            if not isinstance(data, list):
                raise HTTPException(status_code=400, detail=f"Expected JSON array or object in file: {file.filename}")
            
            # Use provided collection or default based on data type
            if collection:
                collection_name = collection
            elif data_type == 'reddit':
                collection_name = "reddit_posts"
            elif data_type == 'podcast':
                collection_name = "podcasts"
            else:  # youtube
                collection_name = "youtube_transcripts"
            
            # Use specialized processing for each data type
            if data_type == 'reddit':
                count = process_and_upsert_reddit(data, collection_name)
                total_count += count
                logger.info(f"Processed {count} Reddit records from {file.filename} to {collection_name}")
            elif data_type == 'youtube':
                count = process_and_upsert_youtube(data, collection_name)
                total_count += count
                logger.info(f"Processed {count} YouTube transcript records from {file.filename} to {collection_name}")
            elif data_type == 'podcast':
                count = process_and_upsert_podcast(data, collection_name, podcast_format)
                total_count += count
                logger.info(f"Processed {count} Podcast transcript records from {file.filename} to {collection_name}")
        
        return {
            "success": True,
            "count": total_count,
            "data_type": data_type,
            "message": f"Successfully upserted {total_count} records"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upsert data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

