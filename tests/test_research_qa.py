import sys
import unittest
from unittest.mock import Mock, MagicMock, patch

# Fake missing modules for import to avoid ModuleNotFoundError
sys.modules['openai'] = MagicMock()
sys.modules['anthropic'] = MagicMock()

from aura import llm  # noqa: E402
from aura.recommender import RecommendationEngine  # noqa: E402
from aura.web.app import create_app  # noqa: E402


class TestResearchQA(unittest.TestCase):
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

    @patch("aura.llm._resolve_api_key", return_value="mock-api-key")
    @patch("aura.llm._load_providers_order", return_value=["openai"])
    def test_stream_ask_paper_success(self, mock_order, mock_key):
        # Mock client and chat.completions.create to stream response
        mock_client = Mock()
        
        # Build generator response mock
        chunk1 = Mock()
        chunk1.choices = [Mock()]
        chunk1.choices[0].delta.content = "This paper "
        
        chunk2 = Mock()
        chunk2.choices = [Mock()]
        chunk2.choices[0].delta.content = "uses ResNet."
        
        mock_client.chat.completions.create.return_value = [chunk1, chunk2]

        with patch("openai.OpenAI", return_value=mock_client):
            stream = llm.stream_ask_paper(
                arxiv_id="2401.00001",
                question="What model is used?",
                full_text="This paper proposes a model that uses ResNet.",
                provider="openai"
            )
            chunks = list(stream)
            self.assertEqual("".join(chunks), "This paper uses ResNet.")
            
            # Verify correct prompt structure was generated and sent
            mock_client.chat.completions.create.assert_called_once()
            _, kwargs = mock_client.chat.completions.create.call_args
            prompt_sent = kwargs["messages"][0]["content"]
            self.assertIn("What model is used?", prompt_sent)
            self.assertIn("This paper proposes a model that uses ResNet.", prompt_sent)
            self.assertIn("Always use UK-English spelling (e.g., colour, prioritising, analysing).", prompt_sent)
            self.assertTrue(kwargs.get("stream", False))

    @patch("aura.llm._resolve_api_key", return_value="mock-api-key")
    @patch("aura.llm._load_providers_order", return_value=["google"])
    def test_stream_ask_paper_google_success(self, mock_order, mock_key):
        self._post_patcher.stop() # Temporarily stop post patcher to mock requests.post
        
        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        # Mock iter_lines to stream JSON lines
        mock_response.iter_lines.return_value = [
            b'[',
            b'  {"candidates": [{"content": {"parts": [{"text": "Gemini "}]}}]}',
            b'  ,{"candidates": [{"content": {"parts": [{"text": "response."}]}}]}',
            b']'
        ]
        
        with patch("aura.llm.requests.post", return_value=mock_response) as mock_post:
            stream = llm.stream_ask_paper(
                arxiv_id="2401.00001",
                question="What model is used?",
                full_text="Test paper text.",
                provider="google"
            )
            chunks = list(stream)
            self.assertEqual("".join(chunks), "Gemini response.")
            mock_post.assert_called_once()
            
        self._post_patcher.start()

    @patch("aura.llm._resolve_api_key", return_value=None)
    def test_stream_ask_paper_no_keys_fails(self, mock_key):
        stream = llm.stream_ask_paper(
            arxiv_id="2401.00001",
            question="What model is used?",
            full_text="Test paper text."
        )
        chunks = list(stream)
        self.assertTrue("".join(chunks).startswith("Error:"))


class TestRecommenderAndWebResearchQA(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        with patch("aura.recommender.PaperDatabase", return_value=self.db), \
             patch("aura.recommender.PreferenceModel"), \
             patch("aura.recommender.get_embedding_dim", return_value=3):
            self.engine = RecommendationEngine(data_dir="/tmp", categories=["astro-ph.CO"])
            
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

    def test_ask_paper_question_cache_hit(self):
        self.db.get_paper_text.return_value = "Cached paper text."
        
        with patch("aura.llm.stream_ask_paper", return_value=["A", "B", "C"]) as mock_stream:
            chunks = list(self.engine.ask_paper_question("2401.00001", "What is dark matter?"))
            
            self.assertEqual(chunks, ["A", "B", "C"])
            self.db.get_paper_text.assert_called_once_with("2401.00001")
            self.db.get_paper.assert_not_called()
            mock_stream.assert_called_once_with("2401.00001", "What is dark matter?", "Cached paper text.")

    @patch("aura.llm.extract_text_from_pdf_url", return_value="Newly extracted PDF text.")
    def test_ask_paper_question_cache_miss(self, mock_extract):
        self.db.get_paper_text.return_value = None
        self.db.get_paper.return_value = {
            "arxiv_id": "2401.00001",
            "title": "A Great Astro Paper",
            "pdf_url": "https://arxiv.org/pdf/2401.00001.pdf"
        }
        
        with patch("aura.llm.stream_ask_paper", return_value=["X", "Y"]) as mock_stream:
            chunks = list(self.engine.ask_paper_question("2401.00001", "What is dark energy?"))
            
            self.assertEqual(chunks, ["X", "Y"])
            self.db.get_paper_text.assert_called_once_with("2401.00001")
            self.db.get_paper.assert_called_once_with("2401.00001")
            mock_extract.assert_called_once_with("https://arxiv.org/pdf/2401.00001.pdf")
            self.db.add_paper_text.assert_called_once_with("2401.00001", "Newly extracted PDF text.")
            mock_stream.assert_called_once_with("2401.00001", "What is dark energy?", "Newly extracted PDF text.")

    def test_web_endpoint_qa_success(self):
        # Setup mock engine responses
        self.engine.ask_paper_question = Mock(return_value=["Stream", "ing", " content"])
        
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
        resp = client.get("/api/papers/2401.00001/ask?question=What+is+this?")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "text/event-stream")
        
        # Read the event stream response
        body = resp.data.decode("utf-8")
        self.assertIn('data: {"chunk": "Stream"}', body)
        self.assertIn('data: {"chunk": "ing"}', body)
        self.assertIn('data: {"chunk": " content"}', body)
        
        self.engine.ask_paper_question.assert_called_once_with("2401.00001", "What is this?")
