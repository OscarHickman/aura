import os
import unittest
from unittest.mock import Mock, patch

from werkzeug.security import generate_password_hash

from aura.web.app import create_app, limiter

USER_ROW = {
    "id": 1,
    "email": "researcher@example.com",
    "is_active": 1,
    "is_admin": 1,
    "scope": "admin",
    "token_id": 10,
}
BEARER = {"Authorization": "Bearer token_xyz123"}


class TestMobileAPI(unittest.TestCase):
    def setUp(self):
        self.engine = Mock()
        self.engine.get_stats.return_value = {
            "database": {"total_rated": 10},
            "model": {},
        }
        self.engine.db = Mock()
        self.engine.get_recommendations.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "Cosmological Inference",
                "abstract": "We explore simulation-based inference.",
                "authors": ["Alice Smith"],
                "score": 0.92,
                "summary": "AI summary of paper",
                "published": "2026-01-01T00:00:00Z",
            }
        ]
        self.engine.db.get_tracked_authors.return_value = []
        self.engine.db.get_papers_citing_user_work.return_value = set()
        self.engine.db.get_paper_tags.return_value = ["cosmology"]
        self.engine.db.get_paper_collections.return_value = []
        self.engine.db.is_in_reading_list.return_value = False
        self.engine.db.get_latest_rating.return_value = None
        self.engine.db.get_paper_notes.return_value = []
        self.engine.db.check_if_paper_cites_user_work.return_value = False
        self.engine.db.get_user_by_token.return_value = None
        self.engine.db.is_email_locked_out.return_value = False
        self.engine.db.rotate_or_create_device_token.return_value = "token_xyz123"
        self.engine.get_similar_papers.return_value = []

        env = {"AURA_CORS_ORIGINS": "http://localhost:8081"}
        with patch("aura.web.app.RecommendationEngine", return_value=self.engine), \
                patch.dict(os.environ, env):
            self.app = create_app()
        limiter.reset()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def _csrf_client(self):
        """A client with CSRF enforced, as in production."""
        self.app.config["TESTING"] = False
        self.app.config["WTF_CSRF_ENABLED"] = True
        return self.app.test_client()

    def test_cors_preflight_allows_listed_origin(self):
        resp = self.client.open(
            "/api/papers", method="OPTIONS", headers={"Origin": "http://localhost:8081"}
        )
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "http://localhost:8081")
        self.assertIn("Authorization", resp.headers.get("Access-Control-Allow-Headers", ""))

    def test_cors_rejects_unlisted_origin(self):
        resp = self.client.open(
            "/api/papers", method="OPTIONS", headers={"Origin": "https://evil.example"}
        )
        self.assertIsNone(resp.headers.get("Access-Control-Allow-Origin"))

    def test_unauthenticated_api_returns_json_401(self):
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.get_json()["error"], "Authentication required")

    def test_unauthenticated_page_still_redirects_to_login(self):
        resp = self.client.get("/reading-list")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.headers["Location"])

    def test_login_is_rate_limited(self):
        self.engine.db.get_user_by_email.return_value = None
        codes = [
            self.client.post("/api/auth/login", json={"email": "a@b.c", "password": "x"}).status_code
            for _ in range(6)
        ]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)

    def test_login_works_with_csrf_enforced(self):
        self.engine.db.get_user_by_email.return_value = None
        resp = self._csrf_client().post("/api/auth/login", json={"email": "a@b.c", "password": "x"})
        self.assertEqual(resp.status_code, 401)

    def test_bearer_request_skips_csrf(self):
        self.engine.db.get_user_by_token.return_value = USER_ROW
        self.engine.db.get_user_by_id.return_value = USER_ROW
        self.engine.db.add_to_reading_list.return_value = True
        resp = self._csrf_client().post(
            "/api/reading-list", json={"arxiv_id": "2401.00001"}, headers=BEARER
        )
        self.assertEqual(resp.status_code, 200)

    def test_invalid_bearer_does_not_skip_csrf(self):
        resp = self._csrf_client().post(
            "/api/reading-list", json={"arxiv_id": "2401.00001"},
            headers={"Authorization": "Bearer forged"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_logout_revokes_calling_token(self):
        self.engine.db.get_user_by_token.return_value = USER_ROW
        self.engine.db.revoke_api_token.return_value = True
        resp = self.client.post("/api/auth/logout", headers=BEARER)
        self.assertEqual(resp.status_code, 200)
        self.engine.db.revoke_api_token.assert_called_once_with(10, 1)

    def test_logout_without_token_is_401(self):
        resp = self.client.post("/api/auth/logout")
        self.assertEqual(resp.status_code, 401)

    def test_liked_filter_paginates_after_filtering(self):
        self.engine.db.get_user_by_token.return_value = USER_ROW
        self.engine.db.get_user_by_id.return_value = USER_ROW
        self.engine.db.get_papers.return_value = [
            {"arxiv_id": f"2401.0000{i}", "authors": []} for i in range(4)
        ]
        self.engine.db.get_latest_rating.side_effect = lambda aid, user_id: int(aid[-1]) % 2
        resp = self.client.get("/api/papers?filter=liked&page=2&per_page=1", headers=BEARER)
        data = resp.get_json()
        self.assertEqual(data["total"], 2)
        self.assertEqual([p["arxiv_id"] for p in data["papers"]], ["2401.00003"])

    def test_bad_paging_params_are_clamped(self):
        self.engine.db.get_user_by_token.return_value = USER_ROW
        self.engine.db.get_user_by_id.return_value = USER_ROW
        resp = self.client.get("/api/papers?page=abc&per_page=5000", headers=BEARER)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["page"], 1)
        self.assertEqual(resp.get_json()["per_page"], 100)

    def test_api_login_success(self):
        pw_hash = generate_password_hash("secretpassword")
        self.engine.db.get_user_by_email.return_value = {
            "id": 1,
            "email": "researcher@example.com",
            "password_hash": pw_hash,
            "is_active": 1,
            "is_admin": 1,
        }
        self.engine.db.create_api_token.return_value = "token_xyz123"

        resp = self.client.post(
            "/api/auth/login",
            json={"email": "researcher@example.com", "password": "secretpassword"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["token"], "token_xyz123")
        self.assertEqual(data["user"]["email"], "researcher@example.com")

    def test_api_login_invalid_password(self):
        pw_hash = generate_password_hash("secretpassword")
        self.engine.db.get_user_by_email.return_value = {
            "id": 1,
            "email": "researcher@example.com",
            "password_hash": pw_hash,
            "is_active": 1,
            "is_admin": 1,
        }

        resp = self.client.post(
            "/api/auth/login",
            json={"email": "researcher@example.com", "password": "wrongpassword"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_endpoints_with_bearer_token(self):
        self.engine.db.get_user_by_token.return_value = USER_ROW
        self.engine.db.get_user_by_id.return_value = USER_ROW
        headers = BEARER

        # 1. /api/auth/me
        resp = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["email"], "researcher@example.com")

        # 2. /api/papers
        resp = self.client.get("/api/papers?filter=unrated", headers=headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("papers", data)
        self.assertEqual(len(data["papers"]), 1)
        self.assertEqual(data["papers"][0]["arxiv_id"], "2401.00001")
        self.assertEqual(data["papers"][0]["tags"], ["cosmology"])

        # 3. /api/papers/<arxiv_id>
        self.engine.db.get_paper.return_value = {
            "arxiv_id": "2401.00001",
            "title": "Cosmological Inference",
            "abstract": "Abstract",
            "authors": ["Alice Smith"],
        }
        resp = self.client.get("/api/papers/2401.00001", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["arxiv_id"], "2401.00001")

        # 4. /api/reading-list (GET)
        self.engine.db.get_reading_list.return_value = [
            {"arxiv_id": "2401.00001", "title": "Cosmological Inference"}
        ]
        resp = self.client.get("/api/reading-list", headers=headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()["papers"]), 1)

    def test_api_login_locked_out(self):
        self.engine.db.is_email_locked_out.return_value = True
        resp = self.client.post(
            "/api/auth/login",
            json={"email": "attacker@example.com", "password": "password"},
        )
        self.assertEqual(resp.status_code, 429)
        self.assertIn("temporarily locked", resp.get_json()["error"])

    def test_api_v1_compatibility_and_headers(self):
        self.engine.db.get_user_by_token.return_value = USER_ROW
        self.engine.db.get_user_by_id.return_value = USER_ROW
        resp = self.client.get("/api/v1/papers", headers=BEARER)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-API-Version"), "1.2.1")
        self.assertEqual(resp.headers.get("X-Min-App-Version"), "1.0.0")

    def test_api_me_returns_versions(self):
        self.engine.db.get_user_by_token.return_value = USER_ROW
        self.engine.db.get_user_by_id.return_value = USER_ROW
        resp = self.client.get("/api/auth/me", headers=BEARER)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["min_app_version"], "1.0.0")
        self.assertEqual(data["server_version"], "1.2.1")


if __name__ == "__main__":
    unittest.main()
