"""Flask web application for browsing and rating papers."""

import logging
import os

import yaml
from flask import Flask, jsonify, render_template, request

from ..recommender import RecommendationEngine

logger = logging.getLogger(__name__)

engine: RecommendationEngine = None


def create_app(config_path: str = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load config
    if config_path is None:
        config_path = os.environ.get("AI_PAPERS_CONFIG", "config.yaml")

    config = _load_config(config_path)
    app.config["AI_PAPERS"] = config

    # Initialize recommendation engine
    global engine
    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
    )

    # Register routes
    _register_routes(app)

    return app


def _load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    path = os.path.abspath(config_path)
    if os.path.exists(path):
        with open(path) as f:
            return yaml.safe_load(f) or {}
    logger.warning(f"Config file not found at {path}, using defaults")
    return {}


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
            paper_list = engine.get_recommendations(limit=per_page * page, unrated_only=True)
        elif filter_type == "liked":
            paper_list = engine.db.get_papers(limit=per_page, offset=(page - 1) * per_page, rated_only=True)
            # Add ratings
            for p in paper_list:
                p["rating"] = engine.db.get_latest_rating(p["arxiv_id"])
                p["score"] = p.get("score", 0)
            paper_list = [p for p in paper_list if p.get("rating") == 1]
        elif filter_type == "disliked":
            paper_list = engine.db.get_papers(limit=per_page, offset=(page - 1) * per_page, rated_only=True)
            for p in paper_list:
                p["rating"] = engine.db.get_latest_rating(p["arxiv_id"])
                p["score"] = p.get("score", 0)
            paper_list = [p for p in paper_list if p.get("rating") == 0]
        else:
            paper_list = engine.get_recommendations(limit=per_page * page, unrated_only=False)

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

        count = engine.fetch_new_papers(
            max_results=max_results,
            days_back=days_back,
            generate_summaries=with_summaries,
        )
        return jsonify({"status": "ok", "new_papers": count})

    @app.route("/api/summarize", methods=["POST"])
    def summarize_papers():
        """API endpoint to launch summary generation separately."""
        data = request.get_json() or {}
        limit = data.get("limit", 20)
        only_missing = data.get("only_missing", False)

        result = engine.generate_missing_summaries(
            limit=limit,
            include_failed=not only_missing,
        )
        return jsonify(result)

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

        result = engine.retrain_full(epochs=epochs)
        return jsonify(result)

    @app.route("/api/stats")
    def stats():
        """API endpoint for system statistics."""
        return jsonify(engine.get_stats())

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
