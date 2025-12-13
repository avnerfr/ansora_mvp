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
subject: 1 short, sharp line focused on a real problem or curiosity

opening: 2 sentences max.
- sentence 1: context that shows relevance to their world
- sentence 2: the specific pain you're seeing teams struggle with

body: 3 bullets (but written as natural bullets, not labeled)
- bullet 1: describe the pain in practitioner language (no “pain:”)
- bullet 2: explain the underlying reason it keeps happening (without calling it "insight")
- bullet 3: how the solution changes their day-to-day (practical, not salesy)

cta: 1 short, friendly sentence offering a quick chat or resource
""",
"one-pager": """
headline: 1 line: problem-oriented or value-oriented
subhead: 1 line: clarifies who it’s for or why it matters

lead paragraph: up to 2 sentences grounding the real-world context
problems: 6 bullets written in practitioner voice, no labels, no abstract phrasing
features: 4 bullets, each starting with "Feature:", each mapped implicitly to a problem (no need to indicate the problem explicitly)
business impact: 3 bullets that describe outcomes in natural language (no numbers required)

cta: 1 line
""",
"landing page": """
headline: 1 line, sharp, focused on the core value
subhead: 1 line, clarifying what pain it solves or what outcome it unlocks
""",
    # Support both "blog" (UI) and "blog post" (notebook wording)
    "blog": """
intro paragraph: 1–2 sentences grounding the problem in a real-world scenario

sections: 3 sections
each section:
- 1 line subhead
- 1 paragraph (4–6 lines) with practical insights, not generic commentary

conclusion: 1 line that ties together the point or gives a forward-looking takeaway
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

SYSTEM_PROMPT = """
You are an enterprise-grade B2B Product Marketing Writer.
Your task is to generate a high-clarity, practitioner-level marketing asset
based ONLY on the INSIGHTS and STRUCTURE provided below.

Do not add external knowledge.
Do not invent numbers, KPIs, improvements, benchmarks, or capabilities that do not explicitly appear in the INSIGHTS.
If you are not sure about the information, use the context and references to make a decision.

You are writing as the Product Marketing Manager of AlgoSec.

AlgoSec is NOT a firewall vendor. AlgoSec does NOT deploy NGFWs.
AlgoSec does NOT provide inline protection, enforcement, or hardware.
MUST NOT describe AlgoSec as making enforcement decisions, blocking traffic, or providing L3-L7 protection.

AlgoSec provides:
- Automated application connectivity management
- End-to-end visibility across hybrid networks (on-prem + cloud)
- Automated policy cleanup across firewalls + cloud SGs + tags
- Change workflow automation with impact analysis
- Risk and compliance checks before implementation
- Tag-based and object-based policy logic
- DevSecOps integration (impact checks inside CI/CD)

Core value proposition:
AlgoSec helps Network & Security Operations teams reduce outages,
eliminate policy sprawl, clean up shadow rules, accelerate approvals,
and gain full visibility across hybrid environments.

Write every asset as if AlgoSec is the intelligence layer that analyzes,
simulates, and orchestrates policies — not a firewall vendor.

Do NOT position AlgoSec as:
- selling firewalls
- deploying NGFWs
- providing network hardware
- replacing cloud-native controls

Always connect messaging to:
CAB fatigue, shadow rules, rule bloat, hybrid inconsistencies,
change backlog pressure, outage anxiety, misconfiguration risk



"""
# context = user provided text
# uploaded documents = user uploaded documents

DEFAULT_TEMPLATE = """
------------------------------------------------------
CONTENT GUARDRAILS (MANDATORY)
------------------------------------------------------
- All claims must come directly from the user text which contains the product description and the request or instruction.
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


VECTOR_DB_RETREIVAL_PROMPT = """
You are a retrieval query condenser for a RAG system.
Your goal is to transform the user’s request into 1–3 dense, self-contained sentences that are fully optimized for vector similarity search.

Inputs:

1. User text: the user’s question or instruction

