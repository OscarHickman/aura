import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
import numpy as np

import requests

from aura.database import PaperDatabase
from aura.recommender import RecommendationEngine
from aura.github import extract_github_url, fetch_github_metadata


def make_paper(arxiv_id: str, abstract: str, has_code: int = 1):
    return {
        "arxiv_id": arxiv_id,
        "title": f"Paper {arxiv_id}",
        "abstract": abstract,
        "authors": ["John Doe"],
        "categories": ["astro-ph.CO"],
        "published": "2026-01-01T00:00:00Z",
        "url": f"http://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"http://arxiv.org/pdf/{arxiv_id}.pdf",
        "has_code": has_code,
        "has_data": 0,
    }


class TestGitHubMetadata(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "papers.db"
        self.db = PaperDatabase(self.db_path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_extract_github_url(self):
        # Test standard URL
        text = "Our code is available at https://github.com/owner/repo-name."
        self.assertEqual(
            extract_github_url(text), "https://github.com/owner/repo-name"
        )

        # Test URL with trailing punctuation
        text_punct = "Check out (github.com/owner/repo-name), it is cool."
        self.assertEqual(
            extract_github_url(text_punct), "https://github.com/owner/repo-name"
        )

        # Test URL ending with .git
        text_git = "Clone from https://github.com/owner/repo-name.git"
        self.assertEqual(
            extract_github_url(text_git), "https://github.com/owner/repo-name"
        )

        # Test no URL
        self.assertIsNone(extract_github_url("No repository link here."))

    @patch("aura.github.requests.get")
    def test_fetch_github_metadata_success(self, mock_get):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "stargazers_count": 42,
            "pushed_at": "2026-06-24T12:00:00Z",
            "language": "Python",
        }
        mock_get.return_value = mock_resp

        meta = fetch_github_metadata("https://github.com/owner/repo-name")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["stars"], 42)
        self.assertEqual(meta["last_commit"], "2026-06-24T12:00:00Z")
        self.assertEqual(meta["language"], "Python")

    @patch("aura.github.requests.get")
    def test_fetch_github_metadata_rate_limit(self, mock_get):
        mock_resp = Mock()
        mock_resp.status_code = 403
        mock_resp.text = "Rate limit exceeded"
        mock_get.return_value = mock_resp

        meta = fetch_github_metadata("https://github.com/owner/repo-name")
        self.assertIsNone(meta)

    @patch(
        "aura.github.requests.get",
        side_effect=requests.RequestException("Network error"),
    )
    def test_fetch_github_metadata_error(self, mock_get):
        meta = fetch_github_metadata("https://github.com/owner/repo-name")
        self.assertIsNone(meta)

    def test_database_repo_metadata_roundtrip(self):
        arxiv_id = "2401.00001"
        self.db.add_paper(make_paper(arxiv_id, "Abstract text"))

        # Add repo metadata
        success = self.db.update_repo_metadata(
            arxiv_id=arxiv_id,
            repo_url="https://github.com/owner/repo-name",
            stars=10,
            last_commit="2026-06-24T00:00:00Z",
            language="Python",
        )
        self.assertTrue(success)

        # Retrieve and verify
        meta = self.db.get_repo_metadata(arxiv_id)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["repo_url"], "https://github.com/owner/repo-name")
        self.assertEqual(meta["stars"], 10)
        self.assertEqual(meta["last_commit"], "2026-06-24T00:00:00Z")
        self.assertEqual(meta["language"], "Python")

        # Update metadata
        success_update = self.db.update_repo_metadata(
            arxiv_id=arxiv_id,
            repo_url="https://github.com/owner/repo-name",
            stars=15,
            last_commit="2026-06-24T06:00:00Z",
            language="Jupyter Notebook",
        )
        self.assertTrue(success_update)

        meta_updated = self.db.get_repo_metadata(arxiv_id)
        self.assertEqual(meta_updated["stars"], 15)
        self.assertEqual(meta_updated["language"], "Jupyter Notebook")

    @patch("aura.github.fetch_github_metadata")
    def test_engine_ingest_and_refresh(self, mock_fetch_github):
        mock_fetch_github.return_value = {
            "repo_url": "https://github.com/owner/repo-name",
            "stars": 100,
            "last_commit": "2026-06-24T08:00:00Z",
            "language": "Python",
        }

        engine = RecommendationEngine(
            data_dir=self.tmp.name,
            categories=["astro-ph.CO"],
            embedding_model="all-MiniLM-L6-v2",
        )
        engine.db = self.db

        paper = make_paper(
            "2401.00002",
            "Code is here: https://github.com/owner/repo-name",
            has_code=1,
        )

        # Ingest paper
        engine.db.add_papers_batch(
            [paper], [np.zeros(384, dtype=np.float32)], ["summary"]
        )
        engine._extract_and_save_github_metadata([paper])

        # Verify database has metadata
        meta = self.db.get_repo_metadata("2401.00002")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["stars"], 100)
        self.assertEqual(meta["language"], "Python")

        # Refresh metadata
        mock_fetch_github.return_value["stars"] = 150
        result = engine.refresh_github_metadata(force=True)
        self.assertEqual(result["updated_papers"], 1)

        meta_refreshed = self.db.get_repo_metadata("2401.00002")
        self.assertEqual(meta_refreshed["stars"], 150)

        engine.close()


if __name__ == "__main__":
    unittest.main()
