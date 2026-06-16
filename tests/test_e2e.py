import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
import numpy as np

from ai_papers.recommender import RecommendationEngine

class TestE2EFlow(unittest.TestCase):
    @patch("ai_papers.recommender.get_embedding_dim", return_value=4)
    @patch("ai_papers.recommender.embed_papers_batch")
    @patch("ai_papers.fetcher.ArxivSource.fetch")
    @patch("ai_papers.fetcher.SemanticScholarSource.fetch")
    def test_fetch_rate_retrain_flow(self, mock_s2, mock_arxiv, mock_embed, mock_get_dim):
        # 1. Mock fetcher response
        mock_arxiv.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "A Great Cosmology Paper",
                "abstract": "We study the CMB radiation and dark energy.",
                "authors": ["Ada Lovelace"],
                "categories": ["astro-ph.CO"],
                "published": "2026-01-01T00:00:00Z",
                "url": "http://arxiv.org/abs/2401.00001",
                "pdf_url": "http://arxiv.org/pdf/2401.00001.pdf",
                "source": "arxiv",
            }
        ]
        mock_s2.return_value = [
            {
                "arxiv_id": "2401.00002",
                "title": "Stellar Evolution in Binary Systems",
                "abstract": "We simulate binary stellar systems and their mass transfer.",
                "authors": ["Linus Torvalds"],
                "categories": ["astro-ph.SR"],
                "published": "2026-01-02T00:00:00Z",
                "url": "http://arxiv.org/abs/2401.00002",
                "pdf_url": "http://arxiv.org/pdf/2401.00002.pdf",
                "source": "semanticscholar",
            }
        ]

        # 2. Mock embeddings
        # Paper 1: strong cosmology feature, Paper 2: strong stellar feature
        mock_embed.return_value = [
            np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
            np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32),
        ]

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(
                data_dir=Path(td),
                categories=["astro-ph.CO", "astro-ph.SR"],
                embedding_model="dummy-model"
            )

            # --- FETCH ---
            new_count = engine.fetch_new_papers(max_results=2)
            self.assertEqual(new_count, 2)

            # Verify saved papers
            papers = engine.get_recommendations(limit=10, unrated_only=False)
            self.assertEqual(len(papers), 2)
            # Scores should be valid float values between 0.0 and 1.0
            for p in papers:
                self.assertTrue(0.0 <= p["score"] <= 1.0)

            # --- RATE ---
            # Rate the cosmology paper as Thumbs Up
            engine.rate_paper("2401.00001", 1)
            # Rate the stellar paper as Thumbs Down
            engine.rate_paper("2401.00002", 0)

            # --- RETRAIN ---
            # Retrain preference model
            retrain_result = engine.retrain_full(epochs=50)
            self.assertEqual(retrain_result["status"], "retrained")

            # --- RECOMMEND ---
            # Recommend again and assert scores have updated correctly
            rec_papers = engine.get_recommendations(limit=10, unrated_only=False)
            
            p1_rec = next(p for p in rec_papers if p["arxiv_id"] == "2401.00001")
            p2_rec = next(p for p in rec_papers if p["arxiv_id"] == "2401.00002")

            # The liked paper should rank higher and have a higher score than the disliked paper
            self.assertGreater(p1_rec["score"], 0.4)
            self.assertGreater(p1_rec["score"], p2_rec["score"])
