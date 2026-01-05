import boto3
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from rag.vectorstore import vector_store
from core.config import settings
from typing import List, Dict, Any, Optional
import logging
import re
import json
import tiktoken
import os
from datetime import datetime
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64
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
# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


asset_type_rules = {
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
    company_analysis: str
) -> str:
    """
    Build an optimized retrieval query using LLM for vector database search.

    Args:
        marketing_text: The user's marketing text
        backgrounds: List of background topics

    Returns:
        str: The optimized retrieval query
    """
    logger.info("Building optimized retrieval query for vector DB...")
    backgrounds_str = ", ".join(backgrounds) if backgrounds else ""

    # Ensure marketing_text and backgrounds_str are strings and not None
    marketing_text = marketing_text or ""
    backgrounds_str = backgrounds_str or ""
    # extract json from company_analysis (between ```json and ```)
    company_json = re.search(r'```json(.*)```', company_analysis, re.DOTALL).group(1)
    company_json = json.loads(company_json)
    company_value_proposition = company_json.get('company_value_proposition', '')
    company_domain = company_json.get('company_domain', '')

    retrieval_prompt = VECTOR_DB_RETREIVAL_PROMPT.format(
        user_provided_text=marketing_text,
        backgrounds=backgrounds_str,
        company_value_proposition=company_value_proposition,
        company_domain=company_domain
    )

    #logger.info("$$$$$$$$$$$$$$$$$$$$$$$$ VECTOR_DB_RETREIVAL_PROMPT $$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    #logger.info(retrieval_prompt)
    #logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")

    retrieval_query = marketing_text
    try:
        #retrieval_llm = ChatOpenAI(
        #    model_name="gpt-4o", #"gpt-5",
        #    openai_api_key=settings.OPENAI_API_KEY,
        #    temperature=1.0,
        #)
        openai_api_key = settings.DEEPINFRA_API_KEY
        base_url = settings.DEEPINFRA_API_BASE_URL
        retrieval_llm = ChatOpenAI(
            model_name="deepseek-ai/DeepSeek-V3.2", #"gpt-5",
            openai_api_key=openai_api_key,
            base_url=base_url,
#            temperature=0.1,
        )
        rq_messages = [HumanMessage(content=retrieval_prompt)]
        rq_response = await retrieval_llm.ainvoke(rq_messages)
        retrieval_query = (rq_response.content or marketing_text).strip()
        logger.info(f"✓ Retrieval query built (length={len(retrieval_query)} chars)")
        logger.info("############################# Retrieval query ###################################")
        logger.info(f"Retrieval query:\n{retrieval_query}")
        logger.info("#################################################################################")
    except Exception as e:
        logger.warning(
            f"⚠ Error building retrieval query, falling back to full context: "
            f"{type(e).__name__}: {str(e)}"
        )

    return retrieval_query, retrieval_prompt


async def retrieve_documents(retrieval_query: str, company_name: str) -> tuple[List[Any], List[Any]]:
    """
    Retrieve relevant documents from vector database using the retrieval query.

    Args:
        retrieval_query: The optimized retrieval query

    Returns:
        tuple: (external_docs, retrieved_docs)
    """
    logger.info("Retrieving relevant documents from vector store...")
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
        # read company_enumerations.json from bucket 
        #  and add the enumerations to the retrieval_query_chunks
        s3 = boto3.client('s3')
        key = company_name.lower()+'_enumerations.json'
        logger.info(f"Reading company enumerations from S3: {key}")
        response = s3.get_object(Bucket='ansora-company-enumerations', Key=key)
        company_enumerations = json.loads(response['Body'].read().decode('utf-8'))

        #logger.info(f"Company enumerations: {company_enumerations}")


        for chunk in retrieval_query_chunks:
            logger.info(f"Searching for chunk: {chunk} in reddit posts, youtube videos, and podcasts")
            reddit_docs.extend(vector_store.search_reddit_posts(chunk, k=10, company_enumerations=company_enumerations, company_name=company_name))
            youtube_docs.extend(vector_store.search_youtube_summaries(chunk, k=3, company_enumerations=company_enumerations, company_name=company_name))
            podcast_docs.extend(vector_store.search_podcast_summaries(chunk, k=3, company_enumerations=company_enumerations, company_name=company_name))


 
        # For Reddit, use post_id if available, otherwise fall back to url
        # Check if post_id exists in any doc
        use_post_id = any(hasattr(doc, 'metadata') and doc.metadata.get('post_id') for doc in reddit_docs[:5]) if reddit_docs else False
        merger_field = "post_id" if use_post_id else "url"
        logger.info(f"Using '{merger_field}' field for Reddit duplicate filtering")
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

    return external_docs, combined_docs


