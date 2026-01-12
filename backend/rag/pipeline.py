import boto3
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from rag.vectorstore import vector_store
from rag import s3_utils
from rag.s3_utils import CompanyDetails
from core.config import settings
from typing import List, Dict, Any, Optional
import logging
import re
import json
import tiktoken
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64
from decimal import Decimal
#from google.auth.transport.requests import Request
#from google.oauth2.credentials import Credentials
#from googleapiclient.discovery import build
#from googleapiclient.errors import HttpError
load_dotenv()   


# Define email sender and receiver
sender_email = os.getenv("GOOGLE_APP_MAIL")
receiver_email = "ansora.tech@gmail.com;avner.fr@gmail.com" # Can be a list of emails
# Gmail API OAuth2 credentials
gmail_client_id = os.getenv("GMAIL_CLIENT_ID")
gmail_client_secret = os.getenv("GMAIL_CLIENT_SECRET")
gmail_refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

from .prompts import SYSTEM_PROMPT, DEFAULT_TEMPLATE, DEFAULT_TEMPLATE_1, VECTOR_DB_RETREIVAL_PROMPT
from .dynamodb_prompts import get_prompt_metadata_for_logging, AWS_REGION
# Configure logging
logger = logging.getLogger(__name__)
# Don't configure logging here - main.py handles it to prevent duplicates


# Fallback asset type rules (used if DynamoDB unavailable)
_DEFAULT_ASSET_TYPE_RULES = {
"email": """
Theme
Name the recurring operational struggle, not the category.

Example format:
“Making changes without knowing what will break later”

Subject (≤10 words)

Describe the gap between expectation and reality.
Use buyer language if possible.

Examples:
“Approved changes that don’t behave as expected”
“The part everyone finds after the incident”

Opening (Hook – max 2 sentences, ≤15 words each)

Purpose: create recognition, not explain.

Rules:

Describe what should happen vs what actually happens.

Embed 1 buyer phrase naturally.

No causes. No fixes.

Structure:

Sentence 1: expectation

Sentence 2: operational reality

Body (Exactly 3 bullets)
Bullet 1 – Whether / Or tension
Purpose: show the decision trap, not the choice.

Rules:
Connect 2–3 aspects of the same pain.
Use uncertainty, tradeoffs, or ambiguity.
No judgment.
Feels like:
“Either we do X and risk Y, or we avoid X and accept Z.”

Bullet 2 – Systemic operational consequence
Purpose: show what this pain forces teams to live with over time.

Rules (very strict):
Describe repeated behavior: chasing, rechecking, second-guessing, backtracking.
Only buyer language. No abstractions.
No mention of what’s missing.
No implied solution.

Mental test:
If you remove Bullet 3, Bullet 2 should still feel complete and heavy.

Bullet 3 – Changed operating reality (pre-decision clarity)
Purpose: describe how work feels when fewer unknowns exist before acting.

Rules:
Observational only.
Same team, same constraints.
Focus on pace, confidence, fewer surprises — without naming why.
No tools, no methods, no concepts.

Think:
“This is how the day goes when you’re not guessing.”

CTA (1 sentence, ≤15 words)
Purpose: invite peer conversation, not action.

Rules:
Neutral.
Operational.
No verbs like “learn”, “see”, “discover”.

Example formats:
“Curious how you deal with this today.”
“Worth comparing notes sometime.”
""",
"one-pager": """
headline:
1 line describing the operational problem surfaced in the JSON.

problem:
2-3 sentences grounded in the insights, describing the current "mess".

why it persists:
2-3 sentences using the "Whether/Or" rule to link technical specifics to systemic risk.

operational shift:
2-3 sentences describing what changes with end-to-end visibility.

""",
"landing page": """
headline: 1 line, sharp, focused on the core struggle from the insights.
subhead: 1 line, clarifying what pain it solves or what outcome it unlocks
""",
    # Support both "blog" (UI) and "blog post" (notebook wording)
"blog": """
intro:
Maximum 2 sentences framing a real operational failure or misconception.

section 1:
One-line subhead stating a clear insight.
2-3 sentences describing the technical problem using practitioner language from the data.

section 2:
One-line subhead.
2-3 sentences using the "Whether/Or" rule to link technical specifics to systemic risk.

section 3:
One-line subhead.
2-3 sentences describing the specific "before vs after" shift found in the JSON's buyer_language.

conclusion:
1 sentence tying the issue back to operational clarity.
""",
    "blog post": """
- Length: Short-form thought leadership (400-600 words max)
- Audience: Senior practitioners (Security, IAM, Platform, DevSecOps)

STRUCTURE:
1. INTRO (max 2 sentences)
   - Start with a concrete observation from real-world operations.
   - No industry clichés, no generic “security is hard” statements.

2. BODY: Exactly 3 sections
   - Each section must have:
     • A ONE-LINE subhead that states a clear insight or claim (not a topic)
     • 2-3 short paragraphs explaining:
       - What teams believe
       - Why that belief breaks down in practice
       - The real operational consequence

3. CONCLUSION (exactly 1 sentence)
   - Reframe the problem in a sharper, more actionable way.
   - Do NOT pitch a product.

""","linkedin post": """
1 short hook sentence based on the data..
1-2 sentences describing the "Whether/Or" struggle using specific technical insights.
1 sentence highlighting the hidden risk or blind spot found in the insight.
1 sentence on why the current state is unsustainable based on the pain_phrases.
""",
}


def _load_asset_type_rules_from_dynamodb() -> dict[str, str]:
    """
    Load asset type rules from DynamoDB.
    Templates starting with 'asset_template_' are loaded as asset type rules.
    The asset type name is extracted from template_name by removing 'asset_template_' prefix.
    
    Returns:
        Dictionary mapping asset type to rule body
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('prompts_templates_tbl')
        
        # Scan for all items starting with 'asset_template_'
        response = table.scan(
            FilterExpression='begins_with(template_name, :prefix)',
            ExpressionAttributeValues={':prefix': 'asset_template_'}
        )
        
        items = response.get('Items', [])
        
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression='begins_with(template_name, :prefix)',
                ExpressionAttributeValues={':prefix': 'asset_template_'},
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))
        
        # Group by template_name and get the latest version (highest edited_at_iso)
        templates_by_name = {}
        for item in items:
            template_name = item.get('template_name')
            edited_at_iso = item.get('edited_at_iso', 0)
            
            # Convert Decimal to int for comparison
            if isinstance(edited_at_iso, Decimal):
                edited_at_iso = int(edited_at_iso)
            
            if template_name not in templates_by_name or edited_at_iso > templates_by_name[template_name].get('edited_at_iso', 0):
                templates_by_name[template_name] = item
        
        # Build asset_type_rules dictionary
        asset_rules = {}
        for template_name, item in templates_by_name.items():
            # Extract asset type name: 'asset_template_one-pager' -> 'one-pager'
            asset_type = template_name.replace('asset_template_', '')
            template_body = item.get('template_body', '')
            
            if template_body:
                asset_rules[asset_type] = template_body
                logger.info(f"Loaded asset type rule '{asset_type}' from DynamoDB (edited_at: {item.get('edited_at_iso')})")
        
        logger.info(f"✓ Loaded {len(asset_rules)} asset type rules from DynamoDB")
        return asset_rules
        
    except Exception as e:
        logger.error(f"✗ Error loading asset type rules from DynamoDB: {e}")
        return {}


def _get_asset_type_rules() -> dict[str, str]:
    """
    Get asset type rules, merging DynamoDB rules with fallback defaults.
    DynamoDB rules take precedence over defaults.
    
    Returns:
        Dictionary mapping asset type to rule body
    """
    # Start with defaults
    rules = _DEFAULT_ASSET_TYPE_RULES.copy()
    
    # Load from DynamoDB and override/add
    dynamodb_rules = _load_asset_type_rules_from_dynamodb()
    if dynamodb_rules:
        rules.update(dynamodb_rules)
        logger.info(f"Using {len(dynamodb_rules)} asset type rules from DynamoDB, {len(_DEFAULT_ASSET_TYPE_RULES)} from defaults")
    else:
        logger.warning("⚠ Using fallback asset type rules (DynamoDB unavailable or returned no rules)")
    
    return rules


# Load asset type rules (combines DynamoDB and defaults)
asset_type_rules = _get_asset_type_rules()











#VECTOR_DB_RETREIVAL_PROMPT = """
#You are a helpful assistant that prepares a retrieval query for a vector database.
#You are given a user query and high-level background/use-case hints.

#this is the user query: {{user_provided_text}}
#this is the context of the query: {{backgrounds}}

