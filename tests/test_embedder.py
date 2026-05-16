import unittest
from unittest.mock import Mock, patch

import numpy as np

from ai_papers import embedder


class TestEmbedder(unittest.TestCase):
    @patch("ai_papers.embedder.get_model")
    def test_embed_paper_returns_float32(self, mock_get_model):
        model = Mock()
        model.encode.return_value = [1.0, 2.0, 3.0]
        mock_get_model.return_value = model

        vec = embedder.embed_paper("Title", "Abstract", model_name="m")

        self.assertIsInstance(vec, np.ndarray)
        self.assertEqual(vec.dtype, np.float32)
        model.encode.assert_called_once_with(
            "Title. Abstract", normalize_embeddings=True
        )

    @patch("ai_papers.embedder.get_model")
    def test_embed_papers_batch_uses_batch_size(self, mock_get_model):
        model = Mock()
        model.encode.return_value = [[0.1, 0.2], [0.3, 0.4]]
        mock_get_model.return_value = model

        papers = [
            {"title": "T1", "abstract": "A1"},
            {"title": "T2", "abstract": "A2"},
        ]
        result = embedder.embed_papers_batch(papers, batch_size=8)

        self.assertEqual(len(result), 2)
        self.assertTrue(all(v.dtype == np.float32 for v in result))
        model.encode.assert_called_once_with(
            ["T1. A1", "T2. A2"],
            normalize_embeddings=True,
            batch_size=8,
            show_progress_bar=True,
        )

    @patch("ai_papers.embedder.get_model")
    def test_get_embedding_dim(self, mock_get_model):
        model = Mock()
        model.get_sentence_embedding_dimension.return_value = 384
        mock_get_model.return_value = model

        self.assertEqual(embedder.get_embedding_dim("x"), 384)


if __name__ == "__main__":
    unittest.main()