2. Backgrounds: prior context such as system instructions or discussion history

Your task:

1. Read the User text and Backgrounds carefully.
2. Identify the precise information need, including relevant entities, technologies, domains, ICP roles, and constraints.
3. Remove all meta-instructions (style, tone, formatting) and any content that doesn’t help retrieve documents.
4. Produce 1–3 standalone sentences, each one clear and independent, containing the core topics the retrieval system should search for.
5. Make the sentences rich with meaningful domain terms relevant to AlgoSec contexts (e.g., hybrid networks, security policy management, firewall change processes, application connectivity, cloud environments, automation, DevOps/DevSecOps, compliance, risk reduction).
6. Do not use generic buzzwords.
7. Do not refer back to the text (“as described above”).
8. Output only the sentences. No bullets, numbering, explanations, or code blocks.

Output format:
1 to 3 standalone sentences, each fully meaningful on its own, separated by line breaks. No additional text.

Example Input:
User text: How does our solution for managing security in hybrid cloud differ from competitors?
Backgrounds: discussion about policy cleanup, visibility, automation

Example Output:
Hybrid cloud security management practices that compare automated policy analysis, risk validation, and unified visibility across on-prem and cloud networks.
Differences in application-centric policy automation and compliance workflows between competing hybrid network security platforms.
Evaluation of how automated policy cleanup and change management reduce risk and operational overhead in hybrid environments.


"""

VECTOR_DB_RETREIVAL_PROMPT_1 = """
You are a retrieval query condenser for a RAG system.
Your goal is to transform a long, messy input into a small number of dense, information-rich sentences that are optimized for vector search.

You are given two inputs:
User text: the user’s question, request, or instruction.
Backgrounds: extra context such as previous messages, system instructions, or document snippets.

Your task:
Read the user text and backgrounds carefully.
Identify the core information needs: entities, topics, constraints (time, location, technology, domain, doc_type), and any disambiguating details.
Ignore anything that is just meta-instruction (style, tone, formatting, “be concise”, etc.) or chit-chat that does not help retrieve relevant documents.
Produce 1–3 standalone sentences that:
Are self-contained and make sense without the original prompt.
Include important proper nouns, key phrases, and domain terms.
Reflect all major sub-topics the user actually needs documents for, if possible.
Avoid references like “as above”, “this document”, “the user”, or “you”.

Output format:
Output only the 1–3 sentences, separated by spaces or line breaks.
Do not add bullet points, numbering, explanations, or any additional text.
Do not wrap the output in quotes or code fences.
this is the backgrounds of the query: {{backgrounds}}
this is the user text: {{user_provided_text}}

"""

VECTOR_DB_RETREIVAL_PROMPT_2 = """
You are a retrieval query condenser for a RAG system.
Your goal is to transform a long, messy input into a small number of dense, information-rich sentences that are optimized for vector search.

You are given two inputs:
User text: the user’s question, request, or instruction.
Backgrounds: extra context such as previous messages, system instructions, or document snippets.

create a search query optimized for a vector database that retrieves the most relevant technical insights. 
Return a short, precise query focusing on:
- pains or problems
- solutions or methods
- technologies or processes
- ICP role context (if implied)
Avoid buzzwords or high-level terms. Focus on concrete operational or security challenges relevant to hybrid networks, firewall policy management, automation, risk, compliance, cloud migration, or application connectivity.


