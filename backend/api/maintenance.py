from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from core.auth import get_current_user
from models import User
from rag.vectorstore import vector_store
from rag.process_and_upsert_reddit import process_and_upsert_reddit
from rag.process_and_upsert_youtube import process_and_upsert_youtube
from rag.process_and_upsert_podcast import process_and_upsert_podcast
from rag.dynamodb_prompts import get_latest_prompt_template, AWS_REGION
import json
import logging
import httpx
import os
import boto3
import time
from decimal import Decimal

project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """Health check endpoint to verify Qdrant connectivity."""
    from core.config import settings
    health_status = {
        "status": "unknown",
        "qdrant_url": settings.QDRANT_URL if settings.QDRANT_URL else "NOT SET",
        "qdrant_api_key_set": bool(settings.QDRANT_API_KEY),
        "error": None
    }
    logger.info(f"QDRANT_API_KEY: {settings.QDRANT_API_KEY}")
    
    try:
        # Try to get collections as a connectivity test
        collections_response = vector_store.client.get_collections()
        health_status["status"] = "healthy"
        health_status["collections_count"] = len(collections_response.collections)
        return health_status
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["error"] = f"{type(e).__name__}: {str(e)}"
        return health_status


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
        from core.config import settings
        logger.info(f"Attempting to connect to Qdrant at {settings.QDRANT_URL}")
        if settings.QDRANT_API_KEY:
            masked_key = f"{settings.QDRANT_API_KEY[:8]}...{settings.QDRANT_API_KEY[-4:]}" if len(settings.QDRANT_API_KEY) > 12 else "***"
            logger.info(f"QDRANT_API_KEY is set: {masked_key} (length: {len(settings.QDRANT_API_KEY)})")
        else:
            logger.warning("QDRANT_API_KEY is NOT set in settings")
        logger.info(f"Vector store client URL: {vector_store.client._url if hasattr(vector_store.client, '_url') else 'N/A'}")
        collections_response = vector_store.client.get_collections()
        collection_names = [c.name for c in collections_response.collections]
        logger.info(f"Retrieved {len(collection_names)} collections")
        return {"collections": collection_names}
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        logger.error(f"Failed to get collections: {error_type}: {error_msg}")
        
        from core.config import settings
        # Provide more helpful error messages
        if "Connection refused" in error_msg or "Errno 111" in error_msg:
            raise HTTPException(
                status_code=503,
                detail=f"Qdrant connection refused. Please verify:\n"
                       f"- QDRANT_URL is correct: {settings.QDRANT_URL}\n"
                       f"- QDRANT_API_KEY is set: {'Yes' if settings.QDRANT_API_KEY else 'No'}\n"
                       f"- Qdrant service is accessible from this network\n"
                       f"- Firewall/security groups allow connections to Qdrant"
            )
        elif "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=504,
                detail=f"Qdrant connection timed out. Please check your QDRANT_URL and QDRANT_API_KEY environment variables, and ensure the Qdrant service is accessible."
            )
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to connect to Qdrant ({error_type}): {error_msg}"
        )


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
        
        # Create indexes on doc_type and post_id fields for efficient filtering
        from qdrant_client.models import PayloadSchemaType
        try:
            vector_store.client.create_payload_index(
                collection_name=collection_name,
                field_name="doc_type",
                field_schema=PayloadSchemaType.KEYWORD
            )
            logger.info(f"Created index on 'doc_type' field for collection: {collection_name}")
        except Exception as index_error:
            # Log but don't fail if index creation fails (e.g., index already exists)
            logger.warning(f"Could not create index on 'doc_type' for {collection_name}: {index_error}")
        
        # Create index on post_id field for duplicate prevention
        try:
            vector_store.client.create_payload_index(
                collection_name=collection_name,
                field_name="id",
                field_schema=PayloadSchemaType.KEYWORD
            )
            logger.info(f"Created index on 'post_id' field for collection: {collection_name}")
        except Exception as index_error:
            # Log but don't fail if index creation fails (e.g., index already exists)
            logger.warning(f"Could not create index on 'post_id' for {collection_name}: {index_error}")
        
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


class QueryCollectionRequest(BaseModel):
    collection: str
    query: str
    doc_type: Optional[str] = None
    limit: int = 10


