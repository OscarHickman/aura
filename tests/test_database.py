import tempfile
import unittest
from pathlib import Path

import numpy as np

from ai_papers.database import PaperDatabase


def make_paper(arxiv_id: str = "2401.00001"):
    return {
        "arxiv_id": arxiv_id,
        "title": "A Paper",
        "abstract": "An abstract.",
        "authors": ["Ada", "Linus"],
        "categories": ["astro-ph.CO"],
        "published": "2026-01-01T00:00:00Z",
        "url": f"http://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"http://arxiv.org/pdf/{arxiv_id}.pdf",
    }


class TestPaperDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = PaperDatabase(Path(self.tmp.name) / "papers.db")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_add_and_get_paper_roundtrip(self):
        emb = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        inserted = self.db.add_paper(make_paper(), embedding=emb, summary="good")
        self.assertTrue(inserted)

        stored = self.db.get_paper("2401.00001")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["title"], "A Paper")
        self.assertEqual(stored["authors"], ["Ada", "Linus"])
        self.assertEqual(stored["summary"], "good")

    def test_add_papers_batch_counts_only_new_rows(self):
        papers = [make_paper("2401.00001"), make_paper("2401.00002")]
        embs = [np.array([1, 2], dtype=np.float32), np.array([3, 4], dtype=np.float32)]
        count1 = self.db.add_papers_batch(papers, embs)
        count2 = self.db.add_papers_batch(papers, embs)
        self.assertEqual(count1, 2)
        self.assertEqual(count2, 0)

    def test_update_summary_does_not_override_real_summary_with_ai_fail(self):
        self.db.add_paper(make_paper(), summary="real summary")
        self.db.update_summary("2401.00001", "AI Fail")
        stored = self.db.get_paper("2401.00001")
        self.assertEqual(stored["summary"], "real summary")

    def test_rating_latest_and_training_data(self):
        emb = np.array([0.5, 0.6, 0.7], dtype=np.float32)
        paper = make_paper()
        self.db.add_paper(paper, embedding=emb)

        self.db.rate_paper(paper["arxiv_id"], 1)
        self.db.rate_paper(paper["arxiv_id"], 0)

        self.assertEqual(self.db.get_latest_rating(paper["arxiv_id"]), 0)

        xs, ys = self.db.get_training_data()
        self.assertEqual(len(xs), 1)
        self.assertEqual(len(ys), 1)
        self.assertEqual(ys[0], 0.0)

    def test_get_papers_filters(self):
        p1 = make_paper("2401.00001")
        p2 = make_paper("2401.00002")
        self.db.add_paper(p1)
        self.db.add_paper(p2)
        self.db.rate_paper("2401.00002", 1)

        unrated = self.db.get_papers(unrated_only=True)
        rated = self.db.get_papers(rated_only=True)

        self.assertEqual([p["arxiv_id"] for p in unrated], ["2401.00001"])
        self.assertEqual([p["arxiv_id"] for p in rated], ["2401.00002"])

    def test_stats_and_log_fetch(self):
        self.db.add_paper(make_paper("2401.00001"))
        self.db.add_paper(make_paper("2401.00002"))
        self.db.rate_paper("2401.00002", 1)
        self.db.log_fetch(2, ["astro-ph.CO"])

        stats = self.db.get_stats()
        self.assertEqual(stats["total_papers"], 2)
        self.assertEqual(stats["total_rated"], 1)

    def test_summary_failed_and_needing_summary(self):
        p1 = make_paper("2401.00001")
        p2 = make_paper("2401.00002")
        self.db.add_paper(p1)
        self.db.add_paper(p2)
        
        # Initially both need summaries
        needing = self.db.get_papers_needing_summary(include_failed=True)
        self.assertEqual(len(needing), 2)
        
        # Mark one failed
        self.db.update_summary("2401.00001", "AI Fail")
        
        # Check needing summary excluding failed (only p2 should be returned)
        needing_no_failed = self.db.get_papers_needing_summary(include_failed=False)
        self.assertEqual(len(needing_no_failed), 1)
        self.assertEqual(needing_no_failed[0]["arxiv_id"], "2401.00002")
        
        # Check needing summary including failed (both returned)
        needing_with_failed = self.db.get_papers_needing_summary(include_failed=True)
        self.assertEqual(len(needing_with_failed), 2)

    def test_task_tracking_lifecycle(self):
        task_id = "task-uuid-123"
        self.db.create_task_entry(task_id, "fetch_papers", "PENDING")
        
        status = self.db.get_task_status(task_id)
        self.assertEqual(status["status"], "PENDING")
        self.assertEqual(status["task_type"], "fetch_papers")
        
        self.db.update_task_progress(task_id, progress=5, total=10, status="RUNNING")
        status = self.db.get_task_status(task_id)
        self.assertEqual(status["status"], "RUNNING")
        self.assertEqual(status["progress"], 5)
        self.assertEqual(status["total"], 10)
        
        self.db.complete_task(task_id, "SUCCESS", result={"new": 3})
        status = self.db.get_task_status(task_id)
        self.assertEqual(status["status"], "SUCCESS")
        self.assertEqual(status["result"], {"new": 3})
        
        # Complete with error
        task_id_err = "task-uuid-err"
        self.db.create_task_entry(task_id_err, "retrain", "PENDING")
        self.db.complete_task(task_id_err, "FAILURE", error="Boom")
        status = self.db.get_task_status(task_id_err)
        self.assertEqual(status["status"], "FAILURE")
        self.assertEqual(status["error"], "Boom")


if __name__ == "__main__":
    unittest.main()
