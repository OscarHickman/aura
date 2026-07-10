import io
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

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

    @patch("aura.recommender.RecommendationEngine")
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

    @patch("aura.recommender.RecommendationEngine")
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

    @patch("aura.email_digest.send_top_recommendations_email")
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

    @patch("subprocess.run")
    def test_cmd_init(self, mock_run):
        args = Namespace()
        config = {}
        run.cmd_init(args, config)
        mock_run.assert_called_once_with(["./setup.sh"], check=True)

    @patch("sys.version_info")
    @patch("pathlib.Path.exists")
    @patch("sqlite3.connect")
    @patch("builtins.open", new_callable=mock_open, read_data="{}")
    def test_cmd_doctor(self, mock_file, mock_connect, mock_exists, mock_version):
        # We need mock_version to look like version_info >= (3, 10)
        mock_version.__ge__.return_value = True
        mock_version.split.return_value = ["3.11.0"]

        # mock exists for config, LLM key, data dir, database, email config
        mock_exists.return_value = True

        # mock sqlite connection
        mock_conn = Mock()
        mock_connect.return_value = mock_conn

        args = Namespace(config="config.yaml")
        config = {"data_dir": "data", "llm_provider": "openai"}

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            out = io.StringIO()
            with redirect_stdout(out):
                run.cmd_doctor(args, config)

            output = out.getvalue()
            self.assertIn("Checking AURA health status...", output)
            self.assertIn("All checks passed!", output)

    @patch("aura.recommender.RecommendationEngine")
    @patch("aura.embedder.get_model")
    def test_cmd_import(self, mock_get_model, mock_engine_cls):
        engine = Mock()
        mock_engine_cls.return_value = engine
        
        mock_model = Mock()
        mock_model.encode.return_value = [0.1, 0.2, 0.3]
        mock_get_model.return_value = mock_model

        bib_content = """@article{testkey,
  title = {Test Paper Title},
  author = {Author One and Author Two},
  year = {2026},
  eprint = {2401.12345},
  url = {https://arxiv.org/abs/2401.12345},
  abstract = {This is a test abstract.},
}"""
        with tempfile.TemporaryDirectory() as td:
            bib_path = Path(td) / "library.bib"
            bib_path.write_text(bib_content, encoding="utf-8")
            
            args = Namespace(file=str(bib_path))
            config = {
                "data_dir": "data",
                "categories": ["astro-ph.CO"],
                "embedding_model": "all-MiniLM-L6-v2",
            }
            
            out = io.StringIO()
            with redirect_stdout(out):
                run.cmd_import(args, config)
                
            self.assertIn("Successfully imported", out.getvalue())

    @patch("aura.recommender.RecommendationEngine")
    def test_cmd_export_json_csv_bibtex(self, mock_engine_cls):
        engine = Mock()
        mock_engine_cls.return_value = engine
        
        mock_papers = [
            {
                "arxiv_id": "2401.00001",
                "title": "A Great Astronomy Paper",
                "authors": '["John Doe", "Jane Smith"]',
                "abstract": "This is a great abstract.",
                "categories": "astro-ph.CO",
                "published": "2026-01-01T00:00:00Z",
                "url": "https://arxiv.org/abs/2401.00001",
                "pdf_url": "https://arxiv.org/pdf/2401.00001.pdf",
                "source": "arxiv",
            }
        ]
        engine.db.get_papers.return_value = mock_papers
        
        with tempfile.TemporaryDirectory() as td:
            # Test JSON export
            out_json = Path(td) / "export.json"
            args_json = Namespace(format="json", output=str(out_json))
            config = {"data_dir": "data"}
            
            run.cmd_export(args_json, config)
            self.assertTrue(out_json.exists())
            self.assertIn("A Great Astronomy Paper", out_json.read_text())
            
            # Test CSV export
            out_csv = Path(td) / "export.csv"
            args_csv = Namespace(format="csv", output=str(out_csv))
            run.cmd_export(args_csv, config)
            self.assertTrue(out_csv.exists())
            self.assertIn("2401.00001", out_csv.read_text())
            
            # Test BibTeX export
            out_bib = Path(td) / "export.bib"
            args_bib = Namespace(format="bibtex", output=str(out_bib))
            run.cmd_export(args_bib, config)
            self.assertTrue(out_bib.exists())
            self.assertIn("@article{doe2026240100001,", out_bib.read_text())


if __name__ == "__main__":
    unittest.main()
