import io
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

import run


class TestRunModule(unittest.TestCase):
    def test_load_config_missing_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "missing.yaml"
            data = run.load_config(str(path))
            self.assertEqual(data, {})

    def test_load_config_reads_yaml(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.yaml"
            path.write_text("port: 9999\n")
            data = run.load_config(str(path))
            self.assertEqual(data["port"], 9999)

    @patch("ai_papers.recommender.RecommendationEngine")
    def test_cmd_fetch_uses_cli_overrides(self, mock_engine_cls):
        engine = Mock()
        engine.fetch_new_papers.return_value = 7
        mock_engine_cls.return_value = engine

        args = Namespace(max_results=11, days_back=4, with_summaries=True)
        config = {
            "data_dir": "data",
            "categories": ["astro-ph.CO"],
            "embedding_model": "all-MiniLM-L6-v2",
        }

        run.cmd_fetch(args, config)

        engine.fetch_new_papers.assert_called_once_with(
            max_results=11, days_back=4, generate_summaries=True
        )
        engine.close.assert_called_once()

    @patch("ai_papers.recommender.RecommendationEngine")
    def test_cmd_summarize_passes_flags(self, mock_engine_cls):
        engine = Mock()
        engine.generate_missing_summaries.return_value = {"status": "ok"}
        mock_engine_cls.return_value = engine

        args = Namespace(limit=20, only_missing=True)
        config = {
            "data_dir": "data",
            "categories": ["astro-ph.CO"],
            "embedding_model": "all-MiniLM-L6-v2",
        }

        run.cmd_summarize(args, config)

        engine.generate_missing_summaries.assert_called_once_with(
            limit=20, include_failed=False
        )

    @patch("ai_papers.email_digest.send_top_recommendations_email")
    def test_cmd_email_digest(self, mock_send):
        mock_send.return_value = {"status": "sent", "sent": True}

        args = Namespace(top_n=3, email_config="user_credentials/email_config.json")
        config = {
            "data_dir": "data",
            "categories": ["astro-ph.CO"],
            "embedding_model": "all-MiniLM-L6-v2",
        }

        run.cmd_email_digest(args, config)

        mock_send.assert_called_once_with(
            data_dir="data",
            categories=["astro-ph.CO"],
            embedding_model="all-MiniLM-L6-v2",
            email_config_path="user_credentials/email_config.json",
            top_n=3,
        )

    def test_setup_scheduler_without_dependency(self):
        app = Mock()
        config = {}

        out = io.StringIO()
        with patch.dict("sys.modules", {"apscheduler": None}):
            with redirect_stdout(out):
                run._setup_scheduler(app, config)

        self.assertIn("Warning: apscheduler not installed", out.getvalue())


if __name__ == "__main__":
    unittest.main()
