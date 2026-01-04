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
                logger.info(f"Creating OpenAI embeddings with model {self._model_name} ({self._vector_size}D)...")
                #logger.info(f">>>>>>>>>>>>>_openai_api_key {self._openai_api_key}")
                #logger.info(f">>>>>>>>>>>>>_openai_base_url {self._openai_base_url}")

                self._embeddings = OpenAIEmbeddings(
                    model=self._model_name,
                    openai_api_key=self._openai_api_key,
                    base_url=self._openai_base_url
                )
                logger.info(f"✓ OpenAI embeddings initialized: {self._vector_size}D")
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


    
    def search_doc_type(self, query: str, k: int = 3, doc_type: str = "reddit_post", company_enumerations: List[str] = [], company_name: str = None) -> List[Document]:
        """Search marketing summaries from the shared cloud Qdrant collection."""
        try:
            logger.info(f"🔍 Searching summaries in cloud Qdrant, k={k}")
            
            # Check if collection exists
            logger.info("Connecting to cloud Qdrant...")
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            logger.info(f"Available collections in cloud Qdrant: {collection_names}")
            
            # Use the unified summaries collection
            collection_name_to_use = None# os.getenv("SUMMARIES_COLLECTION_NAME")
            

            
            # If not set, try to get company domain and construct collection name
            if not collection_name_to_use:
                company_domain = None
                if company_name:
                    logger.info(f"Attempting to get company domain for: {company_name}")
                    try:
                        # Get company information from S3 to extract domain
                        company_file = get_latest_company_file(company_name)
                        if company_file and 'data' in company_file:
                            company_data = company_file['data']
                            company_analysis = company_data.get('company_analysis', '')
                            if company_analysis:
                                try:
                                    # Try to extract JSON from company_analysis
                                    json_match = re.search(r'```json\s*(.*?)\s*```', company_analysis, re.DOTALL)
                                    if json_match:
                                        company_json = json.loads(json_match.group(1).strip())
                                        company_domain = company_json.get('company_domain', '')
                                        logger.info(f"Extracted company_domain from JSON block: {company_domain}")
                                    else:
                                        # Try parsing as direct JSON
                                        company_json = json.loads(company_analysis)
                                        company_domain = company_json.get('company_domain', '')
                                        logger.info(f"Extracted company_domain from direct JSON: {company_domain}")
                                except (json.JSONDecodeError, AttributeError) as e:
                                    logger.warning(f"Error parsing company_analysis for {company_name}: {e}")
                            else:
                                logger.warning(f"No company_analysis found in company file for {company_name}")
                        else:
                            logger.warning(f"No company file found for {company_name}")
                    except Exception as e:
                        logger.warning(f"Error getting company file for {company_name}: {e}", exc_info=True)
                else:
                    logger.info("No company_name provided, will use auto-detection")
                
                # Construct collection name based on domain
                if company_domain:
                    # Normalize domain: lowercase, replace spaces with underscores
                    domain_normalized = company_domain.lower().replace(' ', '_')
                    collection_name_to_use = f"{domain_normalized}-summaries_1_0"
                    logger.info(f"✓ Using collection based on company domain: {collection_name_to_use} (domain: {company_domain}, normalized: {domain_normalized})")
                    
                    # Check if the domain-based collection exists
                    if collection_name_to_use not in collection_names:
                        logger.warning(f"⚠ Domain-based collection '{collection_name_to_use}' not found. Available collections: {collection_names}")
                        # Still use the domain-based name - don't fall back to generic collections
                        # This ensures we always use the domain format when domain is available
                else:
                    logger.info("No company domain found, will use auto-detection")
                
                # Only fall back to auto-detection if no domain was found
                if not collection_name_to_use:
                    # Try to find any summaries collection (prefer newer versions)
                    summaries_collections = [name for name in collection_names if 'summaries' in name.lower()]
                    if summaries_collections:
                        # Sort to prefer newer versions (higher numbers)
                        summaries_collections.sort(reverse=True)
                        collection_name_to_use = summaries_collections[0]
                        logger.info(f"Auto-detected collection: {collection_name_to_use} (from available: {collection_names})")
                    else:
                        logger.warning(f"❌ No SUMMARIES_COLLECTION_NAME set and no summaries collection found. Available collections: {collection_names}")
                        return []
            
            if collection_name_to_use not in collection_names:
                logger.warning(f"❌ {collection_name_to_use} not found in cloud Qdrant. Available collections: {collection_names}")
                return []
            
            # Get collection info
            try:
                collection_info = self.client.get_collection(collection_name_to_use)
                # Access vector size - handle different Qdrant client versions
                actual_vector_size = collection_info.config.params.vectors.size
                points_count = getattr(collection_info, 'points_count', 0)
                logger.info(f"Collection info: {points_count} points, {actual_vector_size}D vectors")
            except Exception as e:
                logger.error(f"❌ Error getting collection info: {type(e).__name__}: {str(e)}", exc_info=True)
                return []
            
            # Generate query embedding using OpenAI text-embedding-3-small
            try:
                if actual_vector_size == 768:
                    # Collection uses BAAI/bge-base-en-v1.5 (768D)
                    logger.info("Generating query embedding with BAAI/bge-base-en-v1.5")
                    embeddings = self.embeddings  # OpenAI embeddings
                    if embeddings is None:
                        logger.error("❌ OpenAI embeddings not initialized!")
                        return []
                    logger.info(f">>>>>>>>>>>>>embed_query {query}")

                    openai_client = OpenAI(api_key=settings.DEEPINFRA_API_KEY, base_url=settings.DEEPINFRA_API_BASE_URL)
                    response = openai_client.embeddings.create(
                        input=query,
                        model=self._model_name
                    )
                    query_vector = response.data[0].embedding
                elif actual_vector_size == 384:
                    # Legacy: Collection uses 384D vectors (old SentenceTransformer setup)
                    logger.warning("⚠ Collection uses 384D vectors - expected 768D. Please re-index your collection.")
                    logger.error(f"❌ Vector size mismatch! Expected 768D, got 384D")
                    return []
                elif actual_vector_size == 3072:
                    # Legacy: Collection uses 3072D vectors (old OpenAI setup)
                    logger.warning("⚠ Collection uses 3072D vectors - expected 768D. Please re-index your collection.")
                    logger.error(f"❌ Vector size mismatch! Expected 768D, got 3072D")
                    return []
                elif actual_vector_size == 1536:
                    # Legacy: Collection uses 1536D vectors (old OpenAI setup)
                    logger.warning("⚠ Collection uses 1536D vectors - expected 768D. Please re-index your collection.")
                    logger.error(f"❌ Vector size mismatch! Expected 768D, got 1536D")
                    return []
                else:
                    logger.error(f"❌ Unsupported vector size: {actual_vector_size}D. Expected 768D.")
                    return []
                
                logger.info(f"✓ Query vector generated: {len(query_vector)}D")
                
                # Verify vector size matches
                if len(query_vector) != actual_vector_size:
                    logger.error(f"❌ Vector size mismatch! Query: {len(query_vector)}D, Collection: {actual_vector_size}D")
                    return []
            except Exception as e:
                logger.error(f"❌ Error generating query embedding: {type(e).__name__}: {str(e)}", exc_info=True)
                return []
            
            # Search using direct Qdrant client API
            logger.info(f"Performing similarity search with k={k} ")

            #logger.info(f"XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
            #logger.info(f"company_enumerations: {company_enumerations}")
            #logger.info(f"company_enumerations.get('domain'): {company_enumerations.get('domain')}")
            #logger.info(f"company_enumerations.get('operational_surface'): {company_enumerations.get('operational_surface')}")
            #logger.info(f"company_enumerations.get('execution_surface'): {company_enumerations.get('execution_surface')}")
            #logger.info(f"company_enumerations.get('failure_type'): {company_enumerations.get('failure_type')}")


            logger.info(f"###########  After reload must change the code here ###########")
            logger.info(f"###########  After reload must change the code here ###########")
            logger.info(f"###########  After reload must change the code here ###########")
            logger.info(f"###########  After reload must change the code here ###########")
            logger.info(f"###########  After reload must change the code here ###########")
            logger.info(f"###########  After reload must change the code here ###########")

            search_results_old = self.client.query_points(
                collection_name=collection_name_to_use,
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
                collection_name=collection_name_to_use,
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
            
    def search_reddit_posts(self, query: str, k: int = 3, company_enumerations: List[str] = [], company_name: str = None) -> List[Document]:
        search_results_points = self.search_doc_type(query, k, "reddit_post", company_enumerations, company_name)

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
            logger.debug(f"Reddit post {i}: post_id={post_id}, title={payload.get('title', 'N/A')[:50]}")


            # Generate appropriate filename based on doc_type
            filename = f"Reddit Post: {payload.get('title', 'Untitled')}"
           
            metadata["filename"] = filename

            # Log what we extracted
            logger.info(f"Extracted Reddit Post metadata:  title={filename}, summary={payload.get('summary', 'Untitled')}, score={point.score}")

            # Create Document
            doc = Document(
                page_content=text,
                metadata=metadata
            )
            documents.append(doc)
            
        
        logger.info(f"✅ Retrieved {len(documents)} Documents  successfully")
        return documents
        

    
    def search_youtube_summaries(self, query: str, k: int = 3, company_enumerations: List[str] = [], company_name: str = None) -> List[Document]:
        search_results_points = self.search_doc_type(query, k, "youtube_summary", company_enumerations, company_name)

        # Convert Qdrant results to LangChain Documents
        documents = []
        for i, point in enumerate(search_results_points, 1):
            # Log the payload to see what fields are available
            #logger.info(f"Point {i} payload keys: {list(point.payload.keys())}")
            
            # Extract text from payload – prefer full text, then snippet/citation
            payload = point.payload or {}
            text = (payload.get("text") or payload.get("content") or payload.get("snippet") or payload.get("citation")) or ""
            
            doc_type = "youtube_summary"
            
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
                'description': point.payload.get("description"),
 
                'detailed_description': point.payload.get("detailed_description"),

            }
            
            # Generate appropriate filename based on doc_type
            filename = f"YouTube Summary: {point.payload.get('title', 'Untitled')}"
           
            metadata["filename"] = filename

            # Log what we extracted
            logger.info(f"Extracted metadata:  doc_type={doc_type}, filename={filename}, score={point.score}, {point.payload.get('key_issues')}, {point.payload.get('pain_phrases')}, {point.payload.get('emotional_triggers')}, {point.payload.get('implicit_risks')}, {point.payload.get('buyer_language')}")
            
            # Create Document
            doc = Document(
                page_content=text,
                metadata=metadata
            )
            documents.append(doc)
            
        
        logger.info(f"✅ Retrieved {len(documents)} Documents  successfully")
        return documents

    def search_podcast_summaries(self, query: str, k: int = 3, company_enumerations: List[str] = [], company_name: str = None) -> List[Document]:
        search_results_points = self.search_doc_type(query, k, "podcast_summary", company_enumerations, company_name)

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
            logger.info(f"Extracted metadata:  doc_type={doc_type}, filename={filename}, score={point.score}, {point.payload.get('key_issues')}, {point.payload.get('pain_phrases')}, {point.payload.get('emotional_triggers')}, {point.payload.get('implicit_risks')}, {point.payload.get('buyer_language')}")
            
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

