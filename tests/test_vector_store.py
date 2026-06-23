import unittest
from unittest.mock import Mock, patch
import numpy as np
from aura.vector_store import NumpyVectorStore, QdrantVectorStore

class TestVectorStore(unittest.TestCase):
    def test_numpy_vector_store(self):
        db = Mock()
        db.get_papers_with_embeddings.return_value = [
            ({"arxiv_id": "2401.00001"}, np.array([1.0, 0.0, 0.0], dtype=np.float32)),
            ({"arxiv_id": "2401.00002"}, np.array([0.0, 1.0, 0.0], dtype=np.float32)),
        ]
        
        vs = NumpyVectorStore(db)
        # Search with vector close to first paper
        results = vs.search_similar(np.array([1.0, 0.1, 0.0], dtype=np.float32), limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "2401.00001")
        self.assertGreater(results[0][1], 0.9)

    @patch("qdrant_client.QdrantClient")
    def test_qdrant_vector_store(self, mock_client_cls):
        mock_client = Mock()
        mock_client_cls.return_value = mock_client
        mock_client.get_collections.return_value.collections = []
        
        vs = QdrantVectorStore(
            url="http://localhost:6333",
            api_key="test-key",
            collection_name="test_collection",
            embedding_dim=3
        )
        
        mock_client.create_collection.assert_called_once()
        
        # Test add paper
        vs.add_paper("2401.00001", np.array([0.1, 0.2, 0.3], dtype=np.float32))
        mock_client.upsert.assert_called_once()
        
        # Test search similar
        mock_search_result = Mock()
        mock_search_result.payload = {"arxiv_id": "2401.00001"}
        mock_search_result.score = 0.95
        mock_client.search.return_value = [mock_search_result]
        
        results = vs.search_similar(np.array([0.1, 0.2, 0.3], dtype=np.float32), limit=2)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], "2401.00001")
        self.assertEqual(results[0][1], 0.95)
        
        # Test delete
        vs.delete_paper("2401.00001")
        mock_client.delete.assert_called_once()

if __name__ == "__main__":
    unittest.main()
