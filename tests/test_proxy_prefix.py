import os
import unittest
from unittest.mock import Mock, patch

from werkzeug.security import generate_password_hash

from aura.web.app import create_app, limiter

PREFIX_HEADERS = {"X-Forwarded-Prefix": "/aura", "X-Forwarded-For": "203.0.113.7"}


class TestProxyPrefix(unittest.TestCase):
    """AURA served behind Caddy at /aura/ with AURA_TRUSTED_PROXY_HOPS=1."""

    def setUp(self):
        self.engine = Mock()
        self.engine.db.get_user_by_token.return_value = None
        self.engine.get_stats.return_value = {"database": {"total_rated": 10}, "model": {}}
        user_row = {
            "id": 1,
            "email": "researcher@example.com",
            "password_hash": generate_password_hash("secretpassword"),
            "is_active": 1,
            "is_admin": 0,
        }
        self.engine.db.get_user_by_email.return_value = user_row
        self.engine.db.get_user_by_id.return_value = user_row
        with patch("aura.web.app.RecommendationEngine", return_value=self.engine), \
                patch.dict(os.environ, {"AURA_TRUSTED_PROXY_HOPS": "1"}):
            self.app = create_app()
        limiter.reset()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def _login(self, next_page: str):
        return self.client.post(
            f"/login?next={next_page}",
            data={"email": "researcher@example.com", "password": "secretpassword"},
            headers=PREFIX_HEADERS,
        )

    def test_login_redirect_includes_prefix(self):
        resp = self.client.get("/", headers=PREFIX_HEADERS)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.headers["Location"].startswith("/aura/login"))

    def test_rendered_links_include_prefix(self):
        html = self.client.get("/login", headers=PREFIX_HEADERS).get_data(as_text=True)
        self.assertIn('href="/aura/static/style.css', html)
        self.assertIn('window.APP_ROOT = "/aura"', html)
        self.assertNotIn('href="/register"', html)

    def test_links_unprefixed_without_proxy_header(self):
        html = self.client.get("/login").get_data(as_text=True)
        self.assertIn('window.APP_ROOT = ""', html)
        self.assertIn('href="/register"', html)

    def test_post_login_next_keeps_prefix(self):
        resp = self._login("/papers")
        self.assertEqual(resp.headers["Location"], "/aura/papers")

    def test_post_login_rejects_external_next(self):
        for evil in ("https://evil.example/", "//evil.example/"):
            resp = self._login(evil)
            self.assertEqual(resp.headers["Location"], "/aura/", evil)

    def test_privacy_policy_is_public(self):
        resp = self.client.get("/privacy", headers=PREFIX_HEADERS)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Privacy Policy", resp.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
