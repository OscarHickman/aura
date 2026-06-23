import sys
import unittest
from unittest.mock import Mock, MagicMock, patch

# Fake missing modules for import to avoid ModuleNotFoundError
sys.modules['openai'] = MagicMock()
sys.modules['anthropic'] = MagicMock()

from aura import llm  # noqa: E402
from aura.recommender import RecommendationEngine  # noqa: E402
from aura.web.app import create_app  # noqa: E402


class TestDeepSummaries(unittest.TestCase):
    def setUp(self):
        llm._provider_config_cache.clear()
        llm._providers_order_cache = None
        llm._warned_messages.clear()

        # Prevent real external LLM/HTTP calls
        self._post_patcher = patch(
            "aura.llm.requests.post",
            side_effect=AssertionError("External LLM POST call attempted during tests"),
        )
        self._get_patcher = patch(
            "aura.llm.requests.get",
            side_effect=AssertionError("External HTTP GET call attempted during tests"),
        )
        self._post_patcher.start()
        self._get_patcher.start()

    def tearDown(self):
        self._post_patcher.stop()
        self._get_patcher.stop()

    @patch("aura.llm.requests.get")
    @patch("pypdf.PdfReader")
    def test_extract_text_from_pdf_url_success(self, mock_reader_class, mock_get):
        # Mock requests.get response
        mock_response = Mock()
        mock_response.content = b"%PDF-1.4 mock bytes"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Mock PdfReader and pages
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "Page one content."
        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "Page two content."

        mock_reader = Mock()
        mock_reader.pages = [mock_page1, mock_page2]
        mock_reader_class.return_value = mock_reader

        extracted_text = llm.extract_text_from_pdf_url("https://arxiv.org/pdf/2401.00001.pdf")
        self.assertEqual(extracted_text, "Page one content.\nPage two content.")
        
        # Verify headers used
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertIn("User-Agent", kwargs["headers"])

    @patch("aura.llm.extract_text_from_pdf_url", return_value="Mock PDF research content.")
    @patch("aura.llm._resolve_api_key", return_value="mock-api-key")
    @patch("aura.llm._load_providers_order", return_value=["openai"])
    def test_generate_full_summary_grad_student(self, mock_order, mock_key, mock_extract):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Grad student structured summary result"
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            summary = llm.generate_full_summary(
                arxiv_id="2401.00001",
                pdf_url="https://arxiv.org/pdf/2401.00001.pdf",
                mode="grad_student",
                provider="openai"
            )
            self.assertEqual(summary, "Grad student structured summary result")
            
            # Verify correct prompt structure was generated and sent
            mock_client.chat.completions.create.assert_called_once()
            _, kwargs = mock_client.chat.completions.create.call_args
            prompt_sent = kwargs["messages"][0]["content"]
            self.assertIn("### Background", prompt_sent)
            self.assertIn("### Methods", prompt_sent)
            self.assertIn("### Results", prompt_sent)
            self.assertIn("### Significance", prompt_sent)
            self.assertIn("graduate student", prompt_sent)
            # Verify UK-English instruction is present
            self.assertIn("Always use UK-English spelling (e.g., colour, prioritising, analysing).", prompt_sent)

    @patch("aura.llm.extract_text_from_pdf_url", return_value="Mock PDF research content.")
    @patch("aura.llm._resolve_api_key", return_value="mock-api-key")
    @patch("aura.llm._load_providers_order", return_value=["openai"])
    def test_generate_full_summary_expert(self, mock_order, mock_key, mock_extract):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Expert structured summary result"
        mock_client.chat.completions.create.return_value = mock_response

        with patch("openai.OpenAI", return_value=mock_client):
            summary = llm.generate_full_summary(
                arxiv_id="2401.00001",
                pdf_url="https://arxiv.org/pdf/2401.00001.pdf",
                mode="expert",
                provider="openai"
            )
            self.assertEqual(summary, "Expert structured summary result")
            
            # Verify correct prompt structure was generated and sent
            mock_client.chat.completions.create.assert_called_once()
            _, kwargs = mock_client.chat.completions.create.call_args
            prompt_sent = kwargs["messages"][0]["content"]
            self.assertIn("### Background", prompt_sent)
            self.assertIn("### Methods", prompt_sent)
            self.assertIn("### Results", prompt_sent)
            self.assertIn("### Significance", prompt_sent)
            self.assertIn("expert researcher", prompt_sent)
            # Verify UK-English instruction is present
            self.assertIn("Always use UK-English spelling (e.g., colour, prioritising, analysing).", prompt_sent)

    @patch("aura.llm.extract_text_from_pdf_url", side_effect=Exception("Failed to fetch PDF"))
    def test_generate_full_summary_extraction_error(self, mock_extract):
        summary = llm.generate_full_summary(
            arxiv_id="2401.00001",
            pdf_url="https://arxiv.org/pdf/2401.00001.pdf",
            mode="grad_student"
        )
        self.assertTrue(summary.startswith("Error:"))
        self.assertIn("Failed to download or parse PDF", summary)

    @patch("aura.llm.extract_text_from_pdf_url", return_value="")
    def test_generate_full_summary_empty_text(self, mock_extract):
        summary = llm.generate_full_summary(
            arxiv_id="2401.00001",
            pdf_url="https://arxiv.org/pdf/2401.00001.pdf",
            mode="grad_student"
        )
        self.assertTrue(summary.startswith("Error:"))
        self.assertIn("Extracted text from PDF was empty.", summary)


