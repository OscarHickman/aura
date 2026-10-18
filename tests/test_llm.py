import json
import os
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock, MagicMock, patch

# Fake missing modules for import
sys.modules['openai'] = MagicMock()
sys.modules['anthropic'] = MagicMock()

from aura import llm  # noqa: E402


class TestLLM(unittest.TestCase):
    def setUp(self):
        llm._provider_config_cache.clear()
        llm._providers_order_cache = None
        llm._warned_messages.clear()

        # Safety rail: fail tests immediately if any code path tries real HTTP LLM calls.
        self._http_patcher = patch(
            "aura.llm.requests.post",
            side_effect=AssertionError("External LLM HTTP call attempted during tests"),
        )
        self._http_patcher.start()

    def tearDown(self):
        self._http_patcher.stop()

    def test_clean_summary_text_strips_prefix(self):
        text = "Here is a summary of the paper covering motivation, key findings, and limitations: Great result."
        cleaned = llm._clean_summary_text(text)
        self.assertEqual(cleaned, "Great result.")

    def test_clean_summary_text_strips_groq_variant_heres_sentances(self):
        text = "heres a summary of the paper in 2 sentances covering motivation, key findings and limitations: Strong lensing constraints are improved."
        cleaned = llm._clean_summary_text(text)
        self.assertEqual(cleaned, "Strong lensing constraints are improved.")

    @patch("aura.llm._load_provider_config", return_value={"api_key": "cfg-key"})
    def test_resolve_api_key_priority(self, _mock_cfg):
        with patch.dict(
            os.environ,
            {"LLM_API_KEY": "global", "OPENAI_API_KEY": "provider"},
            clear=True,
        ):
            self.assertEqual(
                llm._resolve_api_key("explicit", "OPENAI_API_KEY", "openai"), "explicit"
            )
            self.assertEqual(
                llm._resolve_api_key(None, "OPENAI_API_KEY", "openai"), "global"
            )

        with patch.dict(os.environ, {"OPENAI_API_KEY": "provider"}, clear=True):
            self.assertEqual(
                llm._resolve_api_key(None, "OPENAI_API_KEY", "openai"), "provider"
            )

        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                llm._resolve_api_key(None, "OPENAI_API_KEY", "openai"), "cfg-key"
            )

    def test_load_providers_order_from_file_and_default(self):
        with tempfile.TemporaryDirectory() as td:
            cred = Path(td)
            with patch("aura.llm._credentials_dir", return_value=cred):
                llm._providers_order_cache = None
                self.assertEqual(llm._load_providers_order(), ["groq", "google"])

                (cred / "llm_providers.json").write_text(
                    json.dumps({"order": ["openai", "groq"]})
                )
                llm._providers_order_cache = None
                self.assertEqual(llm._load_providers_order(), ["openai", "groq"])

    @patch("aura.llm._load_providers_order", return_value=["groq", "openai"])
    def test_generate_summary_fallback(self, _mock_order):
        with patch.dict(
            llm._PROVIDER_FUNCS,
            {
                "groq": lambda *_args, **_kwargs: None,
                "openai": lambda *_args, **_kwargs: "ok-summary",
            },
            clear=False,
        ):
            summary = llm.generate_summary("t", "a")
            self.assertEqual(summary, "ok-summary")

    @patch("aura.llm._load_providers_order", return_value=["groq"])
    def test_generate_summary_always_cleans_provider_output(self, _mock_order):
        with patch.dict(
            llm._PROVIDER_FUNCS,
            {
                "groq": lambda *_args, **_kwargs: (
                    "heres a summary of the paper in 3 sentances covering motivation, "
                    "key findings and limitations: Final clean summary."
                )
            },
            clear=False,
        ):
            summary = llm.generate_summary("t", "a")
            self.assertEqual(summary, "Final clean summary.")

    @patch("aura.llm._resolve_api_key", return_value="test-key")
    @patch("aura.llm._get_provider_setting", return_value="llama-3.1-8b-instant")
    def test_summarize_groq_success(self, mock_setting, mock_key):
        mock_client = Mock()
        mock_message = Mock()
        mock_message.choices = [Mock()]
        mock_message.choices[0].message.content = "Groq summary response"
        mock_client.chat.completions.create.return_value = mock_message
        
        with patch("groq.Groq", return_value=mock_client):
            summary = llm._summarize_groq("Title", "Abstract")
            self.assertEqual(summary, "Groq summary response")

    @patch("aura.llm._resolve_api_key", return_value="test-key")
    def test_summarize_google_success(self, mock_key):
        self._http_patcher.stop() # stop the safety rail mock temporarily
        
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Google Gemini summary response"}
                        ]
                    }
                }
            ]
        }
        
        with patch("aura.llm.requests.post", return_value=mock_resp) as mock_post:
            summary = llm._summarize_google("Title", "Abstract", retry=False)
            self.assertEqual(summary, "Google Gemini summary response")
            mock_post.assert_called_once()
            
        self._http_patcher.start() # restart safety rail mock

    @patch("aura.llm._resolve_api_key", return_value="test-key")
    def test_summarize_openai_success(self, mock_key):
        mock_client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "OpenAI summary response"
        mock_client.chat.completions.create.return_value = mock_response
        
        with patch("openai.OpenAI", return_value=mock_client):
            summary = llm._summarize_openai("Title", "Abstract")
            self.assertEqual(summary, "OpenAI summary response")

    @patch("aura.llm._resolve_api_key", return_value="test-key")
    def test_summarize_anthropic_success(self, mock_key):
        mock_client = Mock()
        mock_message = Mock()
        mock_message.content = [Mock()]
        mock_message.content[0].text = "Anthropic summary response"
        mock_client.messages.create.return_value = mock_message
        
        with patch("anthropic.Anthropic", return_value=mock_client):
            summary = llm._summarize_anthropic("Title", "Abstract")
            self.assertEqual(summary, "Anthropic summary response")


    @patch("aura.llm._load_providers_order", return_value=["groq"])
    @patch("aura.llm._resolve_api_key", return_value="test-key")
    def test_execute_llm_groq(self, mock_key, _mock_order):
        mock_client = Mock()
        mock_message = Mock()
        mock_message.choices = [Mock()]
        mock_message.choices[0].message.content = '{"observables": ["weak lensing"], "datasets": ["DESI"], "methods": ["MCMC"]}'
        mock_client.chat.completions.create.return_value = mock_message
        
        with patch("groq.Groq", return_value=mock_client):
            res = llm.execute_llm("test prompt")
            self.assertIn("DESI", res)

    @patch("aura.llm.execute_llm")
    def test_extract_cosmology_metadata(self, mock_execute):
        mock_execute.return_value = '{"observables": ["weak lensing", "invalid_obs"], "datasets": ["DESI"], "methods": ["MCMC"]}'
        meta = llm.extract_cosmology_metadata("Title", "Abstract")
        self.assertEqual(meta["observables"], ["weak lensing"]) # invalid_obs filtered out
        self.assertEqual(meta["datasets"], ["DESI"])
        self.assertEqual(meta["methods"], ["MCMC"])

    def test_summarize_extractive(self):
        title = "Constraining Dark Energy with DESI Year 1 BAO"
        abstract = (
            "We present measurements of baryon acoustic oscillations from DESI Year 1. "
            "We measure the expansion rate across redshift ranges up to z = 2.4. "
            "Our results place tight constraints on the dark energy equation of state w(a). "
            "Systematic uncertainties remain dominated by tracer selection effects."
        )
        summary = llm._summarize_extractive(title, abstract)
        self.assertIsNotNone(summary)
        self.assertTrue(len(summary) > 20)
        self.assertIn("baryon acoustic oscillations", summary.lower())

    def test_get_effective_providers_order(self):
        with patch.dict(
            os.environ,
            {"OPENROUTER_API_KEY": "sk-or-test", "OLLAMA_HOST": "http://127.0.0.1:11434"},
            clear=True,
        ):
            with patch("aura.llm._load_providers_order", return_value=["groq", "google"]):
                order = llm.get_effective_providers_order()
                self.assertEqual(order[:2], ["groq", "google"])
                self.assertIn("openrouter", order)
                self.assertIn("ollama", order)
                self.assertEqual(order[-1], "extractive")

    @patch("aura.llm._resolve_api_key", return_value="test-key")
    @patch("aura.llm._get_provider_setting", return_value="llama-3.1-8b-instant")
    def test_summarize_groq_fallback_on_429(self, mock_setting, mock_key):
        from groq import APIStatusError
        mock_client = Mock()
        error_resp = Mock()
        error_resp.status_code = 429
        mock_client.chat.completions.create.side_effect = [
            APIStatusError("Rate limit exceeded", response=error_resp, body={"error": "rate_limit"}),
            Mock(choices=[Mock(message=Mock(content="Fallback model summary"))]),
        ]
        with patch("groq.Groq", return_value=mock_client):
            summary = llm._summarize_groq("Title", "Abstract")
            self.assertEqual(summary, "Fallback model summary")

    @patch("aura.llm._resolve_api_key", return_value="test-or-key")
    def test_summarize_openrouter_success(self, mock_key):
        self._http_patcher.stop()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "OpenRouter generated summary"}}]
        }
        with patch("aura.llm.requests.post", return_value=mock_resp):
            summary = llm._summarize_openrouter("Title", "Abstract")
            self.assertEqual(summary, "OpenRouter generated summary")
        self._http_patcher.start()

    @patch("aura.llm._resolve_api_key", return_value="test-ds-key")
    def test_summarize_deepseek_success(self, mock_key):
        self._http_patcher.stop()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "DeepSeek generated summary"}}]
        }
        with patch("aura.llm.requests.post", return_value=mock_resp):
            summary = llm._summarize_deepseek("Title", "Abstract")
            self.assertEqual(summary, "DeepSeek generated summary")
        self._http_patcher.start()

    def test_summarize_ollama_success(self):
        self._http_patcher.stop()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "Ollama local model summary"}
        with patch("aura.llm.requests.post", return_value=mock_resp):
            with patch.dict(os.environ, {"OLLAMA_HOST": "http://127.0.0.1:11434"}):
                summary = llm._summarize_ollama("Title", "Abstract")
                self.assertEqual(summary, "Ollama local model summary")
        self._http_patcher.start()

    def test_generate_summary_guaranteed_extractive_fallback(self):
        # Even when all cloud API providers fail or are unconfigured, generate_summary must succeed via extractive
        with patch.dict(llm._PROVIDER_FUNCS, {"groq": lambda *_a, **_k: None, "google": lambda *_a, **_k: None}, clear=False):
            with patch("aura.llm._load_providers_order", return_value=["groq", "google"]):
                summary = llm.generate_summary("DESI Analysis", "We analyse baryon acoustic oscillations and measure Hubble parameter constraints.")
                self.assertIsNotNone(summary)
                self.assertTrue(len(summary) > 10)


if __name__ == "__main__":
    unittest.main()