#Output: one short retrieval query (1-3 sentences) that keeps only:
# - entities
# - time range
# - domain keywords
# - constraints (jurisdiction, product, tech stack, etc.)
#"""


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))


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
        # Handle external_docs dictionaries (source objects we created)
        if isinstance(doc, dict):
            # For our source objects, use the dict as metadata and extract content
            metadata = doc.copy()
            # If text field already exists (from retrieve_documents context_excerpt), use it directly
            # Otherwise, use snippet or other fields
            if "text" in doc and doc.get("text"):
                content = doc.get("text")
                display_text = content
            else:
                content = doc.get("snippet", doc.get("citation", doc.get("title", "No content")))
                display_text = content
        else:
            # Handle LangChain Document objects
            metadata = doc.metadata if hasattr(doc, 'metadata') else {}
            content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
        
        # Get score from metadata (where vectorstore puts it)
        score = metadata.get("score", 0.0)
        
        # Determine source type and doc type
        source_type = metadata.get("source", metadata.get("source_type", "document"))
        doc_type = metadata.get("doc_type", "unknown")
        
        # For Reddit posts/threads/comments, prefer the richer discussion
        # description field (if available) for display instead of the raw
        # post text/selftext.
        is_reddit = False
        try:
            st_lower = str(source_type).lower() if source_type else ""
            dt_lower = str(doc_type).lower() if doc_type else ""
            is_reddit = (st_lower == "reddit") or dt_lower.startswith("reddit_")
        except Exception:
            is_reddit = False

        # Initialize these variables for both dict and non-dict paths
        discussion_desc = None
        detailed_expl = None
        
        # Only apply Reddit-specific logic if not already processed (external_docs already have formatted text)
        if not isinstance(doc, dict):
            discussion_desc = metadata.get("discussion_description")
            detailed_expl = (
                discussion_desc
                or metadata.get("detailed-explanation")
                or metadata.get("detailed_explanation")
                or metadata.get("detailed_description")
            )
            display_text = (
                _safe_str(detailed_expl) if is_reddit and _safe_str(detailed_expl) else content
            )
        
        # Build source object with all available fields
        # Prepare filename
        filename = metadata.get("filename")
        filename_str = str(filename) if filename and filename != "Unknown" else "Unknown"
        filename_str = _fix_mojibake(filename_str)
        
        source = {
            # Use detailed_explanation for Reddit, otherwise fall back to content
            "snippet": (display_text[:500] if len(display_text) > 500 else display_text) or "",
            "text": display_text or "",
            "score": score if score is not None else 0.0,
            "source": str(source_type) if source_type else None,
            "source_type": str(source_type) if source_type else None,
            "doc_type": str(doc_type) if doc_type else None,
            
            # Core fields with defaults - ensure proper types
            "filename": filename_str,
            "file_type": str(metadata.get("file_type")) if metadata.get("file_type") and metadata.get("file_type") != "unknown" else None,
            "doc_id": str(metadata.get("file_id") or metadata.get("doc_id") or ""),
            "file_id": _safe_int(metadata.get("file_id")),
            
            # Common fields across all document types (new structure)
            "citation": _safe_str(metadata.get("citation")),
            "citation_start_time": _safe_float(metadata.get("citation_start_time")),
            "icp_role_type": _safe_str(metadata.get("icp_role_type")),
            "title": _fix_mojibake(_safe_str(metadata.get("title"))),
            "channel": _fix_mojibake(_safe_str(metadata.get("channel"))),
            "type": _safe_str(metadata.get("type") or doc_type),
            
            # Podcast-specific fields
            "episode_url": _safe_str(metadata.get("episode_url")),
            "episode_number": _safe_int(metadata.get("episode_number")),
            "mp3_url": _safe_str(metadata.get("mp3_url") or metadata.get("mp3_link")),
            
            # Reddit-specific fields (new structure)
            "selftext": _safe_str(metadata.get("selftext")),
            "thread_author": _safe_str(metadata.get("thread_author")),
            "subreddit": _safe_str(metadata.get("subreddit")),
            "thread_url": _safe_str(metadata.get("thread_url")),
            # Prefer discussion_description; fall back to legacy detailed-explanation
            "detailed_explanation": _safe_str(detailed_expl),
            "discussion_description": _safe_str(discussion_desc or detailed_expl),
            
            # YouTube-specific fields
            "video_url": _safe_str(metadata.get("video_url")),
            "description": _safe_str(metadata.get("description")),
            
            # Legacy fields (for backward compatibility with old data)
            "author": _safe_str(metadata.get("author") or metadata.get("author_fullname")),
            "author_fullname": _safe_str(metadata.get("author_fullname")),
            "comment_url": _safe_str(metadata.get("comment_url")),
            "parent_comment_url": _safe_str(metadata.get("parent_comment_url")),
            "thread_index": _safe_int(metadata.get("thread_index")),
            "reply_index": _safe_int(metadata.get("reply_index")),
            "flair_text": _safe_str(metadata.get("flair_text")),
            "ups": _safe_int(metadata.get("ups")),
            "timestamp": _convert_timestamp(metadata.get("timestamp") or metadata.get("created_utc")),
            "created_utc": _convert_timestamp(metadata.get("created_utc")),
            "start_sec": _safe_float(metadata.get("start_sec")),
            "end_sec": _safe_float(metadata.get("end_sec")),
            "level": _safe_int(metadata.get("level")),

            # Generic URL field (uses the most appropriate URL for each doc type)
            "url": _safe_str(metadata.get("url") or metadata.get("thread_url") or metadata.get("video_url") or metadata.get("episode_url")),

            # RAG-specific metadata fields
            "key_issues": metadata.get("key_issues", []),
            "pain_phrases": metadata.get("pain_phrases", []),
            "emotional_triggers": metadata.get("emotional_triggers", []),
            "buyer_language": metadata.get("buyer_language", []),
            "implicit_risks": metadata.get("implicit_risks", []),
        }
        
        sources.append(source)
    return sources


def merge_and_filter_duplicate_documents(docs: List[Any], merger_by: str, max_docs: int = 10) -> List[Any]:
    """
    Merge and filter duplicate documents based on a metadata key (e.g. 'url', 'video_url').
    Keeps the first occurrence for each unique key value.
    """
    logger.info("Merging and filtering duplicate documents by '%s'", merger_by)
    merged_docs: list[Any] = []
    seen_values: set[str] = set()

    # Debug: log sample of merger_by values
    sample_values = []
    for doc in docs[:5]:  # Check first 5 docs
        metadata = doc.metadata if hasattr(doc, "metadata") else {}
        raw_value = metadata.get(merger_by)
        sample_values.append(str(raw_value) if raw_value is not None else "None")
    logger.info(f"Sample {merger_by} values (first 5): {sample_values}")

    for doc in docs:
        metadata = doc.metadata if hasattr(doc, "metadata") else {}
        raw_value = metadata.get(merger_by)

        # Normalize to string for comparison; None becomes empty string
        value_str = str(raw_value) if raw_value is not None else ""

        if value_str in seen_values:
            logger.debug(f"Skipping duplicate {merger_by}={value_str}")
            continue

        seen_values.add(value_str)
        merged_docs.append(doc)

    logger.info("After merge/filter by '%s': %d → %d (unique values: %d)", merger_by, len(docs), len(merged_docs), len(seen_values))
    #sort the merged_docs by the score in descending order
    merged_docs = sorted(merged_docs, key=lambda x: x.metadata.get('score', 0), reverse=True)
    # leave the top 10 documents with the highest score
    merged_docs = merged_docs[:max_docs]
    logger.info("After sorting and limiting to %d: %d docs", max_docs, len(merged_docs))

    return merged_docs


 

async def build_retrieval_query(
    marketing_text: str,
    backgrounds: List[str],
    company_details: Optional[CompanyDetails]
) -> str:
    """
    Build an optimized retrieval query using LLM for vector database search.

    Args:
        marketing_text: The user's marketing text
        backgrounds: List of background topics

    Returns:
        str: The optimized retrieval query
    """
    logger.info("========Step 1. Building optimized retrieval query for vector DB===========")
    backgrounds_str = ", ".join(backgrounds) if backgrounds else ""

    # Ensure marketing_text and backgrounds_str are strings and not None
    marketing_text = marketing_text or ""
    backgrounds_str = backgrounds_str or ""
    
    # Extract company context from CompanyDetails object
    if company_details:
        company_context = {
            'company_name': company_details.company_context.company_name,
            'company_domain': company_details.company_context.company_domain,
            'self_described_positioning': company_details.company_context.self_described_positioning,
            'product_surface_names': company_details.company_context.product_surface_names,
            'typical_use_cases': company_details.company_context.typical_use_cases,
            'known_competitors': company_details.company_context.known_competitors,
            'target_audience': company_details.company_context.target_audience,
            'operational_pains': company_details.company_context.operational_pains,
        }
    else:
        company_context = {}


    company_value_proposition = ""# company_context.get('company_value_proposition', '')
    company_domain =  company_context.get('company_domain', '')

    retrieval_prompt = VECTOR_DB_RETREIVAL_PROMPT.format(
        user_provided_text=marketing_text,
        backgrounds=backgrounds_str,
        company_value_proposition=company_value_proposition,
        company_domain=company_domain
    )

    retrieval_query = marketing_text
    try:
        openai_api_key = settings.DEEPINFRA_API_KEY
        base_url = settings.DEEPINFRA_API_BASE_URL
        retrieval_llm = ChatOpenAI(
            model_name="deepseek-ai/DeepSeek-V3.2", #"gpt-5",
            openai_api_key=openai_api_key,
            base_url=base_url,
        )
        rq_messages = [HumanMessage(content=retrieval_prompt)]
        rq_response = await retrieval_llm.ainvoke(rq_messages)
        retrieval_query = (rq_response.content or marketing_text).strip()

    except Exception as e:
        logger.warning(
            f"⚠ Error building retrieval query, falling back to full context: "
            f"{type(e).__name__}: {str(e)}"
        )
    logger.info(f"✓ Retrieval query built")
    logger.info("---------------------------------------------------------------------------------")
    query_lines = retrieval_query.split("\n")
    for line in query_lines:
        logger.info(f"{line}")
    logger.info("=================================================================================")
    return retrieval_query, retrieval_prompt


