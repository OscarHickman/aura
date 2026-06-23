import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Fake missing modules for import to avoid ModuleNotFoundError
sys.modules['openai'] = MagicMock()
sys.modules['anthropic'] = MagicMock()

from aura.database import PaperDatabase  # noqa: E402
from aura.recommender import RecommendationEngine  # noqa: E402


class TestCitationGraphDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_papers.db"
        self.db = PaperDatabase(self.db_path)

        # Seed some dummy papers
        self.p1 = {
            "arxiv_id": "2401.00001",
            "title": "Cosmology Paper 1",
            "abstract": "First paper abstract",
            "authors": '["Ada", "Linus"]',
            "categories": '["astro-ph.CO"]',
            "published": "2024-01-01T00:00:00Z",
            "fetched_at": "2024-01-02T00:00:00Z",
        }
        self.p2 = {
            "arxiv_id": "2401.00002",
            "title": "Cosmology Paper 2",
            "abstract": "Second paper abstract",
            "authors": '["Ada"]',
            "categories": '["astro-ph.CO"]',
            "published": "2024-01-02T00:00:00Z",
            "fetched_at": "2024-01-03T00:00:00Z",
        }
        self.db.conn.execute(
            """
            INSERT INTO papers (arxiv_id, title, abstract, authors, categories, published, fetched_at)
            VALUES (:arxiv_id, :title, :abstract, :authors, :categories, :published, :fetched_at)
            """,
            self.p1,
        )
        self.db.conn.execute(
            """
            INSERT INTO papers (arxiv_id, title, abstract, authors, categories, published, fetched_at)
            VALUES (:arxiv_id, :title, :abstract, :authors, :categories, :published, :fetched_at)
            """,
            self.p2,
        )
        self.db.conn.commit()

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_add_and_retrieve_citations(self):
        # Initial check
        self.assertEqual(len(self.db.get_papers_citing("2401.00002")), 0)
        self.assertEqual(len(self.db.get_papers_cited_by("2401.00001")), 0)

        # Insert citation link: 2401.00001 cites 2401.00002
        self.db.add_citations_batch([("2401.00001", "2401.00002")])

        # Verify citation
        citing = self.db.get_papers_citing("2401.00002")
        self.assertEqual(len(citing), 1)
        self.assertEqual(citing[0]["arxiv_id"], "2401.00001")

        # Verify reference
        references = self.db.get_papers_cited_by("2401.00001")
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["arxiv_id"], "2401.00002")

    def test_mark_citations_fetched(self):
        paper = self.db.get_paper("2401.00001")
        self.assertEqual(paper.get("citations_fetched"), 0)

        self.db.mark_citations_fetched("2401.00001", True)
        paper = self.db.get_paper("2401.00001")
        self.assertEqual(paper.get("citations_fetched"), 1)

    def test_get_liked_citations_counts(self):
        # 2401.00001 cites 2401.00002
        self.db.add_citations_batch([("2401.00001", "2401.00002")])
        
        # 2401.00001 is liked
        liked_arxiv_ids = ["2401.00001"]
        
        counts = self.db.get_liked_citations_counts(liked_arxiv_ids)
        self.assertEqual(counts.get("2401.00002"), 1)
        self.assertEqual(counts.get("2401.00001"), None)

    def test_get_liked_references_counts(self):
        # 2401.00001 cites 2401.00002
        self.db.add_citations_batch([("2401.00001", "2401.00002")])
        
        # 2401.00002 is liked
        liked_arxiv_ids = ["2401.00002"]
        
        counts = self.db.get_liked_references_counts(liked_arxiv_ids)
        self.assertEqual(counts.get("2401.00001"), 1)


