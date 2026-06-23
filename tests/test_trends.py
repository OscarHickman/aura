import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# Fake missing modules for import
from unittest.mock import MagicMock
sys.modules['openai'] = MagicMock()
sys.modules['anthropic'] = MagicMock()

import numpy as np  # noqa: E402

from aura import trends  # noqa: E402
from aura.database import PaperDatabase  # noqa: E402


class TestTrends(unittest.TestCase):
    def test_load_save_topics(self):
        with tempfile.TemporaryDirectory() as td:
            topics = trends.load_topics(td)
            self.assertEqual(topics, trends.DEFAULT_TOPICS)

            # Test list-based migration
            custom_topics_list = ["quantum computing", "black holes"]
            trends.save_topics(td, custom_topics_list)
            loaded = trends.load_topics(td)
            expected_migrated = {
                "sbi": [],
                "galaxy_statistics": [],
                "ml_methods": ["quantum computing", "black holes"]
            }
            self.assertEqual(loaded, expected_migrated)

            # Test dictionary-based saving and loading
            custom_topics_dict = {
                "sbi": ["neural posterior estimation"],
                "galaxy_statistics": ["galaxy clustering"],
                "ml_methods": ["quantum computing", "black holes"]
            }
            trends.save_topics(td, custom_topics_dict)
            loaded_dict = trends.load_topics(td)
            self.assertEqual(loaded_dict, custom_topics_dict)

    @patch("aura.trends._load_providers_order", return_value=["groq", "openai", "anthropic"])
    @patch("aura.trends._resolve_api_key", return_value="some-api-key")
    def test_generate_generic_text_providers(self, mock_resolve_key, mock_order):
        # 1. Test Groq success
        with patch("groq.Groq") as mock_groq_cls:
            mock_client = Mock()
            mock_message = Mock()
            mock_message.choices = [Mock(message=Mock(content="groq result"))]
            mock_client.chat.completions.create.return_value = mock_message
            mock_groq_cls.return_value = mock_client

            res = trends._generate_generic_text("test prompt")
            self.assertEqual(res, "groq result")

        # 2. Test OpenAI success (when Groq fails)
        with patch("groq.Groq", side_effect=RuntimeError("fail")), patch("openai.OpenAI") as mock_openai_cls:
            mock_client = Mock()
            mock_response = Mock()
            mock_response.choices = [Mock(message=Mock(content="openai result"))]
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai_cls.return_value = mock_client

            res = trends._generate_generic_text("test prompt")
            self.assertEqual(res, "openai result")

        # 3. Test Anthropic success (when others fail)
        with patch("groq.Groq", side_effect=RuntimeError("fail")), \
             patch("openai.OpenAI", side_effect=RuntimeError("fail")), \
             patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = Mock()
            mock_message = Mock()
            mock_message.content = [Mock(text="anthropic result")]
            mock_client.messages.create.return_value = mock_message
            mock_anthropic_cls.return_value = mock_client

            res = trends._generate_generic_text("test prompt")
            self.assertEqual(res, "anthropic result")

    @patch("aura.trends._generate_generic_text")
    @patch("aura.trends.get_model")
    def test_verbose_discovery_response_not_saved(self, mock_get_model, mock_gen_text):
        """LLM returning a verbose paragraph instead of keywords must not corrupt saved topics."""
        verbose_response = (
            "None of these topics are directly related to the following emerging new subfields:\n\n"
            "Cosmological Distance Tensions, Cosmic-Ray Ionization, Dark Sector Interactions, "
            "Intrinsic Entropy Couplings.\n\nTherefore, the new keywords to track are: "
            "Cosmological Distance Tensions, Cosmic-Ray Ionization."
        )
        mock_gen_text.side_effect = lambda prompt: verbose_response if "emerging" in prompt else "trend summary"

        mock_st = Mock()
        mock_st.encode.return_value = np.array([[0.5, 0.5]])
        mock_get_model.return_value = mock_st

        with tempfile.TemporaryDirectory() as td:
            trends.save_topics(td, {
                "sbi": [],
                "galaxy_statistics": [],
                "ml_methods": ["Machine learning"]
            })
            db_path = Path(td) / "papers.db"
            db = PaperDatabase(db_path)
            from datetime import datetime
            now_iso = datetime.utcnow().isoformat()
            db.add_paper(
                {"arxiv_id": "2401.00002", "title": "A Paper", "abstract": "An abstract.",
                 "authors": ["Ada"], "categories": ["astro-ph.CO"], "published": now_iso},
                embedding=np.array([0.5, 0.5], dtype=np.float32)
            )
            db.close()

            trends.generate_monthly_trends(td)
            saved_topics = trends.load_topics(td)
            flat_saved = []
            for sec_topics in saved_topics.values():
                flat_saved.extend(sec_topics)
            for t in flat_saved:
                self.assertLessEqual(len(t.split()), 5, f"Topic looks like a sentence: {t!r}")
                self.assertNotIn(":", t, f"Topic contains colon: {t!r}")
                self.assertNotIn(".", t, f"Topic contains period: {t!r}")

    @patch("aura.trends._generate_generic_text")
    @patch("aura.trends.get_model")
    def test_no_provider_response_not_saved(self, mock_get_model, mock_gen_text):
        """'No AI provider available' fallback must never be saved as a topic."""
        mock_gen_text.return_value = "No AI provider available to generate trends."

        mock_st = Mock()
        mock_st.encode.return_value = np.array([[0.5, 0.5]])
        mock_get_model.return_value = mock_st

        with tempfile.TemporaryDirectory() as td:
            trends.save_topics(td, {
                "sbi": [],
                "galaxy_statistics": [],
                "ml_methods": ["Machine learning"]
            })
            db_path = Path(td) / "papers.db"
            db = PaperDatabase(db_path)
            from datetime import datetime
            now_iso = datetime.utcnow().isoformat()
            db.add_paper(
                {"arxiv_id": "2401.00003", "title": "A Paper", "abstract": "An abstract.",
                 "authors": ["Ada"], "categories": ["astro-ph.CO"], "published": now_iso},
                embedding=np.array([0.5, 0.5], dtype=np.float32)
            )
            db.close()

            trends.generate_monthly_trends(td)
            saved_topics = trends.load_topics(td)
            flat_saved = []
            for sec_topics in saved_topics.values():
                flat_saved.extend(sec_topics)
            for t in flat_saved:
                self.assertNotIn("no ai provider", t.lower())

    @patch("aura.trends._generate_generic_text")
    @patch("aura.trends.get_model")
    def test_generate_monthly_trends(self, mock_get_model, mock_gen_text):
        def mock_gen_response(prompt):
            if "emerging" in prompt:
                return "dynamic topic"
            if "distinct scientific" in prompt:
                return "YES"
            return "trend summary"

        mock_gen_text.side_effect = mock_gen_response

        # Mock sentence-transformers model. Topic embedding must be a 1D vector (dim 2)
        mock_st = Mock()
        mock_st.encode.return_value = np.array([[0.5, 0.5]])
        mock_get_model.return_value = mock_st

        with tempfile.TemporaryDirectory() as td:
            trends.save_topics(td, {
                "sbi": [],
                "galaxy_statistics": [],
                "ml_methods": ["Machine learning"]
            })
            db_path = Path(td) / "papers.db"
            db = PaperDatabase(db_path)

            # Add a paper published today
            from datetime import datetime
            now_iso = datetime.utcnow().isoformat()
            db.add_paper(
                {
                    "arxiv_id": "2401.00001",
                    "title": "A Great ML Paper",
                    "abstract": "An abstract covering Machine learning emulators.",
                    "authors": ["Ada"],
                    "categories": ["astro-ph.CO"],
                    "published": now_iso,
                },
                embedding=np.array([0.5, 0.5], dtype=np.float32)
            )
            db.close()

            # Run monthly trends
            results = trends.generate_monthly_trends(td)
            self.assertIn("Machine learning", results)
            self.assertEqual(results["Machine learning"], "trend summary")

            # Check if dynamic topic was added
            topics = trends.load_topics(td)
            flat_topics = []
            for sec_topics in topics.values():
                flat_topics.extend(sec_topics)
            self.assertIn("dynamic topic", flat_topics)


if __name__ == "__main__":
    unittest.main()