async def retrieve_rag_documents(retrieval_query: str, company_enumerations: List[str],collection_name: str, company_name: str) -> tuple[List[Any], List[Any]]:
    """
    Retrieve relevant documents from vector database using the retrieval query.

    Args:
        retrieval_query: The optimized retrieval query

    Returns:
        tuple: (external_docs, retrieved_docs)
    """
    logger.info("============== Step 2. Retrieving RAG documents from vector store ================")
    external_docs: list[Any] = []
    combined_docs: list[Any] = []

    # External vector search (e.g., YouTube/Reddit/Podcasts)
    try:
        # chunk retrieval query using sentence chunking
        reddit_docs = []
        youtube_docs = []
        podcast_docs = []

        # seperate the retreival query into lines and then check if they are longer than 100 tokens
        # if they are, then chunk them into smaller pieces
        # if they are not, then add them to the retrieval_query_chunks
        retrieval_query_chunks = []
        for line in retrieval_query.split("\n"):
            if count_tokens(line) > 100:
                retrieval_query_chunks.extend(vector_store.chunking(line))
            else:
                retrieval_query_chunks.append(line) 

        for chunk in retrieval_query_chunks:
            logger.info(f"-------------------Searching for chunk------------------------")
            logger.info(f"{chunk}")
            logger.info(f"--------------------------------------------------------------")
            reddit_docs.extend(vector_store.search_reddit_posts(chunk, k=10, company_enumerations=company_enumerations, collection_name=collection_name, company_name=company_name))
            youtube_docs.extend(vector_store.search_youtube_summaries(chunk, k=3, company_enumerations=company_enumerations, collection_name=collection_name, company_name=company_name))
            podcast_docs.extend(vector_store.search_podcast_summaries(chunk, k=3, company_enumerations=company_enumerations, collection_name=collection_name, company_name=company_name))


 
        # For Reddit, use post_id if available, otherwise fall back to url
        # Check if post_id exists in any doc
        use_post_id = any(hasattr(doc, 'metadata') and doc.metadata.get('post_id') for doc in reddit_docs[:5]) if reddit_docs else False
        merger_field = "post_id" if use_post_id else "url"

        reddit_filtered_docs = merge_and_filter_duplicate_documents(reddit_docs, merger_field, 10)    #extract a vector of json from the reddit_docs
        youtube_filtered_docs = merge_and_filter_duplicate_documents(youtube_docs, "url",3)    #extract a vector of json from the youtube_docs
        podcast_filtered_docs = merge_and_filter_duplicate_documents(podcast_docs, "episode_url",3)    #extract a vector of json from the podcast_docs


        combined_docs = reddit_filtered_docs + youtube_filtered_docs + podcast_filtered_docs
        combined_docs = sorted(combined_docs, key=lambda x: x.metadata.get('score', 0), reverse=True)
        
        for doc in combined_docs:
            doc_type = doc.metadata.get('doc_type', '')
            doc_url = doc.metadata.get('url', '')  # All docs have 'url' field set appropriately
            thread_url = ""
            video_url = ""
            episode_url = ""

            if doc_type == "reddit_post":
                source = "reddit"
                url = doc_url
                thread_url = doc_url  # For frontend compatibility
            elif doc_type == "yt_summary":
                source = "youtube"
                # For YouTube, get video_url from metadata (prefer video_url over url)
                # The url field in metadata should contain the video_url from the payload
                # Use None as default to properly check for existence
                video_url = doc.metadata.get('video_url') or doc.metadata.get('url') or doc_url or ''
                if not video_url:
                    logger.warning(f"YouTube document missing video_url. Metadata keys: {list(doc.metadata.keys())}, url field: {doc.metadata.get('url')}, video_url field: {doc.metadata.get('video_url')}, doc_url: {doc_url}")
                else:
                    # Fix timestamp format in video_url if needed
                    # YouTube expects &t=SECONDSs format, not &t=00:00:23s
                    import re
                    # Check if URL has timestamp in wrong format (time format like 00:00:23)
                    time_format_match = re.search(r'[?&]t=(\d{1,2}):(\d{2}):(\d{2})s?', video_url)
                    if time_format_match:
                        # Convert HH:MM:SS to seconds
                        hours, minutes, seconds = map(int, time_format_match.groups())
                        total_seconds = hours * 3600 + minutes * 60 + seconds
                        # Replace the timestamp in the URL
                        video_url = re.sub(r'[?&]t=\d{1,2}:\d{2}:\d{2}s?', f'&t={total_seconds}', video_url)
                        logger.info(f"Fixed YouTube timestamp format in video_url: {video_url}")
                    # Also check for MM:SS format
                    mmss_format_match = re.search(r'[?&]t=(\d{1,2}):(\d{2})s?', video_url)
                    if mmss_format_match and not time_format_match:
                        minutes, seconds = map(int, mmss_format_match.groups())
                        total_seconds = minutes * 60 + seconds
                        video_url = re.sub(r'[?&]t=\d{1,2}:\d{2}s?', f'&t={total_seconds}', video_url)
                        logger.info(f"Fixed YouTube timestamp format (MM:SS) in video_url: {video_url}")
                url = video_url  # Also set url for backward compatibility
            elif doc_type == "podcast_summary":
                source = "podcast"
                # Podcasts use episode_url, not url
                episode_url = doc.metadata.get('episode_url', '')
                
                # Normalize citation_start_time to seconds if it's in time format
                citation_start_time_raw = doc.metadata.get('citation_start_time')
                if citation_start_time_raw and isinstance(citation_start_time_raw, str):
                    # Handle time format like "00:00:23" or "00:23" (HH:MM:SS or MM:SS)
                    if ':' in citation_start_time_raw:
                        parts = citation_start_time_raw.split(':')
                        try:
                            if len(parts) == 3:  # HH:MM:SS format
                                hours, minutes, seconds = map(int, parts)
                                citation_start_time = hours * 3600 + minutes * 60 + seconds
                            elif len(parts) == 2:  # MM:SS format
                                minutes, seconds = map(int, parts)
                                citation_start_time = minutes * 60 + seconds
                            else:
                                citation_start_time = float(citation_start_time_raw)
                        except (ValueError, AttributeError):
                            citation_start_time = citation_start_time_raw
                    else:
                        try:
                            citation_start_time = float(citation_start_time_raw)
                        except (ValueError, TypeError):
                            citation_start_time = citation_start_time_raw
                elif isinstance(citation_start_time_raw, (int, float)):
                    citation_start_time = citation_start_time_raw
                else:
                    citation_start_time = citation_start_time_raw
                
                url = episode_url  # Use episode_url as the main url
            else:
                source = "unknown"
                url = doc_url
            title = doc.metadata.get('title', '')
            score = doc.metadata.get('score', 0)
            citation = doc.metadata.get('citation', '')
            citation_start_time = doc.metadata.get('citation_start_time')
            mp3_url = doc.metadata.get('mp3_url') or doc.metadata.get('mp3_link')
            # Ensure these fields are always lists/arrays, not strings
            key_issues = doc.metadata.get('key_issues', [])
            if not isinstance(key_issues, list):
                key_issues = [key_issues] if key_issues and str(key_issues).strip() else []
            pain_phrases = doc.metadata.get('pain_phrases', [])
            if not isinstance(pain_phrases, list):
                pain_phrases = [pain_phrases] if pain_phrases and str(pain_phrases).strip() else []
            emotional_triggers = doc.metadata.get('emotional_triggers', [])
            if not isinstance(emotional_triggers, list):
                emotional_triggers = [emotional_triggers] if emotional_triggers and str(emotional_triggers).strip() else []
            buyer_language = doc.metadata.get('buyer_language', [])
            if not isinstance(buyer_language, list):
                buyer_language = [buyer_language] if buyer_language and str(buyer_language).strip() else []
            implicit_risks = doc.metadata.get('implicit_risks', [])
            if not isinstance(implicit_risks, list):
                implicit_risks = [implicit_risks] if implicit_risks and str(implicit_risks).strip() else []
            # Create comprehensive context excerpt from RAG metadata
            context_parts = []
            if key_issues and (isinstance(key_issues, list) and key_issues or str(key_issues).strip()):
                context_parts.append(f"Key Issues: {', '.join(key_issues) if isinstance(key_issues, list) else str(key_issues)}")
            if pain_phrases and (isinstance(pain_phrases, list) and pain_phrases or str(pain_phrases).strip()):
                context_parts.append(f"Pain Phrases: {', '.join(pain_phrases) if isinstance(pain_phrases, list) else str(pain_phrases)}")
            if emotional_triggers and (isinstance(emotional_triggers, list) and emotional_triggers or str(emotional_triggers).strip()):
                context_parts.append(f"Emotional Triggers: {', '.join(emotional_triggers) if isinstance(emotional_triggers, list) else str(emotional_triggers)}")
            if buyer_language and (isinstance(buyer_language, list) and buyer_language or str(buyer_language).strip()):
                context_parts.append(f"Buyer Language: {', '.join(buyer_language) if isinstance(buyer_language, list) else str(buyer_language)}")
            if implicit_risks and (isinstance(implicit_risks, list) and implicit_risks or str(implicit_risks).strip()):
                context_parts.append(f"Implicit Risks: {', '.join(implicit_risks) if isinstance(implicit_risks, list) else str(implicit_risks)}")

            context_excerpt = " | ".join(context_parts) if context_parts else (citation[:500] if citation else "No context available")

            # Create individual source objects for each retrieved document
            source_obj = {
                "filename": title ,
                "snippet": context_excerpt,
                "text": context_excerpt,  # Set text field to context_excerpt so frontend can parse it consistently
                "score": score,
                "source": source,
                "doc_type": doc_type,
                "citation": citation,
                "title": title,
                "key_issues": key_issues,
                "pain_phrases": pain_phrases,
                "emotional_triggers": emotional_triggers,
                "buyer_language": buyer_language,
                "implicit_risks": implicit_risks
            }

            # Add type-specific URL fields for frontend compatibility
            if doc_type == "reddit_post":
                source_obj["url"] = url
                source_obj["thread_url"] = thread_url
            elif doc_type == "yt_summary":
                if video_url:
                    source_obj["video_url"] = video_url
                else:
                    logger.warning(f"YouTube source missing video_url for title: {title}, doc_type: {doc_type}, metadata keys: {list(doc.metadata.keys())}")
                source_obj["citation_start_time"] = citation_start_time
            elif doc_type == "podcast_summary":
                source_obj["episode_url"] = episode_url
                source_obj["citation_start_time"] = citation_start_time
                source_obj["mp3_url"] = _safe_str(mp3_url)
            else:
                source_obj["url"] = url
            external_docs.append(source_obj)
            #logger.info(f"Reddit filtered docs JSON: {reddit_filtered_docs_json_text}")


    except Exception as e:
        logger.warning(f"⚠ Error retrieving external reference documents: {type(e).__name__}: {str(e)}")
        external_docs = []
        combined_docs = []

    logger.info(f"✓ RAG documents retrieved: {len(combined_docs)} documents")
    logger.info("---------------------------------------------------------------------------------")
    logger.debug("=================================================================================")
    logger.debug(f"{combined_docs}")
    logger.debug("=================================================================================")

    # Deduplicate documents by title before reranking
    logger.info("Deduplicating documents by title...")
    seen_titles = {}
    deduplicated_docs = []
    
    for doc in combined_docs:
        # Get title from metadata
        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
        title = metadata.get('title', '')
        
        # If no title, use content hash as fallback
        if not title:
            content = doc.page_content if hasattr(doc, 'page_content') else ''
            title = f"_content_hash_{hash(content)}"
        
        # Keep document with highest score if duplicate title found
        if title not in seen_titles:
            seen_titles[title] = doc
            deduplicated_docs.append(doc)
        else:
            # Compare scores and keep the one with higher score
            existing_score = seen_titles[title].metadata.get('score', 0) if hasattr(seen_titles[title], 'metadata') else 0
            current_score = metadata.get('score', 0)
            
            if current_score > existing_score:
                # Replace with higher-scored document
                deduplicated_docs.remove(seen_titles[title])
                seen_titles[title] = doc
                deduplicated_docs.append(doc)
    
    logger.info(f"✓ Deduplicated: {len(combined_docs)} → {len(deduplicated_docs)} documents ({len(combined_docs) - len(deduplicated_docs)} duplicates removed)")
    combined_docs = deduplicated_docs

    return external_docs, combined_docs


