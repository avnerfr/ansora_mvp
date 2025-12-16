from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from rag.vectorstore import vector_store
from core.config import settings
from typing import List, Dict, Any, Optional
import logging
import re
import json
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    CharacterTextSplitter
)

import nltk

nltk.download('punkt')
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
subhead: 1 line: clarifies who it's for or why it matters

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
intro paragraph: 1-2 sentences grounding the problem in a real-world scenario

sections: 3 sections
each section:
- 1 line subhead
- 1 paragraph (4-6 lines) with practical insights, not generic commentary

conclusion: 1 line that ties together the point or gives a forward-looking takeaway
""",
    "blog post": """
- Length: Short-form thought leadership (400-600 words max)
- Audience: Senior practitioners (Security, IAM, Platform, DevSecOps)
- Tone: Educational, opinionated, practitioner-level. No marketing language.

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

SYSTEM

You are a senior enterprise B2B Product Marketing Writer for Network & Security Operations teams.

You write in practitioner language used by:
- Network Security Engineers
- NetSec Leads
- Security Operations Managers

You do NOT explain frameworks, models, or theory.
You do NOT educate beginners.
You expose operational failure, friction, blind spots, and decision fatigue.

ZERO TRUST CONTEXT
Zero Trust in this task is NOT a framework or maturity model.
Treat Zero Trust as broken trust assumptions in real operations, such as:
- access paths no one can fully explain
- policy changes approved without understanding blast radius
- identities, rules, or connections that exist without clear ownership
- environments where “least privilege” exists only on slides

You are writing as AlgoSec.

ALGOSEC POSITIONING (MANDATORY)
AlgoSec is an intelligence and visibility layer for network and security policy.

AlgoSec analyzes application connectivity, access paths, and policy logic across
on-prem, cloud, and hybrid environments.

AlgoSec MAY be referenced only as a response to operational pain.
Do NOT introduce AlgoSec unless it directly resolves a stated issue.

AlgoSec capabilities you MAY reference when relevant:
- End-to-end application connectivity visibility
- Change impact analysis before implementation
- Risk and compliance checks inside change workflows
- Policy cleanup and shadow rule identification
- CI/CD and DevSecOps integration for pre-change validation

AlgoSec does NOT:
- enforce traffic
- block connections
- deploy firewalls or hardware
- replace cloud-native security controls

Never describe AlgoSec as a firewall vendor or enforcement point.

GLOBAL CONTENT GUARDRAILS (MANDATORY)
- Use ONLY the insights provided in the input JSON
- Do NOT invent metrics, benchmarks, KPIs, or improvements
- Do NOT add external knowledge or assumptions
- No hype, no buzzwords, no generic security claims
- Plain text output only
- Max 18 words per sentence
- Practitioner language only: rule bloat, CAB fatigue, shadow rules, outage fear, hybrid inconsistency

You MUST follow the selected asset template EXACTLY.
Do not add sections.
Do not remove sections.
Do not rename headers.
Do not merge sections.

----------------------------------------------------------------
INPUTS
----------------------------------------------------------------

ASSET_TYPE:
{{asset_type_rules[asset_type]}}

ICP_ROLE:
{{icp}}

PRIMARY_TOPIC:
{{primary_topic}}

use the following tone: {{tone_rules[tone]}}

----------------------------------------------------------------
INSIGHTS_JSON (FROM RAG — MANDATORY)
----------------------------------------------------------------
{{vector_search_context}}

You MUST ground all content in this JSON.
Do NOT introduce concepts not present in it.

----------------------------------------------------------------
ASSET TEMPLATES
----------------------------------------------------------------

IF ASSET_TYPE = EMAIL
OUTPUT FORMAT (STRICT):

subject:
1 short, sharp line focused on a real operational problem or curiosity.

opening:
2 sentences max.
- sentence 1: context that mirrors their day-to-day reality
- sentence 2: a specific operational pain surfaced in the insights

body:
3 natural bullets (no labels).
- bullet 1: describe the pain in practitioner language
- bullet 2: explain why it keeps happening operationally
- bullet 3: how the situation changes when visibility or impact clarity exists

cta:
1 short, friendly sentence offering a quick chat or resource.

------------------------------------------------------------

IF ASSET_TYPE = BLOG_POST
OUTPUT FORMAT (STRICT):

