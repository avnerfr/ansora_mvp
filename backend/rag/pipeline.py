from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from rag.vectorstore import vector_store
from core.config import settings
from typing import List, Dict, Any, Optional
import logging

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


asset_type_rules = {
    "email": """
subject: 1 line, pain-based,
opening: exactly 2 sentences (context → pain),
bullets: exactly 3 bullets,
    1) Pain (practitioner phrasing)
    2) Insight (why it happens)
    3) Solution/value
cta: 1 sentence
""",
    "one-pager": """
headline: 1 line
subhead: 1 line
lead paragraph: max 2 sentences
problems: exactly 6 bullets, practitioner phrasing only
features: exactly 4 bullets starting with "Feature:" mapped to problems
business impact: exactly 3 bullets, high-level, no numbers
cta: 1 line
""",
    "landing page": """
headline: 1 line
subhead: 1 line
""",
    # Support both "blog" (UI) and "blog post" (notebook wording)
    "blog": """
intro paragraph: max 2 sentences
sections: exactly 3 sections with one-line subheads
conclusion: 1 line
""",
    "blog post": """
intro paragraph: max 2 sentences
sections: exactly 3 sections with one-line subheads
conclusion: 1 line
""",
}


tone_rules = {
    "manager": """
- Professional, sharp, technical.
- Max 18 words per sentence.
- Direct practitioner language: rule bloat, CAB fatigue, shadow rules, hybrid inconsistencies, outage fear.
- No hype. No marketing fluff.
""",
    "technical": """
- Clipped, urgent, engineer-to-engineer.
- Max 12 words per sentence.
- Stripped of politeness. Only risk, clarity, pain, consequence.
- Use INSIGHTS aggressively.
""",
}

DEFAULT_TEMPLATE = """


------------------------------------------------------
CONTENT GUARDRAILS (MANDATORY)
------------------------------------------------------
- All claims must come directly from {{context}} (user-provided pain points and context).
- No invented metrics, quotes, statistics, before/after claims, or capabilities.
- No buzzwords. No vague promises.
- Plain text output only.
- Keep structure EXACT.

------------------------------------------------------
INPUTS

Use the following tone and style guidelines:
{{tone_rules[tone]}}

The user provided the following original text: {{user_provided_text}}
Also make sure to use language and key insights from the following context: {{vector_search_context}}

Use cases / key themes to prioritize: {{backgrounds}}

------------------------------------------------------
OUTPUT
Provide the following asset: {{asset_type}} using the following structure and formatting rules:
{{asset_type_rules[asset_type]}}

The Ideal Customer Profile / role is: {{icp}}

Produce a finalized asset following all structure rules,
tone rules, and content guardrails exactly.
No extra commentary.
From references provide all available information.
""".strip()

VECTOR_DB_RETREIVAL_PROMPT = """
You are a helpful assistant that retrieves information from a vector database.
You are given a query and a list of documents.
You need to retrieve the most relevant documents from the list of documents.
You need to return the most relevant documents from the list of documents.
this is the user query: {{user_provided_text}}
this is the list of documents: {{documents}}
this is the context of the documents: {{backgrounds}}

Output: one short retrieval query (1-3 sentences) that keeps only:
 - entities
 - time range
 - domain keywords
 - constraints (jurisdiction, product, tech stack, etc.)

"""



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


def _fix_mojibake(value: Optional[str]) -> Optional[str]:
    """
    Fix common UTF-8/Windows-1252 mojibake issues (e.g., â€“ → –).
    This is mainly for titles coming from external sources like podcasts/YouTube.
    """
    if not value:
        return value
    fixed = value.replace("â€“", "–")
    # Add more replacements here if needed in the future
    return fixed


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
        filename_str = _fix_mojibake(filename_str)
        
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
            
            # Reddit-specific fields
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
            
            # YouTube-specific fields
            "channel": _fix_mojibake(_safe_str(metadata.get("channel"))),
            "title": _fix_mojibake(_safe_str(metadata.get("title"))),
            "video_url": _safe_str(metadata.get("video_url")),
            "start_sec": _safe_float(metadata.get("start_sec")),
            "end_sec": _safe_float(metadata.get("end_sec")),
            "level": _safe_int(metadata.get("level")),
            "description": _safe_str(metadata.get("description")),
            
            # Podcast-specific and citation fields
            "episode_url": _safe_str(metadata.get("episode_url")),
            "episode_number": _safe_int(metadata.get("episode_number")),
            "mp3_url": _safe_str(metadata.get("mp3_url")),
            "citation": _safe_str(metadata.get("citation")),
            "citation_start_time": _safe_float(metadata.get("citation_start_time")),
            "icp_role_type": _safe_str(metadata.get("icp_role_type")),
        }
        
        sources.append(source)
    return sources