async def rerank_and_filter_documents(
    retrieved_docs: List[Any],
    retrieval_queries: str,
    company_name: str | None = None,
    company_domain: str | None = None,
    known_competitors: List[str] | None = None
) -> tuple[List[Any], str, str]:
    """
    Rerank and filter retrieved documents using LLM to keep only relevant ones.
    
    Args:
        retrieved_docs: List of retrieved documents from RAG
        retrieval_queries: The queries sent to RAG
        company_name: Company name
        company_domain: Company domain
        known_competitors: List of known competitors
    
    Returns:
        tuple: (filtered_docs, rerank_prompt, rerank_result)
            - filtered_docs: List of filtered documents (subset of retrieved_docs)
            - rerank_prompt: The prompt sent to reranking LLM
            - rerank_result: The raw result from reranking LLM
    """
    from .dynamodb_prompts import get_latest_prompt_template
    
    logger.info("============== Step 2.5. Reranking and filtering RAG documents ================")
    
    if not retrieved_docs:
        logger.warning("No documents to rerank, returning empty list")
        return [], "", ""
    
    try:
        # Get the reranking template from DynamoDB
        rerank_template_data = get_latest_prompt_template('results_rerank_and_filter_template')
        
        if not rerank_template_data:
            logger.warning("Reranking template not found in DynamoDB, skipping reranking and returning all documents")
            return retrieved_docs, "", ""
        
        rerank_template = rerank_template_data['template_body']
        logger.info(f"✓ Loaded results_rerank_and_filter_template from DynamoDB (edited by: {rerank_template_data.get('edited_by_sub', 'unknown')})")
        
        # Format retrieved docs as JSON string (candidates)
        # Retrieved docs are now cleaned dicts with only relevant fields
        candidates = []
        for i, doc in enumerate(retrieved_docs, 1):
            if isinstance(doc, dict):
                # Already cleaned format - just add ID
                doc_with_id = {'id': i, **doc}
                candidates.append(doc_with_id)
            else:
                # Fallback for full document objects (shouldn't happen after cleaning)
                doc_dict = {
                    'id': i,
                    'content': getattr(doc, 'page_content', ''),
                    'metadata': getattr(doc, 'metadata', {})
                }
                candidates.append(doc_dict)
        
        candidates_json = json.dumps(candidates, indent=2)
        
        logger.info(f"Reranking {len(candidates)} documents...")
        logger.info(f"Input size: {len(candidates_json)} chars, {count_tokens(candidates_json)} tokens")
        
        # Prepare template variables
        known_competitors_str = ", ".join(known_competitors) if known_competitors else ""
        template_vars = {
            'company_name': company_name or '',
            'company_domain': company_domain or '',
            'knwn_compatitors': known_competitors_str,  # Note: keeping the typo from user's spec
            'known_competitors': known_competitors_str,  # Also provide correct spelling
            'retrieval_queries': retrieval_queries or '',
            'candidates': candidates_json
        }
        
        # Format the prompt with safe substitution
        from string import Template
        import re
        try:
            rerank_prompt = rerank_template.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Template has undefined variable: {e}. Using safe substitution.")
            template_str = re.sub(r'\{(\w+)\}', r'$\1', rerank_template)
            template_obj = Template(template_str)
            rerank_prompt = template_obj.safe_substitute(**template_vars)
        
        # Run LLM to filter documents
        llm = ChatOpenAI(
            model_name="deepseek-ai/DeepSeek-V3",
            openai_api_key=settings.DEEPINFRA_API_KEY,
            base_url=settings.DEEPINFRA_API_BASE_URL,
            temperature=0.3,  # Lower temperature for more focused filtering
        )
        
        logger.info("Running reranking model...")
        messages = [HumanMessage(content=rerank_prompt)]
        response = await llm.ainvoke(messages)
        filtered_result = response.content
        
        logger.info(f"✓ Reranking completed: {len(filtered_result)} chars")
        
        # Parse the filtered results - expect JSON array of IDs or full documents
        try:
            # Try to parse as JSON
            filtered_data = json.loads(filtered_result)
            
            # Handle different response formats
            if isinstance(filtered_data, list):
                # If it's a list of IDs (numbers)
                if filtered_data and isinstance(filtered_data[0], (int, str)):
                    filtered_ids = [int(id_val) if isinstance(id_val, str) and id_val.isdigit() else id_val for id_val in filtered_data]
                    filtered_docs = [doc for i, doc in enumerate(retrieved_docs, 1) if i in filtered_ids]
                    logger.info(f"✓ Filtered to {len(filtered_docs)}/{len(retrieved_docs)} documents by ID")
                    return filtered_docs, rerank_prompt, filtered_result
                # If it's a list of document objects
                elif filtered_data and isinstance(filtered_data[0], dict):
                    # Extract IDs from document objects - try multiple field names
                    filtered_ids = []
                    for doc in filtered_data:
                        # Try 'id', 'insight_id', or any field ending with '_id'
                        doc_id = doc.get('id') or doc.get('insight_id')
                        if not doc_id:
                            # Try to find any field ending with '_id'
                            for key, value in doc.items():
                                if key.endswith('_id') and isinstance(value, (int, str)):
                                    doc_id = value
                                    break
                        if doc_id:
                            filtered_ids.append(int(doc_id) if isinstance(doc_id, str) and doc_id.isdigit() else doc_id)
                    
                    if filtered_ids:
                        filtered_docs = [doc for i, doc in enumerate(retrieved_docs, 1) if i in filtered_ids]
                        logger.info(f"✓ Filtered to {len(filtered_docs)}/{len(retrieved_docs)} documents by insight_id/id")
                        return filtered_docs, rerank_prompt, filtered_result
                    else:
                        logger.warning("No valid IDs found in document objects")
                        return retrieved_docs, rerank_prompt, filtered_result
            elif isinstance(filtered_data, dict):
                # If it's a dict with a key containing a list of documents/insights
                logger.info("DEBUG: Checking for nested list in dict...")
                docs_list = (filtered_data.get('documents') or 
                            filtered_data.get('filtered_results') or 
                            filtered_data.get('results') or
                            filtered_data.get('re_ranked_results') or  # Add support for re_ranked_results
                            filtered_data.get('reranked_results') or   # Also support without underscore
                            filtered_data.get('insights') or
                            filtered_data.get('selected_insights'))
                
                logger.info(f"DEBUG: docs_list found: {docs_list is not None}, is list: {isinstance(docs_list, list) if docs_list else False}")
                
                if docs_list and isinstance(docs_list, list):
                    # Extract IDs from the nested list
                    logger.info(f"Found nested list with {len(docs_list)} items")
                    filtered_ids = []
                    for doc in docs_list:
                        if isinstance(doc, dict):
                            doc_id = doc.get('id') or doc.get('insight_id')
                            if not doc_id:
                                for key, value in doc.items():
                                    if key.endswith('_id') and isinstance(value, (int, str)):
                                        doc_id = value
                                        break
                            if doc_id:
                                filtered_ids.append(int(doc_id) if isinstance(doc_id, str) and doc_id.isdigit() else doc_id)
                        elif isinstance(doc, (int, str)):
                            filtered_ids.append(int(doc) if isinstance(doc, str) and doc.isdigit() else doc)
                    
                    logger.info(f"Extracted IDs: {filtered_ids}")
                    
                    if filtered_ids:
                        filtered_docs = [doc for i, doc in enumerate(retrieved_docs, 1) if i in filtered_ids]
                        logger.info(f"✓ Filtered to {len(filtered_docs)}/{len(retrieved_docs)} documents from nested object")
                        if filtered_docs:
                            return filtered_docs, rerank_prompt, filtered_result
                        else:
                            logger.warning(f"No documents matched the extracted IDs {filtered_ids[:10]}... (candidate IDs are 1-{len(retrieved_docs)})")
                            return retrieved_docs, rerank_prompt, filtered_result
                    else:
                        logger.warning("No IDs could be extracted from nested list")
                        return retrieved_docs, rerank_prompt, filtered_result
        
        except json.JSONDecodeError:
            # If not JSON, try to extract IDs from text
            logger.warning("Reranking result is not valid JSON, attempting to extract IDs from text")
            id_pattern = r'\b\d+\b'
            found_ids = [int(id_str) for id_str in re.findall(id_pattern, filtered_result)]
            if found_ids:
                filtered_docs = [doc for i, doc in enumerate(retrieved_docs, 1) if i in found_ids]
                logger.info(f"✓ Extracted {len(filtered_docs)}/{len(retrieved_docs)} documents from text")
                return filtered_docs, rerank_prompt, filtered_result
        
        # If we couldn't parse the result, return all documents
        logger.warning("Could not parse reranking result, returning all documents")
        return retrieved_docs, rerank_prompt, filtered_result
        
    except Exception as e:
        logger.error(f"✗ Error during reranking: {type(e).__name__}: {str(e)}", exc_info=True)
        logger.warning("Returning all documents due to reranking error")
        return retrieved_docs, "", str(e)