intro:
Maximum 2 sentences framing a real operational failure or misconception.

section 1:
One-line subhead.
2-3 sentences describing the operational problem.

section 2:
One-line subhead.
2-3 sentences explaining why teams get stuck or repeat the mistake.

section 3:
One-line subhead.
2-3 sentences describing what changes when assumptions are validated.

conclusion:
1 sentence tying the issue back to operational clarity.

------------------------------------------------------------

IF ASSET_TYPE = LINKEDIN_POST
OUTPUT FORMAT (STRICT):

1 short hook sentence (provocative but technical).
1-2 sentences describing the operational reality.
1 sentence highlighting the hidden risk or blind spot.
1 sentence pointing to what teams should question or re-examine.

------------------------------------------------------------

IF ASSET_TYPE = ONE_PAGER
OUTPUT FORMAT (STRICT):

headline:
1 line describing the operational problem.

problem:
2-3 sentences grounded in the insights.

why_it_persists:
2-3 sentences explaining systemic causes.

operational_shift:
2-3 sentences describing what changes with visibility and impact awareness.

----------------------------------------------------------------
FINAL INSTRUCTIONS
----------------------------------------------------------------

- Write ONLY the final asset.
- No commentary.
- No explanations.
- No references to “insights”, “this discussion”, or “the data”.
- Every sentence must be defensible from the provided JSON.
"""





DEFAULT_TEMPLATE_1 = """
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

The user provided the following original text: 
{{user_provided_text}}
Also make sure to use language and key insights from the following context: 
{{vector_search_context}}

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
You are a retrieval query generator for a practitioner-first RAG system.
Task: Convert any user input—technical, operational, organizational, or even career/personal—into 3–5 concrete, operational search queries. Queries must reflect real-life practitioner struggles and symptoms, phrased as if a practitioner is asking for help in forums, postmortems, or operational discussions.

INPUTS:
User text: any concept, question, or statement
Backgrounds: high-level domain context (e.g., network security, IAM, cloud, DevOps, IT operations)

STEP 1 - Understand the input:
Decide the nature of the input: technical issue, abstract concept, process/policy problem, human/organizational pain.
If the input is abstract (label, framework, role, or principle), discard the abstract label and identify the concrete struggles it may cause.
If the input is concrete, focus on the real operational consequences of the stated problem.

STEP 2 – Generate operational failure angles:
For each input, generate queries that reflect pain points, failures, or risky situations that a practitioner would encounter. Consider:
Systems or processes that break unexpectedly
Access, permissions, or workflow issues
Communication or ownership gaps
Anything teams postpone because fixing it feels risky
Workload, burnout, or human factor problems

STEP 3 – Language & style:
Write as if it were a Reddit post title or opening paragraph of a help request
Be specific about symptoms, consequences, or frustration
Avoid: abstract labels, frameworks, solutions, best practices, vendors, product names, or analyst/marketing language

STEP 4 – Output rules:
Produce 3 to 5 standalone sentences
Each sentence must describe a unique, concrete operational struggle
One sentence per line
Do not add bullets, numbering, explanations, or extra text

FINAL VALIDATION:
Check each sentence: it must directly reflect the input in some way
No sentence should include the original abstract label or synonyms if the input was abstract
Each sentence must describe a practically observable problem or risk
this is the user text: {{user_provided_text}}
this is the backgrounds of the query: {{backgrounds}}
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
        # Handle external_docs dictionaries (source objects we created)
        if isinstance(doc, dict):
            # For our source objects, use the dict as metadata and extract content
            metadata = doc.copy()
            content = doc.get("snippet", doc.get("citation", doc.get("title", "No content")))
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


def merge_and_filter_duplicate_documents(docs: List[Any], merger_by: str) -> List[Any]:
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
    merged_docs = merged_docs[:10]

    return merged_docs


"""
Chunk the text into smaller pieces for retrieval, without external dependencies.
"""
def chunking_model_naive(text: str) -> List[str]:
    """
    Naive sentence chunker:
    - Splits on ., !, ? followed by whitespace.
    - Falls back to a single chunk if anything goes wrong.
    """
    try:
        if not text:
            return []
        chunks = re.split(r'(?<=[.!?])\s+', text)
        return [c.strip() for c in chunks if c.strip()]
    except Exception as e:
        print(f"Error chunking text: {e}")
        return [text]