def build_vector_search_context(retrieved_docs: List[Any]) -> str:
    """
    Build the vector search context JSON for the LLM prompt.

    Args:
        retrieved_docs: List of retrieved document objects

    Returns:
        str: JSON string containing vector search context
    """
    # join all documents metadata to a json array for the vector_search_context
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
    vector_search_context = vector_search_context_text

    logger.info(
        f"✓ Vector search context built: {len(vector_search_context)} chars from {len(retrieved_docs)} sources"
    )

    return vector_search_context


def build_final_prompt(
    template: str,
    backgrounds_str: str,
    marketing_text: str,
    vector_search_context: str,
    asset_type: str | None,
    icp: str | None,
    company_name: str | None,
    company_analysis: str | None = None,
    competition_analysis: str | None = None
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
    logger.info("Building final prompt...")

    # Expand structured rule blocks from asset type dictionaries
    asset_type_instructions = asset_type_rules.get(asset_type, asset_type or "") if asset_type else ""
    
    # Process company analysis if provided
    # Try to extract JSON from company_analysis if it's wrapped in code blocks
    company_info = ""
    company_json = {}
    if company_analysis:
        try:
            # Check if company_analysis contains JSON in code blocks
            json_match = re.search(r'```json\s*(.*?)\s*```', company_analysis, re.DOTALL)
            if json_match:
                company_info = json_match.group(1).strip()
                # Try to parse as JSON
                try:
                    company_json = json.loads(company_info)
                except json.JSONDecodeError:
                    # If JSON parsing fails, use the text as-is
                    company_json = {'company_analysis': company_info}
            else:
                # If no JSON blocks, use the analysis as-is
                company_info = company_analysis
                company_json = {'company_analysis': company_analysis}
        except Exception as e:
            logger.warning(f"Error parsing company analysis: {e}, using as-is")
            company_info = company_analysis or ""
            company_json = {'company_analysis': company_info}
    
    # Process competition analysis if provided
    competition_info = ""
    if competition_analysis:
        try:
            # Check if competition_analysis contains JSON in code blocks
            json_match = re.search(r'```json\s*(.*?)\s*```', competition_analysis, re.DOTALL)
            if json_match:
                competition_info = json_match.group(1).strip()
            else:
                # If no JSON blocks, use the analysis as-is
                competition_info = competition_analysis
        except Exception as e:
            logger.warning(f"Error parsing competition analysis: {e}, using as-is")
            competition_info = competition_analysis or ""


    prompt = template.format(
        backgrounds=backgrounds_str,
        use_cases=backgrounds_str,
        marketing_text=marketing_text,
        context=marketing_text,
        user_provided_text=marketing_text,
        vector_search_context=vector_search_context,
        asset_type=asset_type or '',
        asset_type_instructions=asset_type_instructions,
        icp=icp or '',
        company_analysis=company_info,
        competition_analysis=competition_info,
        latest_anouncements=company_json.get('latest_anouncements'),
        company_name=company_name,
        company_domain=company_json.get('company_domain') or company_json.get('website'),
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
    logger.info("Initializing LLM (GPT-4o)...")
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
    logger.info("Sending request to OpenAI API...")
    messages = [
        #SystemMessage(content=SYSTEM_PROMPT),
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

    return refined_text


async def process_rag(
    user_id: int,
    backgrounds: List[str],
    marketing_text: str,
    asset_type: str | None = None,
    icp: str | None = None,
    template: str | None = None,
    company_name: str | None = None,
    company_analysis: str | None = None,
    competition_analysis: str | None = None,
    is_administrator: bool = False,
) -> tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], str, str]:
    """
    Process RAG pipeline and return refined text, sources, retrieved documents, final prompt, and email content.

    Returns:
        tuple: (refined_text, sources_list, retrieved_docs_list, final_prompt, email_content)
    """
    logger.info(f"=== Starting RAG Pipeline ===")
    logger.info(f"User ID: {user_id}")
    logger.info(f"Backgrounds / use cases: {backgrounds}")
    logger.info(f"Context text length: {len(marketing_text)} chars")
    logger.info(f"Context text preview: {marketing_text[:100]}...")
    logger.info(f"Asset Type: {asset_type}, ICP: {icp}")
    logger.info(f"Full context text: {marketing_text}")
    logger.debug(f"Template: {template}")
    
    # Use default template if none provided
    if template is None:
        template = DEFAULT_TEMPLATE
        logger.info("Using default template")
    else:
        logger.info("Using custom/override template")
    
    # Step 1: Build optimized retrieval query
    retrieval_query, retrieval_prompt = await build_retrieval_query(marketing_text, backgrounds, company_analysis)
    backgrounds_str = ", ".join(backgrounds)

    # Step 2: Retrieve documents from vector DB
    external_docs, retrieved_docs = await retrieve_documents(retrieval_query, company_name)

    # Step 3: Build vector search context
    vector_search_context = build_vector_search_context(retrieved_docs)
    logger.info(f"%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%marketing_text: {marketing_text}")
    # Step 4: Build final prompt
    prompt = build_final_prompt(
        template=template,
        backgrounds_str=backgrounds_str,
        marketing_text=marketing_text,
        vector_search_context=vector_search_context,
        asset_type=asset_type,
        icp=icp,
        company_name=company_name,
        company_analysis=company_analysis,
        competition_analysis=competition_analysis,

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

    logger.info("=== RAG Pipeline Completed Successfully ===")
    
    # Build email content (always build, but only send if administrator)
    email_content = ""
    try:
        email_sent, email_content = send_email(user_id, backgrounds, marketing_text, asset_type, icp, template,
                                               company_name, company_analysis, competition_analysis, retrieval_query, retrieval_prompt, vector_search_context, 
                                               prompt, refined_text, sources, retrieved_docs, send=is_administrator)
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
                                                company_name, company_analysis, competition_analysis, retrieval_query, retrieval_prompt, vector_search_context,
                                                prompt, refined_text, sources, retrieved_docs)
        except Exception as e2:
            logger.error(f"Failed to build email content: {e2}", exc_info=True)
    
    return refined_text, sources, retrieved_docs_formatted, prompt, email_content

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
                        company_name, company_analysis, competition_analysis, retrieval_query, retrieval_prompt, vector_search_context, 
                        prompt, refined_text, sources, retrieved_docs):
    """Build email content string. Returns the email body as a string."""
    # Build email content
    email_body = f"User ID: {user_id}"
    email_body += f"\nContext: {marketing_text}"
    email_body += f"\nAsset Type: {asset_type}"
    email_body += f"\nTarget Audience: {icp}"        
    email_body += f"\nPain Points : {backgrounds}"
    email_body += f"\nCompany Name: {company_name}"
    email_body += f"\n\n------------------------------------------------\n"
    
    # Handle company_analysis - extract JSON if present, otherwise use raw text
    if company_analysis:
        try:
            match = re.search(r'```json(.*)```', company_analysis, re.DOTALL)
            if match:
                json_str = match.group(1)
                json_data = json.loads(json_str)
                email_body += f"\nCompany Analysis:\n{json.dumps(json_data, indent=4)}"
            else:
                email_body += f"\nCompany Analysis:\n{company_analysis}"
        except (AttributeError, json.JSONDecodeError) as e:
            logger.warning(f"Could not parse company_analysis as JSON: {e}, using raw text")
            email_body += f"\nCompany Analysis:\n{company_analysis}"
    else:
        email_body += f"\nCompany Analysis: Not available"
    
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"\nCompetition Analysis:\n{competition_analysis if competition_analysis else 'Not available'}"
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"\nRetrieval Prompt:\n{retrieval_prompt}"
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"\nRetrieval Query:\n{retrieval_query}"
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"\nVector Search Results:\n{vector_search_context}"
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"\nAsset Creation Prompt:\n{prompt}"
    email_body += f"\n\n------------------------------------------------\n"
    email_body += f"\nAsset Creation Result:\n{refined_text}"
    email_body += f"\n\n------------------------------------------------\n"
    
    return email_body


def send_email(user_id, backgrounds, marketing_text, asset_type, icp, template, 
                company_name, company_analysis, competition_analysis, retrieval_query, retrieval_prompt, vector_search_context, 
                prompt, refined_text, sources, retrieved_docs, send: bool = True):
    """Send email notification using Gmail API. Returns (success: bool, email_content: str)."""
    logger.info(f"Attempting to send email notification via Gmail API...")
    logger.info(f"Sender email configured: {bool(sender_email)}")
    logger.info(f"Gmail API credentials configured: client_id={bool(gmail_client_id)}, client_secret={bool(gmail_client_secret)}, refresh_token={bool(gmail_refresh_token)}")
    
    # Build email content
    email_body = build_email_content(user_id, backgrounds, marketing_text, asset_type, icp, template,
                                     company_name, company_analysis, competition_analysis, retrieval_query, retrieval_prompt, vector_search_context,
                                     prompt, refined_text, sources, retrieved_docs)
    
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