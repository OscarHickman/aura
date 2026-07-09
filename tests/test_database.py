import tempfile
import unittest
from pathlib import Path

import numpy as np

from aura.database import PaperDatabase


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

    def test_search_papers(self):
        p1 = make_paper("2401.00001")
        p1["title"] = "Attention is all you need for Transformers"
        p1["abstract"] = "This paper introduces the Transformer architecture based on attention."
        p1["categories"] = ["cs.LG", "cs.CL"]
        p1["published"] = "2026-01-01T10:00:00Z"

        p2 = make_paper("2401.00002")
        p2["title"] = "Deep Residual Learning for Image Recognition"
        p2["abstract"] = "We present a residual learning framework to ease the training of deep networks."
        p2["categories"] = ["cs.CV"]
        p2["published"] = "2026-02-01T10:00:00Z"

        self.db.add_paper(p1)
        self.db.add_paper(p2)

        # 1. Simple keyword search
        results = self.db.search_papers("Attention")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["arxiv_id"], "2401.00001")
        self.assertIn("<mark>Attention</mark>", results[0]["title"])

        # 2. Case insensitivity and abstract match
        results = self.db.search_papers("residual")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["arxiv_id"], "2401.00002")
        self.assertIn("<mark>residual</mark>", results[0]["abstract"])

        # 3. Category filtering
        results = self.db.search_papers("learning", category="cs.CV")
        self.assertEqual(len(results), 1)
        results = self.db.search_papers("learning", category="cs.LG")
        self.assertEqual(len(results), 0) # "learning" is in abstract of p2, which is cs.CV.

        # 4. Date filtering
        results = self.db.search_papers("learning", date_from="2026-01-15")
        self.assertEqual(len(results), 1) # only p2
        results = self.db.search_papers("learning", date_to="2026-01-15")
        self.assertEqual(len(results), 0)

        # 5. Empty/bad query robustness
        self.assertEqual(self.db.search_papers(""), [])
        self.assertEqual(self.db.search_papers("!!!"), [])

    def test_ratings_history_and_papers_by_authors(self):
        # Setup ratings history
        p1 = make_paper("2401.00001")
        p1["authors"] = ["Ada", "Linus"]
        p2 = make_paper("2401.00002")
        p2["authors"] = ["Linus", "Grace"]
        self.db.add_paper(p1)
        self.db.add_paper(p2)

        self.db.rate_paper("2401.00001", 1)
        self.db.rate_paper("2401.00001", 0)

        history = self.db.get_ratings_history("2401.00001")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["rating"], 0)
        self.assertEqual(history[1]["rating"], 1)

        # Same authors test
        by_authors = self.db.get_papers_by_authors(["Linus"], exclude_arxiv_id="2401.00001")
        self.assertEqual(len(by_authors), 1)
        self.assertEqual(by_authors[0]["arxiv_id"], "2401.00002")

    def test_tags_and_collections_database(self):
        p1 = make_paper("2401.00001")
        p2 = make_paper("2401.00002")
        self.db.add_paper(p1)
        self.db.add_paper(p2)

        # 1. Tags
        self.assertTrue(self.db.add_tag("2401.00001", "ML"))
        self.assertTrue(self.db.add_tag("2401.00001", "LLM"))
        self.assertTrue(self.db.add_tag("2401.00002", "ML"))

        self.assertEqual(self.db.get_paper_tags("2401.00001"), ["llm", "ml"])
        self.assertEqual(self.db.get_all_tags(), ["llm", "ml"])

        tagged_papers = self.db.get_papers_by_tag("ML")
        self.assertEqual(len(tagged_papers), 2)

        self.db.remove_tag("2401.00001", "ML")
        self.assertEqual(self.db.get_paper_tags("2401.00001"), ["llm"])

        # 2. Collections
        coll_id = self.db.create_collection("My Thesis", "Papers for my thesis")
        self.assertIsNotNone(coll_id)

        self.assertTrue(self.db.add_paper_to_collection(coll_id, "2401.00001"))
        self.assertTrue(self.db.add_paper_to_collection(coll_id, "2401.00002"))

        colls = self.db.get_collections()
        self.assertEqual(len(colls), 1)
        self.assertEqual(colls[0]["name"], "My Thesis")
        self.assertEqual(colls[0]["paper_count"], 2)

        coll_papers = self.db.get_collection_papers(coll_id)
        self.assertEqual(len(coll_papers), 2)

        paper_colls = self.db.get_paper_collections("2401.00001")
        self.assertEqual(len(paper_colls), 1)
        self.assertEqual(paper_colls[0]["name"], "My Thesis")

        self.assertTrue(self.db.remove_paper_from_collection(coll_id, "2401.00001"))
        colls = self.db.get_collections()
        self.assertEqual(colls[0]["paper_count"], 1)

        self.assertTrue(self.db.delete_collection(coll_id))
        self.assertEqual(len(self.db.get_collections()), 0)

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

    def test_notes_database(self):
        arxiv_id = "2401.00001"
        self.db.add_paper(make_paper(arxiv_id))

        # 1. Add note
        note_id = self.db.add_note(arxiv_id, "This is a test note")
        self.assertIsNotNone(note_id)

        # 2. Get notes
        notes = self.db.get_paper_notes(arxiv_id)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["content"], "This is a test note")
        self.assertEqual(notes[0]["arxiv_id"], arxiv_id)

        # 3. Update note
        success = self.db.update_note(note_id, "Updated content")
        self.assertTrue(success)
        notes = self.db.get_paper_notes(arxiv_id)
        self.assertEqual(notes[0]["content"], "Updated content")

        # 4. Delete note
        success = self.db.delete_note(note_id)
        self.assertTrue(success)
        self.assertEqual(len(self.db.get_paper_notes(arxiv_id)), 0)


    def test_reading_list_database(self):
        arxiv_id = "2401.00001"
        self.db.add_paper(make_paper(arxiv_id))

        # 1. Add to reading list
        self.assertTrue(self.db.add_to_reading_list(arxiv_id))
        self.assertTrue(self.db.is_in_reading_list(arxiv_id))

        # 2. Get unread reading list
        unread = self.db.get_reading_list(only_unread=True)
        self.assertEqual(len(unread), 1)
        self.assertIsNone(unread[0]["read_at"])

        # 3. Mark as read
        self.assertTrue(self.db.mark_as_read(arxiv_id))
        read = self.db.get_reading_list(only_read=True)
        self.assertEqual(len(read), 1)
        self.assertIsNotNone(read[0]["read_at"])

        # Unread should be empty now
        self.assertEqual(len(self.db.get_reading_list(only_unread=True)), 0)

        # 4. Remove from reading list
        self.assertTrue(self.db.remove_from_reading_list(arxiv_id))
        self.assertFalse(self.db.is_in_reading_list(arxiv_id))
        self.assertEqual(len(self.db.get_reading_list()), 0)

    def test_ads_metadata_operations(self):
        arxiv_id = "2401.99999"
        self.db.add_paper(make_paper(arxiv_id))

        # Check paper in refresh list
        papers = self.db.get_all_papers_for_metadata_refresh()
        self.assertTrue(any(p["arxiv_id"] == arxiv_id for p in papers))

        # Update metadata
        success = self.db.update_paper_ads_metadata(
            arxiv_id=arxiv_id,
            bibcode="2026Test...999X",
            citation_count=42,
            read_count=137,
            refereed=1
        )
        self.assertTrue(success)

        # Retrieve paper to verify fields are set
        updated_paper = self.db.get_paper(arxiv_id)
        self.assertEqual(updated_paper["bibcode"], "2026Test...999X")
        self.assertEqual(updated_paper["citation_count"], 42)
        self.assertEqual(updated_paper["read_count"], 137)
        self.assertEqual(updated_paper["refereed"], 1)

    def test_surveys_operations_and_autotag(self):
        # 1. Verification of default seeded surveys on initialization
        surveys = self.db.get_surveys()
        self.assertGreater(len(surveys), 0)
        self.assertTrue(any(s["name"] == "DESI" for s in surveys))

        # 2. Add paper that triggers auto-tagging
        p_desi = make_paper("2401.desi1")
        p_desi["title"] = "First results from the DESI survey"
        p_desi["abstract"] = "This paper presents measurements from the Dark Energy Spectroscopic Instrument."
        
        self.db.add_paper(p_desi)
        tags = self.db.get_paper_tags("2401.desi1")
        self.assertIn("desi", tags)

        # 3. Add a custom survey and check backfill
        p_jwst = make_paper("2401.jwst1")
        p_jwst["title"] = "Discoveries from the James Webb Space Telescope"
        p_jwst["abstract"] = "We discuss JWST observations of galaxies."
        self.db.add_paper(p_jwst)
        
        self.assertNotIn("jwst", self.db.get_paper_tags("2401.jwst1"))
        
        self.assertTrue(self.db.add_survey("JWST", ["JWST", "James Webb"]))
        
        # After adding the survey, the existing paper should be backfilled and tagged
        self.assertIn("jwst", self.db.get_paper_tags("2401.jwst1"))

        # 4. Delete survey removes tags
        self.assertTrue(self.db.delete_survey("JWST"))
        self.assertNotIn("jwst", self.db.get_paper_tags("2401.jwst1"))

    def test_cross_listing_deduplication(self):
        # Test add_paper category merging
        p1 = make_paper("2401.cross1")
        p1["categories"] = ["astro-ph.CO"]
        self.assertTrue(self.db.add_paper(p1))
        
        stored = self.db.get_paper("2401.cross1")
        self.assertEqual(stored["categories"], ["astro-ph.CO"])

        p2 = make_paper("2401.cross1")
        p2["categories"] = ["cs.LG"]
        # Should return False as it is not newly inserted
        self.assertFalse(self.db.add_paper(p2))

        stored = self.db.get_paper("2401.cross1")
        self.assertEqual(sorted(stored["categories"]), sorted(["astro-ph.CO", "cs.LG"]))

        # Test add_papers_batch category merging
        p3 = make_paper("2401.cross2")
        p3["categories"] = ["astro-ph.CO"]
        
        p4 = make_paper("2401.cross2")
        p4["categories"] = ["stat.ML"]
        
        self.assertEqual(self.db.add_papers_batch([p3]), 1)
        self.assertEqual(self.db.add_papers_batch([p4]), 0)
        
        stored2 = self.db.get_paper("2401.cross2")
        self.assertEqual(sorted(stored2["categories"]), sorted(["astro-ph.CO", "stat.ML"]))

    def test_simulation_code_auto_tagging(self):
        # 1. Custom simulation_codes list in constructor
        custom_db = PaperDatabase(
            Path(self.tmp.name) / "papers_sim.db",
            simulation_codes=["Gadget", "CAMB", "JAX"]
        )
        
        # 2. Paper mentioning Gadget in abstract and CAMB in title
        p = make_paper("2401.sim1")
        p["title"] = "Fast CAMB calculations of power spectra"
        p["abstract"] = "We run a cosmological simulation with GADGET."
        custom_db.add_paper(p)
        
        # 3. Retrieve tags for user 1 (should automatically include gadget and camb)
        tags_user1 = custom_db.get_paper_tags("2401.sim1", user_id=1)
        self.assertIn("gadget", tags_user1)
        self.assertIn("camb", tags_user1)
        self.assertNotIn("jax", tags_user1)
        
        # 4. Retrieve tags for user 2 (should also see simulation tags because they are auto-tags)
        tags_user2 = custom_db.get_paper_tags("2401.sim1", user_id=2)
        self.assertIn("gadget", tags_user2)
        self.assertIn("camb", tags_user2)
        
        # 5. Check all tags
        all_tags = custom_db.get_all_tags(user_id=2)
        self.assertIn("gadget", all_tags)
        self.assertIn("camb", all_tags)
        
        # 6. Retrieve papers by tag for user 2
        papers = custom_db.get_papers_by_tag("gadget", user_id=2)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["arxiv_id"], "2401.sim1")

    def test_velocity_alerts_and_weekly_history(self):
        from datetime import datetime
        # 1. Custom simulation_codes and db setup
        custom_db = PaperDatabase(
            Path(self.tmp.name) / "papers_vel.db",
            simulation_codes=["IllustrisTNG", "CAMELS", "sbi"]
        )
        
        # 2. Add 6 papers mentioning "sbi" published in the last 2 days
        now = datetime.utcnow()
        for i in range(6):
            p = make_paper(f"2401.sbi{i}")
            p["title"] = f"Cosmological SBI analysis part {i}"
            p["abstract"] = "Using simulation-based inference methods for cosmology."
            p["published"] = now.isoformat()
            custom_db.add_paper(p)
            
        # 3. Weekly velocity history should have YYYY-MM-DD week_start
        rows = custom_db.conn.execute("SELECT tag, week_start, paper_count FROM weekly_velocity").fetchall()
        self.assertTrue(len(rows) > 0)
        sbi_rows = [r for r in rows if r["tag"] == "sbi"]
        self.assertTrue(len(sbi_rows) > 0)
        self.assertEqual(sbi_rows[0]["paper_count"], 6)
        
        # 4. Check for velocity alerts: we set threshold to 5, sbi has 6 papers so it should trigger
        alerts = custom_db.check_velocity_alerts(threshold=5, keywords=["IllustrisTNG", "CAMELS", "sbi"])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["keyword"], "sbi")
        self.assertEqual(alerts[0]["paper_count"], 6)
        
        # 5. Fetch active velocity alerts
        active_alerts = custom_db.get_active_velocity_alerts(hours_back=48)
        self.assertEqual(len(active_alerts), 1)
        self.assertEqual(active_alerts[0]["keyword"], "sbi")
        self.assertEqual(active_alerts[0]["paper_count"], 6)

    def test_my_papers_operations(self):
        # 1. Add paper to my_papers
        success = self.db.add_my_paper(title="My Cosmological Paper", arxiv_id="2401.12345", doi="10.1088/12345", user_id=1)
        self.assertTrue(success)
        
        # 2. Get registered papers
        papers = self.db.get_my_papers(user_id=1)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["title"], "My Cosmological Paper")
        self.assertEqual(papers[0]["arxiv_id"], "2401.12345")
        
        # 3. Get all registered papers (across users)
        all_papers = self.db.get_all_my_papers()
        self.assertEqual(len(all_papers), 1)
        
        # 4. Update paper (e.g., set new arxiv_id or title)
        update_success = self.db.update_my_paper(papers[0]["id"], arxiv_id="2401.54321", title="My New Title")
        self.assertTrue(update_success)
        
        papers_updated = self.db.get_my_papers(user_id=1)
        self.assertEqual(papers_updated[0]["arxiv_id"], "2401.54321")
        self.assertEqual(papers_updated[0]["title"], "My New Title")
        
        # 5. Check if a paper cites user's work
        # Add citation relation: "2401.99999" cites our paper "2401.54321"
        self.db.add_citations_batch([("2401.99999", "2401.54321")])
        
        cites = self.db.check_if_paper_cites_user_work("2401.99999", user_id=1)
        self.assertTrue(cites)
        
        no_cites = self.db.check_if_paper_cites_user_work("2401.00000", user_id=1)
        self.assertFalse(no_cites)
        
        # Batch check
        citing_batch = self.db.get_papers_citing_user_work(["2401.99999", "2401.00000"], user_id=1)
        self.assertEqual(citing_batch, {"2401.99999"})
        
        # 6. Delete paper
        delete_success = self.db.delete_my_paper(papers[0]["id"], user_id=1)
        self.assertTrue(delete_success)
        
        papers_deleted = self.db.get_my_papers(user_id=1)
        self.assertEqual(len(papers_deleted), 0)


if __name__ == "__main__":
    unittest.main()
