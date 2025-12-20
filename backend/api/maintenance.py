from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from core.auth import get_current_user
from models import User
from rag.vectorstore import vector_store
from rag.process_and_upsert_reddit import process_and_upsert_reddit
from rag.process_and_upsert_youtube import process_and_upsert_youtube
from rag.process_and_upsert_podcast import process_and_upsert_podcast
import json
import logging
import httpx
import os

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
        logger.info(f"QDRANT_API_KEY is {'set' if settings.QDRANT_API_KEY else 'NOT set'}")
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
        
        # Create index on doc_type field for efficient filtering
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


# Model testing models and configuration
class ModelTestRequest(BaseModel):
    vendor: str  # "openai", "deepinfra", "openrouter", "groq"
    model: str
    system_prompt: str
    prompt: str
    placeholders: Dict[str, str]  # key -> text mapping


# Model configurations with costs (per 1M tokens)
MODEL_CONFIGS = {
    "openai": {
        "models": {
            "gpt-4o-mini": {"cost_input": 0.15, "cost_output": 0.6, "display_name": "GPT-4o mini"},
            "gpt-4o": {"cost_input": 2.5, "cost_output": 10.0, "display_name": "GPT-4o"},
            "gpt-4.1": {"cost_input": 10.0, "cost_output": 30.0, "display_name": "GPT-4.1"},
            "gpt-5-mini": {"cost_input": 0.5, "cost_output": 1.5, "display_name": "GPT-5 mini"},
            "gpt-5-nano": {"cost_input": 0.3, "cost_output": 1.0, "display_name": "GPT-5 nano"},
            "gpt-5": {"cost_input": 5.0, "cost_output": 15.0, "display_name": "GPT-5"},
            "gpt-5.2": {"cost_input": 8.0, "cost_output": 25.0, "display_name": "GPT-5.2"},
        }
    },
    "deepinfra": {
        "models": {
            "google/gemma-3-27b-it": {"cost_input": 0.15, "cost_output": 0.15, "display_name": "Google Gemma 3 27B IT"},
            "google/gemma-3-12b-it": {"cost_input": 0.08, "cost_output": 0.08, "display_name": "Google Gemma 3 12B IT"},
            "google/gemma-3-4b-it": {"cost_input": 0.03, "cost_output": 0.03, "display_name": "Google Gemma 3 4B IT"},
            "meta-llama/Llama-3.3-70B-Instruct-Turbo": {"cost_input": 0.59, "cost_output": 0.79, "display_name": "Meta Llama 3.3 70B Instruct Turbo"},
            "microsoft/phi-4": {"cost_input": 0.10, "cost_output": 0.10, "display_name": "Microsoft Phi-4"},
            "nvidia/Nemotron-3-Nano-30B-A3B": {"cost_input": 0.06, "cost_output": 0.24, "display_name": "NVIDIA Nemotron 3 Nano 30B A3B"},
            "deepseek-ai/DeepSeek-V3.2": {"cost_input": 0.13, "cost_output": 0.39, "display_name": "DeepSeek V3.2"},
            "deepseek-ai/DeepSeek-V3.1-Terminus": {"cost_input": 0.21, "cost_output": 0.79, "display_name": "DeepSeek V3.1 Terminus"},
            "deepseek-ai/DeepSeek-V3.1": {"cost_input": 0.21, "cost_output": 0.79, "display_name": "DeepSeek V3.1"},
            "openai/gpt-oss-120b": {"cost_input": 0.039, "cost_output": 0.19, "display_name": "OpenAI GPT-OSS 120B"},
            "openai/gpt-oss-20b": {"cost_input": 0.03, "cost_output": 0.14, "display_name": "OpenAI GPT-OSS 20B"},
            "Qwen/Qwen3-235B-A22B-Instruct-2507": {"cost_input": 0.071, "cost_output": 0.463, "display_name": "Qwen3 235B A22B Instruct 2507"},
            "Qwen/Qwen3-30B-A3B": {"cost_input": 0.08, "cost_output": 0.29, "display_name": "Qwen3 30B A3B"},
            "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8": {"cost_input": 0.15, "cost_output": 0.25, "display_name": "Meta Llama 4 Maverick 17B 128E Instruct FP8"},
            "meta-llama/Llama-4-Scout-17B-16E-Instruct": {"cost_input": 0.12, "cost_output": 0.20, "display_name": "Meta Llama 4 Scout 17B 16E Instruct"},
        }
    },
    "openrouter": {
        "models": {
            "openai/gpt-4o": {"cost_input": 2.5, "cost_output": 10.0},
            "openai/gpt-4o-mini": {"cost_input": 0.15, "cost_output": 0.6},
            "anthropic/claude-3.5-sonnet": {"cost_input": 3.0, "cost_output": 15.0},
            "google/gemini-pro-1.5": {"cost_input": 1.25, "cost_output": 5.0},
        }
    },
    "groq": {
        "models": {
            "llama-3.1-70b-versatile": {"cost_input": 0.0, "cost_output": 0.0},  # Free tier
            "llama-3.1-8b-instant": {"cost_input": 0.0, "cost_output": 0.0},  # Free tier
            "mixtral-8x7b-32768": {"cost_input": 0.0, "cost_output": 0.0},  # Free tier
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
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
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
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
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
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    }
    
    logger.debug(f"DeepInfra API call - URL: {url}, Model: {model}")
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        logger.info(f"DeepInfra API response received for model: {model}")
        return data["choices"][0]["message"]["content"]


async def fetch_openai_models(api_key: str) -> List[Dict[str, Any]]:
    """Fetch available models from OpenAI API."""
    url = "https://api.openai.com/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        models = []
        # Common chat completion model prefixes
        chat_models = ["gpt-4o", "gpt-4", "gpt-3.5-turbo", "gpt-5"]
        
        for model in data.get("data", []):
            model_id = model.get("id", "")
            # Only include chat completion models
            if any(prefix in model_id for prefix in chat_models):
                # Format display name
                display_name = model_id.replace("gpt-", "GPT-").replace("-", " ").title()
                models.append({
                    "id": model_id,
                    "display_name": display_name,
                    "cost": "See pricing page"  # OpenAI doesn't provide pricing in models endpoint
                })
        
        # Sort by model ID (newer models first)
        models.sort(key=lambda x: x["id"], reverse=True)
        return models


async def fetch_deepinfra_models(api_key: str) -> List[Dict[str, Any]]:
    """Fetch available models from DeepInfra API."""
    url = "https://api.deepinfra.com/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        models = []
        # Handle different response formats
        if isinstance(data, list):
            for item in data:
                # Check if item is a dict or string
                if isinstance(item, dict):
                    model_name = item.get("model_name", "") or item.get("id", "") or item.get("name", "")
                    pricing = item.get("pricing", {})
                    if isinstance(pricing, dict):
                        input_price = pricing.get("input", 0)
                        output_price = pricing.get("output", 0)
                    else:
                        input_price = 0
                        output_price = 0
                elif isinstance(item, str):
                    # If it's just a string, use it as model name
                    model_name = item
                    input_price = 0
                    output_price = 0
                else:
                    logger.warning(f"Unexpected model item type: {type(item)}, value: {item}")
                    continue
                
                if not model_name:
                    continue
                
                # Format cost
                if input_price == 0 and output_price == 0:
                    cost_str = "See pricing"
                else:
                    cost_str = f"${input_price:.3f} / ${output_price:.3f} per 1M tokens (input/output)"
                
                models.append({
                    "id": model_name,
                    "display_name": model_name.split("/")[-1] if "/" in model_name else model_name,
                    "cost": cost_str
                })
        elif isinstance(data, dict):
            # Handle dict response (might have 'data' or 'models' key)
            model_list = data.get("data", data.get("models", []))
            for item in model_list:
                if isinstance(item, dict):
                    model_name = item.get("model_name", "") or item.get("id", "") or item.get("name", "")
                    pricing = item.get("pricing", {})
                    if isinstance(pricing, dict):
                        input_price = pricing.get("input", 0)
                        output_price = pricing.get("output", 0)
                    else:
                        input_price = 0
                        output_price = 0
                elif isinstance(item, str):
                    model_name = item
                    input_price = 0
                    output_price = 0
                else:
                    continue
                
                if not model_name:
                    continue
                
                if input_price == 0 and output_price == 0:
                    cost_str = "See pricing"
                else:
                    cost_str = f"${input_price:.3f} / ${output_price:.3f} per 1M tokens (input/output)"
                
                models.append({
                    "id": model_name,
                    "display_name": model_name.split("/")[-1] if "/" in model_name else model_name,
                    "cost": cost_str
                })
        
        logger.info(f"Fetched {len(models)} models from DeepInfra")
        return models


async def fetch_openrouter_models(api_key: str) -> List[Dict[str, Any]]:
    """Fetch available models from OpenRouter API."""
    url = "https://openrouter.ai/api/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://mvp-marketing.app",
        "X-Title": "MVP Marketing"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        models = []
        for model_info in data.get("data", []):
            model_id = model_info.get("id", "")
            pricing = model_info.get("pricing", {})
            prompt_price = pricing.get("prompt", 0) if pricing else 0
            completion_price = pricing.get("completion", 0) if pricing else 0
            
            # Format cost
            if prompt_price == 0 and completion_price == 0:
                cost_str = "Free"
            else:
                cost_str = f"${prompt_price:.4f} / ${completion_price:.4f} per 1M tokens (prompt/completion)"
            
            models.append({
                "id": model_id,
                "display_name": model_info.get("name", model_id),
                "cost": cost_str
            })
        return models


async def fetch_groq_models(api_key: str) -> List[Dict[str, Any]]:
    """Fetch available models from Groq API."""
    url = "https://api.groq.com/openai/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        models = []
        for model in data.get("data", []):
            model_id = model.get("id", "")
            # Groq models are typically free
            models.append({
                "id": model_id,
                "display_name": model_id.replace("-", " ").title(),
                "cost": "Free"
            })
        return models


async def call_groq(model: str, system_prompt: str, prompt: str, api_key: str) -> str:
    """Call Groq API."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
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
        system_prompt = request.system_prompt
        prompt = request.prompt
        
        for key, value in request.placeholders.items():
            # Handle both {key} and key formats
            if key.startswith('{') and key.endswith('}'):
                placeholder = key
            else:
                placeholder = f"{{{key}}}"
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
    """Get available models for a vendor by fetching from vendor API."""
    vendor_lower = vendor.lower()
    
    # Get API key based on vendor
    api_key = None
    if vendor_lower == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY not configured")
        models = await fetch_openai_models(api_key)
    elif vendor_lower == "deepinfra":
        api_key = os.getenv("DEEPINFRA_API_KEY", "")
        if not api_key:
            raise HTTPException(status_code=400, detail="DEEPINFRA_API_KEY not configured")
        models = await fetch_deepinfra_models(api_key)
    elif vendor_lower == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            raise HTTPException(status_code=400, detail="OPENROUTER_API_KEY not configured")
        models = await fetch_openrouter_models(api_key)
    elif vendor_lower == "groq":
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise HTTPException(status_code=400, detail="GROQ_API_KEY not configured")
        models = await fetch_groq_models(api_key)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown vendor: {vendor}")
    
    logger.info(f"Fetched {len(models)} models from {vendor}")
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

