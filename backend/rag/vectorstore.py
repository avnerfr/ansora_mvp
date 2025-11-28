from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from typing import List
from langchain_core.documents import Document
from core.config import settings
import uuid
import logging

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=settings.OPENAI_API_KEY
        )
        
        # Local Docker Qdrant (user documents)
        self.client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None
        )
        
        # Cloud Qdrant (Reddit posts)
        self.cloud_client = QdrantClient(
            url="https://c4c03fda-2e4b-45d9-bf2f-e442ba883e0b.eu-west-1-0.aws.cloud.qdrant.io:6333",
            api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.s53XfrTWp0MHokNbtLSx2ikhLdi9Miru2Q99NxACFo8"
        )
    
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
        """Search Reddit posts from cloud Qdrant database."""
        try:
            logger.info(f"🔍 Searching Reddit posts in cloud Qdrant, k={k}")
            logger.info(f"Query text: '{query[:100]}...'")
            
            # Check if collection exists
            logger.info("Connecting to cloud Qdrant...")
            collections = self.cloud_client.get_collections().collections
            collection_names = [c.name for c in collections]
            logger.info(f"Available collections in cloud Qdrant: {collection_names}")
            
            if "reddit_posts" not in collection_names:
                logger.warning("❌ reddit_posts collection not found in cloud Qdrant")
                logger.warning(f"Available collections: {collection_names}")
                return []
            
            logger.info("✓ reddit_posts collection found")
            
            # Get collection info
            collection_info = self.cloud_client.get_collection("reddit_posts")
            logger.info(f"Collection info: {collection_info.points_count} points, {collection_info.config.params.vectors.size}D vectors")
            
            # Generate query embedding
            logger.info("Generating query embedding...")
            query_vector = self.embeddings.embed_query(query)
            logger.info(f"✓ Query vector generated: {len(query_vector)}D")
            
            # Search using direct Qdrant client API
            logger.info(f"Performing similarity search with k={k}...")
            search_results = self.cloud_client.query_points(
                collection_name="reddit_posts",
                query=query_vector,
                limit=k,
                with_payload=True
            )
            logger.info(f"✓ Search completed: {len(search_results.points)} results")
            
            # Convert Qdrant results to LangChain Documents
            documents = []
            for i, point in enumerate(search_results.points, 1):
                # Extract text from payload
                text = point.payload.get('text', '') or point.payload.get('content', '')
                
                # Create metadata
                metadata = {
                    "source_type": "reddit",
                    "author": point.payload.get('author', 'Unknown'),
                    "filename": f"Reddit: {point.payload.get('author', 'Unknown')}",
                    "file_type": "reddit_post",
                    "thread_url": point.payload.get('thread_url', ''),
                    "timestamp": point.payload.get('timestamp', ''),
                    "score": point.score if hasattr(point, 'score') else 0.0,
                }
                
                # Create Document
                doc = Document(
                    page_content=text,
                    metadata=metadata
                )
                documents.append(doc)
                
                logger.info(f"Result {i}: {len(text)} chars, author: {metadata['author']}, score: {metadata['score']:.4f}")
            
            logger.info(f"✅ Retrieved {len(documents)} Reddit posts successfully")
            return documents
            
        except Exception as e:
            logger.error(f"❌ Error searching Reddit posts: {type(e).__name__}: {str(e)}", exc_info=True)
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