class TestCitationGraphRecommender(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name)

        # Bypass preference model and vector store init during tests
        with patch("aura.recommender.PreferenceModel"), \
             patch("aura.recommender.get_embedding_dim", return_value=3):
            self.engine = RecommendationEngine(data_dir=self.db_path, categories=["astro-ph.CO"])

        # Seed some dummy papers in DB
        self.engine.db.conn.executescript("""
            INSERT INTO papers (arxiv_id, title, abstract, authors, categories, published, fetched_at)
            VALUES ('2401.00001', 'Paper 1', 'Abstract 1', '["Ada"]', '["astro-ph.CO"]', '2024-01-01T00:00:00Z', '2024-01-02T00:00:00Z');
            
            INSERT INTO papers (arxiv_id, title, abstract, authors, categories, published, fetched_at)
            VALUES ('2401.00002', 'Paper 2', 'Abstract 2', '["Ada"]', '["astro-ph.CO"]', '2024-01-02T00:00:00Z', '2024-01-03T00:00:00Z');
        """)
        self.engine.db.conn.commit()

    def tearDown(self):
        self.engine.close()
        self.temp_dir.cleanup()

    def test_get_s2_arxiv_id_parsing(self):
        # ArXiv mapping
        entry_arxiv = {"externalIds": {"ArXiv": "2401.00001"}, "paperId": "s2_id_123"}
        self.assertEqual(self.engine._get_s2_arxiv_id(entry_arxiv), "2401.00001")

        # Fallback to S2 prefix
        entry_s2 = {"paperId": "s2_id_456"}
        self.assertEqual(self.engine._get_s2_arxiv_id(entry_s2), "s2:s2_id_456")

        # Missing both
        entry_none = {}
        self.assertIsNone(self.engine._get_s2_arxiv_id(entry_none))

    @patch("requests.get")
    def test_fetch_and_store_citations_api_integration(self, mock_get):
        # Mock Semantic Scholar response:
        # Paper has citation from 2401.00003 and reference to 2401.00004
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "paperId": "s2_main_id",
            "citations": [
                {"externalIds": {"ArXiv": "2401.00003"}, "paperId": "s2_cit_1"}
            ],
            "references": [
                {"externalIds": {"ArXiv": "2401.00004"}, "paperId": "s2_ref_1"}
            ]
        }
        mock_get.return_value = mock_response

        # Execute
        self.engine.fetch_and_store_citations("2401.00001")

        # Verify API request details
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertIn("https://api.semanticscholar.org/graph/v1/paper/arXiv:2401.00001", args[0])

        # Verify database changes
        paper = self.engine.db.get_paper("2401.00001")
        self.assertEqual(paper["citations_fetched"], 1)

        # Check citation links in db
        rows = self.engine.db.conn.execute("SELECT * FROM citations").fetchall()
        self.assertEqual(len(rows), 2)
        # Link 1: 2401.00003 cites 2401.00001
        # Link 2: 2401.00001 cites 2401.00004
        links = [(row["citing_arxiv_id"], row["cited_arxiv_id"]) for row in rows]
        self.assertIn(("2401.00003", "2401.00001"), links)
        self.assertIn(("2401.00001", "2401.00004"), links)

    @patch("requests.get")
    def test_fetch_and_store_citations_api_rate_limited(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        self.engine.fetch_and_store_citations("2401.00001")

        # Citations should NOT be marked as fetched since it failed with 429
        paper = self.engine.db.get_paper("2401.00001")
        self.assertEqual(paper["citations_fetched"], 0)

    @patch("aura.recommender.RecommendationEngine.fetch_and_store_citations")
    def test_get_or_fetch_citations_orchestration(self, mock_fetch):
        # Seeding a connection
        self.engine.db.add_citations_batch([("2401.00001", "2401.00002")])

        # First call: citations_fetched is false, should trigger fetch
        citing, cited = self.engine.get_or_fetch_citations("2401.00002")
        mock_fetch.assert_called_once_with("2401.00002")
        self.assertEqual(len(citing), 1)
        self.assertEqual(citing[0]["arxiv_id"], "2401.00001")

    def test_recommendation_scoring_citation_boost(self):
        # Setup mock embeddings
        self.engine.db.conn.executescript("""
            UPDATE papers SET embedding = zeroblob(12) WHERE arxiv_id IN ('2401.00001', '2401.00002');
        """)
        self.engine.db.conn.commit()

        # Mock the preference model prediction
        mock_pref_model = Mock()
        mock_pref_model.predict_batch.return_value = ([0.6, 0.6], [0.0, 0.0])
        self.engine.get_user_preference_model = Mock(return_value=mock_pref_model)
        self.engine.get_user_shadow_model = Mock(return_value=mock_pref_model)

        # Mock liked papers: 2401.00001 is liked (rating=5)
        self.engine.db.conn.execute("""
            INSERT INTO ratings (user_id, arxiv_id, rating, rated_at)
            VALUES (1, '2401.00001', 5, '2024-01-01T00:00:00Z');
        """)
        self.engine.db.conn.commit()

        # Scenario A: No citation link. Both papers have same base score
        recs = self.engine.get_recommendations(unrated_only=False)
        self.assertEqual(recs[0]["score"], recs[1]["score"])

        # Scenario B: 2401.00001 (liked) cites 2401.00002.
        # This means 2401.00002 is cited by a liked paper and should receive a boost!
        self.engine.db.add_citations_batch([("2401.00001", "2401.00002")])

        recs = self.engine.get_recommendations(unrated_only=False)
        p2_rec = [p for p in recs if p["arxiv_id"] == "2401.00002"][0]
        p1_rec = [p for p in recs if p["arxiv_id"] == "2401.00001"][0]

        # 2401.00002 has higher score because it receives citation_graph_bonus (+0.05)
        self.assertGreater(p2_rec["score"], p1_rec["score"])
        self.assertEqual(p2_rec["citation_graph_bonus"], 0.05)


if __name__ == "__main__":
    unittest.main()