async def process_rag(
    user_id: int,
    backgrounds: List[str],
    marketing_text: str,
    tone: str | None = None,
    asset_type: str | None = None,
    icp: str | None = None,
    template: str | None = None,
) -> tuple[str, List[Dict[str, Any]]]:
    """
    Process RAG pipeline and return refined text and sources.
    
    Returns:
        tuple: (refined_text, sources_list)
    """
    logger.info(f"=== Starting RAG Pipeline ===")
    logger.info(f"User ID: {user_id}")
    logger.info(f"Backgrounds / use cases: {backgrounds}")
    logger.info(f"Context text length: {len(marketing_text)} chars")
    logger.info(f"Context text preview: {marketing_text[:100]}...")
    logger.info(f"Tone: {tone}, Asset Type: {asset_type}, ICP: {icp}")
    logger.info(f"Full context text: {marketing_text}")
    logger.info(f"Template: {template}")
    
    # Use default template if none provided
    if template is None:
        template = DEFAULT_TEMPLATE
        logger.info("Using default template")
    else:
        logger.info("Using custom/override template")

    # --------------------------------------------------
    # Step 1: Build optimized retrieval query for vector DB using LLM,
    #         with {{documents}} populated from user's uploaded documents.
    # --------------------------------------------------
    logger.info("Building optimized retrieval query for vector DB...")
    backgrounds_str = ", ".join(backgrounds)

    documents_summary = ""
    try:
        # Pre-fetch a large set of user documents (independent of the current query)
        # just to build the {{documents}} field for the retrieval prompt.
        # We intentionally do NOT condition this on marketing_text so that
        # all uploaded content is available to the retrieval LLM.
        pre_retriever = vector_store.get_retriever(user_id, k=1000)
        pre_docs = pre_retriever.get_relevant_documents("")  # neutral query → pull as many chunks as possible

        doc_parts: list[str] = []
        for i, doc in enumerate(pre_docs, 1):
            logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
            logger.info(doc)
            logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
            meta = doc.metadata if hasattr(doc, "metadata") else {}
            filename = meta.get("filename", f"Document {i}")
            text = doc.page_content if hasattr(doc, "page_content") else str(doc)
            # Keep up to 1000 chars per document to avoid overlong prompts
            doc_parts.append(f"[{filename}]: {text[:1000]}")

        documents_summary = "\n\n".join(doc_parts)
        logger.info(
            f"✓ Collected {len(pre_docs)} documents for retrieval prompt "
            f"(summary length={len(documents_summary)} chars)"
        )
    except Exception as e:
        logger.warning(
            f"⚠ Error collecting documents for retrieval prompt; "
            f"{{documents}} will be empty: {type(e).__name__}: {str(e)}"
        )

    retrieval_prompt = VECTOR_DB_RETREIVAL_PROMPT
    retrieval_prompt = retrieval_prompt.replace("{{user_provided_text}}", marketing_text)
    retrieval_prompt = retrieval_prompt.replace("{{documents}}", documents_summary)
    retrieval_prompt = retrieval_prompt.replace("{{backgrounds}}", backgrounds_str)

    logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$retrieval_prompt")
    logger.info(retrieval_prompt)
    logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    retrieval_query = marketing_text
    try:
        retrieval_llm = ChatOpenAI(
            model_name="gpt-4",
            temperature=0.0,
            openai_api_key=settings.OPENAI_API_KEY,
        )
        rq_messages = [HumanMessage(content=retrieval_prompt)]
        rq_response = await retrieval_llm.ainvoke(rq_messages)
        retrieval_query = (rq_response.content or marketing_text).strip()
        logger.info(f"✓ Retrieval query built (length={len(retrieval_query)} chars)")
        logger.debug(f"Retrieval query:\n{retrieval_query}")
    except Exception as e:
        logger.warning(
            f"⚠ Error building retrieval query, falling back to full context: "
            f"{type(e).__name__}: {str(e)}"
        )

    # --------------------------------------------------
    # Step 2: Retrieve documents from vector DB using the optimized query
    # --------------------------------------------------
    logger.info("Retrieving relevant documents from vector store...")
    user_docs: list[Any] = []
    external_docs: list[Any] = []
    
    # Search user's uploaded documents (local Qdrant) – used for retrieval & prompt context
    try:
        retriever = vector_store.get_retriever(user_id, k=3)
        logger.info(f"Retriever created for user_{user_id}_documents collection")
        
        user_docs = retriever.get_relevant_documents(retrieval_query)
        logger.info(f"✓ Retrieved {len(user_docs)} user documents")
        
        # Log document details
        for i, doc in enumerate(user_docs, 1):
            metadata = doc.metadata if hasattr(doc, 'metadata') else {}
            logger.info(f"  User Doc {i}: {metadata.get('filename', 'Unknown')} "
                       f"(file_id: {metadata.get('file_id', 'N/A')}, "
                       f"content length: {len(doc.page_content)} chars)")
            
    except Exception as e:
        logger.warning(f"⚠ Error retrieving user documents: {type(e).__name__}: {str(e)}")
    
    # Optional external vector search (e.g., YouTube/Reddit/Podcasts) – used ONLY for references,
    # not for the prompt context. This preserves web insights in the Sources panel without
    # polluting the guarded RAG context that must be based on user-provided documents.
    try:
        logger.info("Searching external sources (YouTube/Reddit/Podcasts) from cloud Qdrant for references...")
        external_docs = vector_store.search_reddit_posts(retrieval_query, k=10)
        logger.info(f"✓ Retrieved {len(external_docs)} external reference documents")
    except Exception as e:
        logger.warning(f"⚠ Error retrieving external reference documents: {type(e).__name__}: {str(e)}")
        external_docs = []

    # For RAG context, use only user-uploaded documents (no external sources)
    retrieved_docs = user_docs
    logger.info(f"✓ Total context sources: {len(retrieved_docs)} user documents (excluding external references)")
    
    # Format context from retrieved documents
    logger.info("Formatting context from retrieved documents...")
    context_parts = []
    for i, doc in enumerate(retrieved_docs, 1):
        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
        filename = metadata.get("filename", "Unknown")
        content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
        context_parts.append(f"[From {filename}]: {content[:1000]}")
        logger.debug(f"  Context part {i} from {filename}: {len(content)} chars")
    
    vector_search_context = (
        "\n\n".join(context_parts) if context_parts else "No relevant documents found."
    )
    logger.info(
        f"✓ Vector search context built: {len(vector_search_context)} chars from {len(context_parts)} sources"
    )
    
    # Format backgrounds
    logger.info(f"Backgrounds / use cases string: {backgrounds_str}")
    
    # Build prompt - replace template variables
    # User can use:
    #   {{backgrounds}} or {{use_cases}}                  → comma-separated use cases
    #   {{marketing_text}} or {{context}}                → user-provided context text
    #   {{vector_search_context}}                        → RAG context from Qdrant
    #   {{tone}}, {{asset_type}}, {{icp}}                → generation controls
    #   {{tone_instructions}} or {{tone_rules[tone]}}    → expanded tone_rules[tone]
    #   {{asset_type_instructions}} or {{asset_type_rules[asset_type]}}
    #                                                   → expanded asset_type_rules[asset_type]
    #   {{user_provided_text}}                           → alias for user context text
    logger.info("Building final prompt...")

    # Expand structured rule blocks from tone/asset type dictionaries
    tone_instructions = tone_rules.get(tone, tone or "") if tone else ""
    asset_type_instructions = asset_type_rules.get(asset_type, asset_type or "") if asset_type else ""

    prompt = template
    prompt = prompt.replace('{{backgrounds}}', backgrounds_str)
    prompt = prompt.replace('{{use_cases}}', backgrounds_str)
    prompt = prompt.replace('{{marketing_text}}', marketing_text)
    prompt = prompt.replace('{{context}}', marketing_text)
    prompt = prompt.replace('{{user_provided_text}}', marketing_text)
    prompt = prompt.replace('{{vector_search_context}}', vector_search_context)
    prompt = prompt.replace('{{tone}}', tone or '')
    prompt = prompt.replace('{{tone_instructions}}', tone_instructions)
    prompt = prompt.replace('{{tone_rules[tone]}}', tone_instructions)
    prompt = prompt.replace('{{asset_type}}', asset_type or '')
    prompt = prompt.replace('{{asset_type_instructions}}', asset_type_instructions)
    prompt = prompt.replace('{{asset_type_rules[asset_type]}}', asset_type_instructions)
    prompt = prompt.replace('{{icp}}', icp or '')
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
        SystemMessage(content="""
        You are an enterprise-grade B2B Product Marketing Writer.
        Your task is to generate a high-clarity, practitioner-level marketing asset
        based ONLY on the INSIGHTS and STRUCTURE provided below.
        
        Do not add external knowledge.
        Do not invent numbers, KPIs, improvements, benchmarks, or capabilities that do not explicitly appear in the INSIGHTS.
        If you are not sure about the information, use the context and references to make a decision."""),
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
    
    # Format sources – expose only external references (YouTube/Reddit/Podcasts).
    # User-uploaded documents are intentionally NOT surfaced here; they are only
    # used to build the RAG context passed to the LLM in the prompt.
    logger.info("Formatting sources...")
    sources = format_sources(external_docs)
    logger.info(f"✓ Formatted {len(sources)} external sources (user-uploaded documents are used only in prompt context)")
    
    logger.info("=== RAG Pipeline Completed Successfully ===")
    return refined_text, sources