@router.post("/query-collection")
async def query_collection(
    request: QueryCollectionRequest,
    current_user: User = Depends(require_admin)
):
    """Query a collection using semantic search with embedding."""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        from core.config import settings
        from openai import OpenAI
        
        # Check if collection exists
        collections_response = vector_store.client.get_collections()
        collection_names = [c.name for c in collections_response.collections]
        
        if request.collection not in collection_names:
            raise HTTPException(status_code=404, detail=f"Collection '{request.collection}' not found")
        
        logger.info(f"Querying collection '{request.collection}' with: '{request.query}'" + 
                   (f" (doc_type={request.doc_type})" if request.doc_type else ""))
        
        # Log the full query text before embedding
        logger.info(f"Query text to embed: '{request.query}'")
        
        # Step 1: Embed the query
        openai_client = OpenAI(
            api_key=settings.DEEPINFRA_API_KEY,
            base_url=settings.DEEPINFRA_API_BASE_URL
        )
        
        response = openai_client.embeddings.create(
            input=request.query,
            model=vector_store._model_name  # Use same model as vectorstore
        )
        query_vector = response.data[0].embedding
        logger.info(f"✓ Query embedded (model: {vector_store._model_name}, vector dimension: {len(query_vector)})")
        
        # Step 2: Build filter if doc_type specified
        query_filter = None
        if request.doc_type:
            query_filter = Filter(
                must=[FieldCondition(key="doc_type", match=MatchValue(value=request.doc_type))]
            )
        
        # Step 3: Query the collection
        search_results = vector_store.client.query_points(
            collection_name=request.collection,
            query=query_vector,
            limit=min(request.limit, 50),  # Cap at 50
            with_payload=True,
            with_vectors=False,
            query_filter=query_filter
        )
        
        # Step 4: Format results as JSON
        results = []
        for point in search_results.points:
            result = {
                "id": str(point.id),
                "score": float(point.score),
                "payload": point.payload
            }
            results.append(result)
        
        logger.info(f"✓ Retrieved {len(results)} results from {request.collection}")
        
        return {
            "results": results,
            "collection": request.collection,
            "query": request.query,
            "doc_type_filter": request.doc_type,
            "count": len(results)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to query collection: {e}", exc_info=True)
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


# Model testing models and configuration
class ModelTestRequest(BaseModel):
    vendor: str  # "openai", "deepinfra", "openrouter", "groq"
    model: str
    system_prompt: Optional[str] = None
    prompt: str
    placeholders: Dict[str, str]  # key -> text mapping


# Model configurations with costs (per 1M tokens) and description URLs
MODEL_CONFIGS = {
    "openai": {
        "models": {
            "gpt-4o-mini": {
                "cost_input": 0.15, 
                "cost_output": 0.6, 
                "display_name": "GPT-4o mini",
                "url": "https://platform.openai.com/docs/models/gpt-4o-mini"
            },
            "gpt-4o": {
                "cost_input": 2.5, 
                "cost_output": 10.0, 
                "display_name": "GPT-4o",
                "url": "https://platform.openai.com/docs/models/gpt-4o"
            },
            "gpt-4-turbo": {
                "cost_input": 10.0, 
                "cost_output": 30.0, 
                "display_name": "GPT-4 Turbo",
                "url": "https://platform.openai.com/docs/models/gpt-4-turbo"
            },
            "gpt-4": {
                "cost_input": 30.0, 
                "cost_output": 60.0, 
                "display_name": "GPT-4",
                "url": "https://platform.openai.com/docs/models/gpt-4"
            },
            "gpt-3.5-turbo": {
                "cost_input": 0.5, 
                "cost_output": 1.5, 
                "display_name": "GPT-3.5 Turbo",
                "url": "https://platform.openai.com/docs/models/gpt-3-5-turbo"
            },
        }
    },
    "deepinfra": {
        "models": {
            "anthropic/claude-4-opus": {
                "cost_input": 16.50, 
                "cost_output": 82.50, 
                "display_name": "Anthropic Claude 4 Opus",
                "url": "https://deepinfra.com/anthropic/claude-4-opus"
            },
            "anthropic/claude-4-sonnet": {
                "cost_input": 3.0, 
                "cost_output": 15.0, 
                "display_name": "Anthropic Claude 4 Sonnet",
                "url": "https://deepinfra.com/anthropic/claude-4-sonnet"
            },
            "anthropic/claude-3.7-sonnet-latest": {
                "cost_input": 3.0, 
                "cost_output": 15.0, 
                "display_name": "Anthropic Claude 3.7 Sonnet",
                "url": "https://deepinfra.com/anthropic/claude-3-7-sonnet-latest"
            },
            "deepseek-ai/DeepSeek-V3.2": {
                "cost_input": 0.13, 
                "cost_output": 0.39, 
                "display_name": "DeepSeek V3.2",
                "url": "https://deepinfra.com/deepseek-ai/DeepSeek-V3.2"
            },
            "deepseek-ai/DeepSeek-V3.1-Terminus": {
                "cost_input": 0.21, 
                "cost_output": 0.79, 
                "display_name": "DeepSeek V3.1 Terminus",
                "url": "https://deepinfra.com/deepseek-ai/DeepSeek-V3.1-Terminus"
            },
            "deepseek-ai/DeepSeek-V3.1": {
                "cost_input": 0.21, 
                "cost_output": 0.79, 
                "display_name": "DeepSeek V3.1",
                "url": "https://deepinfra.com/deepseek-ai/DeepSeek-V3.1"
            },
            "deepseek-ai/DeepSeek-R1-0528-Turbo": {
                "cost_input": 1.0, 
                "cost_output": 3.0, 
                "display_name": "DeepSeek R1 0528 Turbo",
                "url": "https://deepinfra.com/deepseek-ai/DeepSeek-R1-0528-Turbo"
            },
            "google/gemma-3-27b-it": {
                "cost_input": 0.15, 
                "cost_output": 0.15, 
                "display_name": "Google Gemma 3 27B IT",
                "url": "https://deepinfra.com/google/gemma-3-27b-it"
            },
            "google/gemma-3-12b-it": {
                "cost_input": 0.08, 
                "cost_output": 0.08, 
                "display_name": "Google Gemma 3 12B IT",
                "url": "https://deepinfra.com/google/gemma-3-12b-it"
            },
            "google/gemma-3-4b-it": {
                "cost_input": 0.03, 
                "cost_output": 0.03, 
                "display_name": "Google Gemma 3 4B IT",
                "url": "https://deepinfra.com/google/gemma-3-4b-it"
            },
            "meta-llama/Llama-3.3-70B-Instruct-Turbo": {
                "cost_input": 0.59, 
                "cost_output": 0.79, 
                "display_name": "Meta Llama 3.3 70B Instruct Turbo",
                "url": "https://deepinfra.com/meta-llama/Llama-3.3-70B-Instruct-Turbo"
            },
            "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8": {
                "cost_input": 0.15, 
                "cost_output": 0.25, 
                "display_name": "Meta Llama 4 Maverick 17B",
                "url": "https://deepinfra.com/meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"
            },
            "meta-llama/Llama-4-Scout-17B-16E-Instruct": {
                "cost_input": 0.12, 
                "cost_output": 0.20, 
                "display_name": "Meta Llama 4 Scout 17B",
                "url": "https://deepinfra.com/meta-llama/Llama-4-Scout-17B-16E-Instruct"
            },
            "microsoft/phi-4": {
                "cost_input": 0.10, 
                "cost_output": 0.10, 
                "display_name": "Microsoft Phi-4",
                "url": "https://deepinfra.com/microsoft/phi-4"
            },
            "mistralai/Mixtral-8x7B-Instruct-v0.1": {
                "cost_input": 0.24, 
                "cost_output": 0.24, 
                "display_name": "Mistral Mixtral 8x7B Instruct",
                "url": "https://deepinfra.com/mistralai/Mixtral-8x7B-Instruct-v0.1"
            },
            "mistralai/Voxtral-Small-24B-2507": {
                "cost_input": 0.003, 
                "cost_output": 0.003, 
                "display_name": "Mistral Voxtral Small 24B",
                "url": "https://deepinfra.com/mistralai/Voxtral-Small-24B-2507"
            },
            "moonshotai/Kimi-K2-Instruct-0905": {
                "cost_input": 0.32, 
                "cost_output": 2.0, 
                "display_name": "Moonshot Kimi K2 Instruct",
                "url": "https://deepinfra.com/moonshotai/Kimi-K2-Instruct-0905"
            },
            "nvidia/Nemotron-3-Nano-30B-A3B": {
                "cost_input": 0.06, 
                "cost_output": 0.24, 
                "display_name": "NVIDIA Nemotron 3 Nano 30B",
                "url": "https://deepinfra.com/nvidia/Nemotron-3-Nano-30B-A3B"
            },
            "openai/gpt-oss-120b": {
                "cost_input": 0.039, 
                "cost_output": 0.19, 
                "display_name": "OpenAI GPT-OSS 120B",
                "url": "https://deepinfra.com/openai/gpt-oss-120b"
            },
            "openai/gpt-oss-20b": {
                "cost_input": 0.03, 
                "cost_output": 0.14, 
                "display_name": "OpenAI GPT-OSS 20B",
                "url": "https://deepinfra.com/openai/gpt-oss-20b"
            },
            "Qwen/Qwen3-235B-A22B-Instruct-2507": {
                "cost_input": 0.071, 
                "cost_output": 0.463, 
                "display_name": "Qwen3 235B A22B Instruct",
                "url": "https://deepinfra.com/Qwen/Qwen3-235B-A22B-Instruct-2507"
            },
            "Qwen/Qwen3-30B-A3B": {
                "cost_input": 0.08, 
                "cost_output": 0.29, 
                "display_name": "Qwen3 30B A3B",
                "url": "https://deepinfra.com/Qwen/Qwen3-30B-A3B"
            },
            "Qwen/Qwen3-Coder-480B-A35B-Instruct": {
                "cost_input": 0.40, 
                "cost_output": 1.60, 
                "display_name": "Qwen3 Coder 480B",
                "url": "https://deepinfra.com/Qwen/Qwen3-Coder-480B-A35B-Instruct"
            },
            "zai-org/GLM-4.6": {
                "cost_input": 0.08, 
                "cost_output": 1.75, 
                "display_name": "GLM-4.6",
                "url": "https://deepinfra.com/zai-org/GLM-4.6"
            },
        }
    },
    "openrouter": {
        "models": {
            "openai/gpt-4o": {
                "cost_input": 2.5, 
                "cost_output": 10.0,
                "display_name": "GPT-4o",
                "url": "https://openrouter.ai/models/openai/gpt-4o"
            },
            "openai/gpt-4o-mini": {
                "cost_input": 0.15, 
                "cost_output": 0.6,
                "display_name": "GPT-4o mini",
                "url": "https://openrouter.ai/models/openai/gpt-4o-mini"
            },
            "anthropic/claude-3.5-sonnet": {
                "cost_input": 3.0, 
                "cost_output": 15.0,
                "display_name": "Claude 3.5 Sonnet",
                "url": "https://openrouter.ai/models/anthropic/claude-3.5-sonnet"
            },
            "google/gemini-pro-1.5": {
                "cost_input": 1.25, 
                "cost_output": 5.0,
                "display_name": "Gemini Pro 1.5",
                "url": "https://openrouter.ai/models/google/gemini-pro-1.5"
            },
        }
    },
    "groq": {
        "models": {
            "llama-3.1-70b-versatile": {
                "cost_input": 0.0, 
                "cost_output": 0.0,
                "display_name": "Llama 3.1 70B Versatile",
                "url": "https://console.groq.com/docs/models"
            },
            "llama-3.1-8b-instant": {
                "cost_input": 0.0, 
                "cost_output": 0.0,
                "display_name": "Llama 3.1 8B Instant",
                "url": "https://console.groq.com/docs/models"
            },
            "mixtral-8x7b-32768": {
                "cost_input": 0.0, 
                "cost_output": 0.0,
                "display_name": "Mixtral 8x7B",
                "url": "https://console.groq.com/docs/models"
            },
        }
    }
}


def get_model_cost(vendor: str, model: str) -> str:
    """Get cost information for a model."""
    vendor_config = MODEL_CONFIGS.get(vendor.lower())
    if not vendor_config:
        return "Unknown"
    
    model_info = vendor_config["models"].get(model)
    if not model_info:
        return "Unknown"
    
    cost_input = model_info.get("cost_input", 0)
    cost_output = model_info.get("cost_output", 0)
    
    if cost_input == 0 and cost_output == 0:
        return "Free"
    
    return f"${cost_input:.2f} / ${cost_output:.2f} per 1M tokens (input/output)"


async def call_openai(model: str, system_prompt: str, prompt: str, api_key: str) -> str:
    """Call OpenAI API."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model,
        "messages": messages
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def call_openrouter(model: str, system_prompt: str, prompt: str, api_key: str) -> str:
    """Call OpenRouter API."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://mvp-marketing.app",
        "X-Title": "MVP Marketing"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model,
        "messages": messages
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


async def call_deepinfra(model: str, system_prompt: str, prompt: str, api_key: str) -> str:
    """Call DeepInfra API."""
    url = f"https://api.deepinfra.com/v1/openai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model,
        "messages": messages
    }
    
    logger.debug(f"DeepInfra API call - URL: {url}, Model: {model}")
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        logger.info(f"DeepInfra API response received for model: {model}")
        return data["choices"][0]["message"]["content"]


