import unittest
from unittest.mock import Mock, patch
from aura.notifications import (
    send_slack_notification,
    send_discord_notification,
    send_slack_digest,
    notify_high_scoring_papers,
)

class TestNotifications(unittest.TestCase):
    @patch("aura.notifications.requests.post")
    def test_send_slack_notification(self, mock_post):
        mock_post.return_value.status_code = 200
        paper = {"title": "Test Title", "url": "http://example.com", "authors": ["Ada"], "summary": "A test paper summary."}
        
        result = send_slack_notification("http://webhook.url", paper, 0.85)
        self.assertTrue(result)
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        self.assertIn("Test Title", payload["blocks"][0]["text"]["text"])
        self.assertIn("85%", payload["blocks"][0]["text"]["text"])

    @patch("aura.notifications.requests.post")
    def test_send_discord_notification(self, mock_post):
        mock_post.return_value.status_code = 200
        paper = {"title": "Test Title", "url": "http://example.com", "authors": ["Ada"], "summary": "A test paper summary."}
        
        result = send_discord_notification("http://webhook.url", paper, 0.85)
        self.assertTrue(result)
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        self.assertIn("Test Title", payload["content"])
        self.assertIn("85%", payload["content"])

    @patch("aura.notifications.requests.post")
    def test_send_slack_digest(self, mock_post):
        mock_post.return_value.status_code = 200
        papers = [
            {"title": "Paper 1", "url": "http://example.com/1", "authors": ["Ada"], "summary": "Summary 1", "score": 0.9},
            {"title": "Paper 2", "url": "http://example.com/2", "authors": ["Bob"], "summary": "Summary 2", "score": 0.8},
        ]
        
        result = send_slack_digest("http://webhook.url", papers)
        self.assertTrue(result)
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]["json"]
        self.assertIn("Daily Digest", payload["blocks"][0]["text"]["text"])
        self.assertIn("Paper 1", payload["blocks"][2]["text"]["text"])
        self.assertIn("90%", payload["blocks"][2]["text"]["text"])
        self.assertIn("Paper 2", payload["blocks"][3]["text"]["text"])
        self.assertIn("80%", payload["blocks"][3]["text"]["text"])

    @patch("aura.notifications.send_slack_notification")
    @patch("aura.notifications.send_discord_notification")
    @patch("torch.sigmoid")
    @patch("torch.tensor")
    def test_notify_high_scoring_papers(self, mock_tensor, mock_sigmoid, mock_discord, mock_slack):
        engine = Mock()
        engine.db.get_all_users.return_value = [{"id": 1, "email": "test@example.com"}]
        engine.db.get_papers_with_embeddings.return_value = [("2401.00001", [0.1, 0.2, 0.3])]
        
        pref_model = Mock()
        engine.get_user_preference_model.return_value = pref_model
        
        mock_sigmoid.return_value.item.return_value = 0.95
        
        new_papers = [{"arxiv_id": "2401.00001", "title": "A Great Astro Paper"}]
        config = {
            "integrations": {
                "slack": {"enabled": True, "webhook_url": "http://slack.webhook", "score_threshold": 0.8},
                "discord": {"enabled": True, "webhook_url": "http://discord.webhook", "score_threshold": 0.8},
            }
        }
        
        notify_high_scoring_papers(engine, new_papers, config)
        
        mock_slack.assert_called_once_with("http://slack.webhook", new_papers[0], 0.95)
        mock_discord.assert_called_once_with("http://discord.webhook", new_papers[0], 0.95)

if __name__ == "__main__":
    unittest.main()
