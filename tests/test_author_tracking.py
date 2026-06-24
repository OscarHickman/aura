import tempfile
import unittest
from pathlib import Path
import numpy as np
from unittest.mock import Mock, patch

from aura.database import PaperDatabase
from aura.recommender import RecommendationEngine
from aura.web.app import create_app
from aura.email_digest import _collect_network_papers, _build_email_content
from run import cmd_import

def make_paper(arxiv_id: str = "2401.00001", authors=None):
    return {
        "arxiv_id": arxiv_id,
        "title": f"Paper {arxiv_id}",
        "abstract": "An abstract for computational cosmology research.",
        "authors": authors or ["John Doe", "Jane Smith"],
        "categories": ["astro-ph.CO"],
        "published": "2026-01-01T00:00:00Z",
        "url": f"http://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"http://arxiv.org/pdf/{arxiv_id}.pdf",
    }

class TestAuthorTracking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "papers.db"
        self.db = PaperDatabase(self.db_path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_tracked_authors_crud(self):
        # 1. Add author
        success = self.db.add_tracked_author("Stephen Hawking", orcid="0000-0002-1825-0097", affiliation="Cambridge", relationship="follow")
        self.assertTrue(success)

        # 2. Get authors
        authors = self.db.get_tracked_authors()
        self.assertEqual(len(authors), 1)
        self.assertEqual(authors[0]["name"], "Stephen Hawking")
        self.assertEqual(authors[0]["orcid"], "0000-0002-1825-0097")
        self.assertEqual(authors[0]["affiliation"], "Cambridge")
        self.assertEqual(authors[0]["relationship"], "follow")

        # 3. Add duplicate should fail
        fail = self.db.add_tracked_author("Stephen Hawking", relationship="follow")
        self.assertFalse(fail)

        # 4. Get by ID
        hawking = self.db.get_tracked_author(authors[0]["id"])
        self.assertIsNotNone(hawking)
        self.assertEqual(hawking["name"], "Stephen Hawking")

        # 5. Delete author
        del_success = self.db.delete_tracked_author(authors[0]["id"])
        self.assertTrue(del_success)
        self.assertEqual(len(self.db.get_tracked_authors()), 0)

    def test_auto_tagging_on_insert(self):
        # Add tracked author
        self.db.add_tracked_author("Jane Smith", relationship="follow")
        self.db.add_tracked_author("Stephen Hawking", relationship="collaborator")

        # Add paper by Jane Smith
        p1 = make_paper("2401.00001", authors=["Jane Smith", "John Doe"])
        embs = [np.zeros(384, dtype=np.float32)]
        self.db.add_papers_batch([p1], embs)

        # Verify tags
        tags = self.db.get_paper_tags("2401.00001")
        self.assertIn("followed_author", tags)
        self.assertIn("jane smith", tags)

        # Add paper by Hawking
        p2 = make_paper("2401.00002", authors=["Stephen Hawking", "Albert Einstein"])
        self.db.add_papers_batch([p2], embs)
        tags2 = self.db.get_paper_tags("2401.00002")
        self.assertIn("collaborator", tags2)
        self.assertIn("stephen hawking", tags2)

    def test_retroactive_tagging(self):
        # Add paper first
        p = make_paper("2401.00001", authors=["Jane Smith", "John Doe"])
        self.db.add_papers_batch([p], [np.zeros(384, dtype=np.float32)])

        # Verify no network tag initially
        tags_initial = self.db.get_paper_tags("2401.00001")
        self.assertNotIn("followed_author", tags_initial)

        # Now add author to track
        self.db.add_tracked_author("Jane Smith", relationship="follow")

        # Verify retroactive tag
        tags_after = self.db.get_paper_tags("2401.00001")
        self.assertIn("followed_author", tags_after)
        self.assertIn("jane smith", tags_after)

        # Delete tracked author
        authors = self.db.get_tracked_authors()
        self.db.delete_tracked_author(authors[0]["id"])

        # Verify tag cleanup
        tags_final = self.db.get_paper_tags("2401.00001")
        self.assertNotIn("followed_author", tags_final)
        self.assertNotIn("jane smith", tags_final)

class TestAuthorScoring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "papers.db"
        self.db = PaperDatabase(self.db_path)
        
        # Patch RecommendationEngine database and embedding path
        self.engine = RecommendationEngine(
            data_dir=self.tmp.name,
            categories=["astro-ph.CO"],
            embedding_model="all-MiniLM-L6-v2"
        )
        # Override the engine's db with our clean database instance
        self.engine.db = self.db

    def tearDown(self):
        self.engine.close()
        self.db.close()
        self.tmp.cleanup()

    @patch("aura.recommender.PreferenceModel")
    @patch("aura.recommender.embed_papers_batch")
    def test_recommendation_scoring_boost(self, mock_embed, mock_model):
        mock_model_instance = Mock()
        mock_model_instance.predict.return_value = np.array([0.5, 0.5])
        mock_model.return_value = mock_model_instance
        mock_embed.return_value = [np.zeros(384, dtype=np.float32), np.zeros(384, dtype=np.float32)]

        # Add tracked author
        self.db.add_tracked_author("Jane Smith", relationship="follow")

        # Insert papers
        p1 = make_paper("2401.00001", authors=["Jane Smith"])
        p2 = make_paper("2401.00002", authors=["Albert Einstein"])
        self.db.add_papers_batch([p1, p2], [np.zeros(384, dtype=np.float32), np.zeros(384, dtype=np.float32)])

        recs = self.engine.get_recommendations(user_id=1, limit=10)
        
        # Verify recommendation boost
        p1_rec = next(p for p in recs if p["arxiv_id"] == "2401.00001")
        p2_rec = next(p for p in recs if p["arxiv_id"] == "2401.00002")

        # p1 should have a network_bonus of 0.15, p2 should have 0
        self.assertEqual(p1_rec["network_bonus"], 0.15)
        self.assertEqual(p2_rec["network_bonus"], 0.0)
        self.assertGreater(p1_rec["score"], p2_rec["score"])

class TestAuthorTrackingWebRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "papers.db"
        self.db = PaperDatabase(self.db_path)
        
        # Setup engine mock or real
        self.engine = RecommendationEngine(
            data_dir=self.tmp.name,
            categories=["astro-ph.CO"],
            embedding_model="all-MiniLM-L6-v2"
        )
        self.engine.db = self.db

        with patch("aura.web.app.RecommendationEngine", return_value=self.engine):
            self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF in tests for ease of POSTing
        # Inject our patched engine
        self.app.config["AI_PAPERS_ENGINE"] = self.engine
        self.client = self.app.test_client()

        # Register and log in
        with patch("aura.web.app.generate_password_hash", return_value="hashed"), \
             patch("aura.web.app.check_password_hash", return_value=True):
            self.client.post("/register", data={
                "email": "test@example.com",
                "password": "password123",
                "confirm_password": "password123",
            }, follow_redirects=True)

            self.client.post("/login", data={
                "email": "test@example.com",
                "password": "password123",
            }, follow_redirects=True)

        # Rate 5 dummy papers to bypass onboarding redirect
        for i in range(5):
            arxiv_id = f"dummy.0000{i}"
            paper = make_paper(arxiv_id)
            self.db.add_papers_batch([paper], [np.zeros(384, dtype=np.float32)])
            self.db.rate_paper(arxiv_id, 5, user_id=1)

    def tearDown(self):
        self.engine.close()
        self.db.close()
        self.tmp.cleanup()

    def test_settings_authors_routes(self):
        # 1. GET page
        resp = self.client.get("/settings/authors")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Tracked Authors", resp.data)

        # 2. POST Add Author
        resp_add = self.client.post("/settings/authors", data={
            "action": "add",
            "name": "Richard Feynman",
            "orcid": "0000-0001-2345-6789",
            "affiliation": "Caltech",
            "relationship": "follow"
        }, follow_redirects=True)
        self.assertEqual(resp_add.status_code, 200)
        self.assertIn(b"Richard Feynman", resp_add.data)

        # Check DB
        authors = self.db.get_tracked_authors()
        self.assertEqual(len(authors), 1)
        self.assertEqual(authors[0]["name"], "Richard Feynman")

        # 3. POST Delete Author
        resp_del = self.client.post("/settings/authors", data={
            "action": "delete",
            "author_id": str(authors[0]["id"])
        }, follow_redirects=True)
        self.assertEqual(resp_del.status_code, 200)
        self.assertEqual(len(self.db.get_tracked_authors()), 0)

    def test_settings_authors_import_bibtex(self):
        bibtex = """
        @article{key,
          title = {A physics paper},
          author = {Feynman, Richard and Gell-Mann, Murray},
          year = {1960}
        }
        """
        resp = self.client.post("/settings/authors/import-bibtex", data={
            "bibtex_content": bibtex,
            "relationship": "collaborator"
        }, follow_redirects=True)
        
        self.assertEqual(resp.status_code, 200)
        authors = self.db.get_tracked_authors()
        # Should have imported Feynman, Richard and Gell-Mann, Murray
        self.assertEqual(len(authors), 2)
        names = [a["name"] for a in authors]
        self.assertIn("Feynman, Richard", names)
        self.assertIn("Gell-Mann, Murray", names)

class TestAuthorDigestAndCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "papers.db"
        self.db = PaperDatabase(self.db_path)
        
        self.engine = RecommendationEngine(
            data_dir=self.tmp.name,
            categories=["astro-ph.CO"],
            embedding_model="all-MiniLM-L6-v2"
        )
        self.engine.db = self.db

    def tearDown(self):
        self.engine.close()
        self.db.close()
        self.tmp.cleanup()

    def test_email_digest_network_papers(self):
        # Add author
        self.db.add_tracked_author("Ada Lovelace", relationship="follow")
        # Add paper
        p = make_paper("2401.00001", authors=["Ada Lovelace"])
        self.db.add_papers_batch([p], [np.zeros(384, dtype=np.float32)])

        # Collect
        net_papers = _collect_network_papers(self.engine, user_id=1, limit=5)
        self.assertEqual(len(net_papers), 1)
        self.assertEqual(net_papers[0]["arxiv_id"], "2401.00001")

        # Build email content
        text, html = _build_email_content(
            papers=[],
            trends={},
            app_name="AURA",
            user_id=1,
            network_papers=net_papers
        )
        self.assertIn("From your network", text)
        self.assertIn("From your network", html)
        self.assertIn("Ada Lovelace", html)

    @patch("aura.recommender.RecommendationEngine")
    def test_cli_import_authors(self, mock_engine_class):
        mock_engine = Mock()
        mock_engine.db = self.db
        mock_engine_class.return_value = mock_engine

        # Write dummy BibTeX file
        bib_file = Path(self.tmp.name) / "test.bib"
        bib_content = """
        @article{key,
          title = {My paper},
          author = {Paul Dirac},
          year = {1930}
        }
        """
        with open(bib_file, "w", encoding="utf-8") as f:
            f.write(bib_content)

        # Build dummy args
        args = Mock()
        args.file = str(bib_file)
        args.import_authors = "follow"

        cmd_import(args, {"data_dir": self.tmp.name})

        # Check DB
        authors = self.db.get_tracked_authors()
        self.assertEqual(len(authors), 1)
        self.assertEqual(authors[0]["name"], "Paul Dirac")
        self.assertEqual(authors[0]["relationship"], "follow")
