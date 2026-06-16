import unittest
from unittest.mock import Mock, patch
from ai_papers.web.app import create_app


class TestWebApp(unittest.TestCase):
    def setUp(self):
        self.engine = Mock()
        self.engine.get_stats.return_value = {
            "database": {"total_papers": 10, "with_embeddings": 8, "total_rated": 5},
            "model": {"parameters": 100, "embedding_dim": 384, "learning_rate": 0.001, "total_trained": 10},
            "categories": ["astro-ph.CO", "astro-ph.GA"],
            "data_dir": "data"
        }
        self.engine.get_recommendations.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "A Great Astro Paper",
                "abstract": "A great abstract about stars.",
                "authors": ["Ada"],
                "categories": ["astro-ph.CO"],
                "score": 0.95,
                "model_score": 0.8,
                "freshness_bonus": 0.1,
                "summary_bonus": 0.05,
                "url": "http://arxiv.org/abs/2401.00001",
                "summary": "Existing summary",
                "published": "2026-01-01T00:00:00Z"
            }
        ]
        self.engine.db = Mock()
        self.engine.db.get_papers.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "A Great Astro Paper",
                "abstract": "A great abstract about stars.",
                "authors": ["Ada"],
                "categories": ["astro-ph.CO"],
                "score": 0.95,
                "model_score": 0.8,
                "freshness_bonus": 0.1,
                "summary_bonus": 0.05,
                "url": "http://arxiv.org/abs/2401.00001",
                "summary": "Existing summary",
                "published": "2026-01-01T00:00:00Z"
            }
        ]
        self.engine.db.get_PAPER_NOTES_RETURN_VALUE = []
        self.engine.db.get_latest_rating.return_value = 1
        self.engine.db.get_paper_tags.return_value = []
        self.engine.db.get_paper_collections.return_value = []
        self.engine.db.get_paper_notes.return_value = []
        self.engine.db.get_collections.return_value = []
        self.engine.db.get_all_tags.return_value = []
        self.engine.db.get_ratings_history.return_value = []
        self.engine.db.get_papers_by_authors.return_value = []
        self.engine.db.is_in_reading_list.return_value = False
        self.engine.get_similar_papers.return_value = []
        self.engine.db.get_task_status.return_value = {"status": "SUCCESS", "progress": 10, "total": 10}
        self.engine.db.search_papers.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "A Great <mark>Astro</mark> Paper",
                "abstract": "A great abstract about stars.",
                "authors": ["Ada"],
                "categories": ["astro-ph.CO"],
                "score": 0.95,
                "url": "http://arxiv.org/abs/2401.00001",
                "summary": "Existing summary",
                "published": "2026-01-01T00:00:00Z"
            }
        ]
        self.engine.generate_missing_summaries.return_value = {
            "status": "ok",
            "processed": 1,
            "updated": 1,
        }
        self.engine.retrain_full.return_value = {"status": "retrained"}
        self.engine.fetch_new_papers.return_value = 3

        with patch("ai_papers.web.app.RecommendationEngine", return_value=self.engine):
            app = create_app()

        app.testing = True
        self.client = app.test_client()

    def test_routes_html(self):
        # Test main HTML pages render successfully (status 200)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Dashboard", resp.data)

        resp = self.client.get("/fetch")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Fetch Papers", resp.data)

        resp = self.client.get("/settings")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Settings", resp.data)
        
        self.engine.discover_topics.return_value = [{"id": 0, "name": "Test Topic", "keywords": ["test"], "paper_count": 5, "top_papers": []}]
        resp = self.client.get("/topics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Auto-Discovered Topics", resp.data)
        self.assertIn(b"Test Topic", resp.data)

        # Test health check
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})

    def test_onboarding_route_and_redirect(self):
        # When user has >= 5 ratings, onboarding redirects to /
        self.engine.get_stats.return_value["database"]["total_rated"] = 5
        resp = self.client.get("/onboarding")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers["Location"], "/")
        
        # When user has < 5 ratings, accessing / redirects to /onboarding
        self.engine.get_stats.return_value["database"]["total_rated"] = 2
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.headers["Location"], "/onboarding")

        # Accessing /onboarding directly when < 5 ratings should work
        self.engine.get_diverse_papers.return_value = [{"arxiv_id": "2401.00001", "title": "Paper 1", "authors": [], "categories": [], "published": ""}]
        resp = self.client.get("/onboarding")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Welcome to AURA", resp.data)
        self.assertIn(b"Paper 1", resp.data)

    def test_route_papers_filters(self):
        # Test different filter types on /papers
        for filt in ["unrated", "liked", "disliked", "all"]:
            resp = self.client.get(f"/papers?filter={filt}")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"Papers", resp.data)

    def test_api_rate_validation(self):
        resp = self.client.post("/api/rate", json={})
        self.assertEqual(resp.status_code, 400)

        resp = self.client.post("/api/rate", json={"arxiv_id": "x", "rating": 6})
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

        resp = self.client.get("/api/tasks/mock-task-123")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "SUCCESS")

        resp = self.client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)

    @patch("ai_papers.tasks.generate_missing_summaries_task.delay")
    def test_api_summarize_async(self, mock_delay):
        mock_task = Mock()
        mock_task.id = "mock-task-summarize"
        mock_delay.return_value = mock_task

        resp = self.client.post("/api/summarize", json={"limit": 10, "only_missing": True})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["task_id"], "mock-task-summarize")

    def test_api_summarize_single_not_found(self):
        self.engine.generate_summary_for_paper.return_value = {"status": "not_found"}
        resp = self.client.post("/api/summarize-paper", json={"arxiv_id": "missing"})
        self.assertEqual(resp.status_code, 404)

        self.engine.generate_summary_for_paper.return_value = {"status": "ok", "summary": "good"}
        resp = self.client.post("/api/summarize-paper", json={"arxiv_id": "2401.00001"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["summary"], "good")

    @patch("ai_papers.tasks.retrain_full_task.delay")
    def test_api_retrain_async(self, mock_delay):
        mock_task = Mock()
        mock_task.id = "mock-task-retrain"
        mock_delay.return_value = mock_task

        resp = self.client.post("/api/retrain", json={"epochs": 5})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["task_id"], "mock-task-retrain")

    def test_api_config_read_only(self):
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        config_data = resp.get_json()
        self.assertIn("categories", config_data)

    def test_search_routes(self):
        # 1. Test HTML search page
        resp = self.client.get("/papers?q=Astro&category=astro-ph.CO&date_from=2026-01-01&date_to=2026-01-02")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Search Results", resp.data)
        self.assertIn(b"A Great <mark>Astro</mark> Paper", resp.data)
        self.engine.db.search_papers.assert_called_with(
            query="Astro",
            category="astro-ph.CO",
            date_from="2026-01-01",
            date_to="2026-01-02",
            limit=200
        )

        # 2. Test API search endpoint (FTS)
        resp = self.client.get("/api/search?q=Astro&category=astro-ph.CO&date_from=2026-01-01&date_to=2026-01-02")
        self.assertEqual(resp.status_code, 200)
        results = resp.get_json()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["arxiv_id"], "2401.00001")
        self.assertIn("<mark>Astro</mark>", results[0]["title"])

        # 3. Test API search endpoint (Semantic)
        self.engine.semantic_search.return_value = [{"arxiv_id": "2401.00002", "title": "Semantic Paper"}]
        resp = self.client.get("/api/search?mode=semantic&q=Astro")
        self.assertEqual(resp.status_code, 200)
        results = resp.get_json()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["arxiv_id"], "2401.00002")
        self.engine.semantic_search.assert_called_with(query="Astro", limit=50)

    def test_paper_detail_route(self):
        paper_data = {
            "arxiv_id": "2401.00001",
            "title": "A Great Astro Paper",
            "abstract": "A great abstract about stars.",
            "authors": ["Ada"],
            "categories": ["astro-ph.CO"],
            "url": "http://arxiv.org/abs/2401.00001",
            "pdf_url": "http://arxiv.org/pdf/2401.00001.pdf",
            "summary": "Existing summary",
            "published": "2026-01-01T00:00:00Z"
        }
        self.engine.db.get_paper.return_value = paper_data
        self.engine.db.get_ratings_history.return_value = [
            {"rating": 1, "rated_at": "2026-06-16T12:00:00Z"}
        ]
        self.engine.get_similar_papers.return_value = []
        self.engine.db.get_papers_by_authors.return_value = []

        # 1. Test success detail route
        resp = self.client.get("/papers/2401.00001")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"A Great Astro Paper", resp.data)
        self.assertIn(b"ar5iv.labs.arxiv.org/html/2401.00001", resp.data)
        self.engine.db.get_paper.assert_called_with("2401.00001")

        # 2. Test 404 not found
        self.engine.db.get_paper.return_value = None
        resp = self.client.get("/papers/missing")
        self.assertEqual(resp.status_code, 404)
        self.assertIn(b"Resource Not Found", resp.data)

    def test_tags_and_collections_api_and_ui_routes(self):
        # 1. API: tags list
        self.engine.db.get_all_tags.return_value = ["ml", "llm"]
        resp = self.client.get("/api/tags")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), ["ml", "llm"])

        # 2. API: add tag
        self.engine.db.add_tag.return_value = True
        resp = self.client.post("/api/papers/2401.00001/tags", json={"tag": "quantum"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "tag": "quantum"})
        self.engine.db.add_tag.assert_called_with("2401.00001", "quantum")

        # 3. API: remove tag
        self.engine.db.remove_tag.return_value = True
        resp = self.client.delete("/api/papers/2401.00001/tags/quantum")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.remove_tag.assert_called_with("2401.00001", "quantum")

        # 4. API: collections list
        self.engine.db.get_collections.return_value = [{"id": 1, "name": "A", "paper_count": 0}]
        resp = self.client.get("/api/collections")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [{"id": 1, "name": "A", "paper_count": 0}])

        # 5. API: create collection
        self.engine.db.create_collection.return_value = 2
        resp = self.client.post("/api/collections", json={"name": "B", "description": "Desc"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "id": 2, "name": "B"})
        self.engine.db.create_collection.assert_called_with("B", "Desc")

        # 6. API: delete collection
        self.engine.db.delete_collection.return_value = True
        resp = self.client.delete("/api/collections/2")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.delete_collection.assert_called_with(2)

        # 7. API: add paper to collection
        self.engine.db.add_paper_to_collection.return_value = True
        resp = self.client.post("/api/collections/1/papers", json={"arxiv_id": "2401.00001"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.add_paper_to_collection.assert_called_with(1, "2401.00001")

        # 8. API: remove paper from collection
        self.engine.db.remove_paper_from_collection.return_value = True
        resp = self.client.delete("/api/collections/1/papers/2401.00001")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.remove_paper_from_collection.assert_called_with(1, "2401.00001")

        # 9. UI: Browse by tag / collection
        self.engine.db.get_papers_by_tag.return_value = []
        resp = self.client.get("/papers?tag=ml")
        self.assertEqual(resp.status_code, 200)
        self.engine.db.get_papers_by_tag.assert_called_with("ml", limit=200)

        self.engine.db.get_collection_papers.return_value = []
        self.engine.db.get_collection.return_value = {"id": 1, "name": "A"}
        resp = self.client.get("/papers?collection_id=1")
        self.assertEqual(resp.status_code, 200)
        self.engine.db.get_collection_papers.assert_called_with(1, limit=200)

    def test_notes_api_and_ui_routes(self):
        # 1. API: list notes
        self.engine.db.get_paper_notes.return_value = [{"id": 1, "content": "note 1"}]
        resp = self.client.get("/api/papers/2401.00001/notes")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), [{"id": 1, "content": "note 1"}])

        # 2. API: add note
        self.engine.db.add_note.return_value = 2
        resp = self.client.post("/api/papers/2401.00001/notes", json={"content": "note 2"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok", "id": 2})
        self.engine.db.add_note.assert_called_with("2401.00001", "note 2")

        # 3. API: update note
        self.engine.db.update_note.return_value = True
        resp = self.client.put("/api/notes/1", json={"content": "updated"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.update_note.assert_called_with(1, "updated")

        # 4. API: delete note
        self.engine.db.delete_note.return_value = True
        resp = self.client.delete("/api/notes/1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.delete_note.assert_called_with(1)

        # 5. UI: Paper detail includes notes
        self.engine.db.get_paper.return_value = {
            "arxiv_id": "2401.00001",
            "title": "Title",
            "abstract": "Abstract",
            "authors": ["Author"],
            "categories": ["cat"],
            "url": "url",
            "summary": "summary",
            "published": "2026-01-01"
        }
        self.engine.db.get_paper_notes.return_value = [{"id": 1, "content": "test note", "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}]
        resp = self.client.get("/papers/2401.00001")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"test note", resp.data)
        self.assertIn(b"Personal Notes", resp.data)


    def test_reading_list_api_and_ui_routes(self):
        # 1. API: list reading list
        self.engine.db.get_reading_list.return_value = [{
            "arxiv_id": "2401.00001",
            "title": "Paper 1",
            "authors": ["Ada"],
            "abstract": "Abstract",
            "categories": ["cat"],
            "published": "2026-01-01",
            "added_at": "2026-01-01T00:00:00"
        }]
        resp = self.client.get("/reading-list")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Paper 1", resp.data)

        # 2. API: add to reading list
        self.engine.db.add_to_reading_list.return_value = True
        resp = self.client.post("/api/reading-list", json={"arxiv_id": "2401.00001"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.add_to_reading_list.assert_called_with("2401.00001")

        # 3. API: remove from reading list
        self.engine.db.remove_from_reading_list.return_value = True
        resp = self.client.delete("/api/reading-list/2401.00001")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.remove_from_reading_list.assert_called_with("2401.00001")

        # 4. API: mark as read
        self.engine.db.mark_as_read.return_value = True
        resp = self.client.put("/api/reading-list/2401.00001/read")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.mark_as_read.assert_called_with("2401.00001")

if __name__ == "__main__":
    unittest.main()