async def call_groq(model: str, system_prompt: str, prompt: str, api_key: str) -> str:
    """Call Groq API."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": model,
        "messages": messages
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


@router.post("/model-test")
async def test_model(
    request: ModelTestRequest,
    current_user: User = Depends(require_admin)
):
    """Test a model with a prompt and placeholders."""
    try:
        from core.config import settings
        
        # Replace placeholders in system prompt and prompt
        system_prompt = request.system_prompt or ""
        prompt = request.prompt
        
        for key, value in request.placeholders.items():
            # Handle both {key} and key formats
            if key.startswith('{') and key.endswith('}'):
                placeholder = key
            else:
                placeholder = f"{{{key}}}"
            if system_prompt:
                system_prompt = system_prompt.replace(placeholder, value)
            prompt = prompt.replace(placeholder, value)
        
        # Get API key based on vendor
        vendor = request.vendor.lower()
        api_key = None
        
        if vendor == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "")
            if not api_key:
                raise HTTPException(status_code=400, detail="OPENAI_API_KEY not configured")
            response_text = await call_openai(request.model, system_prompt, prompt, api_key)
        elif vendor == "deepinfra":
            api_key = os.getenv("DEEPINFRA_API_KEY", "")
            if not api_key:
                raise HTTPException(status_code=400, detail="DEEPINFRA_API_KEY not configured")
            logger.info(f"Calling DeepInfra with model: {request.model}")
            response_text = await call_deepinfra(request.model, system_prompt, prompt, api_key)
        elif vendor == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY", "")
            if not api_key:
                raise HTTPException(status_code=400, detail="OPENROUTER_API_KEY not configured")
            response_text = await call_openrouter(request.model, system_prompt, prompt, api_key)
        elif vendor == "groq":
            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key:
                raise HTTPException(status_code=400, detail="GROQ_API_KEY not configured")
            response_text = await call_groq(request.model, system_prompt, prompt, api_key)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown vendor: {vendor}")
        
        logger.info(f"Model test completed - Vendor: {vendor}, Model: {request.model}")
        return {
            "success": True,
            "answer": response_text
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model-test/models")
async def get_models(
    vendor: str,
    current_user: User = Depends(require_admin)
):
    """Get available models for a vendor from MODEL_CONFIGS."""
    vendor_lower = vendor.lower()
    vendor_config = MODEL_CONFIGS.get(vendor_lower)
    
    if not vendor_config:
        raise HTTPException(status_code=400, detail=f"Unknown vendor: {vendor}")
    
    models = []
    for model_id, model_info in vendor_config["models"].items():
        cost_input = model_info.get("cost_input", 0)
        cost_output = model_info.get("cost_output", 0)
        
        # Format cost
        if cost_input == 0 and cost_output == 0:
            cost_str = "Free"
        else:
            cost_str = f"${cost_input:.2f} / ${cost_output:.2f} per 1M tokens (input/output)"
        
        models.append({
            "id": model_id,
            "display_name": model_info.get("display_name", model_id),
            "cost": cost_str,
            "url": model_info.get("url")
        })
    
    logger.info(f"Returned {len(models)} models from MODEL_CONFIGS for {vendor}")
    return {"models": models}


@router.get("/model-test/cost")
async def get_model_cost_endpoint(
    vendor: str,
    model: str,
    current_user: User = Depends(require_admin)
):
    """Get cost information for a specific model."""
    cost = get_model_cost(vendor.lower(), model)
    return {"vendor": vendor, "model": model, "cost": cost}


# ============================================================================
# Prompt Templates Management Endpoints
# ============================================================================

class PromptTemplateUpdate(BaseModel):
    template_name: str
    template_body: str
    edit_comment: Optional[str] = None


def _convert_decimal_to_native(obj):
    """Recursively convert Decimal types to int/float for JSON serialization."""
    if isinstance(obj, list):
        return [_convert_decimal_to_native(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: _convert_decimal_to_native(value) for key, value in obj.items()}
    elif isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


@router.get("/prompts/template-names")
async def get_template_names(current_user: User = Depends(require_admin)):
    """Get unique template names from DynamoDB."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('prompts_templates_tbl')
        
        # Scan to get all items
        response = table.scan(ProjectionExpression='template_name')
        items = response.get('Items', [])
        
        # Handle pagination if needed
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                ProjectionExpression='template_name',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        # Get unique template names
        template_names = sorted(list(set(item['template_name'] for item in items)))
        
        logger.info(f"Retrieved {len(template_names)} unique template names")
        return {"template_names": template_names}
    except Exception as e:
        logger.error(f"Failed to get template names: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts/editors")
