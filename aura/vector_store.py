"""Vector database abstractions and implementations for AURA."""

import logging
import uuid
import numpy as np
from typing import Any, List, Tuple, Optional

logger = logging.getLogger(__name__)

class VectorStore:
    """Base interface for vector database engines."""
    
    def add_paper(self, arxiv_id: str, embedding: np.ndarray) -> None:
        """Add a single paper embedding to the vector store."""
        pass
        
    def add_papers_batch(self, arxiv_ids: List[str], embeddings: List[np.ndarray]) -> None:
        """Add a batch of paper embeddings to the vector store."""
        pass
        
    def search_similar(self, query_emb: np.ndarray, limit: int = 5) -> List[Tuple[str, float]]:
        """Find top similar papers based on query vector. Returns lists of (arxiv_id, similarity_score)."""
        return []
        
    def delete_paper(self, arxiv_id: str) -> None:
        """Remove a paper from the vector store."""
        pass


class NumpyVectorStore(VectorStore):
    """Fallback vector store that queries database and performs in-memory numpy similarity."""
    
    def __init__(self, db: Any):
        self.db = db
        
    def add_paper(self, arxiv_id: str, embedding: np.ndarray) -> None:
        # SQLite database already handles storing embeddings natively
        pass
        
    def add_papers_batch(self, arxiv_ids: List[str], embeddings: List[np.ndarray]) -> None:
        # SQLite database already handles storing embeddings natively
        pass
        
    def search_similar(self, query_emb: np.ndarray, limit: int = 5) -> List[Tuple[str, float]]:
        all_papers = self.db.get_papers_with_embeddings()
        if not all_papers:
            return []
            
        similarities = []
        for paper, emb in all_papers:
            dot = np.dot(query_emb, emb)
            norm_curr = np.linalg.norm(query_emb)
            norm_other = np.linalg.norm(emb)
            sim = float(dot / (norm_curr * norm_other)) if norm_curr > 0 and norm_other > 0 else 0.0
            similarities.append((paper["arxiv_id"], sim))
            
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:limit]


class QdrantVectorStore(VectorStore):
    """Production vector store using the Qdrant Client driver."""
    
    def __init__(self, url: str, api_key: Optional[str], collection_name: str, embedding_dim: int):
        self.url = url
        self.api_key = api_key
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self.client: Optional[Any] = None
        self._connect()
        
    def _connect(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.models import Distance, VectorParams
            
            logger.info(f"Connecting to Qdrant vector store at {self.url}...")
            self.client = QdrantClient(url=self.url, api_key=self.api_key)
            
            # Create collection if missing
            collections = self.client.get_collections().collections
            names = [c.name for c in collections]
            if self.collection_name not in names:
                logger.info(f"Creating Qdrant collection: '{self.collection_name}' (dim: {self.embedding_dim})")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=self.embedding_dim, distance=Distance.COSINE)
                )
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant at {self.url}: {e}")
            self.client = None
            
    def _get_point_uuid(self, arxiv_id: str) -> str:
        """Convert a standard arxiv_id string into a stable UUID v5 for Qdrant compatibility."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"arxiv.org:{arxiv_id}"))
        
    def add_paper(self, arxiv_id: str, embedding: np.ndarray) -> None:
        self.add_papers_batch([arxiv_id], [embedding])
        
    def add_papers_batch(self, arxiv_ids: List[str], embeddings: List[np.ndarray]) -> None:
        if not self.client:
            return
        try:
            from qdrant_client.http.models import PointStruct
            points = []
            for aid, emb in zip(arxiv_ids, embeddings):
                points.append(PointStruct(
                    id=self._get_point_uuid(aid),
                    vector=emb.tolist(),
                    payload={"arxiv_id": aid}
                ))
            self.client.upsert(collection_name=self.collection_name, points=points)
        except Exception as e:
            logger.error(f"Failed to upsert points into Qdrant collection '{self.collection_name}': {e}")
            
    def search_similar(self, query_emb: np.ndarray, limit: int = 5) -> List[Tuple[str, float]]:
        if not self.client:
            return []
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_emb.tolist(),
                limit=limit
            )
            return [(r.payload["arxiv_id"], float(r.score)) for r in results if r.payload and "arxiv_id" in r.payload]
        except Exception as e:
            logger.error(f"Failed to search similar points in Qdrant collection '{self.collection_name}': {e}")
            return []
            
    def delete_paper(self, arxiv_id: str) -> None:
        if not self.client:
            return
        try:
            from qdrant_client.http.models import PointIdsList
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=[self._get_point_uuid(arxiv_id)])
            )
        except Exception as e:
            logger.error(f"Failed to delete paper '{arxiv_id}' from Qdrant: {e}")
