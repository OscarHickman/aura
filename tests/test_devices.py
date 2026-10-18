"""Tests for mobile device token management and Expo push notifications."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aura.database import PaperDatabase
from aura.notifications import (
    is_valid_expo_push_token,
    send_expo_push_notifications,
    send_push_notification_to_user,
    notify_push_digest_ready,
    notify_velocity_spike,
    notify_citation_events,
)
from aura.web.app import create_app


class TestDevicePushNotifications(unittest.TestCase):
    """Test suite for device tokens, push notifications, and API endpoints."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_papers.db"
        self.db = PaperDatabase(self.db_path)
        self.user_id = self.db.create_user("researcher@aura.test", "hashed_password")

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_expo_token_validation(self):
        """Verify validation of Expo push token string format."""
        self.assertTrue(is_valid_expo_push_token("ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"))
        self.assertTrue(is_valid_expo_push_token("ExpoPushToken[xxxxxxxxxxxxxxxxxxxxxx]"))
        self.assertTrue(is_valid_expo_push_token("  ExponentPushToken[abc-123]  "))
        self.assertFalse(is_valid_expo_push_token(""))
        self.assertFalse(is_valid_expo_push_token("invalid_token_123"))
        self.assertFalse(is_valid_expo_push_token(None))  # type: ignore
        self.assertFalse(is_valid_expo_push_token(12345))  # type: ignore

    def test_database_device_token_lifecycle(self):
        """Verify device registration, updating, listing, and unregistering in database."""
        token_1 = "ExponentPushToken[device-test-1]"
        token_2 = "ExponentPushToken[device-test-2]"

        # Register token 1
        dev1 = self.db.register_device_token(
            user_id=self.user_id,
            device_token=token_1,
            platform="android",
            device_name="Pixel 8",
        )
        self.assertIsNotNone(dev1)
        self.assertEqual(dev1["device_token"], token_1)
        self.assertEqual(dev1["platform"], "android")
        self.assertEqual(dev1["device_name"], "Pixel 8")

        # Register token 2
        dev2 = self.db.register_device_token(
            user_id=self.user_id,
            device_token=token_2,
            platform="android",
            device_name="Tablet",
        )
        self.assertIsNotNone(dev2)

        # Re-registering token 1 updates last_used_at without duplicate row
        dev1_updated = self.db.register_device_token(
            user_id=self.user_id,
            device_token=token_1,
            platform="android",
            device_name="Pixel 8 Pro",
        )
        self.assertEqual(dev1_updated["id"], dev1["id"])
        self.assertEqual(dev1_updated["device_name"], "Pixel 8 Pro")

        # Get user tokens
        user_tokens = self.db.get_user_device_tokens(self.user_id)
        self.assertEqual(len(user_tokens), 2)
        tokens_set = {t["device_token"] for t in user_tokens}
        self.assertEqual(tokens_set, {token_1, token_2})

        # Get all tokens
        all_tokens = self.db.get_all_device_tokens()
        self.assertEqual(len(all_tokens), 2)

        # Unregister token 2
        unregistered = self.db.unregister_device_token(self.user_id, token_2)
        self.assertTrue(unregistered)
        user_tokens_after = self.db.get_user_device_tokens(self.user_id)
        self.assertEqual(len(user_tokens_after), 1)
        self.assertEqual(user_tokens_after[0]["device_token"], token_1)

        # Delete stale tokens
        deleted_count = self.db.delete_stale_device_tokens([token_1, "non_existent_token"])
        self.assertEqual(deleted_count, 1)
        self.assertEqual(len(self.db.get_user_device_tokens(self.user_id)), 0)

    @patch("aura.notifications.requests.post")
    def test_send_expo_push_notifications_success_and_stale_handling(self, mock_post):
        """Verify sending Expo notifications and handling DeviceNotRegistered responses."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {"status": "ok", "id": "ticket-1"},
                {
                    "status": "error",
                    "message": "Device not registered",
                    "details": {"error": "DeviceNotRegistered"},
                },
            ]
        }
        mock_post.return_value = mock_response

        messages = [
            {"to": "ExponentPushToken[valid-1]", "title": "Paper Alert", "body": "New paper matched"},
            {"to": "ExponentPushToken[stale-1]", "title": "Paper Alert", "body": "New paper matched"},
        ]

        result = send_expo_push_notifications(messages)
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["stale_tokens"], ["ExponentPushToken[stale-1]"])

    @patch("aura.notifications.send_expo_push_notifications")
    def test_send_push_notification_to_user_prunes_stale_tokens(self, mock_send):
        """Verify that stale tokens returned by Expo are pruned from the database."""
        token_active = "ExponentPushToken[active-1]"
        token_stale = "ExponentPushToken[stale-1]"

        self.db.register_device_token(self.user_id, token_active)
        self.db.register_device_token(self.user_id, token_stale)

        mock_send.return_value = {
            "success_count": 1,
            "failure_count": 1,
            "stale_tokens": [token_stale],
        }

        result = send_push_notification_to_user(
            self.db,
            user_id=self.user_id,
            title="Test Title",
            body="Test Body",
            data={"url": "aura://papers/2401.00001"},
        )

        self.assertEqual(result["success_count"], 1)
        tokens_left = self.db.get_user_device_tokens(self.user_id)
        self.assertEqual(len(tokens_left), 1)
        self.assertEqual(tokens_left[0]["device_token"], token_active)

    @patch("aura.notifications.send_push_notification_to_user")
    def test_notify_push_digest_ready(self, mock_send_user):
        """Verify digest ready push notification formatting."""
        mock_engine = Mock()
        mock_engine.db = self.db
        top_papers = [
            {"arxiv_id": "2401.00001", "title": "Cosmology Mock Paper", "score": 0.95},
            {"arxiv_id": "2401.00002", "title": "Galaxy Clustering", "score": 0.88},
        ]

        notify_push_digest_ready(mock_engine, self.user_id, top_papers)
        mock_send_user.assert_called_once()
        args, kwargs = mock_send_user.call_args
        self.assertIn("Daily Research Digest Ready", kwargs["title"])
        self.assertIn("Cosmology Mock Paper", kwargs["body"])
        self.assertIn("95%", kwargs["body"])
        self.assertEqual(kwargs["data"]["url"], "aura://papers/2401.00001")

    @patch("aura.notifications.send_expo_push_notifications")
    def test_notify_velocity_spike(self, mock_send):
        """Verify publication velocity spike push broadcast."""
        token = "ExponentPushToken[spike-watcher]"
        self.db.register_device_token(self.user_id, token)

        notify_velocity_spike(
            self.db,
            keyword="GALFORM",
            paper_count=8,
            window_start="2026-10-10",
            window_end="2026-10-17",
        )

        mock_send.assert_called_once()
        messages = mock_send.call_args[0][0]
        self.assertEqual(len(messages), 1)
        self.assertIn("GALFORM", messages[0]["body"])
        self.assertEqual(messages[0]["data"]["url"], "aura://intel")

    @patch("aura.notifications.send_push_notification_to_user")
    def test_notify_citation_events_push(self, mock_send_user):
        """Verify citation events trigger push notifications for paper authors."""
        mock_engine = Mock()
        mock_engine.db = self.db
        events = [
            {
                "user_id": self.user_id,
                "my_paper_title": "SaUCE 2PCF Sparse Estimator",
                "citing_title": "Testing Small-Scale Galaxy Clustering",
                "citing_arxiv_id": "2610.99999",
            }
        ]
        config = {"integrations": {}}

        notify_citation_events(mock_engine, events, config)
        mock_send_user.assert_called_once()
        args, kwargs = mock_send_user.call_args
        self.assertEqual(kwargs["user_id"], self.user_id)
        self.assertIn("Citation", kwargs["title"])
        self.assertEqual(kwargs["data"]["url"], "aura://my-papers")

    def test_web_api_device_endpoints(self):
        """Verify Flask REST API endpoints for device token management."""
        config_path = Path(self.temp_dir.name) / "config.yaml"
        config_path.write_text(f"data_dir: {self.temp_dir.name}\nscheduler:\n  enabled: false\n")

        mock_engine = Mock()
        mock_engine.db = self.db

        with patch("aura.web.app.RecommendationEngine", return_value=mock_engine):
            app = create_app(str(config_path))

        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        client = app.test_client()

        # Login to obtain session
        with client.session_transaction() as sess:
            sess["_user_id"] = str(self.user_id)
            sess["_fresh"] = True

        # Test POST /api/devices with invalid token format
        res = client.post(
            "/api/devices",
            data=json.dumps({"device_token": "not-an-expo-token"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

        # Test POST /api/devices with valid token
        valid_token = "ExponentPushToken[test-api-token-12345]"
        res = client.post(
            "/api/devices",
            data=json.dumps({
                "device_token": valid_token,
                "platform": "android",
                "device_name": "Test Pixel",
            }),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["device"]["device_token"], valid_token)

        # Test GET /api/devices
        res = client.get("/api/devices")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(len(data["devices"]), 1)
        self.assertEqual(data["devices"][0]["device_token"], valid_token)

        # Test POST /api/devices/test
        with patch("aura.notifications.send_push_notification_to_user", return_value={"success_count": 1}):
            res = client.post("/api/devices/test")
            self.assertEqual(res.status_code, 200)

        # Test DELETE /api/devices
        res = client.delete(
            "/api/devices",
            data=json.dumps({"device_token": valid_token}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["unregistered"])

        # Check list is now empty
        res = client.get("/api/devices")
        self.assertEqual(len(res.get_json()["devices"]), 0)


if __name__ == "__main__":
    unittest.main()