class TestRecommenderAndWebDeepSummaries(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        with patch("aura.recommender.PaperDatabase", return_value=self.db), \
             patch("aura.recommender.PreferenceModel"), \
             patch("aura.recommender.get_embedding_dim", return_value=3):
            self.engine = RecommendationEngine(data_dir="/tmp", categories=["astro-ph.CO"])
        
        # Mock user details for auth bypass in web app testing
        self._test_user = {
            "id": 1,
            "email": "test@example.com",
            "password_hash": "hashed",
            "is_admin": 1,
            "is_active": 1,
            "created_at": "2024-01-01T00:00:00",
        }
        self.db.count_users.return_value = 0
        self.db.create_user.return_value = self._test_user
        self.db.get_user_by_email.return_value = self._test_user
        self.db.get_user_by_id.return_value = self._test_user
        self.db.get_user_tokens.return_value = []
        self.db.get_user_groups.return_value = []
        self.db.get_all_groups.return_value = []
        self.db.get_public_collections.return_value = []
        self.db.get_all_users.return_value = [self._test_user]
        self.db.get_fetch_log.return_value = []
        self.db.get_stats.return_value = {
            "total_papers": 1,
            "total_rated": 5,
            "thumbs_up": 3,
            "thumbs_down": 2,
            "with_embeddings": 1,
            "with_summaries": 1,
        }
        self.engine.get_stats = Mock(return_value={
            "database": {
                "total_papers": 1,
                "total_rated": 5,
                "thumbs_up": 3,
                "thumbs_down": 2,
                "with_embeddings": 1,
                "with_summaries": 1,
            },
            "model": {
                "parameters": 100,
                "embedding_dim": 3,
                "learning_rate": 0.001,
                "total_trained": 5,
                "replay_buffer_size": 5,
            },
            "categories": ["astro-ph.CO"],
            "data_dir": "/tmp",
        })

    def test_get_or_generate_full_summary_cache_hit(self):
        self.db.get_full_summary.return_value = "This is a cached summary."
        
        # Calling get_or_generate_full_summary should fetch cached content directly
        summary = self.engine.get_or_generate_full_summary(arxiv_id="2401.00001", mode="grad_student")
        
        self.assertEqual(summary, "This is a cached summary.")
        self.db.get_full_summary.assert_called_once_with("2401.00001", "grad_student")
        self.db.get_paper.assert_not_called()

    @patch("aura.llm.generate_full_summary", return_value="Newly generated structured summary.")
    def test_get_or_generate_full_summary_cache_miss(self, mock_gen):
        self.db.get_full_summary.return_value = None
        self.db.get_paper.return_value = {
            "arxiv_id": "2401.00001",
            "title": "A Great Astro Paper",
            "pdf_url": "https://arxiv.org/pdf/2401.00001.pdf"
        }
        
        summary = self.engine.get_or_generate_full_summary(arxiv_id="2401.00001", mode="grad_student")
        
        self.assertEqual(summary, "Newly generated structured summary.")
        self.db.get_full_summary.assert_called_once_with("2401.00001", "grad_student")
        self.db.get_paper.assert_called_once_with("2401.00001")
        mock_gen.assert_called_once_with("2401.00001", "https://arxiv.org/pdf/2401.00001.pdf", "grad_student")
        self.db.add_full_summary.assert_called_once_with("2401.00001", "grad_student", "Newly generated structured summary.")

    def test_web_endpoint_deep_summary_success(self):
        # Setup mock engine responses
        self.engine.get_or_generate_full_summary = Mock(return_value="Detailed research overview.")
        
        with patch("aura.web.app.RecommendationEngine", return_value=self.engine):
            app = create_app()
        app.testing = True
        client = app.test_client()

        # Log in
        with patch("aura.web.app.generate_password_hash", return_value="hashed"), \
             patch("aura.web.app.check_password_hash", return_value=True):
            client.post("/register", data={
                "email": "test@example.com",
                "password": "password123",
                "confirm_password": "password123",
            }, follow_redirects=True)
            client.post("/login", data={
                "email": "test@example.com",
                "password": "password123",
            }, follow_redirects=True)

        # GET request to deep summary API
        resp = client.get("/api/papers/2401.00001/deep-summary?mode=expert")
        self.assertEqual(resp.status_code, 200)
        
        json_data = resp.get_json()
        self.assertEqual(json_data["arxiv_id"], "2401.00001")
        self.assertEqual(json_data["mode"], "expert")
        self.assertEqual(json_data["summary"], "Detailed research overview.")
        
        self.engine.get_or_generate_full_summary.assert_called_once_with("2401.00001", mode="expert")

    def test_web_endpoint_deep_summary_invalid_mode(self):
        with patch("aura.web.app.RecommendationEngine", return_value=self.engine):
            app = create_app()
        app.testing = True
        client = app.test_client()

        # Log in
        with patch("aura.web.app.generate_password_hash", return_value="hashed"), \
             patch("aura.web.app.check_password_hash", return_value=True):
            client.post("/register", data={
                "email": "test@example.com",
                "password": "password123",
                "confirm_password": "password123",
            }, follow_redirects=True)
            client.post("/login", data={
                "email": "test@example.com",
                "password": "password123",
            }, follow_redirects=True)

        resp = client.get("/api/papers/2401.00001/deep-summary?mode=invalid_mode")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid mode", resp.get_json()["error"])
