"""Flask web application for browsing and rating papers."""

import logging
import os
import uuid

from flask import Flask, jsonify, render_template, request, g

from ..recommender import RecommendationEngine
from ..config import get_validated_config
from ..logging_config import setup_logging

logger = logging.getLogger(__name__)

engine: RecommendationEngine | None = None


def create_app(config_path: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    # Setup structured JSON logging
    setup_logging(level=logging.INFO, structured=True)

    app = Flask(__name__)

    # Load config
    if config_path is None:
        config_path = os.environ.get("AI_PAPERS_CONFIG", "config.yaml")

    try:
        config = get_validated_config(config_path)
    except Exception as e:
        logger.error(f"Failed to start AURA: {e}")
        raise SystemExit(f"Configuration error: {e}")
        
    app.config["AI_PAPERS"] = config

    # Initialize recommendation engine
    global engine
    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        rss_urls=config.get("rss_feeds", []),
    )

    # Register X-Request-ID hooks
    @app.before_request
    def before_request():
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        from ..logging_config import request_id_var
        request_id_var.set(req_id)
        g.request_id = req_id
        logger.info(f"Incoming request: {request.method} {request.path}")

    @app.after_request
    def after_request(response):
        req_id = getattr(g, "request_id", None)
        if req_id:
            response.headers["X-Request-ID"] = req_id
        return response

    # Register routes
    _register_routes(app)

    return app