async def rerank_and_filter_battle_cards(
    retrieved_docs: List[Any],
    company_name: str | None = None,
    company_domain: str | None = None,
    known_competitors: List[str] | None = None,
    target_competitor: str | None = None,
    icp: str | None = None
) -> tuple[List[Any], str, str]:
    """
    Rerank and filter battle cards documents using LLM with battle-cards-specific template.
    
    Args:
        retrieved_docs: List of retrieved documents from RAG
        company_name: Company name
        company_domain: Company domain
        known_competitors: List of known competitors
        target_competitor: The specific competitor selected for battle cards
        icp: Target audience/ICP
    
    Returns:
        tuple: (filtered_docs, rerank_prompt, rerank_result)
    """
    from .dynamodb_prompts import get_latest_prompt_template
    
    logger.info("============== Step 2.5. Reranking and filtering battle cards documents ================")
    
    if not retrieved_docs:
        logger.warning("No documents to rerank, returning empty list")
        return [], "", ""
    
    try:
        # Get the battle cards specific reranking template from DynamoDB
        rerank_template_data = get_latest_prompt_template('results_rerank_and_filter_battle_cards_template')
        
        if not rerank_template_data:
            logger.warning("Battle cards reranking template not found in DynamoDB, skipping reranking and returning all documents")
            return retrieved_docs, "", ""
        
        rerank_template = rerank_template_data['template_body']
        logger.info(f"✓ Loaded results_rerank_and_filter_battle_cards_template from DynamoDB (edited by: {rerank_template_data.get('edited_by_sub', 'unknown')})")
        
        # Format retrieved docs as JSON string (candidates)
        # Retrieved docs are now cleaned dicts with only relevant fields
        candidates = []
        for i, doc in enumerate(retrieved_docs, 1):
            if isinstance(doc, dict):
                # Already cleaned format - just add ID
                doc_with_id = {'id': i, **doc}
                candidates.append(doc_with_id)
            else:
                # Fallback for full document objects (shouldn't happen after cleaning)
                doc_dict = {
                    'id': i,
                    'content': getattr(doc, 'page_content', ''),
                    'metadata': getattr(doc, 'metadata', {})
                }
                candidates.append(doc_dict)
        
        candidates_json = json.dumps(candidates, indent=2)
        
        logger.info(f"Reranking {len(candidates)} battle cards documents...")
        logger.info(f"Input size: {len(candidates_json)} chars, {count_tokens(candidates_json)} tokens")
        
        # Prepare battle-cards-specific template variables
        known_competitors_str = ", ".join(known_competitors) if known_competitors else ""
        template_vars = {
            'company_name': company_name or '',
            'company_domain': company_domain or '',
            'knwn_compatitors': known_competitors_str,  # Note: keeping the typo from user's spec
            'known_competitors': known_competitors_str,  # Also provide correct spelling
            'target_competitor': target_competitor or '',
            'icp': icp or '',
            'target_audience': icp or '',  # Alias
            'candidates': candidates_json
        }
        
        # Format the prompt with safe substitution
        from string import Template
        import re
        try:
            rerank_prompt = rerank_template.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Template has undefined variable: {e}. Using safe substitution.")
            template_str = re.sub(r'\{(\w+)\}', r'$\1', rerank_template)
            template_obj = Template(template_str)
            rerank_prompt = template_obj.safe_substitute(**template_vars)
        
        # Run LLM to filter documents
        llm = ChatOpenAI(
            model_name="deepseek-ai/DeepSeek-V3",
            openai_api_key=settings.DEEPINFRA_API_KEY,
            base_url=settings.DEEPINFRA_API_BASE_URL,
            temperature=0.3,  # Lower temperature for more focused filtering
        )
        
        logger.info("Running battle cards reranking model...")
        messages = [HumanMessage(content=rerank_prompt)]
        response = await llm.ainvoke(messages)
        filtered_result = response.content
        
        logger.info(f"✓ Battle cards reranking completed: {len(filtered_result)} chars")

        logger.info(f"---------------------------------------------------------------------------------")
        logger.info(f"Battle cards reranking result: ")
        logger.info(f"{filtered_result}")
        logger.info(f"---------------------------------------------------------------------------------")
        
        # Parse the filtered results - expect JSON array of IDs or full documents
        try:
            # Try to parse as JSON
            filtered_data = json.loads(filtered_result)
            
            logger.info(f"DEBUG: Parsed JSON type: {type(filtered_data).__name__}")
            if isinstance(filtered_data, dict):
                logger.info(f"DEBUG: Dict keys: {list(filtered_data.keys())}")
            elif isinstance(filtered_data, list):
                logger.info(f"DEBUG: List length: {len(filtered_data)}, first item type: {type(filtered_data[0]).__name__ if filtered_data else 'empty'}")
            
            # Handle different response formats
            if isinstance(filtered_data, list):
                # If it's a list of IDs (numbers)
                if filtered_data and isinstance(filtered_data[0], (int, str)):
                    filtered_ids = [int(id_val) if isinstance(id_val, str) and id_val.isdigit() else id_val for id_val in filtered_data]
                    filtered_docs = [doc for i, doc in enumerate(retrieved_docs, 1) if i in filtered_ids]
                    logger.info(f"✓ Filtered to {len(filtered_docs)}/{len(retrieved_docs)} battle cards documents by ID")
                    return filtered_docs, rerank_prompt, filtered_result
                # If it's a list of document objects
                elif filtered_data and isinstance(filtered_data[0], dict):
                    # Extract IDs from document objects - try multiple field names
                    filtered_ids = []
                    for doc in filtered_data:
                        # Try 'id', 'insight_id', or any field ending with '_id'
                        doc_id = doc.get('id') or doc.get('insight_id')
                        if not doc_id:
                            # Try to find any field ending with '_id'
                            for key, value in doc.items():
                                if key.endswith('_id') and isinstance(value, (int, str)):
                                    doc_id = value
                                    break
                        if doc_id:
                            filtered_ids.append(int(doc_id) if isinstance(doc_id, str) and doc_id.isdigit() else doc_id)
                    
                    if filtered_ids:
                        filtered_docs = [doc for i, doc in enumerate(retrieved_docs, 1) if i in filtered_ids]
                        logger.info(f"✓ Filtered to {len(filtered_docs)}/{len(retrieved_docs)} battle cards documents by insight_id/id")
                        return filtered_docs, rerank_prompt, filtered_result
                    else:
                        logger.warning("No valid IDs found in document objects")
                        return retrieved_docs, rerank_prompt, filtered_result
            elif isinstance(filtered_data, dict):
                # If it's a dict with a key containing a list of documents/insights
                logger.info("DEBUG: Checking for nested list in dict...")
                docs_list = (filtered_data.get('documents') or 
                            filtered_data.get('filtered_results') or 
                            filtered_data.get('results') or
                            filtered_data.get('re_ranked_results') or  # Add support for re_ranked_results
                            filtered_data.get('reranked_results') or   # Also support without underscore
                            filtered_data.get('insights') or
                            filtered_data.get('selected_insights'))
                
                logger.info(f"DEBUG: docs_list found: {docs_list is not None}, is list: {isinstance(docs_list, list) if docs_list else False}")
                
                if docs_list and isinstance(docs_list, list):
                    # Extract IDs from the nested list
                    logger.info(f"Found nested list with {len(docs_list)} items")
                    filtered_ids = []
                    for doc in docs_list:
                        if isinstance(doc, dict):
                            doc_id = doc.get('id') or doc.get('insight_id')
                            if not doc_id:
                                for key, value in doc.items():
                                    if key.endswith('_id') and isinstance(value, (int, str)):
                                        doc_id = value
                                        break
                            if doc_id:
                                filtered_ids.append(int(doc_id) if isinstance(doc_id, str) and doc_id.isdigit() else doc_id)
                        elif isinstance(doc, (int, str)):
                            filtered_ids.append(int(doc) if isinstance(doc, str) and doc.isdigit() else doc)
                    
                    logger.info(f"Extracted IDs: {filtered_ids}")
                    
                    if filtered_ids:
                        filtered_docs = [doc for i, doc in enumerate(retrieved_docs, 1) if i in filtered_ids]
                        logger.info(f"✓ Filtered to {len(filtered_docs)}/{len(retrieved_docs)} battle cards documents from nested object")
                        if filtered_docs:
                            return filtered_docs, rerank_prompt, filtered_result
                        else:
                            logger.warning(f"No documents matched the extracted IDs {filtered_ids[:10]}... (candidate IDs are 1-{len(retrieved_docs)})")
                            return retrieved_docs, rerank_prompt, filtered_result
                    else:
                        logger.warning("No IDs could be extracted from nested list")
                        return retrieved_docs, rerank_prompt, filtered_result
        
        except json.JSONDecodeError:
            # If not JSON, try to extract IDs from text
            logger.warning("Battle cards reranking result is not valid JSON, attempting to extract IDs from text")
            id_pattern = r'\b\d+\b'
            found_ids = [int(id_str) for id_str in re.findall(id_pattern, filtered_result)]
            if found_ids:
                filtered_docs = [doc for i, doc in enumerate(retrieved_docs, 1) if i in found_ids]
                logger.info(f"✓ Extracted {len(filtered_docs)}/{len(retrieved_docs)} battle cards documents from text")
                return filtered_docs, rerank_prompt, filtered_result
        
        # If we couldn't parse the result, return all documents
        logger.warning("Could not parse battle cards reranking result, returning all documents")
        return retrieved_docs, rerank_prompt, filtered_result
        
    except Exception as e:
        logger.error(f"✗ Error during battle cards reranking: {type(e).__name__}: {str(e)}", exc_info=True)
        logger.warning("Returning all documents due to battle cards reranking error")
        return retrieved_docs, "", str(e)


