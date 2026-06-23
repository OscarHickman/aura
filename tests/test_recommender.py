import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from aura.recommender import RecommendationEngine


def _paper(arxiv_id="2401.00001"):
    return {
        "arxiv_id": arxiv_id,
        "title": "T",
        "abstract": "A",
        "authors": ["A"],
        "categories": ["astro-ph.CO"],
        "published": "2026-01-01T00:00:00Z",
        "url": "u",
        "pdf_url": "p",
    }


class TestRecommendationEngine(unittest.TestCase):
    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.PaperDatabase")
    @patch("aura.recommender.get_embedding_dim", return_value=3)
    @patch("aura.recommender.embed_papers_batch")
    @patch("aura.fetcher.SemanticScholarSource.fetch", return_value=[])
    @patch("aura.fetcher.ArxivSource.fetch_simple")
    @patch("aura.fetcher.ArxivSource.fetch")
    def test_fetch_new_papers_fallback_path(
        self,
        mock_fetch,
        mock_fetch_simple,
        mock_s2,
        mock_embed,
        _mock_dim,
        mock_db_cls,
        _mock_model_cls,
    ):
        mock_fetch.return_value = []
        mock_fetch_simple.return_value = [_paper()]
        mock_embed.return_value = [np.array([0.1, 0.2, 0.3], dtype=np.float32)]

        db = Mock()
        db.get_paper.return_value = None
        db.add_papers_batch.return_value = 1
        mock_db_cls.return_value = db

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(Path(td), ["astro-ph.CO"])
            added = engine.fetch_new_papers(max_results=10)

        self.assertEqual(added, 1)
        db.log_fetch.assert_called_once_with(1, ["astro-ph.CO"])

    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.PaperDatabase")
    @patch("aura.recommender.get_embedding_dim", return_value=3)
    @patch("aura.recommender.embed_papers_batch")
    @patch("aura.fetcher.SemanticScholarSource.fetch", return_value=[])
    @patch("aura.fetcher.ArxivSource.fetch")
    def test_fetch_new_papers_generate_summaries(
        self,
        mock_fetch,
        mock_s2,
        mock_embed,
        _mock_dim,
        mock_db_cls,
        _mock_model_cls,
    ):
        mock_fetch.return_value = [_paper("1"), _paper("2")]
        mock_embed.return_value = [np.array([0.1, 0.2, 0.3], dtype=np.float32)]

        db = Mock()
        db.get_paper.side_effect = lambda arxiv_id: {"arxiv_id": "2", "summary": ""} if arxiv_id == "2" else None
        db.add_papers_batch.return_value = 1
        mock_db_cls.return_value = db

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(Path(td), ["astro-ph.CO"])
            with patch.object(engine, "_generate_summaries_for_papers", return_value=["summary1"]) as mock_gen:
                with patch.object(engine, "generate_missing_summaries") as mock_missing:
                    added = engine.fetch_new_papers(max_results=10, generate_summaries=True)
                    self.assertEqual(added, 1)
                    mock_gen.assert_called_once()
                    mock_missing.assert_called_once_with(limit=1, include_failed=False)

    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.PaperDatabase")
    @patch("aura.recommender.get_embedding_dim", return_value=3)
    def test_get_recommendations_defaults_when_no_embeddings(
        self, _mock_dim, mock_db_cls, _mock_model_cls
    ):
        db = Mock()
        db.get_papers.return_value = [_paper("1"), _paper("2")]
        db.get_papers_with_embeddings.return_value = []
        mock_db_cls.return_value = db

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(Path(td), ["astro-ph.CO"])
            papers = engine.get_recommendations(limit=2)

        self.assertEqual(len(papers), 2)
        self.assertTrue(all(p["score"] == 0.5 for p in papers))

    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.PaperDatabase")
    @patch("aura.recommender.get_embedding_dim", return_value=3)
    def test_generate_summary_for_paper_not_found(
        self, _mock_dim, mock_db_cls, _mock_model_cls
    ):
        db = Mock()
        db.get_paper.return_value = None
        mock_db_cls.return_value = db

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(Path(td), ["astro-ph.CO"])
            result = engine.generate_summary_for_paper("missing")

        self.assertEqual(result["status"], "not_found")

    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.PaperDatabase")
    @patch("aura.recommender.get_embedding_dim", return_value=3)
    def test_rate_paper_trains_when_embedding_exists(
        self, _mock_dim, mock_db_cls, mock_model_cls
    ):
        db = Mock()
        db.get_papers_with_embeddings.return_value = [
            (_paper(), np.array([0.1, 0.2, 0.3], dtype=np.float32))
        ]
        mock_db_cls.return_value = db

        model = Mock()
        model.train_single.return_value = 0.123
        model.total_trained = 10
        mock_model_cls.return_value = model

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(Path(td), ["astro-ph.CO"])
            result = engine.rate_paper("2401.00001", 1)

        self.assertEqual(result["status"], "rated")
        self.assertTrue(result["trained"])
        model.train_single.assert_called_once()

    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.PaperDatabase")
    @patch("aura.recommender.get_embedding_dim", return_value=3)
    def test_rate_paper_no_embedding(self, _mock_dim, mock_db_cls, _mock_model_cls):
        db = Mock()
        db.get_papers_with_embeddings.return_value = []
        mock_db_cls.return_value = db

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(Path(td), ["astro-ph.CO"])
            result = engine.rate_paper("2401.00001", 1)

        self.assertEqual(result["status"], "rated")
        self.assertFalse(result["trained"])
        self.assertEqual(result["reason"], "no embedding")

    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.PaperDatabase")
    @patch("aura.recommender.get_embedding_dim", return_value=3)
    def test_retrain_full_no_data(self, _mock_dim, mock_db_cls, _mock_model_cls):
        db = Mock()
        db.get_training_data.return_value = ([], [])
        mock_db_cls.return_value = db

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(Path(td), ["astro-ph.CO"])
            result = engine.retrain_full()

        self.assertEqual(result["status"], "no_data")

    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.PaperDatabase")
    @patch("aura.recommender.get_embedding_dim", return_value=3)
    def test_generate_missing_summaries_no_work(self, _mock_dim, mock_db_cls, _mock_model_cls):
        db = Mock()
        db.get_papers_needing_summary.return_value = []
        mock_db_cls.return_value = db

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(Path(td), ["astro-ph.CO"])
            result = engine.generate_missing_summaries()

        self.assertEqual(result["status"], "no_work")

    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.PaperDatabase")
    @patch("aura.recommender.get_embedding_dim", return_value=3)
    def test_get_similar_papers(self, _mock_dim, mock_db_cls, _mock_model_cls):
        db = Mock()
        p1 = {"arxiv_id": "2401.00001", "title": "Paper 1"}
        p2 = {"arxiv_id": "2401.00002", "title": "Paper 2"}
        emb1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        emb2 = np.array([1.0, 1.0, 0.0], dtype=np.float32)

        # When querying single paper embedding
        db.get_papers_with_embeddings.side_effect = lambda ids=None: (
            [(p1, emb1)] if ids == ["2401.00001"] else [(p1, emb1), (p2, emb2)]
        )
        db.get_latest_rating.return_value = None
        mock_db_cls.return_value = db

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(Path(td), ["astro-ph.CO"])
            similar = engine.get_similar_papers("2401.00001", limit=5)

        self.assertEqual(len(similar), 1)
        self.assertEqual(similar[0]["arxiv_id"], "2401.00002")
        # cosine similarity between [1, 0, 0] and [1, 1, 0] is 1 / sqrt(2) = 0.7071
        self.assertAlmostEqual(similar[0]["similarity"], 0.7071, places=3)

    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.PaperDatabase")
    @patch("aura.recommender.get_embedding_dim", return_value=3)
    def test_get_diverse_papers(self, _mock_dim, mock_db_cls, _mock_model_cls):
        db = Mock()
        p1 = {"arxiv_id": "2401.00001", "title": "Paper 1"}
        p2 = {"arxiv_id": "2401.00002", "title": "Paper 2"}
        emb1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        emb2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        db.get_papers.return_value = [p1, p2]
        db.get_papers_with_embeddings.return_value = [(p1, emb1), (p2, emb2)]
        mock_db_cls.return_value = db

        with tempfile.TemporaryDirectory() as td:
            engine = RecommendationEngine(Path(td), ["astro-ph.CO"])
            diverse = engine.get_diverse_papers(limit=2)

        self.assertEqual(len(diverse), 2)
        ids = [p["arxiv_id"] for p in diverse]
        self.assertIn("2401.00001", ids)
        self.assertIn("2401.00002", ids)


if __name__ == "__main__":
    unittest.main()
