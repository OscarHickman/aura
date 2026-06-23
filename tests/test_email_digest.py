import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aura import email_digest


class TestEmailDigest(unittest.TestCase):
    def test_load_email_config_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            email_digest.load_email_config("/tmp/definitely_missing_email_config.json")

    def test_build_email_content(self):
        papers = [
            {
                "title": "Paper A",
                "authors": ["Ada", "Linus"],
                "score": 0.93,
                "url": "http://arxiv.org/abs/1",
                "summary": "Good summary",
            }
        ]
        trends = {"Machine learning": "AI models are improving."}
        text, html = email_digest._build_email_content(papers, trends=trends, app_name="AURA")
        self.assertIn("Paper A", text)
        self.assertIn("Good summary", text)
        self.assertIn("Machine Learning", text)
        self.assertIn("AI models are improving", text)
        self.assertIn("Paper A", html)

    @patch("aura.email_digest._send_smtp_email")
    @patch("aura.email_digest.RecommendationEngine")
    def test_send_top_recommendations_email(self, mock_engine_cls, mock_send):
        engine = Mock()
        engine.get_recommendations.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "Paper A",
                "authors": ["Ada"],
                "score": 0.9,
                "url": "http://arxiv.org/abs/2401.00001",
                "summary": "Existing summary",
            }
        ]
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

            result = email_digest.send_top_recommendations_email(
                data_dir="data",
                categories=["astro-ph.CO"],
                embedding_model="all-MiniLM-L6-v2",
                email_config_path=str(cfg),
                top_n=3,
            )

        self.assertEqual(result["status"], "sent")
        self.assertTrue(result["sent"])
        mock_send.assert_called_once()
        engine.close.assert_called_once()

    @patch("aura.email_digest._send_graph_email")
    @patch("aura.email_digest.RecommendationEngine")
    def test_send_top_recommendations_email_graph_path(
        self, mock_engine_cls, mock_graph_send
    ):
        engine = Mock()
        engine.get_recommendations.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "Paper A",
                "authors": ["Ada"],
                "score": 0.9,
                "url": "http://arxiv.org/abs/2401.00001",
                "summary": "Existing summary",
            }
        ]
        mock_engine_cls.return_value = engine

        with tempfile.TemporaryDirectory() as td:
            cfg = Path(td) / "email_graph.json"
            cfg.write_text(
                """
{
  "from_email": "o.hickman@outlook.com",
  "to_email": "oscarhickman7@hotmail.co.uk",
  "use_graph_api": true,
  "ms_client_id": "00000000-0000-0000-0000-000000000000",
  "ms_tenant": "consumers"
}
                """.strip()
            )

            result = email_digest.send_top_recommendations_email(
                data_dir="data",
                categories=["astro-ph.CO"],
                embedding_model="all-MiniLM-L6-v2",
                email_config_path=str(cfg),
                top_n=3,
            )

        self.assertEqual(result["status"], "sent")
        self.assertTrue(result["sent"])
        mock_graph_send.assert_called_once()
        engine.close.assert_called_once()

    @patch("smtplib.SMTP_SSL")
    def test_send_smtp_email_ssl(self, mock_smtp_ssl_cls):
        mock_smtp = Mock()
        mock_smtp_ssl_cls.return_value.__enter__.return_value = mock_smtp
        
        cfg = {
            "smtp_host": "smtp.ssl.com",
            "smtp_port": 465,
            "smtp_username": "user",
            "smtp_password": "pwd",
            "from_email": "from@test.com",
            "to_email": "to@test.com",
            "use_ssl": True
        }
        
        email_digest._send_smtp_email(cfg, "Sub", "Text", "HTML")
        mock_smtp_ssl_cls.assert_called_once_with("smtp.ssl.com", 465, timeout=30)
        mock_smtp.login.assert_called_once_with("user", "pwd")
        mock_smtp.send_message.assert_called_once()

    @patch("smtplib.SMTP")
    @patch("ssl.create_default_context")
    def test_send_smtp_email_tls(self, mock_ssl_context, mock_smtp_cls):
        mock_smtp = Mock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
        
        cfg = {
            "smtp_host": "smtp.tls.com",
            "smtp_port": 587,
            "smtp_username": "user",
            "smtp_password": "pwd",
            "from_email": "from@test.com",
            "to_email": "to@test.com",
            "use_ssl": False,
            "use_tls": True
        }
        
        email_digest._send_smtp_email(cfg, "Sub", "Text", "HTML")
        mock_smtp_cls.assert_called_once_with("smtp.tls.com", 587, timeout=30)
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with("user", "pwd")
        mock_smtp.send_message.assert_called_once()

    @patch("requests.post")
    @patch("aura.email_digest._acquire_graph_token", return_value="token123")
    def test_send_graph_email_failure(self, mock_token, mock_post):
        mock_resp = Mock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal error"
        mock_post.return_value = mock_resp
        
        cfg = {
            "from_email": "from@test.com",
            "to_email": "to@test.com",
        }
        
        with self.assertRaises(RuntimeError) as ctx:
            email_digest._send_graph_email(cfg, "Sub", "Text", "HTML")
        self.assertIn("Microsoft Graph send failed", str(ctx.exception))

    def test_collect_top_papers_with_summaries_fallback(self):
        engine = Mock()
        engine.get_recommendations.return_value = [
            {"arxiv_id": "1", "title": "Paper 1", "summary": ""},
            {"arxiv_id": "2", "title": "Paper 2", "summary": "AI FAIL"},
        ]
        engine.generate_summary_for_paper.side_effect = [
            {"summary": "Gen summary 1"},
            {"summary": ""}, # Generates empty summary (so it falls back to AI FAIL)
        ]
        
        res = email_digest._collect_top_papers_with_summaries(engine, 2)
        self.assertEqual(res[0]["summary"], "Gen summary 1")
        self.assertEqual(res[1]["summary"], "AI FAIL")

    @patch("aura.email_digest._send_smtp_email")
    @patch("aura.email_digest.RecommendationEngine")
    def test_send_group_digest_email(self, mock_engine_cls, mock_send):
        engine = Mock()
        engine.db.get_group.return_value = {"id": 1, "name": "Lab Group"}
        engine.db.get_group_members.return_value = [
            {"id": 1, "email": "alice@example.com"},
            {"id": 2, "email": "bob@example.com"}
        ]
        engine.db.get_group_paper_feed.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "Paper G",
                "authors": ["Ada"],
                "best_rating": 5,
                "url": "http://arxiv.org/abs/2401.00001",
                "summary": "Group paper summary",
            }
        ]
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

            result = email_digest.send_group_digest_email(
                data_dir="data",
                group_id=1,
                categories=["astro-ph.CO"],
                embedding_model="all-MiniLM-L6-v2",
                email_config_path=str(cfg),
                top_n=3,
            )

        self.assertEqual(result["status"], "sent")
        self.assertTrue(result["sent"])
        self.assertEqual(result["sent_count"], 2)
        self.assertEqual(result["sent_to"], ["alice@example.com", "bob@example.com"])
        self.assertEqual(mock_send.call_count, 2)
        engine.close.assert_called_once()

if __name__ == "__main__":
    unittest.main()
