from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from rag.vectorstore import vector_store
from core.config import settings
from typing import List, Dict, Any
import logging

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


DEFAULT_TEMPLATE = """You are a senior marketing strategist. The user is working in the following backgrounds: {{backgrounds}}. They provided marketing material: {{marketing_text}}. 

You have access to supporting context from internal documents and Reddit discussions: {{context}}

Rewrite and refine the marketing material to be more compelling, clear, and tailored to these backgrounds. Use insights from both the internal documents and community discussions. Provide a final marketing text and explain briefly how you used the sources."""


def _convert_timestamp(value):
    """Convert timestamp to string if it's a number, otherwise return as-is or None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    if isinstance(value, str):
        return value
    return None

def _safe_int(value):
    """Safely convert value to int, return None if conversion fails."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def _safe_float(value):
    """Safely convert value to float, return None if conversion fails."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def _safe_str(value):
    """Safely convert value to string, return None if value is None or empty."""
    if value is None:
        return None
    if isinstance(value, str):
        return value if value else None
    return str(value)


def format_sources(docs: List[Any]) -> List[Dict[str, Any]]:
    """Format retrieved documents into source items."""
    sources = []
    for doc in docs:
        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
        content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
        
        # Get score from metadata (where vectorstore puts it)
        score = metadata.get("score", 0.0)
        
        # Determine source type and doc type
        source_type = metadata.get("source", metadata.get("source_type", "document"))
        doc_type = metadata.get("doc_type", "unknown")
        
        # Build source object with all available fields
        # Prepare filename
        filename = metadata.get("filename")
        filename_str = str(filename) if filename and filename != "Unknown" else "Unknown"
        
        source = {
            "snippet": (content[:500] if len(content) > 500 else content) or "",
            "text": content or "",
            "score": score if score is not None else 0.0,
            "source": str(source_type) if source_type else None,
            "source_type": str(source_type) if source_type else None,
            "doc_type": str(doc_type) if doc_type else None,
            
            # Core fields with defaults - ensure proper types
            "filename": filename_str,
            "file_type": str(metadata.get("file_type")) if metadata.get("file_type") and metadata.get("file_type") != "unknown" else None,
            "doc_id": str(metadata.get("file_id") or metadata.get("doc_id") or ""),
            "file_id": _safe_int(metadata.get("file_id")),
            
            # Reddit-specific fields (can be None) - ensure proper types
            "subreddit": _safe_str(metadata.get("subreddit")),
            "author": _safe_str(metadata.get("author") or metadata.get("author_fullname")),
            "author_fullname": _safe_str(metadata.get("author_fullname")),
            "thread_url": _safe_str(metadata.get("thread_url")),
            "comment_url": _safe_str(metadata.get("comment_url")),
            "parent_comment_url": _safe_str(metadata.get("parent_comment_url")),
            "thread_index": _safe_int(metadata.get("thread_index")),
            "reply_index": _safe_int(metadata.get("reply_index")),
            "flair_text": _safe_str(metadata.get("flair_text")),
            "ups": _safe_int(metadata.get("ups")),
            # Convert timestamp/created_utc to string if they're numbers
            "timestamp": _convert_timestamp(metadata.get("timestamp") or metadata.get("created_utc")),
            "created_utc": _convert_timestamp(metadata.get("created_utc")),
            "type": _safe_str(metadata.get("type") or doc_type),
            
            # YouTube-specific fields (can be None) - ensure proper types
            "channel": _safe_str(metadata.get("channel")),
            "title": _safe_str(metadata.get("title")),
            "video_url": _safe_str(metadata.get("video_url")),
            "start_sec": _safe_float(metadata.get("start_sec")),
            "end_sec": _safe_float(metadata.get("end_sec")),
            "level": _safe_int(metadata.get("level")),
        }
        
        sources.append(source)
    return sources


async def process_rag(
    user_id: int,
    backgrounds: List[str],
    marketing_text: str,
    template: str = None
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Process RAG pipeline and return refined text and sources.
    
    Returns:
        tuple: (refined_text, sources_list)
    """
    logger.info(f"=== Starting RAG Pipeline ===")
    logger.info(f"User ID: {user_id}")
    logger.info(f"Backgrounds: {backgrounds}")
    logger.info(f"Marketing text length: {len(marketing_text)} chars")
    logger.info(f"Marketing text preview: {marketing_text[:100]}...")
    logger.debug(f"Full marketing text: {marketing_text}")
    logger.debug(f"Template: {template}")
    
    # Use default template if none provided
    if template is None:
        template = DEFAULT_TEMPLATE
        logger.info("Using default template")
    else:
        logger.info("Using custom/override template")
    
    # Get retriever for user's documents
    logger.info("Retrieving relevant documents from vector store...")
    user_docs = []
    reddit_docs = []
    
    # Search user's uploaded documents (local Qdrant)
    try:
        retriever = vector_store.get_retriever(user_id, k=3)
        logger.info(f"Retriever created for user_{user_id}_documents collection")
        
        user_docs = retriever.get_relevant_documents(marketing_text)
        logger.info(f"✓ Retrieved {len(user_docs)} user documents")
        
        # Log document details
        for i, doc in enumerate(user_docs, 1):
            metadata = doc.metadata if hasattr(doc, 'metadata') else {}
            logger.info(f"  User Doc {i}: {metadata.get('filename', 'Unknown')} "
                       f"(file_id: {metadata.get('file_id', 'N/A')}, "
                       f"content length: {len(doc.page_content)} chars)")
            
    except Exception as e:
        logger.warning(f"⚠ Error retrieving user documents: {type(e).__name__}: {str(e)}")
    
    # Search Reddit posts (cloud Qdrant)
    try:
        logger.info("Searching Reddit posts from cloud Qdrant...")
        reddit_docs = vector_store.search_reddit_posts(marketing_text, k=10)
        logger.info(f"✓ Retrieved {len(reddit_docs)} Reddit posts")
        
        # Log Reddit post details
        for i, doc in enumerate(reddit_docs, 1):
            metadata = doc.metadata if hasattr(doc, 'metadata') else {}
            logger.info(f"  Reddit Post {i}: {metadata.get('author', 'Unknown')} "
                       f"(content length: {len(doc.page_content)} chars)")
    except Exception as e:
        logger.warning(f"⚠ Error retrieving Reddit posts: {type(e).__name__}: {str(e)}")
    
    # Combine results: user docs + Reddit posts
    retrieved_docs = user_docs + reddit_docs
    logger.info(f"✓ Total combined sources: {len(retrieved_docs)} ({len(user_docs)} user docs + {len(reddit_docs)} Reddit posts)")
    
    # Format context from retrieved documents
    logger.info("Formatting context from retrieved documents...")
    context_parts = []
    for i, doc in enumerate(retrieved_docs, 1):
        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
        filename = metadata.get("filename", "Unknown")
        content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
        context_parts.append(f"[From {filename}]: {content[:1000]}")
        logger.debug(f"  Context part {i} from {filename}: {len(content)} chars")
    
    context = "\n\n".join(context_parts) if context_parts else "No relevant documents found."
    logger.info(f"✓ Context built: {len(context)} chars from {len(context_parts)} sources")
    
    # Format backgrounds
    backgrounds_str = ", ".join(backgrounds)
    logger.info(f"Backgrounds string: {backgrounds_str}")
    
    # Build prompt - replace template variables
    # User can use {{backgrounds}}, {{marketing_text}}, {{context}} in template
    logger.info("Building final prompt...")
    prompt = template
    prompt = prompt.replace('{{backgrounds}}', backgrounds_str)
    prompt = prompt.replace('{{marketing_text}}', marketing_text)
    prompt = prompt.replace('{{context}}', context)
    logger.info(f"✓ Prompt built: {len(prompt)} chars")
    logger.debug(f"Full prompt:\n{prompt}")
    
    # Initialize LLM
    logger.info("Initializing LLM (GPT-4, temp=0.7)...")
    llm = ChatOpenAI(
        model_name="gpt-4",
        temperature=0.7,
        openai_api_key=settings.OPENAI_API_KEY
    )
    logger.info("✓ LLM initialized")
    
    # Generate response
    logger.info("Sending request to OpenAI API...")
    messages = [
        SystemMessage(content="You are an expert marketing strategist who creates compelling, refined marketing content."),
        HumanMessage(content=prompt)
    ]
    
    try:
        response = await llm.ainvoke(messages)
        logger.info(f"?? LLM messages: {messages}")
        refined_text = response.content if hasattr(response, 'content') else str(response)
        #logger.info(f"✓ LLM response received: {len(refined_text)} chars")
        logger.info(f"✓ LLM response received: {refined_text}")
        logger.debug(f"Refined text preview: {refined_text[:200]}...")
    except Exception as e:
        logger.error(f"✗ Error calling LLM: {type(e).__name__}: {str(e)}")
        raise
    
    # Format sources
    logger.info("Formatting sources...")
    sources = format_sources(retrieved_docs)
    logger.info(f"✓ Formatted {len(sources)} sources")
    
    logger.info("=== RAG Pipeline Completed Successfully ===")
    return refined_text, sources