async def get_editors(
    template_name: str,
    current_user: User = Depends(require_admin)
):
    """Get unique editors for a specific template."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('prompts_templates_tbl')
        
        # Query by template_name
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('template_name').eq(template_name),
            ProjectionExpression='edited_by_sub'
        )
        
        items = response.get('Items', [])
        
        # Get unique editors
        editors = sorted(list(set(item.get('edited_by_sub', 'unknown') for item in items)))
        
        logger.info(f"Retrieved {len(editors)} unique editors for template: {template_name}")
        return {"editors": editors}
    except Exception as e:
        logger.error(f"Failed to get editors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts/versions")
async def get_template_versions(
    template_name: str,
    edited_by: Optional[str] = None,
    current_user: User = Depends(require_admin)
):
    """Get versions (edited_at_iso timestamps) for a template, optionally filtered by editor."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('prompts_templates_tbl')
        
        # Query by template_name
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('template_name').eq(template_name)
        )
        
        items = response.get('Items', [])
        
        # Filter by editor if specified
        if edited_by:
            items = [item for item in items if item.get('edited_by_sub') == edited_by]
        
        # Convert to serializable format and sort by edited_at_iso descending
        versions = []
        for item in items:
            versions.append({
                'edited_at_iso': _convert_decimal_to_native(item.get('edited_at_iso')),
                'edited_by_sub': item.get('edited_by_sub', 'unknown'),
                'edit_comment': item.get('edit_comment', '')
            })
        
        # Sort by timestamp descending (newest first)
        versions.sort(key=lambda x: x['edited_at_iso'], reverse=True)
        
        logger.info(f"Retrieved {len(versions)} versions for template: {template_name}")
        return {"versions": versions}
    except Exception as e:
        logger.error(f"Failed to get template versions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts/template")
