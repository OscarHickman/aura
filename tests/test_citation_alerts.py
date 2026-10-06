"""Unit tests for 'My Papers' citation alerts, auto-ingestion, and tracking."""

import unittest
from unittest.mock import MagicMock, patch
import os
import shutil
import tempfile
from aura.database import PaperDatabase
from aura.recommender import RecommendationEngine
from aura.notifications import (
    send_slack_citation_alert,
    send_discord_citation_alert,
    notify_citation_events,
)
from aura.web.app import create_app


class TestCitationAlertsAndTracking(unittest.TestCase):
    """Test suite for citation event detection, auto-ingestion, and alert delivery."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_papers.db")
        self.db = PaperDatabase(db_path=self.db_path)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_database_citation_events_and_history(self):
        """Test recording citation events, notification flags, and citation count snapshots."""
        user_id = 1
        self.db.add_my_paper("Test Title", arxiv_id="2301.00001", user_id=user_id)
        papers = self.db.get_my_papers(user_id=user_id)
        self.assertEqual(len(papers), 1)
        my_paper_id = papers[0]["id"]
        self.assertEqual(papers[0]["citation_count"], 0)

        # Record citation history milestone
        self.db.record_citation_history(user_id, my_paper_id, 5)
        self.db.record_citation_history(user_id, my_paper_id, 12)

        history = self.db.get_paper_citation_history(my_paper_id)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["citation_count"], 5)
        self.assertEqual(history[1]["citation_count"], 12)

        # get_my_papers should reflect the latest citation count (12)
        papers_updated = self.db.get_my_papers(user_id=user_id)
        self.assertEqual(papers_updated[0]["citation_count"], 12)

        # Record citation events
        inserted1 = self.db.record_citation_event(
            user_id=user_id,
            my_paper_id=my_paper_id,
            citing_arxiv_id="2401.99999",
            citing_title="Citing Paper 1",
            citing_authors="Author A, Author B",
        )
        self.assertTrue(inserted1)

        # Duplicate event should not re-insert
        inserted2 = self.db.record_citation_event(
            user_id=user_id,
            my_paper_id=my_paper_id,
            citing_arxiv_id="2401.99999",
            citing_title="Citing Paper 1",
            citing_authors="Author A, Author B",
        )
        self.assertFalse(inserted2)

        # Retrieve unnotified events
        unnotified = self.db.get_unnotified_citation_events(user_id=user_id)
        self.assertEqual(len(unnotified), 1)
        self.assertEqual(unnotified[0]["citing_arxiv_id"], "2401.99999")
        self.assertEqual(unnotified[0]["my_paper_title"], "Test Title")

        # Mark as notified
        self.db.mark_citation_events_notified([unnotified[0]["id"]])
        self.assertEqual(len(self.db.get_unnotified_citation_events(user_id=user_id)), 0)

        # Check recent citation events
        recent = self.db.get_recent_citation_events(user_id=user_id)
        self.assertEqual(len(recent), 1)

    @patch("aura.recommender.get_embedding_dim", return_value=3)
    @patch("aura.fetcher.ADSSource.fetch_citations_for_identifier")
    def test_recommender_auto_ingestion_and_refresh(self, mock_fetch_citations, _mock_dim):
        """Test that refreshing paper citations records events and auto-ingests citing papers."""
        mock_fetch_citations.return_value = [
            {
                "arxiv_id": "2402.12345",
                "title": "Novel Applications of Deep Cosmology",
                "authors": ["Carl Sagan", "Neil deGrasse Tyson"],
                "abstract": "We build upon previous work 2301.00001...",
                "categories": ["astro-ph.CO"],
                "published": "2026-02-15T00:00:00Z",
                "url": "https://arxiv.org/abs/2402.12345",
            }
        ]

        engine = RecommendationEngine(
            data_dir=self.test_dir,
            categories=["astro-ph.CO"],
            embedding_model="all-MiniLM-L6-v2",
        )
        try:
            user_id = 1
            engine.db.add_my_paper("My Seminal Work", arxiv_id="2301.00001", user_id=user_id)
            papers = engine.db.get_my_papers(user_id=user_id)
            my_paper_id = papers[0]["id"]

            with patch.dict(os.environ, {"ADS_API_KEY": "mock_key"}):
                with patch.object(engine, "_notify_new_citation_events") as mock_notify:
                    engine.refresh_single_my_paper_citations(my_paper_id, user_id)
                    mock_notify.assert_called_once()

            # Verify citing paper was auto-ingested
            citing_paper = engine.db.get_paper("2402.12345")
            self.assertIsNotNone(citing_paper)
            self.assertEqual(citing_paper["title"], "Novel Applications of Deep Cosmology")

            # Verify history was recorded
            history = engine.db.get_paper_citation_history(my_paper_id)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["citation_count"], 1)

            # Verify citation event was recorded
            events = engine.db.get_recent_citation_events(user_id)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["citing_arxiv_id"], "2402.12345")
        finally:
            engine.close()

    @patch("requests.post")
    def test_webhook_alerts(self, mock_post):
        """Test Slack and Discord citation alert formatting and dispatch."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        event = {
            "my_paper_title": "Cosmological Inference with JAX",
            "citing_title": "Accelerating Markov Chain Monte Carlo",
            "citing_arxiv_id": "2403.00001",
            "citing_authors": "Hawking, Penrose",
        }

        # Slack
        self.assertTrue(send_slack_citation_alert("https://hooks.slack.com/services/test", event))
        mock_post.assert_called()
        slack_payload = mock_post.call_args[1]["json"]
        self.assertIn("blocks", slack_payload)
        self.assertIn("Cosmological Inference with JAX", slack_payload["blocks"][0]["text"]["text"])

        # Discord
        mock_post.reset_mock()
        self.assertTrue(send_discord_citation_alert("https://discord.com/api/webhooks/test", event))
        mock_post.assert_called()
        discord_payload = mock_post.call_args[1]["json"]
        self.assertIn("content", discord_payload)
        self.assertIn("Accelerating Markov Chain Monte Carlo", discord_payload["content"])

        # notify_citation_events orchestrator
        mock_post.reset_mock()
        config = {
            "integrations": {
                "slack": {"enabled": True, "webhook_url": "https://hooks.slack.com/services/test"},
                "discord": {"enabled": True, "webhook_url": "https://discord.com/api/webhooks/test"},
            }
        }
        notify_citation_events(None, [event], config)
        self.assertEqual(mock_post.call_count, 2)


