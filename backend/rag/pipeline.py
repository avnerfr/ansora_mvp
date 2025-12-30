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


from .prompts import SYSTEM_PROMPT, DEFAULT_TEMPLATE, DEFAULT_TEMPLATE_1, VECTOR_DB_RETREIVAL_PROMPT
# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


asset_type_rules = {
"email": """
Theme: Identify a broad operational struggle from INSIGHTS_JSON.

Subject (1 line, ≤10 words): Focus on a technical gap or operational pain.

Opening (Hook, 2 sentences max):
Start with a visceral observation about the gap between theory and messy operational reality.
Embed 1-2 pain_phrases naturally.
Keep it short and punchy; do not pre-solve.
Max 15 words per sentence.

Body (Exactly 3 bullets, natural prose):
Bullet 1 - Whether/Or framework: Connect 2-3 key_issues. Use pain_phrases naturally. Keep ≤15 words per sentence.
Bullet 2 - Operational friction: Describe systemic consequence in buyer_language. Show frustration, inefficiency, or blind spots.
Bullet 3 - AlgoSec Logic Map: Show operational clarity or improvement. Keep peer-to-peer tone, neutral, no marketing language.

CTA (1 sentence, ≤15 words):
Short, operational, friendly, neutral.
Example: “Let’s have a quick chat to navigate this policy maze.”


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

    for doc in docs:
        metadata = doc.metadata if hasattr(doc, "metadata") else {}
        raw_value = metadata.get(merger_by)

        # Normalize to string for comparison; None becomes empty string
        value_str = str(raw_value) if raw_value is not None else ""

        if value_str in seen_values:
            continue

        seen_values.add(value_str)
        merged_docs.append(doc)

    logger.info("After merge/filter by '%s': %d → %d", merger_by, len(docs), len(merged_docs))
    #sort the merged_docs by the score in descending order
    merged_docs = sorted(merged_docs, key=lambda x: x.metadata.get('score', 0), reverse=True)
    # leave the top 10 documents with the highest score
    merged_docs = merged_docs[:max_docs]

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

    logger.info("$$$$$$$$$$$$$$$$$$$$$$$$ VECTOR_DB_RETREIVAL_PROMPT $$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    logger.info(retrieval_prompt)
    logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")

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

    return retrieval_query


async def retrieve_documents(retrieval_query: str) -> tuple[List[Any], List[Any]]:
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

        for chunk in retrieval_query_chunks:
            logger.info(f"Searching for chunk: {chunk} in reddit posts, youtube videos, and podcasts")
            reddit_docs.extend(vector_store.search_reddit_posts(chunk, k=10))
            youtube_docs.extend(vector_store.search_youtube_summaries(chunk, k=3))
            podcast_docs.extend(vector_store.search_podcast_summaries(chunk, k=3))

        reddit_filtered_docs = merge_and_filter_duplicate_documents(reddit_docs, "url",10)    #extract a vector of json from the reddit_docs
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
            elif doc_type == "youtube_summary":
                source = "youtube"
                url = doc_url
                video_url = doc_url  # For frontend compatibility
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
                "url": url,
                "key_issues": key_issues,
                "pain_phrases": pain_phrases,
                "emotional_triggers": emotional_triggers,
                "buyer_language": buyer_language,
                "implicit_risks": implicit_risks
            }

            # Add type-specific URL fields for frontend compatibility
            if doc_type == "reddit_post":
                source_obj["thread_url"] = thread_url
            elif doc_type == "youtube_summary":
                source_obj["video_url"] = video_url
                source_obj["citation_start_time"] = citation_start_time
            elif doc_type == "podcast_summary":
                source_obj["episode_url"] = episode_url
                source_obj["citation_start_time"] = citation_start_time
                source_obj["mp3_url"] = _safe_str(mp3_url)
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
) -> tuple[str, List[Dict[str, Any]], List[Dict[str, Any]], str]:
    """
    Process RAG pipeline and return refined text, sources, retrieved documents, and final prompt.

    Returns:
        tuple: (refined_text, sources_list, retrieved_docs_list, final_prompt)
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
    retrieval_query = await build_retrieval_query(marketing_text, backgrounds, company_analysis)
    backgrounds_str = ", ".join(backgrounds)

    # Step 2: Retrieve documents from vector DB
    external_docs, retrieved_docs = await retrieve_documents(retrieval_query)

    # Step 3: Build vector search context
    vector_search_context = build_vector_search_context(retrieved_docs)

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
    return refined_text, sources, retrieved_docs_formatted, prompt
