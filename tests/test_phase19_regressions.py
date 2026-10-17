"""Regression tests for the Phase 19 audit fixes."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from aura.model import PreferenceModel
from aura.web.app import create_app


class TestPreferenceModelScoring(unittest.TestCase):
    def test_predict_is_a_probability_and_model_not_callable(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = PreferenceModel(Path(tmp) / "m.pt", embedding_dim=8)
            score, unc = model.predict(np.random.rand(8).astype(np.float32), num_samples=1)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)
            self.assertEqual(unc, 0.0)
            # The wrapper is deliberately not callable: callers must use predict(),
            # because the net already ends in a sigmoid.
            with self.assertRaises(TypeError):
                model(np.zeros(8))  # type: ignore[operator]

    def test_notifications_score_with_real_model(self):
        from aura.notifications import notify_high_scoring_papers

        with tempfile.TemporaryDirectory() as tmp:
            model = PreferenceModel(Path(tmp) / "m.pt", embedding_dim=8)
            engine = Mock()
            engine.db.get_all_users.return_value = [{"id": 1}]
            engine.db.get_papers_with_embeddings.return_value = [("x", np.random.rand(8))]
            engine.get_user_preference_model.return_value = model
            config = {"integrations": {"slack": {
                "enabled": True, "webhook_url": "http://h", "score_threshold": 0.0}}}
            with patch("aura.notifications.send_slack_notification") as slack:
                notify_high_scoring_papers(engine, [{"arxiv_id": "x", "title": "t"}], config)
            # threshold 0.0 means any valid score must trigger the alert
            slack.assert_called_once()


class TestTokenLimits(unittest.TestCase):
    def test_brief_and_latex_request_long_output(self):
        with patch("aura.briefs._generate_generic_text", return_value="<div>ok</div>") as gen:
            from aura.briefs import generate_weekly_brief_content  # noqa: F401
        # Signature must accept max_tokens, defaulting to the old short limit.
        import inspect
        from aura.trends import _generate_generic_text
        sig = inspect.signature(_generate_generic_text)
        self.assertEqual(sig.parameters["max_tokens"].default, 300)
        self.assertIsNotNone(gen)

    def test_latex_synthesis_passes_max_tokens(self):
        from aura.latex_export import synthesize_related_work

        papers = [{"cite_key": "A2026", "title": "T", "abstract": "x" * 50, "arxiv_id": "1"}]
        with patch("aura.trends._generate_generic_text", return_value="y" * 200) as gen:
            synthesize_related_work(papers, {})
        self.assertEqual(gen.call_args.kwargs.get("max_tokens"), 2500)


class _WebBase(unittest.TestCase):
    is_admin = 1

    def setUp(self):
        self.engine = Mock()
        self.engine.db = Mock()
        self.engine.get_stats.return_value = {
            "database": {"total_papers": 10, "with_embeddings": 8, "total_rated": 10,
                         "thumbs_up": 5, "thumbs_down": 5, "with_summaries": 4},
            "model": {"parameters": 1, "embedding_dim": 8, "learning_rate": 0.001,
                      "total_trained": 1, "replay_buffer_size": 1},
            "categories": [], "data_dir": "data"}
        user = {"id": 1, "email": "u@example.com", "password_hash": "h",
                "is_admin": self.is_admin, "is_active": 1, "created_at": "2024-01-01"}
        self.engine.db.count_users.return_value = 0
        self.engine.db.create_user.return_value = user
        self.engine.db.get_user_by_email.return_value = user
        self.engine.db.get_user_by_id.return_value = user
        self.engine.db.get_user_tokens.return_value = []
        self.engine.db.is_email_locked_out.return_value = False
        with patch("aura.web.app.RecommendationEngine", return_value=self.engine):
            app = create_app()
        app.testing = True
        self.app = app
        self.client = app.test_client()
        with patch("aura.web.app.generate_password_hash", return_value="h"), \
             patch("aura.web.app.check_password_hash", return_value=True):
            self.client.post("/login", data={"email": "u@example.com", "password": "pw"})


class TestTemplateInjection(_WebBase):
    def test_unsubscribe_does_not_evaluate_jinja_in_email(self):
        self.engine.db.get_user_by_unsubscribe_token.return_value = {
            "id": 1, "email": "{{ 7*7 }}@example.com"}
        resp = self.client.get("/unsubscribe/tok")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"{{ 7*7 }}@example.com", resp.data)
        self.assertNotIn(b"49@example.com", resp.data)

    def test_rate_direct_escapes_title(self):
        from itsdangerous import URLSafeTimedSerializer

        token = URLSafeTimedSerializer(self.app.secret_key).dumps(
            {"user_id": 1, "arxiv_id": "2401.00001", "rating": 1})
        self.engine.db.get_paper.return_value = {
            "title": "{{ config }}<script>alert(1)</script>"}
        resp = self.client.get(f"/rate-direct?token={token}")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"<script>alert(1)</script>", resp.data)
        self.assertIn(b"&lt;script&gt;", resp.data)
        self.assertNotIn(b"SECRET_KEY", resp.data)


class TestAskPaperFormats(_WebBase):
    def test_json_response_for_non_streaming_clients(self):
        self.engine.ask_paper_question.return_value = iter(["Hello ", "world"])
        resp = self.client.post("/api/papers/2401.00001/ask", json={"question": "q?"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["answer"], "Hello world")

    def test_sse_when_requested(self):
        self.engine.ask_paper_question.return_value = iter(["a"])
        resp = self.client.post(
            "/api/papers/2401.00001/ask", json={"question": "q?"},
            headers={"Accept": "text/event-stream"})
        self.assertEqual(resp.mimetype, "text/event-stream")
        self.assertIn(b'"chunk": "a"', resp.data)


class TestAuthBoundaries(_WebBase):
    def test_extension_endpoints_require_login(self):
        anon = self.app.test_client()
        self.assertIn(anon.get("/api/extension/check?arxiv_id=1").status_code, (401, 302))
        self.assertIn(anon.post("/api/extension/add", json={"arxiv_id": "1"}).status_code, (401, 302))


class TestNonAdminRestrictions(_WebBase):
    is_admin = 0

    def test_server_wide_jobs_forbidden(self):
        self.assertEqual(self.client.post("/api/fetch", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/summarize", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/daily-job/run").status_code, 403)

    def test_settings_post_cannot_change_global_config(self):
        with patch("aura.config.save_config_file") as save:
            resp = self.client.post("/settings", data={
                "digest_frequency": "weekly",
                "email_submitted": "1", "smtp_host": "evil.example.com"})
        self.assertEqual(resp.status_code, 302)
        save.assert_not_called()
        self.engine.db.update_user.assert_called_with(1, digest_frequency="weekly")


if __name__ == "__main__":
    unittest.main()
