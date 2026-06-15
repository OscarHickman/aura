import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# Fake missing modules for import
from unittest.mock import MagicMock
sys.modules['openai'] = MagicMock()
sys.modules['anthropic'] = MagicMock()

import numpy as np

from ai_papers import trends
from ai_papers.database import PaperDatabase


class TestTrends(unittest.TestCase):
    def test_load_save_topics(self):
        with tempfile.TemporaryDirectory() as td:
            topics = trends.load_topics(td)
            self.assertEqual(topics, trends.DEFAULT_TOPICS)

            custom_topics = ["quantum computing", "black holes"]
            trends.save_topics(td, custom_topics)
            loaded = trends.load_topics(td)
            self.assertEqual(loaded, custom_topics)

    @patch("ai_papers.trends._load_providers_order", return_value=["groq", "openai", "anthropic"])
    @patch("ai_papers.trends._resolve_api_key", return_value="some-api-key")
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

    @patch("ai_papers.trends._generate_generic_text")
    @patch("ai_papers.trends.get_model")
    @patch("ai_papers.trends.load_topics", return_value=["Machine learning"])
    def test_generate_monthly_trends(self, mock_load_topics, mock_get_model, mock_gen_text):
        mock_gen_text.side_effect = lambda prompt: "dynamic_topic" if "emerging" in prompt else "trend summary"
        
        # Mock sentence-transformers model. Topic embedding must be a 1D vector (dim 2)
        mock_st = Mock()
        mock_st.encode.return_value = np.array([[0.5, 0.5]])
        mock_get_model.return_value = mock_st

        with tempfile.TemporaryDirectory() as td:
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
            self.assertIn("dynamic_topic", topics)


if __name__ == "__main__":
    unittest.main()