def clean_documents_for_reranking(retrieved_docs: List[Any]) -> List[Dict[str, Any]]:
    """
    Clean documents to only include relevant marketing fields before reranking.
    This reduces token usage significantly by removing unnecessary metadata.
    
    Args:
        retrieved_docs: List of retrieved document objects with full metadata
    
    Returns:
        List of cleaned document dictionaries with only essential fields
    """
    logger.info("Cleaning documents: extracting only relevant fields for reranking...")
    
    cleaned_docs = []
    for doc in retrieved_docs:
        if hasattr(doc, 'metadata') and doc.metadata:
            # Extract only the fields we actually use
            cleaned_doc = {
                "title": doc.metadata.get('title', ''),
                "citation": doc.metadata.get('citation', ''),
                "key_issues": doc.metadata.get('key_issues', ''),
                "pain_phrases": doc.metadata.get('pain_phrases', ''),
                "emotional_triggers": doc.metadata.get('emotional_triggers', ''),
                "buyer_language": doc.metadata.get('buyer_language', ''),
                "implicit_risks": doc.metadata.get('implicit_risks', ''),
                "score": doc.metadata.get('score', 0)
            }
            cleaned_docs.append(cleaned_doc)
        elif isinstance(doc, dict):
            # Handle dict format (already cleaned or from battle cards)
            metadata = doc.get('metadata', {})
            cleaned_doc = {
                "title": metadata.get('title', ''),
                "citation": metadata.get('citation', ''),
                "key_issues": metadata.get('key_issues', ''),
                "pain_phrases": metadata.get('pain_phrases', ''),
                "emotional_triggers": metadata.get('emotional_triggers', ''),
                "buyer_language": metadata.get('buyer_language', ''),
                "implicit_risks": metadata.get('implicit_risks', ''),
                "score": metadata.get('score', 0)
            }
            cleaned_docs.append(cleaned_doc)
    
    # Calculate token savings
    original_size = sum(len(str(doc)) for doc in retrieved_docs)
    cleaned_size = sum(len(str(doc)) for doc in cleaned_docs)
    if original_size > 0:
        logger.info(f"✓ Cleaned {len(cleaned_docs)} documents: {original_size} → {cleaned_size} chars ({100 * (1 - cleaned_size/original_size):.1f}% reduction)")
    else:
        logger.info(f"✓ Cleaned {len(cleaned_docs)} documents: 0 → {cleaned_size} chars (0% reduction)")
    
    return cleaned_docs


def build_vector_search_context(retrieved_docs: List[Any]) -> str:
    """
    Build the vector search context JSON for the LLM prompt.

    Args:
        retrieved_docs: List of retrieved document objects (can be cleaned dicts or full docs)

    Returns:
        str: JSON string containing vector search context
    """
    logger.info("================== Step 3. Building vector search context ====================")

    # If already cleaned (dict format), use directly
    if retrieved_docs and isinstance(retrieved_docs[0], dict):
        vector_search_context_text = json.dumps(retrieved_docs, indent=4)
    else:
        # Extract fields from full document objects
        vector_search_context = []

    for doc in retrieved_docs:
        if hasattr(doc, 'metadata') and doc.metadata:
            doc_context = {
                "title": doc.metadata.get('title', ''),
                "citation": doc.metadata.get('citation', ''),
                "key_issues": doc.metadata.get('key_issues', ''),
                "pain_phrases": doc.metadata.get('pain_phrases', ''),
                "emotional_triggers": doc.metadata.get('emotional_triggers', ''),
                "buyer_language": doc.metadata.get('buyer_language', ''),
                "implicit_risks": doc.metadata.get('implicit_risks', ''),
                "score": doc.metadata.get('score', 0)
            }
            vector_search_context.append(doc_context)
    vector_search_context_text = json.dumps(vector_search_context, indent=4)

    logger.info(
        f"✓ Vector search context built: {len(vector_search_context_text)} chars from {len(retrieved_docs)} sources"
    )

    return vector_search_context_text


