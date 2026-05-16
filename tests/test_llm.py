import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_papers import llm


class TestLLM(unittest.TestCase):
    def setUp(self):
        llm._provider_config_cache.clear()
        llm._providers_order_cache = None
        llm._warned_messages.clear()

        # Safety rail: fail tests immediately if any code path tries real HTTP LLM calls.
        self._http_patcher = patch(
            "ai_papers.llm.requests.post",
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

    @patch("ai_papers.llm._load_provider_config", return_value={"api_key": "cfg-key"})
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
            with patch("ai_papers.llm._credentials_dir", return_value=cred):
                llm._providers_order_cache = None
                self.assertEqual(llm._load_providers_order(), ["groq"])

                (cred / "llm_providers.json").write_text(
                    json.dumps({"order": ["openai", "groq"]})
                )
                llm._providers_order_cache = None
                self.assertEqual(llm._load_providers_order(), ["openai", "groq"])

    @patch("ai_papers.llm._load_providers_order", return_value=["groq", "openai"])
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

    @patch("ai_papers.llm._load_providers_order", return_value=["groq"])
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


if __name__ == "__main__":
    unittest.main()