class TestCitationAlertsWebEndpoints(unittest.TestCase):
    """Test suite for /api/my-papers REST API routes."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_papers.db")
        self.db = PaperDatabase(db_path=self.db_path)

        self.mock_engine = MagicMock()
        self.mock_engine.db = self.db
        self.mock_engine.refresh_single_my_paper_citations = MagicMock()
        self.mock_engine.refresh_my_papers_citations = MagicMock()

        with patch("aura.web.app.RecommendationEngine", return_value=self.mock_engine):
            self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

        # Create test user and token
        user_id = self.db.create_user("cituser@example.com", "Password123!")
        self.token = self.db.create_api_token(user_id, "Test Client")

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_api_my_papers_crud(self):
        """Test listing, adding, and deleting papers via /api/my-papers."""
        headers = {"Authorization": f"Bearer {self.token}"}

        # 1. Initially empty
        res = self.client.get("/api/my-papers", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["papers"], [])

        # 2. Add paper
        res = self.client.post(
            "/api/my-papers",
            json={"title": "Registered Paper A", "arxiv_id": "2401.00001"},
            headers=headers,
        )
        self.assertEqual(res.status_code, 201)
        self.mock_engine.refresh_single_my_paper_citations.assert_called_once()

        # 3. List papers
        res = self.client.get("/api/my-papers", headers=headers)
        self.assertEqual(res.status_code, 200)
        papers = res.get_json()["papers"]
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["title"], "Registered Paper A")
        paper_id = papers[0]["id"]

        # 4. Citation history & events endpoints
        self.db.record_citation_history(1, paper_id, 3)
        self.db.record_citation_event(1, paper_id, "2402.00002", "Citing Title", "Citing Authors")

        res = self.client.get(f"/api/my-papers/{paper_id}/citation-history", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["history"]), 1)

        res = self.client.get("/api/my-papers/citation-events", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["events"]), 1)

        # 5. Trigger refresh
        res = self.client.post("/api/my-papers/refresh-citations", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.mock_engine.refresh_my_papers_citations.assert_called_once()

        # 6. Delete paper
        res = self.client.delete(f"/api/my-papers/{paper_id}", headers=headers)
        self.assertEqual(res.status_code, 200)
        papers_after = self.db.get_my_papers(user_id=1)
        self.assertEqual(len(papers_after), 0)


if __name__ == "__main__":
    unittest.main()