def build_final_prompt(
    template: str,
    backgrounds_str: str,
    marketing_text: str,
    vector_search_context: str,
    asset_type: str | None,
    icp: str | None,
    company_name: str | None,
    company_details: Optional[CompanyDetails] = None
) -> str:
    """
    Build the final prompt by replacing template variables.

    Args:
        template: The prompt template
        backgrounds_str: Comma-separated backgrounds
        marketing_text: User's marketing text
        vector_search_context: JSON context from retrieved docs
        asset_type: Selected asset type
        icp: Ideal customer profile

    Returns:
        str: The final prompt with all variables replaced
    """
    logger.info("===================== Step 4. Building final prompt =========================")

    # Get asset type rules (reload if asset type not found)
    global asset_type_rules
    asset_type_instructions = ""
    
    if asset_type:
        asset_type_instructions = asset_type_rules.get(asset_type, "")
        
        # If asset type not found, try reloading from DynamoDB (in case new ones were added)
        if not asset_type_instructions:
            logger.info(f"Asset type '{asset_type}' not found, reloading rules from DynamoDB...")
            asset_type_rules = _get_asset_type_rules()
            asset_type_instructions = asset_type_rules.get(asset_type, asset_type)
            
            if asset_type_instructions == asset_type:
                logger.warning(f"⚠ Asset type '{asset_type}' still not found after reload, using asset type name as fallback")
    
    # Extract company context from CompanyDetails object
    if company_details:
        company_context = {
            'company_name': company_details.company_context.company_name,
            'company_domain': company_details.company_context.company_domain,
            'self_described_positioning': company_details.company_context.self_described_positioning,
            'product_surface_names': company_details.company_context.product_surface_names,
            'typical_use_cases': company_details.company_context.typical_use_cases,
            'known_competitors': company_details.company_context.known_competitors,
            'target_audience': company_details.company_context.target_audience,
            'operational_pains': company_details.company_context.operational_pains,
        }
    else:
        company_context = {}





    # Build company_info string from CompanyDetails for the template
    company_info = ""
    company_json = {}
    if company_details:
        company_json = {
            'company_context': {
                'company_name': company_details.company_context.company_name,
                'company_domain': company_details.company_context.company_domain,
                'self_described_positioning': company_details.company_context.self_described_positioning,
                'product_surface_names': company_details.company_context.product_surface_names,
                'typical_use_cases': company_details.company_context.typical_use_cases,
                'known_competitors': company_details.company_context.known_competitors,
                'target_audience': company_details.company_context.target_audience,
                'operational_pains': company_details.company_context.operational_pains,
            },
            'usage_rules': company_details.company_context.usage_rules
        }
        company_info = json.dumps(company_json, indent=2)
    

    # Use icp value for both target_audience and icp for backward compatibility
    icp_value = icp or ''
    prompt = template.format(
        operational_pain_point=backgrounds_str,
        backgrounds=backgrounds_str,  # Alias for backgrounds placeholder
        use_cases=backgrounds_str,
        campaing_context=marketing_text,
        marketing_text=marketing_text,  # Alias for marketing_text placeholder
        context=marketing_text,
        user_provided_text=marketing_text,
        vector_search_context=vector_search_context,
        asset_type=asset_type or '',
        asset_type_instructions=asset_type_instructions,
        target_audience=icp_value,  # New format
        icp=icp_value,  # Old format for backward compatibility
        company_analysis=company_info,
        latest_anouncements=company_json.get('company_context', {}).get('latest_anouncements', ''),
        company_name=company_name,
        competition_analysis='',  # No longer used
        company_domain=company_json.get('company_context', {}).get('company_domain', ''),
        company_value_proposition=company_json.get('company_value_proposition'),
    )

    # Check for any remaining template variables
    remaining_vars = re.findall(r'\{\{.*?\}\}', prompt)
    if remaining_vars:
        logger.warning(f"⚠ Found unreplaced template variables: {remaining_vars}")
        # Log the prompt with markers around remaining variables for debugging
        for var in remaining_vars:
            prompt = prompt.replace(var, f"***UNREPLACED:{var}***")
        logger.warning(f"Prompt with unreplaced variables marked:\n{prompt}")
    else:
        logger.info("✓ All template variables successfully replaced")

    logger.info(f"✓ Prompt built: {len(prompt)} chars")
    logger.debug(f"Full prompt:\n{prompt}")

    return prompt


