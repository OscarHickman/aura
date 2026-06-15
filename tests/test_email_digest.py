import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ai_papers import email_digest


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
        text, html = email_digest._build_email_content(papers, trends=trends, app_name="AI Papers")
        self.assertIn("Paper A", text)
        self.assertIn("Good summary", text)
        self.assertIn("Machine Learning", text)
        self.assertIn("AI models are improving", text)
        self.assertIn("Paper A", html)

    @patch("ai_papers.email_digest._send_smtp_email")
    @patch("ai_papers.email_digest.RecommendationEngine")
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

    @patch("ai_papers.email_digest._send_graph_email")
    @patch("ai_papers.email_digest.RecommendationEngine")
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


if __name__ == "__main__":
    unittest.main()
