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

    @app.route("/")
    def index():
        """Dashboard / home page."""
        stats = engine.get_stats()
        return render_template("index.html", stats=stats)

    @app.route("/papers")
    def papers():
        """Browse recommended papers."""
        filter_type = request.args.get("filter", "unrated")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 30))

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

        # Add current rating info
        for p in paper_list:
            if "rating" not in p:
                p["rating"] = engine.db.get_latest_rating(p["arxiv_id"])

        return render_template(
            "papers.html",
            papers=paper_list,
            filter_type=filter_type,
            page=page,
            per_page=per_page,
        )

    @app.route("/api/rate", methods=["POST"])
    def rate_paper():
        """API endpoint to rate a paper (thumbs up/down)."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400

        arxiv_id = data.get("arxiv_id")
        rating = data.get("rating")

        if not arxiv_id or rating is None:
            return jsonify({"error": "arxiv_id and rating are required"}), 400

        if rating not in (0, 1):
            return jsonify({"error": "rating must be 0 or 1"}), 400

        result = engine.rate_paper(arxiv_id, rating)
        return jsonify(result)

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
