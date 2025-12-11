from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from typing import List
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from core.config import settings
import uuid
import logging
import types

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self):
        # Use OpenAI text-embedding-3-small for all embeddings (user docs + cloud data)
        # Vector size: 1536 dimensions
        self._model_name = "text-embedding-3-small"
        self._vector_size = 1536
        self._embeddings = None
        
        # Single Qdrant client (cloud) for both user documents and summaries
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None,
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
    
    @property
    def embeddings(self):
        """Lazy-load OpenAI embeddings for both user documents and cloud collections (LangChain compatible)."""
        if self._embeddings is None:
            try:
                logger.info(f"Creating OpenAI embeddings with model {self._model_name} ({self._vector_size}D)...")
                self._embeddings = OpenAIEmbeddings(
                    model=self._model_name,
                    openai_api_key=settings.OPENAI_API_KEY
                )
                logger.info(f"✓ OpenAI embeddings initialized: {self._vector_size}D")
            except Exception as e:
                logger.error(f"❌ Failed to create embeddings: {type(e).__name__}: {str(e)}")
                self._embeddings = None
        return self._embeddings
    
    def get_collection_name(self, user_id: int) -> str:
        """Get the Qdrant collection name for a user."""
        return f"user_{user_id}_documents"
    
    def create_collection_if_not_exists(self, user_id: int, vector_size: int = 1536):
        """Create a Qdrant collection for a user if it doesn't exist."""
        collection_name = self.get_collection_name(user_id)
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            if collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config={"size": vector_size, "distance": "Cosine"}
                )
        except Exception as e:
            print(f"Error creating collection: {e}")
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
    
    def search_reddit_posts(self, query: str, k: int = 3) -> List[Document]:
        """Search marketing summaries from the shared cloud Qdrant collection."""
        try:
            logger.info(f"🔍 Searching summaries in cloud Qdrant, k={k}")
            logger.info(f"Query text: '{query[:100]}...'")
            
            # Check if collection exists
            logger.info("Connecting to cloud Qdrant...")
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            logger.info(f"Available collections in cloud Qdrant: {collection_names}")
            
            # Use the unified summaries collection
            collection_name_to_use = "summaries_1_0"
            if collection_name_to_use not in collection_names:
                logger.warning(
                    f"❌ summaries_1_0 collection not found in cloud Qdrant. "
                    f"Available collections: {collection_names}"
                )
                return []
            
            # Get collection info
            try:
                collection_info = self.client.get_collection(collection_name_to_use)
                # Access vector size - handle different Qdrant client versions
                try:
                    # Try standard access pattern
                    actual_vector_size = collection_info.config.params.vectors.size
                except (AttributeError, TypeError):
                    try:
                        # Try alternative access pattern
                        actual_vector_size = collection_info.config.vectors.size
                    except (AttributeError, TypeError):
                        # Try direct access
                        actual_vector_size = getattr(collection_info.config, 'vectors', {}).get('size') or \
                                           getattr(collection_info.config.params, 'vectors', {}).get('size')
                        if actual_vector_size is None:
                            logger.error(f"❌ Could not determine vector size from collection config")
                            logger.error(f"Collection config structure: {collection_info.config}")
                            return []
                
                points_count = getattr(collection_info, 'points_count', 0)
                logger.info(f"Collection info: {points_count} points, {actual_vector_size}D vectors")
            except Exception as e:
                logger.error(f"❌ Error getting collection info: {type(e).__name__}: {str(e)}", exc_info=True)
                return []
            
            # Generate query embedding using OpenAI text-embedding-3-small
            try:
                if actual_vector_size == 1536:
                    # Collection uses text-embedding-3-small (3072D)
                    logger.info("Generating query embedding with text-embedding-3-small (1536D)...")
                    embeddings = self.embeddings  # OpenAI embeddings
                    if embeddings is None:
                        logger.error("❌ OpenAI embeddings not initialized!")
                        return []
                    query_vector = embeddings.embed_query(query)
                elif actual_vector_size == 384:
                    # Legacy: Collection uses 384D vectors (old SentenceTransformer setup)
                    logger.warning("⚠ Collection uses 384D vectors - expected 3072D. Please re-index your collection.")
                    logger.error("❌ Vector size mismatch! Expected 1536D, got 384D")
                    return []
                elif actual_vector_size == 3072:
                    # Legacy: Collection uses 1536D vectors (old OpenAI setup)
                    logger.warning("⚠ Collection uses 1536D vectors.")
                    logger.error("❌ Vector size mismatch! Expected 1536D, got D3072")
                    return []
                else:
                    logger.error(f"❌ Unsupported vector size: {actual_vector_size}D. Expected 3072.")
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
            logger.info(f"Performing similarity search with k={k}...")
            search_results = self.client.query_points(
                collection_name=collection_name_to_use,
                query=query_vector,
                limit=k,
                with_payload=True
            )
            logger.info(f"✓ Search completed: {len(search_results.points)} results")
            
            # Convert Qdrant results to LangChain Documents
            documents = []
            for i, point in enumerate(search_results.points, 1):
                # Log the payload to see what fields are available
                logger.info(f"Point {i} payload keys: {list(point.payload.keys())}")
                
                # Extract text from payload – prefer full text, then snippet/citation
                payload = point.payload or {}
                text = (
                    payload.get("text")
                    or payload.get("content")
                    or payload.get("snippet")
                    or payload.get("citation")
                    or ""
                )
                
                # Determine source type and doc type
                source = point.payload.get("source", "unknown")
                doc_type = point.payload.get("doc_type", "unknown")
                
                # Build metadata with all available fields (use None instead of "Unknown" for optional fields)
                metadata = {
                    "source": source,
                    "doc_type": doc_type,
                    "score": point.score,  # Similarity score from Qdrant

                    # Common fields across all document types
                    'citation': point.payload.get("citation"),
                    'citation_start_time': point.payload.get("citation_start_time"),
                    'icp_role_type': point.payload.get("icp_role_type"),
                    'title': point.payload.get("title"),
                    'channel': point.payload.get("channel"),
                    'type': point.payload.get("type"),

                    # Podcast-specific fields
                    'episode_url': point.payload.get("episode_url"),
                    'episode_number': point.payload.get("episode_number"),
                    'mp3_url': point.payload.get("mp3_url"),

                    # YouTube-specific fields
                    'video_url': point.payload.get("video_url"),
                    'description': point.payload.get("description"),

                    # Reddit-specific fields
                    'selftext': point.payload.get("selftext"),
                    'thread_author': point.payload.get("thread_author"),
                    'subreddit': point.payload.get("subreddit"),
                    'thread_url': point.payload.get("thread_url"),
                    # Support both legacy "detailed-explanation" and new "detailed_description"
                    'detailed-explanation': point.payload.get("detailed-explanation") or point.payload.get("discussion_description"),
                    'detailed_description': point.payload.get("detailed_description"),

                }
                
                # Generate appropriate filename based on doc_type
                if doc_type == "yt_summary":
                    filename = f"YouTube: {point.payload.get('title', '')}"
                elif doc_type == "reddit_post":
                    filename = f"Reddit Post: {point.payload.get('title', 'Untitled')}"
                elif doc_type == "reddit_thread":
                    filename = f"Reddit Thread: {point.payload.get('title', 'Untitled')}"
                elif doc_type == "reddit_comment":
                    filename = f"Reddit Comment by {point.payload.get('author_fullname', 'Unknown')}"
                elif doc_type == "podcast_summary":
                    filename = f"Podcast Summary: {point.payload.get('title', 'Untitled')}"
                else:
                    filename = f"{source.title()}: {doc_type.replace('_', ' ').title()}"
                
                metadata["filename"] = filename

                # Log what we extracted
                logger.info(f"Extracted metadata: source={source}, doc_type={doc_type}, filename={filename}, score={point.score}")
                
                # Create Document
                doc = Document(
                    page_content=text,
                    metadata=metadata
                )
                documents.append(doc)
                
            
            logger.info(f"✅ Retrieved {len(documents)} Documents  successfully")
            return documents
            
        except Exception as e:
            logger.error(f"❌ Error searching Documents: {type(e).__name__}: {str(e)}", exc_info=True)
            return []
    
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


vector_store = VectorStore()