def _register_routes(app: Flask):
    """Register all route handlers."""

    @app.before_request
    def check_onboarding():
        """Redirect to onboarding if the user has rated fewer than 5 papers."""
        if request.endpoint and request.endpoint not in ['onboarding', 'static', 'rate_paper', 'health'] and not request.path.startswith('/api/'):
            stats = engine.get_stats()
            if stats["database"]["total_rated"] < 5:
                # Don't redirect if they are already on the onboarding page
                if request.path != '/onboarding':
                    from flask import redirect
                    return redirect('/onboarding')

    @app.route("/")
    def index():
        """Dashboard / home page."""
        stats = engine.get_stats()
        return render_template("index.html", stats=stats)

    @app.route("/topics")
    def topics():
        """Auto-discovered topic clusters."""
        clusters = engine.discover_topics() if engine else []
        return render_template("topics.html", clusters=clusters)

    @app.route("/onboarding")
    def onboarding():
        """Onboarding wizard to solve the cold start problem."""
        stats = engine.get_stats()
        total_rated = stats["database"]["total_rated"]

        if total_rated >= 5:
            from flask import redirect
            return redirect("/")

        # Get diverse unrated papers
        papers = engine.get_diverse_papers(limit=20)

        return render_template("onboarding.html", papers=papers, total_rated=total_rated)

    @app.route("/papers")
    def papers():
        """Browse recommended papers or search papers."""
        query = request.args.get("q", "").strip()
        search_mode = request.args.get("mode", "fts") # 'fts' or 'semantic'
        category = request.args.get("category", "").strip() or None
        date_from = request.args.get("date_from", "").strip() or None
        date_to = request.args.get("date_to", "").strip() or None
        tag = request.args.get("tag", "").strip() or None
        collection_id = request.args.get("collection_id", type=int)
        filter_type = request.args.get("filter", "unrated")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 30))

        if query:
            if search_mode == "semantic":
                paper_list = engine.semantic_search(query=query, limit=200)
            else:
                # Full-text search with optional filters
                paper_list = engine.db.search_papers(
                    query=query,
                    category=category,
                    date_from=date_from,
                    date_to=date_to,
                    limit=200,
                )
            filter_type = "search"
        elif tag:
            paper_list = engine.db.get_papers_by_tag(tag, limit=200)
            filter_type = f"tag: {tag}"
        elif collection_id:
            paper_list = engine.db.get_collection_papers(collection_id, limit=200)
            coll = engine.db.get_collection(collection_id)
            coll_name = coll["name"] if coll else "Collection"
            filter_type = f"collection: {coll_name}"
        else:
            if filter_type == "unrated":
                paper_list = engine.get_recommendations(
                    limit=per_page * page, unrated_only=True
                )
            elif filter_type == "liked":
                paper_list = engine.db.get_papers(
                    limit=per_page, offset=(page - 1) * per_page, rated_only=True
                )
                # Add ratings
                for p in paper_list:
                    p["rating"] = engine.db.get_latest_rating(p["arxiv_id"])
                    p["score"] = p.get("score", 0)
                paper_list = [p for p in paper_list if p.get("rating") == 1]
            elif filter_type == "disliked":
                paper_list = engine.db.get_papers(
                    limit=per_page, offset=(page - 1) * per_page, rated_only=True
                )
                for p in paper_list:
                    p["rating"] = engine.db.get_latest_rating(p["arxiv_id"])
                    p["score"] = p.get("score", 0)
                paper_list = [p for p in paper_list if p.get("rating") == 0]
            else:
                paper_list = engine.get_recommendations(
                    limit=per_page * page, unrated_only=False
                )

        # Paginate
        start = (page - 1) * per_page
        paper_list = paper_list[start : start + per_page]

        # Add current rating, tags, and collections info
        for p in paper_list:
            if "rating" not in p:
                p["rating"] = engine.db.get_latest_rating(p["arxiv_id"])
            p["tags"] = engine.db.get_paper_tags(p["arxiv_id"])
            p["collections"] = engine.db.get_paper_collections(p["arxiv_id"])
            p["in_reading_list"] = engine.db.is_in_reading_list(p["arxiv_id"])

        categories = app.config.get("AI_PAPERS", {}).get("categories", [])
        collections = engine.db.get_collections() if engine else []
        all_tags = engine.db.get_all_tags() if engine else []

        return render_template(
            "papers.html",
            papers=paper_list,
            filter_type=filter_type,
            page=page,
            per_page=per_page,
            categories=categories,
            collections=collections,
            all_tags=all_tags,
            q=query,
            category=category,
            date_from=date_from,
            date_to=date_to,
            selected_tag=tag,
            selected_collection_id=collection_id,
        )

    @app.route("/papers/<path:arxiv_id>")
    def paper_detail(arxiv_id):
        """Show full details of a paper."""
        paper = engine.db.get_paper(arxiv_id) if engine else None
        if not paper:
            return render_template("404.html"), 404

        # Add current rating info, tags, and collections
        paper["rating"] = engine.db.get_latest_rating(arxiv_id) if engine else None
        paper["tags"] = engine.db.get_paper_tags(arxiv_id) if engine else []
        paper["collections"] = engine.db.get_paper_collections(arxiv_id) if engine else []
        paper["notes"] = engine.db.get_paper_notes(arxiv_id) if engine else []
        paper["in_reading_list"] = engine.db.is_in_reading_list(arxiv_id) if engine else False

        # Get ratings history
        ratings_history = engine.db.get_ratings_history(arxiv_id) if engine else []

        # Get similar papers
        similar_papers = engine.get_similar_papers(arxiv_id, limit=5) if engine else []

        # Get papers by the same authors
        same_author_papers = engine.db.get_papers_by_authors(
            paper["authors"], exclude_arxiv_id=arxiv_id, limit=5
        ) if engine else []

        # Get all collections for the dropdown
        collections = engine.db.get_collections() if engine else []

        # ar5iv URL for HTML view
        ar5iv_url = f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}"

        return render_template(
            "paper_detail.html",
            paper=paper,
            ratings_history=ratings_history,
            similar_papers=similar_papers,
            same_author_papers=same_author_papers,
            collections=collections,
            ar5iv_url=ar5iv_url,
        )

    @app.route("/api/rate", methods=["POST"])
    def rate_paper():
        """API endpoint to rate a paper (1-5 stars, or -1 for skip)."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        arxiv_id = data.get("arxiv_id")
        rating = data.get("rating")

        if not arxiv_id or rating is None:
            return jsonify({"error": "arxiv_id and rating are required"}), 400

        if rating not in (-1, 0, 1, 2, 3, 4, 5):
            return jsonify({"error": "rating must be -1 (skip) or 1-5 (stars)"}), 400

        result = engine.rate_paper(arxiv_id, rating)
        return jsonify(result)

    @app.route("/reading-list")
    def reading_list():
        """Show the user's reading list."""
        filter_type = request.args.get("filter", "unread")
        if filter_type == "read":
            papers = engine.db.get_reading_list(only_read=True)
        else:
            papers = engine.db.get_reading_list(only_unread=True)

        # Add tags, collections, etc.
        for p in papers:
            p["rating"] = engine.db.get_latest_rating(p["arxiv_id"])
            p["tags"] = engine.db.get_paper_tags(p["arxiv_id"])
            p["collections"] = engine.db.get_paper_collections(p["arxiv_id"])
            p["in_reading_list"] = True

        return render_template("reading_list.html", papers=papers, filter_type=filter_type)

    @app.route("/api/reading-list", methods=["POST"])
    def add_to_reading_list():
        """API endpoint to add a paper to the reading list."""
        data = request.get_json() or {}
        arxiv_id = data.get("arxiv_id")
        if not arxiv_id:
            return jsonify({"error": "arxiv_id is required"}), 400

        success = engine.db.add_to_reading_list(arxiv_id) if engine else False
        if not success:
            return jsonify({"error": "failed to add to reading list"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/reading-list/<path:arxiv_id>", methods=["DELETE"])
    def remove_from_reading_list(arxiv_id):
        """API endpoint to remove a paper from the reading list."""
        success = engine.db.remove_from_reading_list(arxiv_id) if engine else False
        if not success:
            return jsonify({"error": "failed to remove from reading list"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/reading-list/<path:arxiv_id>/read", methods=["PUT"])
    def mark_paper_as_read(arxiv_id):
        """API endpoint to mark a paper as read."""
        success = engine.db.mark_as_read(arxiv_id) if engine else False
        if not success:
            return jsonify({"error": "failed to mark as read"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/explain/<path:arxiv_id>", methods=["GET"])
    def explain_paper(arxiv_id):
        """API endpoint to get explainability data for a recommendation."""
        paper = engine.db.get_paper(arxiv_id) if engine else None
        if not paper:
            return jsonify({"error": "Paper not found"}), 404
        
        similar_liked = engine.get_similar_liked_papers(arxiv_id, limit=3) if engine else []
        
        return jsonify({
            "arxiv_id": arxiv_id,
            "similar_liked": similar_liked
        })

    @app.route("/api/papers/<path:arxiv_id>/notes", methods=["GET"])
    def get_paper_notes(arxiv_id):
        """API endpoint to get all notes for a paper."""
        notes = engine.db.get_paper_notes(arxiv_id) if engine else []
        return jsonify(notes)

    @app.route("/api/papers/<path:arxiv_id>/notes", methods=["POST"])
    def add_paper_note(arxiv_id):
        """API endpoint to add a note to a paper."""
        data = request.get_json() or {}
        content = data.get("content", "").strip()
        if not content:
            return jsonify({"error": "content is required"}), 400

        note_id = engine.db.add_note(arxiv_id, content) if engine else None
        if note_id is None:
            return jsonify({"error": "failed to add note"}), 500
        return jsonify({"status": "ok", "id": note_id})

    @app.route("/api/notes/<int:note_id>", methods=["PUT"])
    def update_paper_note(note_id):
        """API endpoint to update a paper note."""
        data = request.get_json() or {}
        content = data.get("content", "").strip()
        if not content:
            return jsonify({"error": "content is required"}), 400

        success = engine.db.update_note(note_id, content) if engine else False
        if not success:
            return jsonify({"error": "failed to update note"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/notes/<int:note_id>", methods=["DELETE"])
    def delete_paper_note(note_id):
        """API endpoint to delete a paper note."""
        success = engine.db.delete_note(note_id) if engine else False
        if not success:
            return jsonify({"error": "failed to delete note"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/tags", methods=["GET"])
    def get_tags():
        """API endpoint to get all unique tags."""
        tags = engine.db.get_all_tags() if engine else []
        return jsonify(tags)

    @app.route("/api/papers/<path:arxiv_id>/tags", methods=["POST"])
    def add_paper_tag(arxiv_id):
        """API endpoint to add a tag to a paper."""
        data = request.get_json() or {}
        tag = data.get("tag", "").strip()
        if not tag:
            return jsonify({"error": "tag is required"}), 400

        success = engine.db.add_tag(arxiv_id, tag) if engine else False
        if not success:
            return jsonify({"error": "failed to add tag"}), 500
        return jsonify({"status": "ok", "tag": tag.lower()})

    @app.route("/api/papers/<path:arxiv_id>/tags/<tag>", methods=["DELETE"])
    def remove_paper_tag(arxiv_id, tag):
        """API endpoint to remove a tag from a paper."""
        success = engine.db.remove_tag(arxiv_id, tag) if engine else False
        if not success:
            return jsonify({"error": "failed to remove tag"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/collections", methods=["GET"])
    def get_collections():
        """API endpoint to get all collections."""
        colls = engine.db.get_collections() if engine else []
        return jsonify(colls)

    @app.route("/api/collections", methods=["POST"])
    def create_collection():
        """API endpoint to create a new collection."""
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        description = data.get("description", "").strip() or None
        if not name:
            return jsonify({"error": "name is required"}), 400

        coll_id = engine.db.create_collection(name, description) if engine else None
        if coll_id is None:
            return jsonify({"error": "failed to create collection (possibly duplicate name)"}), 500
        return jsonify({"status": "ok", "id": coll_id, "name": name})

    @app.route("/api/collections/<int:collection_id>", methods=["DELETE"])
    def delete_collection(collection_id):
        """API endpoint to delete a collection."""
        success = engine.db.delete_collection(collection_id) if engine else False
        if not success:
            return jsonify({"error": "failed to delete collection"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/collections/<int:collection_id>/papers", methods=["POST"])
    def add_paper_to_collection(collection_id):
        """API endpoint to add a paper to a collection."""
        data = request.get_json() or {}
        arxiv_id = data.get("arxiv_id")
        if not arxiv_id:
            return jsonify({"error": "arxiv_id is required"}), 400

        success = engine.db.add_paper_to_collection(collection_id, arxiv_id) if engine else False
        if not success:
            return jsonify({"error": "failed to add paper to collection"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/collections/<int:collection_id>/papers/<path:arxiv_id>", methods=["DELETE"])
    def remove_paper_from_collection(collection_id, arxiv_id):
        """API endpoint to remove a paper from a collection."""
        success = engine.db.remove_paper_from_collection(collection_id, arxiv_id) if engine else False
        if not success:
            return jsonify({"error": "failed to remove paper from collection"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/search", methods=["GET"])
    def search_api():
        """API endpoint to search papers."""
        query = request.args.get("q", "").strip()
        search_mode = request.args.get("mode", "fts")
        if not query:
            return jsonify([])

        category = request.args.get("category", "").strip() or None
        date_from = request.args.get("date_from", "").strip() or None
        date_to = request.args.get("date_to", "").strip() or None
        limit = request.args.get("limit", 50, type=int)

        if search_mode == "semantic":
            results = engine.semantic_search(query=query, limit=limit)
        else:
            results = engine.db.search_papers(
                query=query,
                category=category,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
            )
        return jsonify(results)

    @app.route("/api/fetch", methods=["POST"])
    def fetch_papers():
        """API endpoint to trigger paper fetching."""
        data = request.get_json() or {}
        max_results = data.get("max_results", 200)
        days_back = data.get("days_back", 2)
        with_summaries = data.get("with_summaries", False)

        from ..tasks import fetch_papers_task
        task = fetch_papers_task.delay(
            max_results=max_results,
            days_back=days_back,
            generate_summaries=with_summaries,
        )
        return jsonify({"status": "ok", "task_id": task.id})

    @app.route("/api/summarize", methods=["POST"])
    def summarize_papers():
        """API endpoint to launch summary generation separately."""
        data = request.get_json() or {}
        limit = data.get("limit", 20)
        only_missing = data.get("only_missing", False)

        from ..tasks import generate_missing_summaries_task
        task = generate_missing_summaries_task.delay(
            limit=limit,
            include_failed=not only_missing,
        )
        return jsonify({"status": "ok", "task_id": task.id})

    @app.route("/api/summarize-paper", methods=["POST"])
    def summarize_single_paper():
        """API endpoint to generate a summary for one paper."""
        data = request.get_json() or {}
        arxiv_id = data.get("arxiv_id")
        if not arxiv_id:
            return jsonify({"error": "arxiv_id is required"}), 400

        result = engine.generate_summary_for_paper(arxiv_id)
        if result.get("status") == "not_found":
            return jsonify(result), 404

        return jsonify(result)

    @app.route("/api/retrain", methods=["POST"])
    def retrain():
        """API endpoint to fully retrain the model."""
        data = request.get_json() or {}
        epochs = data.get("epochs", 20)

        from ..tasks import retrain_full_task
        task = retrain_full_task.delay(epochs=epochs)
        return jsonify({"status": "ok", "task_id": task.id})

    @app.route("/api/tasks/<task_id>", methods=["GET"])
    def get_task_status(task_id):
        """Get the progress and status of a background task."""
        status_info = engine.db.get_task_status(task_id)
        if not status_info:
            return jsonify({"error": "Task not found"}), 404
        return jsonify(status_info)

    @app.route("/api/stats")
    def stats():
        """API endpoint for system statistics."""
        return jsonify(engine.get_stats())

    @app.route("/api/config", methods=["GET"])
    def get_live_config():
        """API endpoint to get live configuration, stripping out any secrets."""
        import copy
        config_copy = copy.deepcopy(app.config.get("AI_PAPERS", {}))
        
        # Strip secrets
        if "email" in config_copy:
            if "smtp_password" in config_copy["email"]:
                config_copy["email"]["smtp_password"] = "********"
        if "llm" in config_copy and "providers" in config_copy["llm"]:
            for prov in config_copy["llm"]["providers"]:
                if "api_key" in config_copy["llm"]["providers"][prov]:
                    config_copy["llm"]["providers"][prov]["api_key"] = "********"
                    
        return jsonify(config_copy)

    @app.route("/api/logs", methods=["GET"])
    def get_logs():
        """API endpoint to get rolling memory logs (admin token authenticated)."""
        admin_token = os.environ.get("AURA_ADMIN_TOKEN")
        if admin_token:
            auth_header = request.headers.get("Authorization")
            token = None
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1]
            if not token:
                token = request.args.get("token")
            if token != admin_token:
                return jsonify({"error": "Unauthorized"}), 401

        limit = request.args.get("limit", 100, type=int)
        from ..logging_config import memory_log_handler
        raw_logs = memory_log_handler.get_logs()
        
        import json
        logs = []
        for line in raw_logs:
            try:
                logs.append(json.loads(line))
            except Exception:
                logs.append({"raw": line})
                
        return jsonify(logs[-limit:])

    @app.route("/health")
    def health():
        """Simple health check for load balancers and orchestrators."""
        return jsonify({"status": "ok"}), 200

    @app.route("/fetch")
    def fetch_page():
        """Page to trigger and monitor paper fetching."""
        stats = engine.get_stats()
        return render_template("fetch.html", stats=stats)

    @app.route("/settings")
    def settings():
        """Settings page showing model stats and config."""
        stats = engine.get_stats()
        config = app.config.get("AI_PAPERS", {})
        return render_template("settings.html", stats=stats, config=config)