this is the backgrounds of the query: {{backgrounds}}
this is the user text: {{user_provided_text}}
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
            "mp3_url": _safe_str(metadata.get("mp3_url")),
            
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
    logger.debug(f"Template: {template}")
    
    # Use default template if none provided
    if template is None:
        template = DEFAULT_TEMPLATE
        logger.info("Using default template")
    else:
        logger.info("Using custom/override template")

    # --------------------------------------------------
    # Step 1: Build optimized retrieval query for vector DB using LLM.
    #         We no longer rely on persisted user documents; the retrieval
    #         query is built purely from the user's context and backgrounds.
    # --------------------------------------------------
    logger.info("Building optimized retrieval query for vector DB...")
    backgrounds_str = ", ".join(backgrounds)

    retrieval_prompt = VECTOR_DB_RETREIVAL_PROMPT
    retrieval_prompt = retrieval_prompt.replace("{{user_provided_text}}", marketing_text)
    retrieval_prompt = retrieval_prompt.replace("{{backgrounds}}", backgrounds_str)

    logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ VECTOR_DB_RETREIVAL_PROMPT")
    logger.info(retrieval_prompt)
    logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    retrieval_query = marketing_text
    try:
        # NOTE:
        # Some newer OpenAI models (e.g., reasoning / latest GPT models)
        # only support the default temperature value of 1.0 and will
        # return a 400 error if another value (like the LangChain default
        # of 0.7) is sent. We explicitly set temperature=1.0 here to
        # avoid sending an unsupported value.
        retrieval_llm = ChatOpenAI(
            model_name="gpt-4o", #"gpt-5",
            openai_api_key=settings.OPENAI_API_KEY,
            temperature=1.0,
        )
        rq_messages = [HumanMessage(content=retrieval_prompt)]
        rq_response = await retrieval_llm.ainvoke(rq_messages)
        retrieval_query = (rq_response.content or marketing_text).strip()
        logger.info(f"✓ Retrieval query built (length={len(retrieval_query)} chars)")
        logger.info("################################################################################# Retrieval query")
        logger.info(f"Retrieval query:\n{retrieval_query}")
        logger.info("#################################################################################")
    except Exception as e:
        logger.warning(
            f"⚠ Error building retrieval query, falling back to full context: "
            f"{type(e).__name__}: {str(e)}"
        )

    # --------------------------------------------------
    # Step 2: Retrieve documents from vector DB using the optimized query
    # --------------------------------------------------
    logger.info("Retrieving relevant documents from vector store...")
    external_docs: list[Any] = []

    # External vector search (e.g., YouTube/Reddit/Podcasts)
    try:
        logger.info("Searching external sources (YouTube/Reddit/Podcasts) from cloud Qdrant for references...")
        external_docs = vector_store.search_reddit_posts(retrieval_query, k=10)
        logger.info(f"✓ Retrieved {len(external_docs)} external reference documents")
    except Exception as e:
        logger.warning(f"⚠ Error retrieving external reference documents: {type(e).__name__}: {str(e)}")
        external_docs = []

    # For RAG context, we now use the external documents (no persisted user documents).
    retrieved_docs = external_docs
    logger.info(f"✓ Total context sources: {len(retrieved_docs)} external documents")
    
    # Format context from retrieved documents
    logger.info("Formatting context from retrieved documents...")
    context_parts: list[str] = []
    seen_snippets: set[str] = set()
    for i, doc in enumerate(retrieved_docs, 1):
        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
        filename = metadata.get("filename", "Unknown")
        content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
        snippet = content[:1000]

        # Avoid adding identical snippets multiple times (can happen with
        # overlapping chunks or duplicate content in the vector store).
        if snippet in seen_snippets:
            logger.debug(f"  Skipping duplicate context snippet from {filename}")
            continue

        seen_snippets.add(snippet)
        context_parts.append(f"[From {filename}]: {snippet}")
        logger.debug(f"  Context part {i} from {filename}: {len(content)} chars (snippet len={len(snippet)})")
    
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
    logger.info("Initializing LLM (GPT-4o)...")
    # See note above on temperature: we set temperature=1.0 explicitly
    # to comply with models that only accept the default temperature.
    llm = ChatOpenAI(
        model_name="gpt-4o", #"gpt-5",
        openai_api_key=settings.OPENAI_API_KEY,
        temperature=1.0,
    )
    logger.info("✓ LLM initialized")
    
    # Generate response
    logger.info("Sending request to OpenAI API...")
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
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
    
    logger.info("=== RAG Pipeline Completed Successfully ===")
    return refined_text, sources
