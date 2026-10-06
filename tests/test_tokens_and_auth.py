import os
import tempfile
import unittest
from datetime import timedelta

from aura.database import PaperDatabase
from aura.timeutil import utcnow


class TestTokensAndAuth(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.db = PaperDatabase(self.db_path)
        # Create a test user
        self.user_id = self.db.create_user("researcher@example.com", "dummy_hash", is_admin=False)

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_token_creation_and_expiry(self):
        # 1. Unexpiring token
        t_unexpired = self.db.create_api_token(self.user_id, "Permanent Token")
        self.assertIsNotNone(t_unexpired)
        user = self.db.get_user_by_token(t_unexpired)
        self.assertIsNotNone(user)
        self.assertEqual(user["id"], self.user_id)

        # 2. Token expired in the past
        past_date = (utcnow() - timedelta(days=1)).isoformat()
        t_past = self.db.create_api_token(self.user_id, "Old Token", expires_at=past_date)
        self.assertIsNotNone(t_past)
        user_expired = self.db.get_user_by_token(t_past)
        self.assertIsNone(user_expired)

        # 3. Token expiring in future
        t_future = self.db.create_api_token(self.user_id, "Future Token", expires_in_days=30)
        self.assertIsNotNone(t_future)
        user_future = self.db.get_user_by_token(t_future)
        self.assertIsNotNone(user_future)

    def test_device_token_rotation(self):
        # Initial login on device
        t1 = self.db.rotate_or_create_device_token(self.user_id, "AURA Android App", expires_in_days=60)
        self.assertIsNotNone(t1)
        tokens_1 = self.db.get_user_tokens(self.user_id)
        self.assertEqual(len(tokens_1), 1)
        self.assertEqual(tokens_1[0]["name"], "AURA Android App")

        # Second login on same device rotates the token
        t2 = self.db.rotate_or_create_device_token(self.user_id, "AURA Android App", expires_in_days=60)
        self.assertIsNotNone(t2)
        self.assertNotEqual(t1, t2)

        # Old token is no longer valid; new token is valid
        self.assertIsNone(self.db.get_user_by_token(t1))
        self.assertIsNotNone(self.db.get_user_by_token(t2))

        # Total active tokens for user remains 1
        tokens_2 = self.db.get_user_tokens(self.user_id)
        self.assertEqual(len(tokens_2), 1)

    def test_get_user_tokens_metadata(self):
        past_date = (utcnow() - timedelta(days=1)).isoformat()
        self.db.create_api_token(self.user_id, "Expired Script", expires_at=past_date)
        self.db.create_api_token(self.user_id, "Active Device", expires_in_days=30)

        tokens = self.db.get_user_tokens(self.user_id)
        self.assertEqual(len(tokens), 2)

        # Confirm masked_token and is_expired flags
        expired_token = next(t for t in tokens if t["name"] == "Expired Script")
        active_token = next(t for t in tokens if t["name"] == "Active Device")

        self.assertTrue(expired_token["is_expired"])
        self.assertFalse(active_token["is_expired"])
        self.assertTrue(expired_token["masked_token"].endswith("…"))

    def test_login_attempts_and_lockout(self):
        email = "testlock@example.com"
        self.assertFalse(self.db.is_email_locked_out(email))

        # 4 failures -> still not locked out
        for _ in range(4):
            self.db.record_login_attempt(email, ip_address="127.0.0.1", success=False)
        self.assertFalse(self.db.is_email_locked_out(email))

        # 5th failure -> locked out
        self.db.record_login_attempt(email, ip_address="127.0.0.1", success=False)
        self.assertTrue(self.db.is_email_locked_out(email))

        # Successful login -> clears consecutive failure chain
        self.db.record_login_attempt(email, ip_address="127.0.0.1", success=True)
        self.assertFalse(self.db.is_email_locked_out(email))


if __name__ == "__main__":
    unittest.main()