async def generate_llm_response(prompt: str) -> str:
    """
    Generate response from LLM using the final prompt.

    Args:
        prompt: The final prompt to send to LLM

    Returns:
        str: The refined text response from LLM
    """
    # Initialize LLM
    logger.info("===================== Step 5. Generating LLM response =========================")
    # See note above on temperature: we set temperature=1.0 explicitly
    # to comply with models that only accept the default temperature.
    #llm = ChatOpenAI(
    #    model_name="gpt-4o", #"gpt-5",
    #    openai_api_key=settings.OPENAI_API_KEY,
    #    temperature=1.0,
    #)
    llm = ChatOpenAI(
        model_name="deepseek-ai/DeepSeek-V3.2", #"gpt-5",
        openai_api_key=settings.DEEPINFRA_API_KEY,
        base_url=settings.DEEPINFRA_API_BASE_URL,
        temperature=1.0,
    )
    logger.info("✓ LLM initialized")

    # Generate response
    messages = [
        #SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ]

    try:
        response = await llm.ainvoke(messages)
        #logger.info(f"?? LLM messages: {messages}")
        refined_text = response.content if hasattr(response, 'content') else str(response)
        #logger.info(f"✓ LLM response received: {len(refined_text)} chars")
        #logger.info(f"✓ LLM response received: {refined_text}")
        #logger.debug(f"Refined text preview: {refined_text[:200]}...")
    except Exception as e:
        logger.error(f"✗ Error calling LLM: {type(e).__name__}: {str(e)}")
        raise
    logger.debug("=================================================================================")
    logger.debug(f"LLM response: {refined_text}")
    logger.debug("=================================================================================")
    logger.info("✓ Response generated")
    return refined_text

def get_company_enumerations(company_name: str) -> List[str]:
    """Get company enumerations from S3 bucket."""
    s3 = boto3.client('s3')
    key = company_name.lower()+'_enumerations.json'
    logger.info(f"Reading company enumerations from S3: {key}")
    response = s3.get_object(Bucket='ansora-company-enumerations', Key=key)
    return json.loads(response['Body'].read().decode('utf-8'))


def get_collection_name(company_details: Optional[CompanyDetails]) -> str:
    """Get collection name from CompanyDetails object, resolving all possible variations."""
            
    if not company_details:
        logger.error("Company details is empty")
        return None

    try:
        company_domain = company_details.company_context.company_domain
        # Use the vectorstore's resolve_collection_name to try all variations
        collection_name = vector_store.resolve_collection_name(company_domain, "summaries_1_0")
        logger.info(f"✓ Resolved collection name: {collection_name} for domain: {company_domain}")
        return collection_name
    except Exception as e:
        logger.error(f"Error getting collection name: {e}")
        return None

           

# Track active pipeline executions to prevent duplicates
_active_pipelines: dict[str, bool] = {}
_pipeline_lock = asyncio.Lock()

async def process_rag(
    user_id: int,
    backgrounds: List[str],
    marketing_text: str,
    asset_type: str | None = None,
    icp: str | None = None,
    template: str | None = None,
    company_name: str | None = None,
    company_details: Optional[CompanyDetails] = None,
    is_administrator: bool = False,
    request_id: str | None = None,
) -> tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], str, str]:
    """
    Process RAG pipeline and return refined text, sources, retrieved documents, final prompt, and email content.

    Returns:
        tuple: (refined_text, sources_list, retrieved_docs_list, final_prompt, email_content)
    """
    import uuid as uuid_lib
    
    # Create a unique execution key
    execution_key = f"{request_id}_{user_id}_{hash(tuple(backgrounds))}_{hash(marketing_text)}"
    
    # Use lock to make check-and-set atomic (prevent race conditions)
    async with _pipeline_lock:
        # Check if this pipeline is already running
        if execution_key in _active_pipelines:
            logger.error(f"❌ DUPLICATE EXECUTION DETECTED! Pipeline already running for key: {execution_key}. Request ID: {request_id}")
            raise RuntimeError(f"Pipeline execution already in progress for request {request_id}. This should not happen.")
        
        # Mark as active (atomic operation)
        _active_pipelines[execution_key] = True
        logger.info(f"✓ Lock acquired and pipeline marked as active: {execution_key[:20]}")
    
    try:
        pipeline_id = str(uuid_lib.uuid4())[:8]
        logger.info(f"Generated pipeline_id: {pipeline_id} for request {request_id}")
        request_id_str = f"[Request {request_id}]" if request_id else ""
        logger.info(f">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        logger.info(f">>>>>>>>>>>>>>>>>>>>>>>>>>>> Starting RAG Pipeline >>>>>>>>>>>>>>>>>>>>>")#{request_id_str} [Pipeline ID: {pipeline_id}] [Execution Key: {execution_key[:16]}] >>>>>>>>>>>>>>>>>>>")
        logger.info(f">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Operational Pain Point: {backgrounds}")
        logger.info(f"Campaign Context: {marketing_text}")
        logger.info(f"Target Audience: {icp}")
        logger.info(f"Asset Type: {asset_type}")
        logger.info(f"Company Name: {company_name}")
    #    logger.info(f"Company Domain: {json.dumps(company_analysis, indent=4).get('company_domain')}")
     
        # Log prompt template metadata
        prompt_metadata = get_prompt_metadata_for_logging()
        logger.info(f"Prompt Templates:")
        logger.info(f"  - Retrieval Prompt: edited by {prompt_metadata.get('retrieval_prompt_edited_by')} at {prompt_metadata.get('retrieval_prompt_edited_at')}")
        logger.info(f"  - System Prompt: edited by {prompt_metadata.get('system_prompt_edited_by')} at {prompt_metadata.get('system_prompt_edited_at')}")


        company_enumerations = get_company_enumerations(company_name)
        collection_name = get_collection_name(company_details)

        # Step 1: Build optimized retrieval query
        retrieval_query, retrieval_prompt = await build_retrieval_query(marketing_text, backgrounds, company_details)


        # Step 2: Retrieve documents from vector DB
        external_docs, retrieved_docs = await retrieve_rag_documents(retrieval_query, company_enumerations,collection_name, company_name)

        # Step 2.4: Clean documents to reduce token usage before reranking
        cleaned_docs = clean_documents_for_reranking(retrieved_docs)

        # Step 2.5: Rerank and filter cleaned documents
        filtered_docs, rerank_prompt, rerank_result = await rerank_and_filter_documents(
            retrieved_docs=cleaned_docs,
            retrieval_queries=retrieval_query,
            company_name=company_name,
            company_domain=company_details.company_context.company_domain if company_details else None,
            known_competitors=company_details.company_context.known_competitors if company_details else None
        )
        
        logger.info(f"✓ After reranking: {len(filtered_docs)}/{len(cleaned_docs)} documents retained")

        # Step 3: Build vector search context from filtered documents (already cleaned)
        vector_search_context = build_vector_search_context(filtered_docs)


        backgrounds_str = ", ".join(backgrounds)

        # Step 4: Build final prompt
        prompt = build_final_prompt(
            template=template,
            backgrounds_str=backgrounds_str,
            marketing_text=marketing_text,
            vector_search_context=vector_search_context,
            asset_type=asset_type,
            icp=icp,
            company_name=company_name,
            company_details=company_details
        )

        # Step 5: Generate LLM response
        refined_text = await generate_llm_response(prompt)
        
        # Format sources for the UI.
        # We ONLY include external references (YouTube/Reddit/Podcasts) as sources
        # for the UI. User‑uploaded documents are used as hidden context for RAG,
        # but are not returned as visible "sources" in the result list.
        logger.info("Formatting sources...")
        source_docs: list[Any] = []
        if external_docs:
            logger.info(f"Including {len(external_docs)} external reference documents as sources (excluding user uploads)")
            source_docs.extend(external_docs)
        else:
            logger.info("No external reference documents found; returning empty sources list (user uploads excluded)")

        sources = format_sources(source_docs)
        logger.info(
            f"✓ Formatted {len(sources)} sources "
            f"(0 user documents, {len(external_docs)} external references)"
        )
        
        # Format retrieved documents for frontend
        retrieved_docs_formatted = []
        for doc in retrieved_docs:
            if hasattr(doc, 'metadata') and hasattr(doc, 'page_content'):
                doc_dict = {
                    "page_content": doc.page_content,
                    "metadata": doc.metadata
                }
                retrieved_docs_formatted.append(doc_dict)


        
        # Build email content (always build, but only send if administrator)
        email_content = ""
        try:
            email_sent, email_content = send_email(user_id, backgrounds, marketing_text, asset_type, icp, template,
                                                   company_name, company_details, retrieval_query, retrieval_prompt, vector_search_context, 
                                                   prompt, refined_text, sources, retrieved_docs, send=is_administrator,
                                                   rerank_prompt=rerank_prompt, rerank_result=rerank_result)
            if is_administrator:
                if email_sent:
                    logger.info("Email sent successfully to administrators")
                else:
                    logger.warning("Failed to send email to administrators")
        except Exception as e:
            logger.error(f"Email processing failed (non-critical): {e}", exc_info=True)
            # Still build email content even if sending fails
            try:
                email_content = build_email_content(user_id, backgrounds, marketing_text, asset_type, icp, template,
                                                    company_name, company_details, retrieval_query, retrieval_prompt, vector_search_context,
                                                    prompt, refined_text, sources, retrieved_docs, rerank_prompt, rerank_result)
            except Exception as e2:
                logger.error(f"Failed to build email content: {e2}", exc_info=True)
        
        logger.info(f"<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
        logger.info(f"<<<<<<<<<<<<<<  RAG Pipeline Completed Successfully <<<<<<<<<<<<<<<<<<<")
        logger.info(f"<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<")
        
        return refined_text, sources, retrieved_docs_formatted, prompt, email_content
    finally:
        # Always remove from active pipelines, even if there was an error
        if execution_key in _active_pipelines:
            del _active_pipelines[execution_key]
            logger.debug(f"Removed execution key {execution_key[:20]} from active pipelines")

def get_gmail_service():
    """Get authenticated Gmail API service instance."""
    if not all([gmail_client_id, gmail_client_secret, gmail_refresh_token]):
        logger.error("Gmail API credentials not fully configured")
        return None
    
    try:
        # Create credentials from refresh token
        creds = Credentials(
            token=None,
            refresh_token=gmail_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=gmail_client_id,
            client_secret=gmail_client_secret
        )
        
        # Refresh the token if needed
        if creds.expired:
            creds.refresh(Request())
        
        # Build the Gmail service
        service = build('gmail', 'v1', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Failed to create Gmail service: {e}", exc_info=True)
        return None


def build_email_content(user_id, backgrounds, marketing_text, asset_type, icp, template, 
                        company_name, company_details, retrieval_query, retrieval_prompt, vector_search_context, 
                        prompt, refined_text, sources, retrieved_docs, rerank_prompt="", rerank_result=""):
    """Build email content string. Returns the email body as a string."""
    # Build email content
    email_body = f"User ID: {user_id}"
    email_body += f"\nContext: {marketing_text}"
    email_body += f"\nAsset Type: {asset_type}"
    email_body += f"\nTarget Audience: {icp}"        
    email_body += f"\nPain Points : {backgrounds}"
    email_body += f"\nCompany Name: {company_name}"
    
    # Add prompt template metadata
    prompt_metadata = get_prompt_metadata_for_logging()
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"Prompt Templates Used:"
    email_body += f"\n  - Retrieval Prompt: edited by {prompt_metadata.get('retrieval_prompt_edited_by')} at {prompt_metadata.get('retrieval_prompt_edited_at')}"
    email_body += f"\n  - System Prompt: edited by {prompt_metadata.get('system_prompt_edited_by')} at {prompt_metadata.get('system_prompt_edited_at')}"
    email_body += f"\n\n------------------------------------------------\n"
    

    # Extract company details from CompanyDetails object
    if company_details:
        company_domain = company_details.company_context.company_domain
        company_competitors = company_details.company_context.known_competitors
        company_operational_pains = company_details.company_context.operational_pains
        company_target_audience = company_details.company_context.target_audience
        company_value_proposition = company_details.company_context.self_described_positioning

        email_body += f"\nCompany Value Proposition: {company_value_proposition}"
        email_body += f"\nCompany Domain: {company_domain}"
        email_body += f"\nCompany Competitors: {company_competitors}"
        email_body += f"\nCompany Operational Pains: {company_operational_pains}"
        email_body += f"\nCompany Target Audience: {company_target_audience}"
        
        # Add full company details
        company_json = {
            'company_context': {
                'company_name': company_details.company_context.company_name,
                'company_domain': company_details.company_context.company_domain,
                'self_described_positioning': company_details.company_context.self_described_positioning,
                'product_surface_names': company_details.company_context.product_surface_names,
                'typical_use_cases': company_details.company_context.typical_use_cases,
                'known_competitors': company_details.company_context.known_competitors,
                'target_audience': company_details.company_context.target_audience,
                'operational_pains': company_details.company_context.operational_pains,
            },
            'usage_rules': company_details.company_context.usage_rules
        }
        email_body += f"\nCompany Analysis:\n{json.dumps(company_json, indent=4)}"
    else:
        email_body += f"\nCompany Analysis: Not available"
    
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"\nRetrieval Prompt:\n{retrieval_prompt}"
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"\nRetrieval Query:\n{retrieval_query}"
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"\nVector Search Results:\n{vector_search_context}"
    email_body += f"\n\n------------------------------------------------\n"
    
    # Add reranking information if available
    if rerank_prompt:
        email_body += f"\nRerank and Filter Prompt:\n{rerank_prompt}"
        email_body += f"\n\n------------------------------------------------\n"
    if rerank_result:
        email_body += f"\nRerank and Filter Result:\n{rerank_result}"
        email_body += f"\n\n------------------------------------------------\n"
    
    email_body += f"\nAsset Creation Prompt:\n{prompt}"
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"\nAsset Creation Result:\n{refined_text}"
    email_body += f"\n\n------------------------------------------------\n"
    
    return email_body


def send_email(user_id, backgrounds, marketing_text, asset_type, icp, template, 
                company_name, company_details, retrieval_query, retrieval_prompt, vector_search_context, 
                prompt, refined_text, sources, retrieved_docs, send: bool = True, rerank_prompt="", rerank_result=""):
    """Send email notification using Gmail API. Returns (success: bool, email_content: str)."""
    logger.info(f"Attempting to send email notification via Gmail API...")
    logger.info(f"Sender email configured: {bool(sender_email)}")
    logger.info(f"Gmail API credentials configured: client_id={bool(gmail_client_id)}, client_secret={bool(gmail_client_secret)}, refresh_token={bool(gmail_refresh_token)}")
    
    # Build email content
    email_body = build_email_content(user_id, backgrounds, marketing_text, asset_type, icp, template,
                                     company_name, company_details, retrieval_query, retrieval_prompt, vector_search_context,
                                     prompt, refined_text, sources, retrieved_docs, rerank_prompt, rerank_result)
    
    # If not sending, just return the content
    if not send:
        return False, email_body
    
    if not sender_email:
        logger.warning(f"Sender email not configured")
        return False, email_body
    
    if not all([gmail_client_id, gmail_client_secret, gmail_refresh_token]):
        logger.warning(f"Gmail API credentials not fully configured")
        return False, email_body

    try:
        # Parse receiver emails (handle semicolon-separated list)
        receiver_list = [email.strip() for email in receiver_email.split(';') if email.strip()]
        
        # Create the email message
        message = MIMEMultipart()
        message['From'] = sender_email
        message['To'] = ', '.join(receiver_list)
        message['Subject'] = f"RAG Pipeline Completed Successfully - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        message.attach(MIMEText(email_body, 'plain'))
        
        # Encode the message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        # Get Gmail service and send
        service = get_gmail_service()
        if not service:
            logger.error("Failed to get Gmail service")
            return False, email_body
        
        logger.info(f"Sending email from {sender_email} to {receiver_list}")
        send_message = {'raw': raw_message}
        result = service.users().messages().send(userId='me', body=send_message).execute()
        logger.info(f"Email sent successfully to {len(receiver_list)} recipient(s). Message ID: {result.get('id')}")
        return True, email_body
        
    except HttpError as e:
        logger.error(f"Gmail API error while sending email: {e}", exc_info=True)
        return False, email_body
    except Exception as e:
        logger.error(f"Failed to send email notification: {e}", exc_info=True)
        return False, email_body