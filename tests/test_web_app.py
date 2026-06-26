import unittest
from unittest.mock import Mock, patch
from aura.web.app import create_app


class TestWebApp(unittest.TestCase):
    def setUp(self):
        self.engine = Mock()
        self.engine.get_stats.return_value = {
            "database": {
                "total_papers": 10, 
                "with_embeddings": 8, 
                "total_rated": 5,
                "thumbs_up": 3,
                "thumbs_down": 2,
                "with_summaries": 4
            },
            "model": {
                "parameters": 100, 
                "embedding_dim": 384, 
                "learning_rate": 0.001, 
                "total_trained": 10,
                "replay_buffer_size": 5
            },
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
        self.engine.db.get_events.return_value = []
        self.engine.db.get_all_notes.return_value = []
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
        self.engine.data_dir = "/tmp"
        self.engine.embedding_model = "all-MiniLM-L6-v2"

        # Multi-user mocks required by Flask-Login
        _test_user = {
            "id": 1,
            "email": "test@example.com",
            "password_hash": "hashed",
            "is_admin": 1,
            "is_active": 1,
            "created_at": "2024-01-01T00:00:00",
        }
        self.engine.db.count_users.return_value = 0
        self.engine.db.create_user.return_value = _test_user
        self.engine.db.get_user_by_email.return_value = _test_user
        self.engine.db.get_user_by_id.return_value = _test_user
        self.engine.db.get_user_tokens.return_value = []
        self.engine.db.get_user_groups.return_value = []
        self.engine.db.get_all_groups.return_value = []
        self.engine.db.get_public_collections.return_value = []
        self.engine.db.get_all_users.return_value = [_test_user]
        self.engine.db.get_fetch_log.return_value = []

        with patch("aura.web.app.RecommendationEngine", return_value=self.engine):
            app = create_app()

        app.testing = True
        self.client = app.test_client()

        # Register and log in so Flask-Login doesn't redirect all routes
        with patch("aura.web.app.generate_password_hash", return_value="hashed"), \
             patch("aura.web.app.check_password_hash", return_value=True):
            self.client.post("/register", data={
                "email": "test@example.com",
                "password": "password123",
                "confirm_password": "password123",
            }, follow_redirects=True)
            self.client.post("/login", data={
                "email": "test@example.com",
                "password": "password123",
            }, follow_redirects=True)

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

        # Test Trends page
        resp = self.client.get("/trends")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Trend Radar", resp.data)

        # Test health check
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("details", data)
        self.assertEqual(data["details"]["db"], "ok")

    def test_metrics_endpoint(self):
        # Test Prometheus metrics endpoint
        resp = self.client.get("/metrics")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "text/plain")
        content = resp.data.decode("utf-8")
        self.assertIn("aura_papers_total", content)
        self.assertIn("aura_model_trained_samples_total", content)
        self.assertIn("# HELP", content)
        self.assertIn("# TYPE", content)

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

    @patch("aura.tasks.fetch_papers_task.delay")
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

    @patch("aura.tasks.generate_missing_summaries_task.delay")
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

    @patch("aura.tasks.retrain_full_task.delay")
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
            has_code=None,
            has_data=None,
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
        self.engine.db.add_tag.assert_called_with("2401.00001", "quantum", user_id=1)

        # 3. API: remove tag
        self.engine.db.remove_tag.return_value = True
        resp = self.client.delete("/api/papers/2401.00001/tags/quantum")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.remove_tag.assert_called_with("2401.00001", "quantum", user_id=1)

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
        self.engine.db.create_collection.assert_called_with("B", user_id=1, description="Desc")

        # 6. API: delete collection
        self.engine.db.delete_collection.return_value = True
        resp = self.client.delete("/api/collections/2")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.delete_collection.assert_called_with(2, user_id=1)

        # 7. API: add paper to collection
        self.engine.db.add_paper_to_collection.return_value = True
        resp = self.client.post("/api/collections/1/papers", json={"arxiv_id": "2401.00001"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.add_paper_to_collection.assert_called_with(1, "2401.00001", user_id=1)

        # 8. API: remove paper from collection
        self.engine.db.remove_paper_from_collection.return_value = True
        resp = self.client.delete("/api/collections/1/papers/2401.00001")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.remove_paper_from_collection.assert_called_with(1, "2401.00001", user_id=1)

        # 9. UI: Browse by tag / collection
        self.engine.db.get_papers_by_tag.return_value = []
        resp = self.client.get("/papers?tag=ml")
        self.assertEqual(resp.status_code, 200)
        self.engine.db.get_papers_by_tag.assert_called_with("ml", user_id=1, limit=200)

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
        self.engine.db.add_note.assert_called_with("2401.00001", "note 2", user_id=1)

        # 3. API: update note
        self.engine.db.update_note.return_value = True
        resp = self.client.put("/api/notes/1", json={"content": "updated"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.update_note.assert_called_with(1, "updated", user_id=1)

        # 4. API: delete note
        self.engine.db.delete_note.return_value = True
        resp = self.client.delete("/api/notes/1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.delete_note.assert_called_with(1, user_id=1)

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

    def test_notes_dashboard(self):
        self.engine.db.get_all_notes.return_value = [
            {
                "id": 1,
                "arxiv_id": "2401.00001",
                "content": "Dashboard note",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-02T00:00:00",
                "title": "A Great Astro Paper",
                "authors": ["Ada"],
                "published": "2026-01-01",
                "categories": ["astro-ph.CO"],
            }
        ]
        resp = self.client.get("/notes")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Study Notes", resp.data)
        self.assertIn(b"Dashboard note", resp.data)
        self.assertIn(b"A Great Astro Paper", resp.data)

    def test_export_collection_notes(self):
        self.engine.db.get_collection.return_value = {"id": 1, "name": "My Collection"}
        self.engine.db.get_notes_for_collection.return_value = [
            {
                "id": 1,
                "arxiv_id": "2401.00001",
                "content": "Great methods section.",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "title": "A Great Astro Paper",
                "authors": ["Ada"],
                "published": "2026-01-01",
                "categories": ["astro-ph.CO"],
            }
        ]
        resp = self.client.get("/api/collections/1/export-notes")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "text/markdown")
        content = resp.data.decode("utf-8")
        self.assertIn("Study Notes: My Collection", content)
        self.assertIn("A Great Astro Paper", content)
        self.assertIn("Great methods section.", content)
        self.assertIn("@article{", content)
        self.assertIn("notes_my_collection.md", resp.headers["Content-Disposition"])

    def test_export_collection_notes_not_found(self):
        self.engine.db.get_collection.return_value = None
        resp = self.client.get("/api/collections/999/export-notes")
        self.assertEqual(resp.status_code, 404)

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
        self.engine.db.add_to_reading_list.assert_called_with("2401.00001", user_id=1)

        # 3. API: remove from reading list
        self.engine.db.remove_from_reading_list.return_value = True
        resp = self.client.delete("/api/reading-list/2401.00001")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.remove_from_reading_list.assert_called_with("2401.00001", user_id=1)

        # 4. API: mark as read
        self.engine.db.mark_as_read.return_value = True
        resp = self.client.put("/api/reading-list/2401.00001/read")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.mark_as_read.assert_called_with("2401.00001", user_id=1)

    def test_admin_routes(self):
        # 1. GET /admin panel
        self.engine.db.get_all_users.return_value = [{"id": 1, "email": "test@example.com", "is_admin": 1, "is_active": 1, "created_at": "2026-01-01T00:00:00"}]
        self.engine.db.get_fetch_log.return_value = []
        resp = self.client.get("/admin")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Admin Panel", resp.data)

        # 2. POST /api/admin/users/2/suspend
        self.engine.db.update_user.return_value = True
        resp = self.client.post("/api/admin/users/2/suspend")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.update_user.assert_called_with(2, is_active=False)

        # 3. POST /api/admin/users/2/activate
        resp = self.client.post("/api/admin/users/2/activate")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.update_user.assert_called_with(2, is_active=True)

        # 4. DELETE /api/admin/users/2
        self.engine.db.delete_user.return_value = True
        resp = self.client.delete("/api/admin/users/2")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.engine.db.delete_user.assert_called_with(2)

        # 5. POST /api/admin/users/2/reset-password
        resp = self.client.post("/api/admin/users/2/reset-password", json={"password": "newpassword123"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        self.assertTrue(self.engine.db.update_user.called)

    def test_reference_manager_export(self):
        # Mock paper
        test_paper = {
            "arxiv_id": "2401.00001",
            "title": "A Great Astro Paper",
            "abstract": "A great abstract about stars.",
            "authors": ["Ada Lovelace", "Charles Babbage"],
            "categories": ["astro-ph.CO"],
            "url": "http://arxiv.org/abs/2401.00001",
            "pdf_url": "http://arxiv.org/pdf/2401.00001.pdf",
            "published": "2026-01-01T00:00:00Z"
        }
        self.engine.db.get_paper.return_value = test_paper
        
        # 1. Test single paper BibTeX export
        resp = self.client.get("/papers/2401.00001/export/bibtex")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/x-bibtex")
        self.assertIn(b"@article{2401.00001,", resp.data)
        self.assertIn(b"title={A Great Astro Paper}", resp.data)
        self.assertIn(b"author={Ada Lovelace and Charles Babbage}", resp.data)
        self.assertIn(b"journal={arXiv preprint arXiv:2401.00001}", resp.data)
        self.assertIn(b"year={2026}", resp.data)
        self.assertIn(b"archivePrefix={arXiv}", resp.data)
        self.assertIn(b"primaryClass={astro-ph.CO}", resp.data)
        
        # 2. Test single paper RIS export
        resp = self.client.get("/papers/2401.00001/export/ris")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/x-research-info-systems")
        self.assertIn(b"TY  - JOUR", resp.data)
        self.assertIn(b"TI  - A Great Astro Paper", resp.data)
        self.assertIn(b"AU  - Ada Lovelace", resp.data)
        self.assertIn(b"AU  - Charles Babbage", resp.data)
        self.assertIn(b"JO  - arXiv preprint arXiv:2401.00001", resp.data)
        self.assertIn(b"PY  - 2026", resp.data)
        self.assertIn(b"ER  -", resp.data)
        
        # 3. Test bulk BibTeX export (collection ownership verified)
        self.engine.db.get_collection.return_value = {"id": 1, "user_id": 1, "name": "My List", "is_public": 0}
        self.engine.db.get_collection_papers.return_value = [test_paper]
        resp = self.client.get("/papers/export/bibtex?collection=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/x-bibtex")
        self.assertIn(b"@article{2401.00001,", resp.data)
        
        # 4. Test bulk RIS export (collection ownership verified)
        resp = self.client.get("/papers/export/ris?collection=1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/x-research-info-systems")
        self.assertIn(b"TY  - JOUR", resp.data)
        
        # 5. Test single RIS export via query parameter
        resp = self.client.get("/papers/export/ris?arxiv_id=2401.00001")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "application/x-research-info-systems")
        self.assertIn(b"TY  - JOUR", resp.data)
        
        # 6. Test unauthorized collection export (different user, not public)
        self.engine.db.get_collection.return_value = {"id": 2, "user_id": 2, "name": "Secret List", "is_public": 0}
        resp = self.client.get("/papers/export/bibtex?collection=2")
        self.assertEqual(resp.status_code, 403)
        
        # 7. Test Zotero Connector compatibility header on paper detail
        self.engine.db.get_latest_rating.return_value = None
        self.engine.db.get_paper_tags.return_value = []
        self.engine.db.get_paper_collections.return_value = []
        self.engine.db.get_paper_notes.return_value = []
        self.engine.db.is_in_reading_list.return_value = False
        resp = self.client.get("/papers/2401.00001")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Link", resp.headers)
        link_header = resp.headers["Link"]
        self.assertIn("export/bibtex", link_header)
        self.assertIn("export/ris", link_header)

    def test_one_click_unsubscribe_and_rate_direct(self):
        # 1. Test unsubscribe success
        self.engine.db.get_user_by_unsubscribe_token.return_value = {
            "id": 1,
            "email": "test@example.com",
            "digest_frequency": "daily",
        }
        self.engine.db.update_user.return_value = True
        resp = self.client.get("/unsubscribe/my_unsub_token")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Unsubscribed Successfully", resp.data)
        self.engine.db.update_user.assert_called_with(1, digest_frequency="off")

        # 2. Test unsubscribe fail (missing token)
        self.engine.db.get_user_by_unsubscribe_token.return_value = None
        resp = self.client.get("/unsubscribe/invalid_token")
        self.assertEqual(resp.status_code, 404)

        # 3. Test rate-direct success
        from itsdangerous import URLSafeTimedSerializer
        secret_key = self.client.application.secret_key
        serializer = URLSafeTimedSerializer(secret_key)
        valid_token = serializer.dumps({"user_id": 1, "arxiv_id": "2401.00001", "rating": 1})

        self.engine.db.get_paper.return_value = {"title": "A Great Astro Paper"}
        self.engine.rate_paper.return_value = {"status": "rated", "trained": True}

        resp = self.client.get(f"/rate-direct?token={valid_token}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Feedback Received", resp.data)
        self.assertIn(b"A Great Astro Paper", resp.data)
        self.assertIn(b"Thumbs Up", resp.data)
        self.engine.rate_paper.assert_called_with("2401.00001", 1, user_id=1)

        # 4. Test rate-direct missing token
        resp = self.client.get("/rate-direct")
        self.assertEqual(resp.status_code, 400)

        # 5. Test rate-direct invalid token
        resp = self.client.get("/rate-direct?token=badtoken")
        self.assertEqual(resp.status_code, 400)

    def test_slack_command(self):
        # 1. Test help response
        resp = self.client.post("/api/integrations/slack/command", data={"command": "/aura", "text": "help"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("Usage", data["text"])

        # 2. Test recommend response
        self.engine.get_recommendations.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "A Great Astro Paper",
                "score": 0.95,
                "url": "http://arxiv.org/abs/2401.00001",
                "authors": ["Ada"],
                "summary": "This is a great paper.",
            }
        ]
        resp = self.client.post("/api/integrations/slack/command", data={"command": "/aura", "text": "recommend"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["response_type"], "in_channel")
        self.assertIn("A Great Astro Paper", data["blocks"][2]["text"]["text"])
        self.assertIn("Score: *95%*", data["blocks"][2]["text"]["text"])
        self.engine.get_recommendations.assert_called_with(limit=5, user_id=1)

        # 3. Test recommend with custom limit
        resp = self.client.post("/api/integrations/slack/command", data={"command": "/aura", "text": "recommend 10"})
        self.assertEqual(resp.status_code, 200)
        self.engine.get_recommendations.assert_called_with(limit=10, user_id=1)

        # 4. Test recommend no papers found
        self.engine.get_recommendations.return_value = []
        resp = self.client.post("/api/integrations/slack/command", data={"command": "/aura", "text": "recommend"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("No recommendations found", data["text"])

    @patch("aura.embedder.embed_papers_batch")
    @patch("aura.fetcher.ArxivSource")
    @patch("torch.sigmoid")
    @patch("torch.tensor")
    def test_extension_endpoints(self, mock_tensor, mock_sigmoid, mock_source_cls, mock_embed_batch):
        # 1. Test check when paper exists in DB
        self.engine.db.get_paper.return_value = {"title": "Existing Paper", "summary": "A summary"}
        self.engine.db.get_latest_rating.return_value = 1
        self.engine.db.get_papers_with_embeddings.return_value = [("2401.00001", [0.1, 0.2, 0.3])]
        
        pref_model = Mock()
        self.engine.get_user_preference_model.return_value = pref_model
        mock_sigmoid.return_value.item.return_value = 0.92
        
        resp = self.client.get("/api/extension/check?arxiv_id=2401.00001")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["exists"])
        self.assertEqual(data["score"], 0.92)
        self.assertEqual(data["rating"], 1)

        # 2. Test check when paper NOT in DB
        self.engine.db.get_paper.return_value = None
        mock_source = Mock()
        mock_source.fetch_by_id.return_value = {"title": "New Paper"}
        mock_source_cls.return_value = mock_source
        mock_embed_batch.return_value = [[0.1, 0.2, 0.3]]
        
        resp = self.client.get("/api/extension/check?arxiv_id=2401.00002")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertFalse(data["exists"])
        self.assertEqual(data["title"], "New Paper")
        self.assertEqual(data["score"], 0.92)

        # 3. Test add paper
        self.engine.fetch_and_add_paper.return_value = {"title": "New Paper", "summary": "A summary"}
        self.engine.db.get_latest_rating.return_value = None
        
        resp = self.client.post("/api/extension/add", json={"arxiv_id": "2401.00002"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["title"], "New Paper")

    @patch("aura.briefs.generate_weekly_brief_content")
    def test_research_brief_routes(self, mock_gen_content):
        mock_gen_content.return_value = "<div>Mock Brief Content</div>"
        
        # 1. Test get all briefs list
        self.engine.db.get_all_briefs.return_value = [
            {"date": "2026-06-23", "content": "<div>Brief content</div>", "created_at": "2026-06-23T23:39:34"}
        ]
        resp = self.client.get("/briefs")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Weekly Research Briefs", resp.data)
        self.assertIn(b"Brief for 2026-06-23", resp.data)

        # 2. Test get a specific brief (existing)
        self.engine.db.get_brief.return_value = {
            "date": "2026-06-23", "content": "<div>Brief content</div>", "created_at": "2026-06-23T23:39:34"
        }
        resp = self.client.get("/briefs/2026-06-23")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Weekly Research Brief", resp.data)
        self.assertIn(b"Brief content", resp.data)

        # 3. Test get a specific brief (non-existing, should trigger generate)
        self.engine.db.get_brief.return_value = None
        resp = self.client.get("/briefs/2026-06-24")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Mock Brief Content", resp.data)
        mock_gen_content.assert_called_once()

        # 4. Test generate endpoint (POST)
        mock_gen_content.reset_mock()
        resp = self.client.post("/api/briefs/generate")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "success")
        self.assertTrue("date" in data)
        mock_gen_content.assert_called_once()

    def test_api_docs_route(self):
        # Test get interactive API docs
        resp = self.client.get("/api/docs")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"AURA API Documentation", resp.data)
        self.assertIn(b"/static/openapi.json", resp.data)

    def test_surveys_ui_filtering(self):
        # Configure mock surveys on self.engine.db
        self.engine.db.get_surveys.return_value = [
            {"id": 1, "name": "DESI", "keywords": '["DESI"]'},
            {"id": 2, "name": "Planck", "keywords": '["Planck"]'},
        ]
        self.engine.db.get_papers_by_tag.return_value = []
        
        # Access /papers route and check if mocked survey names are rendered
        resp = self.client.get("/papers")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"DESI", resp.data)
        self.assertIn(b"Planck", resp.data)
        
        # Access /papers?tag=desi to test filtering by a survey tag
        resp_filter = self.client.get("/papers?tag=desi")
        self.assertEqual(resp_filter.status_code, 200)

    def test_my_papers_routes_and_badges(self):
        # 1. Mock database methods on self.engine.db
        self.engine.db.get_my_papers.return_value = [
            {
                "id": 12,
                "arxiv_id": "2401.12345",
                "doi": "10.1088/12345",
                "title": "My Test Paper",
                "created_at": "2026-06-26T12:00:00"
            }
        ]
        self.engine.db.add_my_paper.return_value = True
        self.engine.db.delete_my_paper.return_value = True
        
        # Mock connection and cursor/fetchone to return a dummy row
        from unittest.mock import MagicMock
        dummy_row = MagicMock()
        dummy_row.__getitem__.side_effect = lambda key: 12 if key == "id" else None
        self.engine.db.conn.execute.return_value.fetchone.return_value = dummy_row
        
        # Patch refresh_single_my_paper_citations to do nothing
        with patch.object(self.engine, "refresh_single_my_paper_citations") as mock_refresh:
            # Test GET /my-papers
            resp = self.client.get("/my-papers")
            self.assertEqual(resp.status_code, 200)
            self.assertIn(b"My Test Paper", resp.data)
            self.assertIn(b"2401.12345", resp.data)
            
            # Test POST /my-papers/add
            resp_add = self.client.post("/my-papers/add", data={
                "title": "New Paper",
                "arxiv_id": "2401.54321",
                "doi": ""
            }, follow_redirects=True)
            self.assertEqual(resp_add.status_code, 200)
            self.assertIn(b"Successfully registered your paper", resp_add.data)
            mock_refresh.assert_called_once()
            
            # Test POST /my-papers/delete/<id>
            resp_del = self.client.post("/my-papers/delete/12", follow_redirects=True)
            self.assertEqual(resp_del.status_code, 200)
            self.assertIn(b"Successfully removed paper registration", resp_del.data)

        # 2. Test paper card badging for "Cites your work"
        # Mock get_papers_citing_user_work to return a set containing the mocked paper's arxiv_id
        self.engine.db.get_papers_citing_user_work.return_value = {"2401.00001"}
        
        # Access papers page (contains paper 2401.00001)
        resp_papers = self.client.get("/papers")
        self.assertEqual(resp_papers.status_code, 200)
        self.assertIn(b"Cites your work", resp_papers.data)


if __name__ == "__main__":
    unittest.main()
