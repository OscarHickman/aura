import unittest
from unittest.mock import patch, Mock, PropertyMock
import numpy as np

from aura.tasks import (
    fetch_papers_task,
    fetch_papers_page_task,
    generate_missing_summaries_task,
    retrain_full_task,
)

class TestCeleryTasks(unittest.TestCase):

    @patch("aura.tasks.fetch_papers_page_task.delay")
    @patch("aura.tasks.RecommendationEngine")
    def test_fetch_papers_task(self, mock_engine_cls, mock_page_delay):
        mock_engine = Mock()
        mock_engine_cls.return_value = mock_engine
        
        # Patch the read-only request property using patch.object
        mock_request = Mock()
        mock_request.id = "task-123"
        with patch.object(fetch_papers_task.__class__, 'request', new_callable=PropertyMock) as mock_req_prop:
            mock_req_prop.return_value = mock_request
            
            fetch_papers_task.run(max_results=50, days_back=1, generate_summaries=False)
        
        # Assert database task history is updated
        mock_engine.db.create_task_entry.assert_called_with("task-123", "fetch_papers", status="RUNNING")
        mock_engine.db.update_task_progress.assert_called_with("task-123", progress=0, total=50, status="RUNNING")
        
        # Assert page fetch is queued
        mock_page_delay.assert_called_once()
        args, kwargs = mock_page_delay.call_args
        self.assertEqual(kwargs["task_id"], "task-123")
        self.assertEqual(kwargs["max_results"], 50)
        self.assertEqual(kwargs["start"], 0)

    @patch("aura.tasks.fetch_papers_page_task.apply_async")
    @patch("aura.tasks.requests.get")
    @patch("aura.tasks.embed_papers_batch")
    @patch("aura.tasks.RecommendationEngine")
    def test_fetch_papers_page_task_complete(self, mock_engine_cls, mock_embed, mock_get, mock_apply_async):
        mock_engine = Mock()
        mock_engine_cls.return_value = mock_engine
        mock_engine.embedding_model = "all-MiniLM-L6-v2"
        mock_engine.db.get_paper.return_value = None
        mock_engine.db.add_papers_batch.return_value = 2
        
        mock_embed.return_value = [np.array([1]), np.array([2])]
        
        # Mock XML response from arXiv containing 2 entries
        mock_resp = Mock()
        mock_resp.text = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
            <entry>
                <id>http://arxiv.org/abs/2401.00001v1</id>
                <title>Paper One</title>
                <summary>Abstract One</summary>
                <published>2026-01-01T00:00:00Z</published>
                <author><name>Author A</name></author>
                <category term="astro-ph.CO"/>
            </entry>
            <entry>
                <id>http://arxiv.org/abs/2401.00002v1</id>
                <title>Paper Two</title>
                <summary>Abstract Two</summary>
                <published>2026-01-01T00:00:00Z</published>
                <author><name>Author B</name></author>
                <category term="astro-ph.CO"/>
            </entry>
        </feed>
        """
        mock_get.return_value = mock_resp
        
        # Call page fetch via .run
        fetch_papers_page_task.run(
            task_id="task-123",
            categories=["astro-ph.CO"],
            max_results=2,
            days_back=1,
            generate_summaries=False,
            start=0,
            new_papers_count=0
        )
        
        # Verify db insert
        mock_engine.db.add_papers_batch.assert_called_once()
        mock_engine.db.complete_task.assert_called_with("task-123", status="SUCCESS", result={"new_papers": 2})
        mock_apply_async.assert_not_called()

    @patch("aura.tasks.RecommendationEngine")
    def test_generate_missing_summaries_task(self, mock_engine_cls):
        mock_engine = Mock()
        mock_engine_cls.return_value = mock_engine
        mock_engine.generate_missing_summaries.return_value = {"processed": 5, "updated": 4}
        
        mock_request = Mock()
        mock_request.id = "summarize-123"
        with patch.object(generate_missing_summaries_task.__class__, 'request', new_callable=PropertyMock) as mock_req_prop:
            mock_req_prop.return_value = mock_request
            
            res = generate_missing_summaries_task.run(limit=10, include_failed=True)
        
        mock_engine.db.create_task_entry.assert_called_with("summarize-123", "summarize", status="RUNNING")
        mock_engine.generate_missing_summaries.assert_called_once()
        mock_engine.db.complete_task.assert_called_with("summarize-123", status="SUCCESS", result={"processed": 5, "updated": 4})
        self.assertEqual(res["processed"], 5)

    @patch("aura.tasks.RecommendationEngine")
    def test_retrain_full_task(self, mock_engine_cls):
        mock_engine = Mock()
        mock_engine_cls.return_value = mock_engine
        mock_engine.retrain_full.return_value = {"status": "retrained"}
        
        mock_request = Mock()
        mock_request.id = "retrain-123"
        with patch.object(retrain_full_task.__class__, 'request', new_callable=PropertyMock) as mock_req_prop:
            mock_req_prop.return_value = mock_request
            
            res = retrain_full_task.run(epochs=10)
        
        mock_engine.db.create_task_entry.assert_called_with("retrain-123", "retrain", status="RUNNING")
        mock_engine.retrain_full.assert_called_once()
        mock_engine.db.complete_task.assert_called_with("retrain-123", status="SUCCESS", result={"status": "retrained"})
        self.assertEqual(res["status"], "retrained")

    @patch("aura.tasks.RecommendationEngine")
    def test_generate_missing_summaries_task_failure(self, mock_engine_cls):
        mock_engine = Mock()
        mock_engine_cls.return_value = mock_engine
        mock_engine.generate_missing_summaries.side_effect = Exception("error summarizing")
        
        mock_request = Mock()
        mock_request.id = "summarize-fail"
        with patch.object(generate_missing_summaries_task.__class__, 'request', new_callable=PropertyMock) as mock_req_prop:
            mock_req_prop.return_value = mock_request
            with self.assertRaises(Exception):
                generate_missing_summaries_task.run(limit=10, include_failed=True)
                
        mock_engine.db.complete_task.assert_called_with("summarize-fail", status="FAILURE", error="error summarizing")

    @patch("aura.tasks.RecommendationEngine")
    def test_retrain_full_task_failure(self, mock_engine_cls):
        mock_engine = Mock()
        mock_engine_cls.return_value = mock_engine
        mock_engine.retrain_full.side_effect = Exception("error retraining")
        
        mock_request = Mock()
        mock_request.id = "retrain-fail"
        with patch.object(retrain_full_task.__class__, 'request', new_callable=PropertyMock) as mock_req_prop:
            mock_req_prop.return_value = mock_request
            with self.assertRaises(Exception):
                retrain_full_task.run(epochs=10)
                
        mock_engine.db.complete_task.assert_called_with("retrain-fail", status="FAILURE", error="error retraining")


    @patch("aura.tasks.RecommendationEngine")
    def test_refresh_ads_metadata_task_success(self, mock_engine_cls):
        mock_engine = Mock()
        mock_engine_cls.return_value = mock_engine
        
        # Setup mock db queries and updates
        mock_engine.db.get_all_papers_for_metadata_refresh.return_value = [
            {"arxiv_id": "2401.12345", "bibcode": "2026Test...123P"}
        ]
        mock_engine.db.update_paper_ads_metadata.return_value = True
        
        # Mock ADSSource
        mock_ads_source = Mock()
        mock_ads_source.api_key = "mock_key"
        mock_ads_source.fetch_metadata_for_papers.return_value = [
            {
                "arxiv_id": "2401.12345",
                "bibcode": "2026Test...123P",
                "citation_count": 10,
                "read_count": 20,
                "refereed": 1
            }
        ]
        
        # Use patch to inject ADSSource and PropertyMock for request
        mock_request = Mock()
        mock_request.id = "ads-task-123"
        
        from aura.tasks import refresh_ads_metadata_task
        with patch("aura.tasks.ADSSource", return_value=mock_ads_source):
            with patch.object(refresh_ads_metadata_task.__class__, 'request', new_callable=PropertyMock) as mock_req_prop:
                mock_req_prop.return_value = mock_request
                
                res = refresh_ads_metadata_task.run()
                
        mock_engine.db.create_task_entry.assert_called_with("ads-task-123", "refresh_ads_metadata", status="RUNNING")
        mock_ads_source.fetch_metadata_for_papers.assert_called_once()
        mock_engine.db.update_paper_ads_metadata.assert_called_with(
            arxiv_id="2401.12345",
            bibcode="2026Test...123P",
            citation_count=10,
            read_count=20,
            refereed=1
        )
        mock_engine.db.complete_task.assert_called_with("ads-task-123", status="SUCCESS", result={"updated_papers": 1})
        self.assertEqual(res["updated_papers"], 1)


if __name__ == "__main__":
    unittest.main()
