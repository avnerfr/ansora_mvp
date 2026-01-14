from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from typing import List
from qdrant_client.models import PointStruct, VectorParams, Distance
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, Prefetch
from core.config import settings
import uuid
import logging
import types
import nltk
import re
from langchain_text_splitters import (RecursiveCharacterTextSplitter, CharacterTextSplitter)
from openai import OpenAI
import os
from dotenv import load_dotenv
import json
from rag.s3_utils import get_latest_company_file
load_dotenv()


nltk.download('punkt')

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self):
        # Use OpenAI text-embedding-3-small for all embeddings (user docs + cloud data)
        # Vector size: 1536 dimensions
        self._model_name = "BAAI/bge-base-en-v1.5"
        self._vector_size = 768
        self._embeddings = None
        self._openai_api_key = settings.DEEPINFRA_API_KEY
        self._openai_base_url = settings.DEEPINFRA_API_BASE_URL
        
        # Single Qdrant client (cloud) for both user documents and summaries
        # Configure with increased timeout for operations that may take longer
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None,
            timeout=300.0,  # 5 minutes timeout for operations
        )

        # Backwards-compatibility shim: some LangChain Qdrant versions expect
        # QdrantClient.search(), which was removed in newer qdrant-client
        # versions in favor of query_points(). We provide a thin wrapper so
        # retrievers work without pinning an old client version.
        if not hasattr(self.client, "search"):
            def _search(  # type: ignore[override]
                client_self,
                collection_name: str,
                query_vector,
                query_filter=None,
                limit: int = 10,
                with_payload: bool = True,
                **kwargs,
            ):
                """
                Compatibility wrapper for older LangChain QdrantVectorStore, which
                expects `QdrantClient.search(...)` to exist and return an iterable
                of ScoredPoint objects (each having `.payload`, `.id`, `.score`, …).

                Newer `qdrant-client` versions removed `.search` in favor of
                `.query_points`, which returns a `ScoredPoint` collection object
                with a `.points` list. This shim adapts the old call signature to
                the new client API and always returns a list of points.
                """
                res = client_self.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=with_payload,
                    **kwargs,
                )
                # qdrant-client>=1.0 returns a response object with `.points`
                if hasattr(res, "points") and isinstance(res.points, list):
                    return res.points
                # Some client versions may already return a list/tuple of points
                if isinstance(res, (list, tuple)):
                    return list(res)
                return res

            # Monkey‑patch client.search so that LangChain can call it
            self.client.search = types.MethodType(_search, self.client)
    
    def str_to_qdrant_id(self, str_id: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, str_id.strip().lower()))
    
    @property
    def embeddings(self):
        """Lazy-load OpenAI embeddings for both user documents and cloud collections (LangChain compatible)."""
        if self._embeddings is None:
            try:
                #logger.info(f"Creating OpenAI embeddings with model {self._model_name} ({self._vector_size}D)...")
                #logger.info(f">>>>>>>>>>>>>_openai_api_key {self._openai_api_key}")
                #logger.info(f">>>>>>>>>>>>>_openai_base_url {self._openai_base_url}")

                self._embeddings = OpenAIEmbeddings(
                    model=self._model_name,
                    openai_api_key=self._openai_api_key,
                    base_url=self._openai_base_url
                )
                #logger.info(f"✓ OpenAI embeddings initialized: {self._vector_size}D")
            except Exception as e:
                logger.error(f"❌ Failed to create embeddings: {type(e).__name__}: {str(e)}")
                self._embeddings = None
        return self._embeddings

    def chunking(self, text, model: str = "nltk") -> List[str]:
        """Chunk the text into a list of strings."""
        if model == "nltk":
            try:
                return nltk.sent_tokenize(text)
            except Exception as e:
                logger.error(f"❌ Error chunking text: {e}")
            return [text]
        return [text]

    def chunking_langchain(self, text: str,recursive_splitter = False) -> List[str]:
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
            logger.error(f"Error chunking text: {e}", exc_info=True)
            return [text]   

    def chunking_naive(self, text: str) -> List[str]:
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
            logger.error(f"Error chunking text: {e}", exc_info=True)
            return [text]


    
    def get_collection_name(self, user_id: int) -> str:
        """Get the Qdrant collection name for a user."""
        return f"user_{user_id}_documents"
    
    def resolve_collection_name(self, domain: str, suffix: str = "summaries_1_0") -> str:
        """
        Resolve the correct collection name from domain, trying all possible variations.
        Domain may contain spaces, underscores, or hyphens in any combination.
        Qdrant collection names may use any of these separators.
        
        Args:
            domain: Company domain (e.g., "Cloud Media Management", "software_developement_optimization")
            suffix: Collection suffix (default: "summaries_1_0")
            
        Returns:
            The first matching collection name found in Qdrant, or the lowercase underscore version as fallback
        """
        if not domain:
            logger.warning("Empty domain provided to resolve_collection_name")
            return None
        
        # Generate all possible variations of the domain
        variations = self._generate_domain_variations(domain)
        
        # Append suffix to each variation
        collection_candidates = [f"{var}-{suffix}" for var in variations]
        
        # Add variations with underscore separator too
        collection_candidates.extend([f"{var}_{suffix}" for var in variations])
        
        # Remove duplicates while preserving order
        seen = set()
        collection_candidates = [x for x in collection_candidates if not (x in seen or seen.add(x))]
        
        logger.info(f"Checking {len(collection_candidates)} possible collection names for domain '{domain}'")
        logger.info(f"Collection candidates: {collection_candidates[:5]}...")  # Log first 5
        
        try:
            # Get all existing collections from Qdrant
            collections = self.client.get_collections().collections
            existing_collection_names = [c.name for c in collections]
            logger.debug(f"Found {len(existing_collection_names)} existing collections in Qdrant")
            

            # Try to find a match
            for candidate in collection_candidates:
                if candidate in existing_collection_names:
                    logger.info(f"✓ Resolved collection name: '{candidate}' for domain '{domain}'")
                    return candidate
            
            # No match found - return the most common format as fallback
            fallback = f"{domain.lower().replace(' ', '_').replace('-', '_')}-{suffix}"
            logger.warning(f"No matching collection found for domain '{domain}'. Using fallback: '{fallback}'")
            logger.debug(f"Available collections: {existing_collection_names[:10]}")
            return fallback
            
        except Exception as e:
            logger.error(f"Error resolving collection name: {e}", exc_info=True)
            # Return fallback on error
            fallback = f"{domain.lower().replace(' ', '_').replace('-', '_')}-{suffix}"
            return fallback
    
    def _generate_domain_variations(self, domain: str) -> List[str]:
        """
        Generate all possible variations of a domain string with different separators.
        
        Examples:
            "Cloud Media Management" → ["cloud-media-management", "cloud_media_management", "cloudmediamanagement", ...]
            "software_developement_optimization" → ["software-developement-optimization", "software_developement_optimization", ...]
        """
        # Normalize to lowercase
        domain_lower = domain.lower()
        
        # Split by any separator (space, underscore, hyphen)
        parts = re.split(r'[\s_-]+', domain_lower)
        
        # Generate variations:
        # 1. hyphen-separated
        # 2. underscore-separated
        # 3. no separator (concatenated)
        # 4. Original format preserved (if it had specific separators)
        
        variations = [
            '-'.join(parts),          # hyphen-separated
            '_'.join(parts),          # underscore-separated
            ''.join(parts),           # no separator
            domain_lower.replace(' ', '-').replace('_', '-'),   # all hyphens
            domain_lower.replace(' ', '_').replace('-', '_'),   # all underscores
            domain_lower.replace(' ', '').replace('_', '').replace('-', ''),  # no separators
        ]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variations = [x for x in variations if x and not (x in seen or seen.add(x))]
        
        return unique_variations
    
    def create_collection_if_not_exists(self, user_id: int, vector_size: int = None):
        """Create a Qdrant collection for a user if it doesn't exist."""
        if vector_size is None:
            vector_size = self._vector_size  # Use the model's vector size
        collection_name = self.get_collection_name(user_id)
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            if collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config={"size": vector_size, "distance": "Cosine"}
                )
                logger.info(f"Created collection {collection_name} with vector size {vector_size}")
        except Exception as e:
            logger.error(f"Error creating collection: {e}", exc_info=True)
            # Collection might already exist, continue
    
    def add_documents(
        self,
        user_id: int,
        documents: List[Document],
        file_id: int,
        filename: str,
        file_type: str
    ) -> None:
        """Add documents to the user's vector store."""
        collection_name = self.get_collection_name(user_id)
        self.create_collection_if_not_exists(user_id)
        
        # Add metadata to documents
        for doc in documents:
            doc.metadata.update({
                "user_id": user_id,
                "file_id": file_id,
                "filename": filename,
                "file_type": file_type,
            })
        
        # Use Qdrant vector store
        vector_store = Qdrant(
            client=self.client,
            collection_name=collection_name,
            embeddings=self.embeddings,
        )
        vector_store.add_documents(documents)
    
    def get_retriever(self, user_id: int, k: int = 5):
        """Get a retriever for the user's vector store."""
        collection_name = self.get_collection_name(user_id)
        vector_store = Qdrant(
            client=self.client,
            collection_name=collection_name,
            embeddings=self.embeddings,
        )
        return vector_store.as_retriever(search_kwargs={"k": k})


    
    def search_doc_type(self, query: str, k: int = 3, doc_type: str = "reddit_post", company_enumerations: List[str] = [], collection_name: str = None, company_name: str = None) -> List[Document]:
        """Search marketing summaries from the shared cloud Qdrant collection."""
        try:
            logger.info(f"🔍 Searching summaries in cloud Qdrant, k={k}, doc_type={doc_type}, company_name={company_name}, collection={collection_name}")

            embeddings = self.embeddings  # OpenAI embeddings
            if embeddings is None:
                logger.error("❌ OpenAI embeddings not initialized!")
                return []
            logger.info(f"Query: {query}")

            openai_client = OpenAI(api_key=settings.DEEPINFRA_API_KEY, base_url=settings.DEEPINFRA_API_BASE_URL)
            response = openai_client.embeddings.create(
                input=query,
                model=self._model_name
            )
            query_vector = response.data[0].embedding
            logger.info(f"###########  After reload must remove the security_control_surface from the code ###########")


            search_results_old = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=k,
                with_payload=True,
                with_vectors=False,
               query_filter=Filter(
                    must=[FieldCondition(key="doc_type", match=MatchValue(value=doc_type)),
                        FieldCondition(key="domain", match=MatchAny(any=company_enumerations.get("domain", []))),
                        FieldCondition(key="operational_surface", match=MatchAny(any=company_enumerations.get("operational_surface", []))),
                        FieldCondition(key="security_control_surface", match=MatchAny(any=company_enumerations.get("execution_surface", []))),
                        FieldCondition(key="failure_type", match=MatchAny(any=company_enumerations.get("failure_type", [])))
                    ]
                ),
            )
            search_results_new = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=k,
                with_payload=True,
                with_vectors=False,

                query_filter=Filter(
                    must=[FieldCondition(key="doc_type", match=MatchValue(value=doc_type)),
                        FieldCondition(key="domain", match=MatchAny(any=company_enumerations.get("domain", []))),
                        FieldCondition(key="operational_surface", match=MatchAny(any=company_enumerations.get("operational_surface", []))),
                        FieldCondition(key="execution_surface", match=MatchAny(any=company_enumerations.get("execution_surface", []))),
                        FieldCondition(key="failure_type", match=MatchAny(any=company_enumerations.get("failure_type", [])))
                    ]
                ),
            )
            
            # Combine points from both responses, deduplicate by ID, and sort by score
            combined_points = {}
            for point in search_results_old.points:
                combined_points[point.id] = point
            for point in search_results_new.points:
                # Keep the point with higher score if duplicate
                if point.id not in combined_points or point.score > combined_points[point.id].score:
                    combined_points[point.id] = point
            
            # Sort by score descending and limit to k
            sorted_points = sorted(combined_points.values(), key=lambda p: p.score, reverse=True)[:k]
            
            logger.info(f"✓ Search completed: {len(sorted_points)} results (combined from {len(search_results_old.points)} + {len(search_results_new.points)} points)")
            return sorted_points
        except Exception as e:
            logger.error(f"❌ Error searching Documents: {type(e).__name__}: {str(e)}", exc_info=True)
            return []
            
    def search_reddit_posts(self, query: str, k: int = 3, company_enumerations: List[str] = [], collection_name: str = None, company_name: str = None) -> List[Document]:
        search_results_points = self.search_doc_type(query, k, "reddit_post", company_enumerations,collection_name, company_name)

        # Convert Qdrant results to LangChain Documents
        documents = []
        for i, point in enumerate(search_results_points, 1):
            # Extract text from payload – prefer full text, then snippet/citation
            payload = point.payload or {}
            text = (payload.get("text") or payload.get("content") or payload.get("snippet") or payload.get("citation")) or ""
            
            doc_type = "reddit_post"
            
            # Get post_id from payload - try multiple possible field names
            post_id = payload.get("post_id") or payload.get("id")
            
            # Build metadata with all available fields (use None instead of "Unknown" for optional fields)
            metadata = {
                "doc_type": doc_type,
                "score": point.score,  # Similarity score from Qdrant

                # Common fields across all document types
                'title': payload.get("title"),
                'citation': payload.get("citation"),
                "detailed_description": payload.get("detailed_description"),
                'selftext': payload.get("selftext"),
                "summary": payload.get("summary"),
                "key_issues": payload.get("key_issues"),
                "pain_phrases": payload.get("pain_phrases"),
                "emotional_triggers": payload.get("emotional_triggers"),
                "buyer_language": payload.get("buyer_language"),
                "implicit_risks": payload.get("implicit_risks"),
                'url': payload.get("thread_url"),
                'thread_author': payload.get("thread_author"),
                'subreddit': payload.get("subreddit"),
                'post_id': post_id,  # Add post_id for duplicate filtering

                'citation_start_time': payload.get("citation_start_time"),
                'icp_role_type': payload.get("icp_role_type"),
                "ups": payload.get("ups"),
                "tone": payload.get("tone"),
                "classification": payload.get("classification"),
                "date_created_utc": payload.get("date_created_utc"),
                "flair_text": payload.get("flair_text"),
            }
            # Debug logging for post_id
            #logger.debug(f"Reddit post {i}: post_id={post_id}, title={payload.get('title', 'N/A')[:50]}")


            # Generate appropriate filename based on doc_type
            filename = f"Reddit Post: {payload.get('title', 'Untitled')}"
           
            metadata["filename"] = filename

            # Log what we extracted
            #logger.info(f"Extracted Reddit Post metadata:  title={filename}, summary={payload.get('summary', 'Untitled')}, score={point.score}")

            # Create Document
            doc = Document(
                page_content=text,
                metadata=metadata
            )
            documents.append(doc)
            
        
        logger.info(f"✅ Retrieved {len(documents)} Documents  successfully")
        return documents
        

    
    def search_youtube_summaries(self, query: str, k: int = 3, company_enumerations: List[str] = [], collection_name: str = None, company_name: str = None) -> List[Document]:
        search_results_points = self.search_doc_type(query, k, "yt_summary", company_enumerations, collection_name, company_name)

    def search_reddit_posts_minimal_filter(self, query: str, k: int = 10, collection_name: str = None, doc_type: str = "reddit_post") -> List[Document]:
        """
        Search Reddit posts with minimal filtering - only doc_type filter.
        Useful for competitive intelligence and battle cards where we want broad coverage.
        No company-specific metadata filters applied.
        """
        try:
            logger.info(f"🔍 Minimal filter search: k={k}, doc_type={doc_type}, collection={collection_name}")
            
            if self.embeddings is None:
                logger.error("❌ OpenAI embeddings not initialized!")
                return []
            
            logger.info(f"Query: {query[:100]}...")
            
            # Embed the query
            openai_client = OpenAI(api_key=settings.DEEPINFRA_API_KEY, base_url=settings.DEEPINFRA_API_BASE_URL)
            response = openai_client.embeddings.create(
                input=query,
                model=self._model_name
            )
            query_vector = response.data[0].embedding
            
            # Search with only doc_type filter (no company enumeration filters)
            search_results = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=k,
                with_payload=True,
                with_vectors=False,
                query_filter=Filter(
                    must=[FieldCondition(key="doc_type", match=MatchValue(value=doc_type))]
                )
            )
            
            # Convert to Documents
            documents = []
            for i, point in enumerate(search_results.points, 1):
                payload = point.payload or {}
                
                # Try multiple fields for text content
                text = (
                    payload.get("text") or 
                    payload.get("content") or 
                    payload.get("full_text") or
                    payload.get("selftext") or
                    payload.get("snippet") or 
                    payload.get("summary") or
                    payload.get("citation") or 
                    ""
                )
                
                metadata = {
                    "doc_type": doc_type,
                    "score": point.score,
                    "title": payload.get("title"),
                    "citation": payload.get("citation"),
                    "url": payload.get("url"),
                    "link": payload.get("link"),
                    "summary": payload.get("summary"),
                    **payload  # Include all payload fields
                }
                
                doc = Document(page_content=text, metadata=metadata)
                documents.append(doc)
                
                # Enhanced logging
                title_preview = metadata.get('title', 'Untitled')[:50]
                text_length = len(text)
                has_citation = bool(metadata.get('citation') or metadata.get('url') or metadata.get('link'))
                logger.info(f"  {i}. {title_preview}... (score: {point.score:.4f}, text_len: {text_length}, has_link: {has_citation})")
            
            logger.info(f"✅ Retrieved {len(documents)} documents with minimal filter")
            return documents
            
        except Exception as e:
            logger.error(f"❌ Error in minimal filter search: {type(e).__name__}: {str(e)}", exc_info=True)
            return []

    def search_youtube_summaries(self, query: str, k: int = 3, company_enumerations: List[str] = [], collection_name: str = None, company_name: str = None) -> List[Document]:
        search_results_points = self.search_doc_type(query, k, "yt_summary", company_enumerations, collection_name, company_name)

        # Convert Qdrant results to LangChain Documents
        documents = []
        for i, point in enumerate(search_results_points, 1):
            # Log the payload to see what fields are available
            #logger.info(f"Point {i} payload keys: {list(point.payload.keys())}")
            
            # Extract text from payload – prefer full text, then snippet/citation
            payload = point.payload or {}
            text = (payload.get("text") or payload.get("content") or payload.get("snippet") or payload.get("citation")) or ""
            
            doc_type = "yt_summary"
            
            # Build metadata with all available fields (use None instead of "Unknown" for optional fields)
            metadata = {
                "doc_type": doc_type,
                "score": point.score,  # Similarity score from Qdrant

                # Common fields across all document types
                'citation': point.payload.get("citation"),
                'citation_start_time': point.payload.get("citation_start_time"),
                'icp_role_type': point.payload.get("icp_role_type"),
                'title': point.payload.get("title"),
                'channel': point.payload.get("channel"),
                'type': point.payload.get("type"),
                'key_issues': point.payload.get("key_issues"),
                'pain_phrases': point.payload.get("pain_phrases"),
                'emotional_triggers': point.payload.get("emotional_triggers"),
                'implicit_risks': point.payload.get("implicit_risks"),
                'buyer_language': point.payload.get("buyer_language"),

                # YouTube-specific fields
                'url': point.payload.get("video_url"),
                'video_url': point.payload.get("video_url"),  # Also store as video_url for consistency
                'description': point.payload.get("description"),
 
                'detailed_description': point.payload.get("detailed_description"),

            }
      
            # Generate appropriate filename based on doc_type
            filename = f"YouTube Summary: {point.payload.get('title', 'Untitled')}"
           
            metadata["filename"] = filename

            # Log what we extracted
            logger.debug("=================================================================================")
            logger.debug(f"Extracted metadata:  doc_type={doc_type}, filename={filename}, score={point.score}, {point.payload.get('key_issues')}, {point.payload.get('pain_phrases')}, {point.payload.get('emotional_triggers')}, {point.payload.get('implicit_risks')}, {point.payload.get('buyer_language')}")
            logger.debug("=================================================================================")

            # Create Document
            doc = Document(
                page_content=text,
                metadata=metadata
            )
            documents.append(doc)
        
        logger.info(f"✅ Retrieved {len(documents)} Documents  successfully")
        return documents

    def search_podcast_summaries(self, query: str, k: int = 3, company_enumerations: List[str] = [],collection_name: str = None, company_name: str = None) -> List[Document]:
        search_results_points = self.search_doc_type(query, k, "podcast_summary", company_enumerations, collection_name,  company_name)

        # Convert Qdrant results to LangChain Documents
        documents = []
        for i, point in enumerate(search_results_points, 1):
            # Log the payload to see what fields are available
            #logger.info(f"Point {i} payload keys: {list(point.payload.keys())}")
            
            # Extract text from payload – prefer full text, then snippet/citation
            payload = point.payload or {}
            text = (payload.get("text") or payload.get("content") or payload.get("snippet") or payload.get("citation")) or ""
            
            doc_type = "podcast_summary"
            
            # Build metadata with all available fields (use None instead of "Unknown" for optional fields)
            metadata = {
                "doc_type": doc_type,
                "score": point.score,  # Similarity score from Qdrant

                # Common fields across all document types
                'citation': point.payload.get("citation"),
                'citation_start_time': point.payload.get("citation_start_time"),
                'icp_role_type': point.payload.get("icp_role_type"),
                'title': point.payload.get("title"),
                'channel': point.payload.get("channel"),
                'type': point.payload.get("type"),
                'key_issues': point.payload.get("key_issues"),
                'pain_phrases': point.payload.get("pain_phrases"),
                'emotional_triggers': point.payload.get("emotional_triggers"),
                'implicit_risks': point.payload.get("implicit_risks"),
                'buyer_language': point.payload.get("buyer_language"),
                # Podcast-specific fields
                'episode_url': point.payload.get("episode_url"),
                'episode_number': point.payload.get("episode_number"),
                'mp3_url': point.payload.get("mp3_url") or point.payload.get("mp3_link"),

                'detailed_description': point.payload.get("detailed_description"),

            }
            
            # Generate appropriate filename based on doc_type
            filename = f"Podcast Summary: {point.payload.get('title', 'Untitled')}"
        
            metadata["filename"] = filename

            # Log what we extracted
          
            # Create Document
            doc = Document(
                page_content=text,
                metadata=metadata
            )
            documents.append(doc)
            
        
        logger.info(f"✅ Retrieved {len(documents)} Documents  successfully")
        return documents

    def clear_user_collection(self, user_id: int) -> bool:
        """Delete a user's collection from local Qdrant."""
        try:
            collection_name = self.get_collection_name(user_id)
            logger.info(f"Attempting to clear collection: {collection_name}")
            
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if collection_name in collection_names:
                self.client.delete_collection(collection_name=collection_name)
                logger.info(f"✓ Cleared collection: {collection_name}")
                return True
            else:
                logger.info(f"Collection {collection_name} does not exist, nothing to clear")
                return False
                
        except Exception as e:
            logger.error(f"✗ Error clearing collection for user {user_id}: {type(e).__name__}: {str(e)}")
            return False

    def upsert_document(self, collection_name: str, text: str, metadata: dict) -> bool:
        """Upsert a single document into a collection."""
        try:
            
            # Generate embedding
            if self.embeddings is None:
                logger.error("Embeddings not initialized")
                return False
            logger.debug(f"Generating embedding for text: {text[:100]}...")
            vector = self.embeddings.embed_query(text)
            logger.debug(f"✓ Vector generated: {len(vector)}D")

            # Generate unique ID
            # If metadata["id"] is already a UUID string, use it directly; otherwise hash it
            point_id_str = str(metadata["id"])
            try:
                # Try to parse as UUID to check if it's already a valid UUID
                uuid.UUID(point_id_str)
                # It's a valid UUID, use it directly (Qdrant accepts UUID strings)
                point_id = point_id_str
            except (ValueError, AttributeError, TypeError):
                # Not a UUID, use the hash function to generate a deterministic UUID5
                point_id = self.str_to_qdrant_id(point_id_str)
            logger.debug("✓ Point ID generated: " + str(point_id))
            # Upsert point
            self.client.upsert(
                collection_name=collection_name,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=metadata
                    )
                ]
            )
            
            logger.info(f"✓ Upserted document to {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"✗ Error upserting document: {type(e).__name__}: {str(e)}")
            return False


vector_store = VectorStore()