def chunking_model_nltk(text: str) -> List[str]:
    """
    Use nltk to chunk the text into smaller pieces.
    """
    try:
        if not text:
            return []
        chunks = nltk.sent_tokenize(text)
        return [c.strip() for c in chunks if c.strip()]
    except Exception as e:
        print(f"Error chunking text: {e}")
        return [text]

def chunking_model_langchain(text: str,recursive_splitter = False) -> List[str]:
    """
    Chunk the text into smaller pieces for retrieval using LangChain.
    """
    try:
        if not text:
            return []
        if recursive_splitter:
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=0,
                length_function=len,
            )
        else:
            text_splitter = CharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=0,
                length_function=len,
            )
        chunks = text_splitter.split_text(text)
        return [c.strip() for c in chunks if c.strip()]
    except Exception as e:
        print(f"Error chunking text: {e}")
        return [text]   

    

async def process_rag(
    user_id: int,
    backgrounds: List[str],
    marketing_text: str,
    tone: str | None = None,
    asset_type: str | None = None,
    icp: str | None = None,
    template: str | None = None,
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

    logger.info("$$$$$$$$$$$$$$$$$$$$$$$$ VECTOR_DB_RETREIVAL_PROMPT $$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    logger.info(retrieval_prompt)
    logger.info("$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
    retrieval_query = marketing_text
    try:
        retrieval_llm = ChatOpenAI(
            model_name="gpt-4o", #"gpt-5",
            openai_api_key=settings.OPENAI_API_KEY,
            temperature=1.0,
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

    # --------------------------------------------------
    # Step 2: Retrieve documents from vector DB using the optimized query
    # --------------------------------------------------
    logger.info("Retrieving relevant documents from vector store...")
    external_docs: list[Any] = []

    # External vector search (e.g., YouTube/Reddit/Podcasts)
    try:
        # chunk retreival query using sentence chunking
        reddit_docs = []
        youtube_docs = []
        podcast_docs = []
        retrieval_query_chunks = chunking_model_nltk(retrieval_query)

        for chunk in retrieval_query_chunks:
            logger.info(f"Searching for chunk: {chunk} in reddit posts")
            reddit_docs.extend(vector_store.search_reddit_posts(chunk, k=10))


        reddit_filtered_docs = merge_and_filter_duplicate_documents(reddit_docs, "url")    #extract a vector of json from the reddit_docs
        
        logger.info(f"############################# Reddit filtered docs: {len(reddit_filtered_docs)} #############################")
        for doc in reddit_filtered_docs:
            title = doc.metadata.get('title', '')
            score = doc.metadata.get('score', 0)
            citation = doc.metadata.get('citation', '')
            key_issues = doc.metadata.get('key_issues', '')
            pain_phrases = doc.metadata.get('pain_phrases', '')
            emotional_triggers = doc.metadata.get('emotional_triggers', '')
            buyer_language = doc.metadata.get('buyer_language', '')
            implicit_risks = doc.metadata.get('implicit_risks', '')
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
                "filename": title or "Reddit Post",
                "snippet": context_excerpt,
                "score": score,
                "source": "reddit",
                "doc_type": "reddit_post",
                "citation": citation,
                "title": title,
                "url": doc.metadata.get('url', ''),
                "key_issues": key_issues,
                "pain_phrases": pain_phrases,
                "emotional_triggers": emotional_triggers,
                "buyer_language": buyer_language,
                "implicit_risks": implicit_risks
            }
            external_docs.append(source_obj)  
            #logger.info(f"Reddit filtered docs JSON: {reddit_filtered_docs_json_text}")
        logger.info("#################################################################################")  
    
    except Exception as e:
        logger.warning(f"⚠ Error retrieving external reference documents: {type(e).__name__}: {str(e)}")
        external_docs = []
    # For RAG context, we now use the external documents (no persisted user documents).
    retrieved_docs = reddit_filtered_docs
    context_parts: list[str] = []
    seen_snippets: set[str] = set()
    for i, doc in enumerate(retrieved_docs, 1):
        metadata = doc.metadata if hasattr(doc, 'metadata') else {}

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
        f"✓ Vector search context built: {len(vector_search_context)} chars from {len(context_parts)} sources"
    )
    
    # Format backgrounds
    #logger.info(f"Backgrounds / use cases string: {backgrounds_str}")
    
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