async def get_template(
    template_name: str,
    edited_at_iso: int,
    current_user: User = Depends(require_admin)
):
    """Get a specific template version."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('prompts_templates_tbl')
        
        # Get specific item by partition key and sort key
        response = table.get_item(
            Key={
                'template_name': template_name,
                'edited_at_iso': edited_at_iso
            }
        )
        
        item = response.get('Item')
        if not item:
            raise HTTPException(status_code=404, detail="Template version not found")
        
        # Convert Decimal types
        template = {
            'template_name': item.get('template_name'),
            'template_body': item.get('template_body', ''),
            'edited_at_iso': _convert_decimal_to_native(item.get('edited_at_iso')),
            'edited_by_sub': item.get('edited_by_sub', 'unknown'),
            'edit_comment': item.get('edit_comment', '')
        }
        
        logger.info(f"Retrieved template: {template_name} at {edited_at_iso}")
        return template
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompts/template")
async def update_template(
    request: PromptTemplateUpdate,
    current_user: User = Depends(require_admin)
):
    """Create/update a prompt template."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('prompts_templates_tbl')
        
        # Get user info from Cognito token (already verified by require_admin)
        edited_by_sub = current_user.email if hasattr(current_user, 'email') else 'admin'
        
        # Create new version with current timestamp
        timestamp = int(time.time())
        
        item = {
            'template_name': request.template_name,
            'edited_at_iso': timestamp,
            'edited_by_sub': edited_by_sub,
            'template_body': request.template_body,
            'edit_comment': request.edit_comment or ''
        }
        
        # Put item into DynamoDB
        table.put_item(Item=item)
        
        logger.info(f"Updated template: {request.template_name} by {edited_by_sub} at {timestamp}")
        return {
            "success": True,
            "template_name": request.template_name,
            "edited_at_iso": timestamp,
            "edited_by_sub": edited_by_sub,
            "message": f"Template '{request.template_name}' updated successfully"
        }
    except Exception as e:
        logger.error(f"Failed to update template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


