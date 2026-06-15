import unittest
from unittest.mock import Mock, patch

from ai_papers.web.app import create_app


class TestWebApp(unittest.TestCase):
    def setUp(self):
        self.engine = Mock()
        self.engine.get_stats.return_value = {"database": {}, "model": {}}
        self.engine.get_recommendations.return_value = []
        self.engine.generate_missing_summaries.return_value = {
            "status": "ok",
            "processed": 0,
            "updated": 0,
        }
        self.engine.retrain_full.return_value = {"status": "retrained"}
        self.engine.fetch_new_papers.return_value = 3

        with patch("ai_papers.web.app.RecommendationEngine", return_value=self.engine):
            app = create_app()

        app.testing = True
        self.client = app.test_client()

    def test_api_rate_validation(self):
        resp = self.client.post("/api/rate", json={})
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post("/api/rate", json={"arxiv_id": "x", "rating": 3})
        self.assertEqual(resp.status_code, 400)

    def test_api_rate_success(self):
        self.engine.rate_paper.return_value = {"status": "rated"}
        resp = self.client.post("/api/rate", json={"arxiv_id": "x", "rating": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "rated")

    @patch("ai_papers.tasks.fetch_papers_task.delay")
    def test_api_fetch_and_stats(self, mock_delay):
        mock_task = Mock()
        mock_task.id = "mock-task-123"
        mock_delay.return_value = mock_task

        resp = self.client.post("/api/fetch", json={"max_results": 10, "days_back": 2})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["task_id"], "mock-task-123")

        # Mock the get_task_status database call
        self.engine.db.get_task_status.return_value = {
            "task_id": "mock-task-123",
            "task_type": "fetch_papers",
            "status": "RUNNING",
            "progress": 5,
            "total": 10
        }
        resp = self.client.get("/api/tasks/mock-task-123")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "RUNNING")

        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)

    def test_api_summarize_single_not_found(self):
        self.engine.generate_summary_for_paper.return_value = {"status": "not_found"}
        resp = self.client.post("/api/summarize-paper", json={"arxiv_id": "missing"})
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
