import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from aura import briefs


class TestResearchBriefs(unittest.TestCase):
    def test_build_fallback_brief_html(self):
        papers = [
            {
                "arxiv_id": "2401.00001",
                "title": "A Great Paper",
                "authors": '["Ada", "Linus"]',
                "categories": "astro-ph.CO",
                "summary": "Good summary of paper",
                "published": "2026-01-01T00:00:00Z"
            }
        ]
        html = briefs.build_fallback_brief_html(papers, "2026-06-23")
        self.assertIn("Weekly Research Brief for 2026-06-23", html)
        self.assertIn("A Great Paper", html)
        self.assertIn("Ada", html)

    @patch("aura.briefs._generate_generic_text")
    def test_generate_weekly_brief_content_llm(self, mock_gen):
        mock_gen.return_value = "<div>LLM Weekly Brief Content</div>"
        engine = Mock()
        engine.get_recommendations.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "A Great Paper",
                "authors": '["Ada", "Linus"]',
                "categories": "astro-ph.CO",
                "summary": "Good summary of paper",
                "published": "2026-01-01T00:00:00Z"
            }
        ]
        
        content = briefs.generate_weekly_brief_content(engine, "2026-06-23")
        self.assertEqual(content, "<div>LLM Weekly Brief Content</div>")
        mock_gen.assert_called_once()

    @patch("aura.briefs._generate_generic_text")
    def test_generate_weekly_brief_content_fallback(self, mock_gen):
        mock_gen.return_value = "No AI provider available to generate trends."
        engine = Mock()
        engine.get_recommendations.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "A Great Paper",
                "authors": '["Ada", "Linus"]',
                "categories": "astro-ph.CO",
                "summary": "Good summary of paper",
                "published": "2026-01-01T00:00:00Z"
            }
        ]
        
        content = briefs.generate_weekly_brief_content(engine, "2026-06-23")
        self.assertIn("Weekly Research Brief for 2026-06-23", content)
        self.assertIn("A Great Paper", content)

    def test_get_weekly_recommendations(self):
        engine = Mock()
        now = datetime.utcnow()
        recent_pub = (now - timedelta(days=2)).isoformat() + "Z"
        old_pub = (now - timedelta(days=10)).isoformat() + "Z"
        
        engine.get_recommendations.return_value = [
            {
                "arxiv_id": "1",
                "title": "Recent Paper",
                "published": recent_pub,
                "authors": '["Ada"]'
            },
            {
                "arxiv_id": "2",
                "title": "Old Paper",
                "published": old_pub,
                "authors": '["Bob"]'
            }
        ]
        
        recs = briefs.get_weekly_recommendations(engine, limit=5)
        self.assertEqual(len(recs), 2)
        
        engine.get_recommendations.return_value = [
            {"arxiv_id": "1", "title": "Recent 1", "published": recent_pub},
            {"arxiv_id": "2", "title": "Recent 2", "published": recent_pub},
            {"arxiv_id": "3", "title": "Recent 3", "published": recent_pub},
            {"arxiv_id": "4", "title": "Old 1", "published": old_pub},
        ]
        recs = briefs.get_weekly_recommendations(engine, limit=5)
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]["arxiv_id"], "1")
        self.assertEqual(recs[1]["arxiv_id"], "2")
        self.assertEqual(recs[2]["arxiv_id"], "3")

    @patch("aura.email_digest._send_smtp_email")
    @patch("aura.briefs.generate_weekly_brief_content")
    @patch("aura.briefs.RecommendationEngine")
    def test_send_weekly_brief_email(self, mock_engine_cls, mock_gen_content, mock_send):
        mock_gen_content.return_value = "<div>Mock Brief Content</div>"
        engine = Mock()
        engine.db = Mock()
        engine.db.get_brief.return_value = None
        mock_engine_cls.return_value = engine
        
        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "email.json"
            cfg.write_text(
                """
{
  "smtp_host": "smtp.example.com",
  "smtp_port": 587,
  "smtp_username": "u",
  "smtp_password": "p",
  "from_email": "from@example.com",
  "to_email": "to@example.com",
  "use_tls": true,
  "use_ssl": false
}
                """.strip()
            )
            
            result = briefs.send_weekly_brief_email(
                data_dir="data",
                categories=["astro-ph.CO"],
                embedding_model="all-MiniLM-L6-v2",
                date_str="2026-06-23",
                email_config_path=str(cfg)
            )
            
        self.assertEqual(result["status"], "sent")
        self.assertTrue(result["sent"])
        mock_send.assert_called_once()
        engine.db.add_brief.assert_called_once()
