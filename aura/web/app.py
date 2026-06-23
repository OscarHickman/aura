"""Flask web application for browsing and rating papers."""

import logging
import os
import secrets
import uuid

from flask import Flask, jsonify, redirect, render_template, request, g, url_for, flash
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash

from ..recommender import RecommendationEngine
from ..config import get_validated_config
from ..logging_config import setup_logging

import html
import re
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_talisman import Talisman

logger = logging.getLogger(__name__)

engine: RecommendationEngine | None = None
login_manager: LoginManager | None = None

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100 per minute"],
    storage_uri="memory://",
)
csrf = CSRFProtect()


def sanitise_input(text: str) -> str:
    """Escapes HTML entities to prevent XSS."""
    return html.escape(text.strip()) if text else ""


def sanitise_tag(tag: str) -> str:
    """Sanitise tag to alphanumeric, underscores, and hyphens only."""
    if not tag:
        return ""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", tag.strip())
    return cleaned.lower()


class User(UserMixin):
    """Flask-Login User adapter backed by the SQLite users table."""

    def __init__(self, user_dict: dict):
        self.id: int = user_dict["id"]
        self.email: str = user_dict["email"]
        self.is_admin_flag: bool = bool(user_dict.get("is_admin", 0))
        self._is_active: bool = bool(user_dict.get("is_active", 1))

    @property
    def is_active(self) -> bool:  # type: ignore[override]
        return self._is_active

    @property
    def is_admin(self) -> bool:
        return self.is_admin_flag


def _get_current_user_id() -> int:
    """Return the current user's DB id, defaulting to 1 for unauthenticated requests."""
    if current_user and current_user.is_authenticated:
        return int(current_user.id)
    return 1


def _paper_to_bibtex(paper: dict) -> str:
    """Format a paper dictionary into a BibTeX string."""
    cite_key = paper.get("arxiv_id", "").replace("/", "_")
    title = paper.get("title", "").replace("\n", " ").strip()
    authors = " and ".join(paper.get("authors", []))
    
    pub_date = paper.get("published", "")
    year = "2026"
    if pub_date:
        try:
            year = pub_date[:4]
        except Exception:
            pass
            
    eprint = paper.get("arxiv_id", "")
    categories = paper.get("categories", [])
    primary_class = categories[0] if categories else ""
    
    lines = [
        f"@article{{{cite_key},",
        f"  title={{{title}}},",
        f"  author={{{authors}}},",
        f"  journal={{arXiv preprint arXiv:{eprint}}},",
        f"  year={{{year}}},",
        f"  eprint={{{eprint}}},",
        "  archivePrefix={arXiv},"
    ]
    if primary_class:
        lines.append(f"  primaryClass={{{primary_class}}},")
    if paper.get("url"):
        lines.append(f"  url={{{paper['url']}}},")
        
    lines[-1] = lines[-1].rstrip(",")
    lines.append("}")
    return "\n".join(lines)


def _paper_to_ris(paper: dict) -> str:
    """Format a paper dictionary into an RIS string."""
    lines = []
    lines.append("TY  - JOUR")
    
    title = paper.get("title", "").replace("\n", " ").strip()
    lines.append(f"TI  - {title}")
    
    for author in paper.get("authors", []):
        lines.append(f"AU  - {author}")
        
    eprint = paper.get("arxiv_id", "")
    lines.append(f"JO  - arXiv preprint arXiv:{eprint}")
    
    pub_date = paper.get("published", "")
    year = ""
    if pub_date:
        try:
            year = pub_date[:4]
        except Exception:
            pass
    if year:
        lines.append(f"PY  - {year}")
        
    if paper.get("url"):
        lines.append(f"UR  - {paper['url']}")
        
    abstract = paper.get("abstract", "").replace("\n", " ").strip()
    if abstract:
        lines.append(f"AB  - {abstract}")
        
    categories = paper.get("categories", [])
    for cat in categories:
        lines.append(f"KW  - {cat}")
        
    lines.append("ER  - ")
    return "\r\n".join(lines)


def create_app(config_path: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    setup_logging(level=logging.INFO, structured=True)

    app = Flask(__name__)

    # Secret key required by Flask-Login session cookies
    app.secret_key = os.environ.get("AURA_SECRET_KEY") or secrets.token_hex(32)

    # Disable CSRF protection dynamically during testing
    @app.before_request
    def check_testing_csrf():
        if app.testing or app.config.get("TESTING"):
            app.config["WTF_CSRF_ENABLED"] = False

    # Load config
    if config_path is None:
        config_path = os.environ.get("AI_PAPERS_CONFIG", "config.yaml")

    try:
        config = get_validated_config(config_path)
    except Exception as e:
        logger.error(f"Failed to start AURA: {e}")
        raise SystemExit(f"Configuration error: {e}")

    app.config["AI_PAPERS"] = config

    # Initialize Limiter
    limiter.init_app(app)

    # Initialize CSRF Protection
    csrf.init_app(app)

    # Initialize Talisman (Security Headers)
    csp = {
        "default-src": "'self'",
        "style-src": [
            "'self'",
            "'unsafe-inline'",
            "https://cdn.jsdelivr.net",
        ],
        "script-src": [
            "'self'",
            "'unsafe-inline'",
            "https://cdn.jsdelivr.net",
        ],
        "font-src": [
            "'self'",
            "https://cdn.jsdelivr.net",
        ],
        "img-src": [
            "'self'",
            "data:",
            "https:",
        ],
        "connect-src": "'self'",
    }
    Talisman(
        app,
        content_security_policy=csp,
        force_https=False,
        session_cookie_secure=False,
    )

    # Initialize recommendation engine
    global engine
    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        rss_urls=config.get("rss_feeds", []),
        sources_config=config.get("sources", {}),
    )

    # Flask-Login setup
    global login_manager
    login_manager = LoginManager(app)
    login_manager.login_view = "login"  # type: ignore[assignment]
    login_manager.login_message = "Please log in to access AURA."

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        if engine is None:
            return None
        row = engine.db.get_user_by_id(int(user_id))
        return User(row) if row else None

    @login_manager.request_loader
    def load_user_from_request(req) -> User | None:
        """Authenticate via Bearer token for API requests."""
        if engine is None:
            return None
        auth_header = req.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]
            row = engine.db.get_user_by_token(token)
            if row:
                return User(row)
        return None

    # Request ID tracking
    @app.before_request
    def before_request() -> None:
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
    _register_auth_routes(app)
    _register_routes(app)

    return app


def _register_auth_routes(app: Flask) -> None:
    """Register authentication routes."""

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            remember = bool(request.form.get("remember"))
            user_row = engine.db.get_user_by_email(email) if engine else None
            if user_row and check_password_hash(user_row["password_hash"], password):
                if not user_row.get("is_active", 1):
                    flash("Your account has been suspended.", "danger")
                    return render_template("login.html")
                user = User(user_row)
                login_user(user, remember=remember)
                next_page = request.args.get("next")
                return redirect(next_page or url_for("index"))
            flash("Invalid email or password.", "danger")
        return render_template("login.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            if not email or not password:
                flash("Email and password are required.", "danger")
                return render_template("register.html")
            if password != confirm:
                flash("Passwords do not match.", "danger")
                return render_template("register.html")
            if len(password) < 8:
                flash("Password must be at least 8 characters.", "danger")
                return render_template("register.html")
            if engine and engine.db.get_user_by_email(email):
                flash("An account with that email already exists.", "danger")
                return render_template("register.html")
            # First registered user becomes admin
            is_admin = engine is not None and engine.db.count_users() == 0
            pw_hash = generate_password_hash(password)
            user_id = engine.db.create_user(email, pw_hash, is_admin=is_admin) if engine else None
            if not user_id:
                flash("Registration failed. Please try again.", "danger")
                return render_template("register.html")
            user_row = engine.db.get_user_by_id(user_id) if engine else None
            if user_row:
                login_user(User(user_row))
            return redirect(url_for("index"))
        return render_template("register.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))


def _register_routes(app: Flask) -> None:
    """Register all route handlers."""

    @app.before_request
    def check_onboarding():
        """Redirect to onboarding if the user has rated fewer than 5 papers."""
        open_endpoints = {"login", "register", "logout", "static", "health", "metrics",
                          "public_collection", "browse_public_collections"}
        if request.endpoint in open_endpoints or request.path.startswith("/api/"):
            return None
        if not current_user.is_authenticated:
            return None
        stats = engine.get_stats(user_id=_get_current_user_id())
        if stats["database"]["total_rated"] < 5:
            if request.path != "/onboarding":
                return redirect("/onboarding")
        return None

    @app.route("/")
    @login_required
    def index():
        stats = engine.get_stats(user_id=_get_current_user_id())
        return render_template("index.html", stats=stats)

    @app.route("/topics")
    @login_required
    def topics():
        clusters = engine.discover_topics() if engine else []
        return render_template("topics.html", clusters=clusters)

    @app.route("/onboarding")
    @login_required
    def onboarding():
        uid = _get_current_user_id()
        stats = engine.get_stats(user_id=uid)
        total_rated = stats["database"]["total_rated"]
        if total_rated >= 5:
            return redirect("/")
        papers = engine.get_diverse_papers(limit=20)
        return render_template("onboarding.html", papers=papers, total_rated=total_rated)

    @app.route("/papers")
    @login_required
    def papers():
        uid = _get_current_user_id()
        query = request.args.get("q", "").strip()
        search_mode = request.args.get("mode", "fts")
        category = request.args.get("category", "").strip() or None
        date_from = request.args.get("date_from", "").strip() or None
        date_to = request.args.get("date_to", "").strip() or None
        has_code = request.args.get("has_code", type=int)
        has_data = request.args.get("has_data", type=int)
        tag = request.args.get("tag", "").strip() or None
        collection_id = request.args.get("collection_id", type=int)
        filter_type = request.args.get("filter", "unrated")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 30))

        if query:
            if search_mode == "semantic":
                paper_list = engine.semantic_search(query=query, limit=200)
            else:
                paper_list = engine.db.search_papers(
                    query=query,
                    category=category,
                    date_from=date_from,
                    date_to=date_to,
                    has_code=has_code,
                    has_data=has_data,
                    limit=200,
                )
            filter_type = "search"
        elif tag:
            paper_list = engine.db.get_papers_by_tag(tag, user_id=uid, limit=200)
            filter_type = f"tag: {tag}"
        elif collection_id:
            paper_list = engine.db.get_collection_papers(collection_id, limit=200)
            coll = engine.db.get_collection(collection_id)
            coll_name = coll["name"] if coll else "Collection"
            filter_type = f"collection: {coll_name}"
        else:
            if filter_type == "unrated":
                paper_list = engine.get_recommendations(
                    limit=per_page * page, unrated_only=True, user_id=uid
                )
            elif filter_type == "liked":
                paper_list = engine.db.get_papers(
                    limit=per_page, offset=(page - 1) * per_page, rated_only=True
                )
                for p in paper_list:
                    p["rating"] = engine.db.get_latest_rating(p["arxiv_id"], user_id=uid)
                    p["score"] = p.get("score", 0)
                paper_list = [p for p in paper_list if p.get("rating") == 1]
            elif filter_type == "disliked":
                paper_list = engine.db.get_papers(
                    limit=per_page, offset=(page - 1) * per_page, rated_only=True
                )
                for p in paper_list:
                    p["rating"] = engine.db.get_latest_rating(p["arxiv_id"], user_id=uid)
                    p["score"] = p.get("score", 0)
                paper_list = [p for p in paper_list if p.get("rating") == 0]
            else:
                paper_list = engine.get_recommendations(
                    limit=per_page * page, unrated_only=False, user_id=uid
                )

        start = (page - 1) * per_page
        paper_list = paper_list[start : start + per_page]

        for p in paper_list:
            if "rating" not in p:
                p["rating"] = engine.db.get_latest_rating(p["arxiv_id"], user_id=uid)
            p["tags"] = engine.db.get_paper_tags(p["arxiv_id"], user_id=uid)
            p["collections"] = engine.db.get_paper_collections(p["arxiv_id"], user_id=uid)
            p["in_reading_list"] = engine.db.is_in_reading_list(p["arxiv_id"], user_id=uid)

        categories = app.config.get("AI_PAPERS", {}).get("categories", [])
        collections = engine.db.get_collections(user_id=uid) if engine else []
        all_tags = engine.db.get_all_tags(user_id=uid) if engine else []
        surveys = []
        if engine:
            res = engine.db.get_surveys()
            from unittest.mock import Mock
            if isinstance(res, list) and not isinstance(res, Mock):
                surveys = res

        return render_template(
            "papers.html",
            papers=paper_list,
            filter_type=filter_type,
            page=page,
            per_page=per_page,
            categories=categories,
            collections=collections,
            all_tags=all_tags,
            surveys=surveys,
            q=query,
            category=category,
            date_from=date_from,
            date_to=date_to,
            has_code=has_code,
            has_data=has_data,
            selected_tag=tag,
            selected_collection_id=collection_id,
        )

    @app.route("/papers/<path:arxiv_id>")
    @login_required
    def paper_detail(arxiv_id):
        uid = _get_current_user_id()
        paper = engine.db.get_paper(arxiv_id) if engine else None
        if not paper:
            return render_template("404.html"), 404

        paper["rating"] = engine.db.get_latest_rating(arxiv_id, user_id=uid) if engine else None
        paper["tags"] = engine.db.get_paper_tags(arxiv_id, user_id=uid) if engine else []
        paper["collections"] = engine.db.get_paper_collections(arxiv_id, user_id=uid) if engine else []
        paper["notes"] = engine.db.get_paper_notes(arxiv_id, user_id=uid) if engine else []
        paper["in_reading_list"] = engine.db.is_in_reading_list(arxiv_id, user_id=uid) if engine else False

        ratings_history = engine.db.get_ratings_history(arxiv_id, user_id=uid) if engine else []
        similar_papers = engine.get_similar_papers(arxiv_id, limit=5) if engine else []
        same_author_papers = engine.db.get_papers_by_authors(
            paper["authors"], exclude_arxiv_id=arxiv_id, limit=5
        ) if engine else []
        collections = engine.db.get_collections(user_id=uid) if engine else []
        citing_papers, cited_papers = ([], [])
        if engine:
            res = engine.get_or_fetch_citations(arxiv_id)
            if isinstance(res, tuple) and len(res) == 2:
                citing_papers, cited_papers = res

        ads_url = None
        if not arxiv_id.startswith("s2:") and not arxiv_id.startswith("biorxiv-"):
            ads_url = f"https://ui.adsabs.harvard.edu/search/q=arxiv:{arxiv_id}"

        ar5iv_url = None
        if not arxiv_id.startswith("s2:") and not arxiv_id.startswith("biorxiv-"):
            ar5iv_url = f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}"

        from flask import make_response
        response = make_response(
            render_template(
                "paper_detail.html",
                paper=paper,
                ratings_history=ratings_history,
                similar_papers=similar_papers,
                same_author_papers=same_author_papers,
                collections=collections,
                ar5iv_url=ar5iv_url,
                ads_url=ads_url,
                citing_papers=citing_papers,
                cited_papers=cited_papers,
            )
        )
        bibtex_url = url_for("export_paper_bibtex", arxiv_id=arxiv_id)
        ris_url = url_for("export_paper_ris", arxiv_id=arxiv_id)
        response.headers["Link"] = (
            f'<{bibtex_url}>; rel="alternate"; type="application/x-bibtex", '
            f'<{ris_url}>; rel="alternate"; type="application/x-research-info-systems"'
        )
        return response

    @app.route("/api/rate", methods=["POST"])
    @login_required
    def rate_paper():
        uid = _get_current_user_id()
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        arxiv_id = data.get("arxiv_id")
        rating = data.get("rating")
        if not arxiv_id or rating is None:
            return jsonify({"error": "arxiv_id and rating are required"}), 400
        if rating not in (-1, 0, 1, 2, 3, 4, 5):
            return jsonify({"error": "rating must be -1 (skip) or 1-5 (stars)"}), 400
        result = engine.rate_paper(arxiv_id, rating, user_id=uid)
        return jsonify(result)

    @app.route("/reading-list")
    @login_required
    def reading_list():
        uid = _get_current_user_id()
        filter_type = request.args.get("filter", "unread")
        if filter_type == "read":
            reading_papers = engine.db.get_reading_list(user_id=uid, only_read=True)
        else:
            reading_papers = engine.db.get_reading_list(user_id=uid, only_unread=True)
        for p in reading_papers:
            p["rating"] = engine.db.get_latest_rating(p["arxiv_id"], user_id=uid)
            p["tags"] = engine.db.get_paper_tags(p["arxiv_id"], user_id=uid)
            p["collections"] = engine.db.get_paper_collections(p["arxiv_id"], user_id=uid)
            p["in_reading_list"] = True
        return render_template("reading_list.html", papers=reading_papers, filter_type=filter_type)

    @app.route("/api/reading-list", methods=["POST"])
    @login_required
    def add_to_reading_list():
        uid = _get_current_user_id()
        data = request.get_json() or {}
        arxiv_id = data.get("arxiv_id")
        if not arxiv_id:
            return jsonify({"error": "arxiv_id is required"}), 400
        success = engine.db.add_to_reading_list(arxiv_id, user_id=uid) if engine else False
        if not success:
            return jsonify({"error": "failed to add to reading list"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/reading-list/<path:arxiv_id>", methods=["DELETE"])
    @login_required
    def remove_from_reading_list(arxiv_id):
        uid = _get_current_user_id()
        success = engine.db.remove_from_reading_list(arxiv_id, user_id=uid) if engine else False
        if not success:
            return jsonify({"error": "failed to remove from reading list"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/reading-list/<path:arxiv_id>/read", methods=["PUT"])
    @login_required
    def mark_paper_as_read(arxiv_id):
        uid = _get_current_user_id()
        success = engine.db.mark_as_read(arxiv_id, user_id=uid) if engine else False
        if not success:
            return jsonify({"error": "failed to mark as read"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/explain/<path:arxiv_id>", methods=["GET"])
    @login_required
    def explain_paper(arxiv_id):
        paper = engine.db.get_paper(arxiv_id) if engine else None
        if not paper:
            return jsonify({"error": "Paper not found"}), 404
        similar_liked = engine.get_similar_liked_papers(arxiv_id, limit=3) if engine else []
        return jsonify({"arxiv_id": arxiv_id, "similar_liked": similar_liked})

    @app.route("/api/papers/<path:arxiv_id>/deep-summary", methods=["GET"])
    @login_required
    def get_paper_deep_summary(arxiv_id):
        if not engine:
            return jsonify({"error": "Engine not initialized"}), 500
        mode = request.args.get("mode", "grad_student")
        if mode not in ["grad_student", "expert"]:
            return jsonify({"error": f"Invalid mode: {mode}"}), 400
        
        summary = engine.get_or_generate_full_summary(arxiv_id, mode=mode)
        if summary.startswith("Error:"):
            return jsonify({"error": summary}), 500
            
        return jsonify({
            "arxiv_id": arxiv_id,
            "mode": mode,
            "summary": summary
        })

    @app.route("/api/papers/<path:arxiv_id>/ask", methods=["GET", "POST"])
    @login_required
    def ask_paper_question(arxiv_id):
        if not engine:
            return jsonify({"error": "Engine not initialized"}), 500
            
        if request.method == "POST":
            data = request.get_json() or {}
            question = data.get("question", "").strip()
        else:
            question = request.args.get("question", "").strip()
            
        if not question:
            return jsonify({"error": "Question is required."}), 400
            
        from flask import Response
        import json
        def generate():
            try:
                for chunk in engine.ask_paper_question(arxiv_id, question):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                
        return Response(generate(), mimetype="text/event-stream")

    @app.route("/api/papers/<path:arxiv_id>/notes", methods=["GET"])
    @login_required
    def get_paper_notes(arxiv_id):
        uid = _get_current_user_id()
        notes = engine.db.get_paper_notes(arxiv_id, user_id=uid) if engine else []
        return jsonify(notes)

    @app.route("/api/papers/<path:arxiv_id>/notes", methods=["POST"])
    @login_required
    def add_paper_note(arxiv_id):
        uid = _get_current_user_id()
        data = request.get_json() or {}
        content = sanitise_input(data.get("content", ""))
        if not content:
            return jsonify({"error": "content is required"}), 400
        note_id = engine.db.add_note(arxiv_id, content, user_id=uid) if engine else None
        if note_id is None:
            return jsonify({"error": "failed to add note"}), 500
        return jsonify({"status": "ok", "id": note_id})

    @app.route("/api/notes/<int:note_id>", methods=["PUT"])
    @login_required
    def update_paper_note(note_id):
        uid = _get_current_user_id()
        data = request.get_json() or {}
        content = sanitise_input(data.get("content", ""))
        if not content:
            return jsonify({"error": "content is required"}), 400
        success = engine.db.update_note(note_id, content, user_id=uid) if engine else False
        if not success:
            return jsonify({"error": "failed to update note"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/notes/<int:note_id>", methods=["DELETE"])
    @login_required
    def delete_paper_note(note_id):
        uid = _get_current_user_id()
        success = engine.db.delete_note(note_id, user_id=uid) if engine else False
        if not success:
            return jsonify({"error": "failed to delete note"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/tags", methods=["GET"])
    @login_required
    def get_tags():
        uid = _get_current_user_id()
        tags = engine.db.get_all_tags(user_id=uid) if engine else []
        return jsonify(tags)

    @app.route("/api/papers/<path:arxiv_id>/tags", methods=["POST"])
    @login_required
    def add_paper_tag(arxiv_id):
        uid = _get_current_user_id()
        data = request.get_json() or {}
        tag = sanitise_tag(data.get("tag", ""))
        if not tag:
            return jsonify({"error": "tag is required"}), 400
        success = engine.db.add_tag(arxiv_id, tag, user_id=uid) if engine else False
        if not success:
            return jsonify({"error": "failed to add tag"}), 500
        return jsonify({"status": "ok", "tag": tag})

    @app.route("/api/papers/<path:arxiv_id>/tags/<tag>", methods=["DELETE"])
    @login_required
    def remove_paper_tag(arxiv_id, tag):
        uid = _get_current_user_id()
        success = engine.db.remove_tag(arxiv_id, tag, user_id=uid) if engine else False
        if not success:
            return jsonify({"error": "failed to remove tag"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/collections", methods=["GET"])
    @login_required
    def get_collections():
        uid = _get_current_user_id()
        colls = engine.db.get_collections(user_id=uid) if engine else []
        return jsonify(colls)

    @app.route("/api/collections", methods=["POST"])
    @login_required
    def create_collection():
        uid = _get_current_user_id()
        data = request.get_json() or {}
        name = sanitise_input(data.get("name", ""))
        raw_desc = data.get("description", "")
        description = sanitise_input(raw_desc) if raw_desc else None
        if not name:
            return jsonify({"error": "name is required"}), 400
        coll_id = engine.db.create_collection(name, user_id=uid, description=description) if engine else None
        if coll_id is None:
            return jsonify({"error": "failed to create collection (possibly duplicate name)"}), 500
        return jsonify({"status": "ok", "id": coll_id, "name": name})

    @app.route("/api/collections/<int:collection_id>", methods=["DELETE"])
    @login_required
    def delete_collection(collection_id):
        uid = _get_current_user_id()
        success = engine.db.delete_collection(collection_id, user_id=uid) if engine else False
        if not success:
            return jsonify({"error": "failed to delete collection"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/collections/<int:collection_id>/papers", methods=["POST"])
    @login_required
    def add_paper_to_collection(collection_id):
        uid = _get_current_user_id()
        data = request.get_json() or {}
        arxiv_id = data.get("arxiv_id")
        if not arxiv_id:
            return jsonify({"error": "arxiv_id is required"}), 400
        success = engine.db.add_paper_to_collection(collection_id, arxiv_id, user_id=uid) if engine else False
        if not success:
            return jsonify({"error": "failed to add paper to collection"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/collections/<int:collection_id>/papers/<path:arxiv_id>", methods=["DELETE"])
    @login_required
    def remove_paper_from_collection(collection_id, arxiv_id):
        uid = _get_current_user_id()
        success = engine.db.remove_paper_from_collection(collection_id, arxiv_id, user_id=uid) if engine else False
        if not success:
            return jsonify({"error": "failed to remove paper from collection"}), 500
        return jsonify({"status": "ok"})

    @app.route("/api/search", methods=["GET"])
    @login_required
    def search_api():
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
                query=query, category=category, date_from=date_from, date_to=date_to, limit=limit,
            )
        return jsonify(results)

    @app.route("/api/fetch", methods=["POST"])
    @login_required
    def fetch_papers():
        data = request.get_json() or {}
        max_results = data.get("max_results", 200)
        days_back = data.get("days_back", 2)
        with_summaries = data.get("with_summaries", False)
        from ..tasks import fetch_papers_task
        task = fetch_papers_task.delay(
            max_results=max_results, days_back=days_back, generate_summaries=with_summaries,
        )
        return jsonify({"status": "ok", "task_id": task.id})

    @app.route("/api/summarize", methods=["POST"])
    @login_required
    def summarize_papers():
        data = request.get_json() or {}
        limit = data.get("limit", 20)
        only_missing = data.get("only_missing", False)
        from ..tasks import generate_missing_summaries_task
        task = generate_missing_summaries_task.delay(limit=limit, include_failed=not only_missing)
        return jsonify({"status": "ok", "task_id": task.id})

    @app.route("/api/summarize-paper", methods=["POST"])
    @login_required
    def summarize_single_paper():
        data = request.get_json() or {}
        arxiv_id = data.get("arxiv_id")
        if not arxiv_id:
            return jsonify({"error": "arxiv_id is required"}), 400
        result = engine.generate_summary_for_paper(arxiv_id)
        if result.get("status") == "not_found":
            return jsonify(result), 404
        return jsonify(result)

    @app.route("/api/retrain", methods=["POST"])
    @login_required
    def retrain():
        uid = _get_current_user_id()
        data = request.get_json() or {}
        epochs = data.get("epochs", 20)
        from ..tasks import retrain_full_task
        task = retrain_full_task.delay(epochs=epochs, user_id=uid)
        return jsonify({"status": "ok", "task_id": task.id})

    @app.route("/api/tasks/<task_id>", methods=["GET"])
    @login_required
    def get_task_status(task_id):
        status_info = engine.db.get_task_status(task_id)
        if not status_info:
            return jsonify({"error": "Task not found"}), 404
        return jsonify(status_info)

    @app.route("/api/docs")
    @login_required
    def api_docs():
        """Serve interactive Swagger UI documentation for AURA API."""
        return render_template("swagger_ui.html")

    @app.route("/api/stats")
    @login_required
    def stats():
        uid = _get_current_user_id()
        return jsonify(engine.get_stats(user_id=uid))

    @app.route("/api/config", methods=["GET"])
    @login_required
    def get_live_config():
        import copy
        config_copy = copy.deepcopy(app.config.get("AI_PAPERS", {}))
        if "email" in config_copy:
            if "smtp_password" in config_copy["email"]:
                config_copy["email"]["smtp_password"] = "********"
        if "llm" in config_copy and "providers" in config_copy["llm"]:
            for prov in config_copy["llm"]["providers"]:
                if "api_key" in config_copy["llm"]["providers"][prov]:
                    config_copy["llm"]["providers"][prov]["api_key"] = "********"
        return jsonify(config_copy)

    @app.route("/api/logs", methods=["GET"])
    @login_required
    def get_logs():
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

    # ------------------------------------------------------------------
    # API Tokens (Phase 5.2)
    # ------------------------------------------------------------------

    @app.route("/api/tokens", methods=["GET"])
    @login_required
    def list_tokens():
        uid = _get_current_user_id()
        tokens = engine.db.get_user_tokens(uid) if engine else []
        return jsonify(tokens)

    @app.route("/api/tokens", methods=["POST"])
    @login_required
    def create_token():
        uid = _get_current_user_id()
        data = request.get_json() or {}
        name = data.get("name", "").strip() or "Unnamed token"
        scope = data.get("scope", "read")
        if scope not in ("read", "write", "admin"):
            return jsonify({"error": "scope must be read, write, or admin"}), 400
        token = engine.db.create_api_token(uid, name, scope=scope) if engine else None
        if not token:
            return jsonify({"error": "failed to create token"}), 500
        return jsonify({"status": "ok", "token": token, "name": name, "scope": scope})

    @app.route("/api/tokens/<int:token_id>", methods=["DELETE"])
    @login_required
    def revoke_token(token_id):
        uid = _get_current_user_id()
        success = engine.db.revoke_api_token(token_id, uid) if engine else False
        if not success:
            return jsonify({"error": "failed to revoke token"}), 500
        return jsonify({"status": "ok"})

    # ------------------------------------------------------------------
    # Admin Panel (Phase 5.3)
    # ------------------------------------------------------------------

    @app.route("/admin")
    @login_required
    def admin_panel():
        if not current_user.is_admin:
            return render_template("403.html"), 403
        users = engine.db.get_all_users() if engine else []
        fetch_log = engine.db.get_fetch_log(limit=10) if engine else []
        stats_data = engine.get_stats(user_id=_get_current_user_id()) if engine else {}
        groups = engine.db.get_all_groups() if engine else []
        return render_template("admin.html", users=users, fetch_log=fetch_log, stats=stats_data, groups=groups)

    @app.route("/api/admin/users/<int:user_id>/suspend", methods=["POST"])
    @login_required
    def admin_suspend_user(user_id):
        if not current_user.is_admin:
            return jsonify({"error": "Forbidden"}), 403
        if user_id == current_user.id:
            return jsonify({"error": "Cannot suspend yourself"}), 400
        success = engine.db.update_user(user_id, is_active=False) if engine else False
        return jsonify({"status": "ok" if success else "error"})

    @app.route("/api/admin/users/<int:user_id>/activate", methods=["POST"])
    @login_required
    def admin_activate_user(user_id):
        if not current_user.is_admin:
            return jsonify({"error": "Forbidden"}), 403
        success = engine.db.update_user(user_id, is_active=True) if engine else False
        return jsonify({"status": "ok" if success else "error"})

    @app.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
    @login_required
    def admin_delete_user(user_id):
        if not current_user.is_admin:
            return jsonify({"error": "Forbidden"}), 403
        if user_id == current_user.id:
            return jsonify({"error": "Cannot delete yourself"}), 400
        success = engine.db.delete_user(user_id) if engine else False
        return jsonify({"status": "ok" if success else "error"})

    @app.route("/api/admin/users/<int:user_id>/reset-password", methods=["POST"])
    @login_required
    def admin_reset_user_password(user_id):
        if not current_user.is_admin:
            return jsonify({"error": "Forbidden"}), 403
        data = request.get_json() or {}
        password = data.get("password", "").strip()
        if not password or len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400
        pw_hash = generate_password_hash(password)
        success = engine.db.update_user(user_id, password_hash=pw_hash) if engine else False
        return jsonify({"status": "ok" if success else "error"})

    @app.route("/api/admin/fetch", methods=["POST"])
    @login_required
    def admin_trigger_fetch():
        if not current_user.is_admin:
            return jsonify({"error": "Forbidden"}), 403
        from ..tasks import fetch_papers_task
        task = fetch_papers_task.delay(max_results=200, days_back=2, generate_summaries=False)
        return jsonify({"status": "ok", "task_id": task.id})

    @app.route("/api/admin/summarize", methods=["POST"])
    @login_required
    def admin_trigger_summarize():
        if not current_user.is_admin:
            return jsonify({"error": "Forbidden"}), 403
        from ..tasks import generate_missing_summaries_task
        task = generate_missing_summaries_task.delay(limit=50, include_failed=True)
        return jsonify({"status": "ok", "task_id": task.id})

    @app.route("/api/admin/retrain", methods=["POST"])
    @login_required
    def admin_trigger_retrain():
        if not current_user.is_admin:
            return jsonify({"error": "Forbidden"}), 403
        from ..tasks import retrain_full_task
        task = retrain_full_task.delay(epochs=20, user_id=1)
        return jsonify({"status": "ok", "task_id": task.id})

    # ------------------------------------------------------------------
    # Collections sharing (Phase 6.2)
    # ------------------------------------------------------------------

    @app.route("/collections")
    @login_required
    def browse_public_collections():
        """Browse all public collections."""
        public = engine.db.get_public_collections() if engine else []
        return render_template("public_collections.html", collections=public)

    @app.route("/collections/<slug>")
    def public_collection(slug):
        """Public shareable collection page (no login required)."""
        coll = engine.db.get_collection_by_slug(slug) if engine else None
        if not coll:
            return render_template("404.html"), 404
        collection_papers = engine.db.get_collection_papers(coll["id"]) if engine else []
        return render_template("public_collection.html", collection=coll, papers=collection_papers)

    # ------------------------------------------------------------------
    # Weekly Research Briefs (Phase 9.5)
    # ------------------------------------------------------------------

    @app.route("/briefs")
    @login_required
    def briefs_list():
        """List all generated briefs."""
        briefs = engine.db.get_all_briefs() if engine else []
        return render_template("briefs_list.html", briefs=briefs)

    @app.route("/briefs/<date>")
    @login_required
    def view_brief(date):
        """View a specific weekly brief, generating it if it doesn't exist."""
        from datetime import datetime
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            return "Invalid date format. Use YYYY-MM-DD.", 400
            
        brief = engine.db.get_brief(date) if engine else None
        if not brief:
            from aura.briefs import generate_weekly_brief_content
            content = generate_weekly_brief_content(engine, date) if engine else ""
            if engine:
                engine.db.add_brief(date, content)
            brief = {
                "date": date,
                "content": content,
                "created_at": datetime.utcnow().isoformat()
            }
        return render_template("brief_detail.html", brief=brief)

    @app.route("/api/briefs/generate", methods=["POST"])
    @login_required
    def generate_brief():
        """Trigger generation of a new brief for today."""
        from datetime import date
        today_str = date.today().isoformat()
        from aura.briefs import generate_weekly_brief_content
        content = generate_weekly_brief_content(engine, today_str) if engine else ""
        if engine:
            engine.db.add_brief(today_str, content)
        return jsonify({"status": "success", "date": today_str})

    @app.route("/api/collections/<int:collection_id>/share", methods=["POST"])
    @login_required
    def toggle_collection_share(collection_id):
        uid = _get_current_user_id()
        data = request.get_json() or {}
        is_public = bool(data.get("is_public", False))
        success = engine.db.update_collection(collection_id, user_id=uid, is_public=is_public) if engine else False
        if not success:
            return jsonify({"error": "failed to update collection"}), 500
        coll = engine.db.get_collection(collection_id)
        return jsonify({"status": "ok", "slug": coll.get("slug") if coll else None})

    @app.route("/api/collections/<int:collection_id>/fork", methods=["POST"])
    @login_required
    def fork_collection(collection_id):
        uid = _get_current_user_id()
        data = request.get_json() or {}
        new_name = data.get("name")
        new_id = engine.db.fork_collection(collection_id, uid, new_name=new_name) if engine else None
        if new_id is None:
            return jsonify({"error": "failed to fork collection (not public or duplicate name)"}), 500
        return jsonify({"status": "ok", "id": new_id})

    # ------------------------------------------------------------------
    # Groups (Phase 6.3)
    # ------------------------------------------------------------------

    @app.route("/groups")
    @login_required
    def groups_page():
        uid = _get_current_user_id()
        my_groups = engine.db.get_user_groups(uid) if engine else []
        all_groups = engine.db.get_all_groups() if engine else []
        return render_template("groups.html", my_groups=my_groups, all_groups=all_groups)

    @app.route("/groups/<int:group_id>")
    @login_required
    def group_detail(group_id):
        group = engine.db.get_group(group_id) if engine else None
        if not group:
            return render_template("404.html"), 404
        members = engine.db.get_group_members(group_id) if engine else []
        group_papers = engine.db.get_group_paper_feed(group_id, limit=50) if engine else []
        uid = _get_current_user_id()
        is_member = any(m["id"] == uid for m in members)
        return render_template(
            "group_detail.html",
            group=group,
            members=members,
            papers=group_papers,
            is_member=is_member,
        )

    @app.route("/api/groups", methods=["POST"])
    @login_required
    def create_group():
        if not current_user.is_admin:
            return jsonify({"error": "Only admins can create groups"}), 403
        data = request.get_json() or {}
        name = sanitise_input(data.get("name", ""))
        raw_desc = data.get("description", "")
        description = sanitise_input(raw_desc) if raw_desc else None
        if not name:
            return jsonify({"error": "name is required"}), 400
        gid = engine.db.create_group(name, description) if engine else None
        if gid is None:
            return jsonify({"error": "failed to create group"}), 500
        return jsonify({"status": "ok", "id": gid})

    @app.route("/api/groups/<int:group_id>/join", methods=["POST"])
    @login_required
    def join_group(group_id):
        uid = _get_current_user_id()
        success = engine.db.add_group_member(group_id, uid) if engine else False
        return jsonify({"status": "ok" if success else "error"})

    @app.route("/api/groups/<int:group_id>/leave", methods=["POST"])
    @login_required
    def leave_group(group_id):
        uid = _get_current_user_id()
        success = engine.db.remove_group_member(group_id, uid) if engine else False
        return jsonify({"status": "ok" if success else "error"})

    @app.route("/api/groups/<int:group_id>/members", methods=["POST"])
    @login_required
    def add_group_member(group_id):
        if not current_user.is_admin:
            return jsonify({"error": "Forbidden"}), 403
        data = request.get_json() or {}
        user_id = data.get("user_id")
        role = data.get("role", "member")
        if not user_id:
            return jsonify({"error": "user_id is required"}), 400
        success = engine.db.add_group_member(group_id, int(user_id), role=role) if engine else False
        return jsonify({"status": "ok" if success else "error"})

    @app.route("/api/groups/<int:group_id>/members/<int:user_id>", methods=["DELETE"])
    @login_required
    def remove_group_member(group_id, user_id):
        if not current_user.is_admin and user_id != _get_current_user_id():
            return jsonify({"error": "Forbidden"}), 403
        success = engine.db.remove_group_member(group_id, user_id) if engine else False
        return jsonify({"status": "ok" if success else "error"})

    # ------------------------------------------------------------------
    # Utility routes
    # ------------------------------------------------------------------

    @app.route("/health")
    def health():
        status = "ok"
        code = 200
        details: dict = {}
        try:
            engine.db.conn.execute("SELECT 1")
            details["db"] = "ok"
        except Exception as e:
            status = "degraded"
            code = 503
            details["db"] = f"error: {str(e)}"
        try:
            from ..embedder import _model
            details["embedder"] = "ok" if _model is not None else "lazy_not_loaded"
            if engine.preference_model and engine.preference_model.model:
                details["preference_model"] = "ok"
            else:
                status = "degraded"
                code = 503
                details["preference_model"] = "not_loaded"
        except Exception as e:
            status = "degraded"
            code = 503
            details["embedder"] = f"error: {str(e)}"
        return jsonify({"status": status, "details": details}), code

    @app.route("/metrics")
    def metrics():
        stats_data = engine.get_stats()
        db = stats_data["database"]
        model = stats_data["model"]
        lines = [
            "# HELP aura_papers_total Total number of papers in database",
            "# TYPE aura_papers_total gauge",
            f"aura_papers_total {db['total_papers']}",
            "# HELP aura_papers_with_embeddings_total Papers with embeddings",
            "# TYPE aura_papers_with_embeddings_total gauge",
            f"aura_papers_with_embeddings_total {db['with_embeddings']}",
            "# HELP aura_papers_rated_total Total unique papers rated",
            "# TYPE aura_papers_rated_total gauge",
            f"aura_papers_rated_total {db['total_rated']}",
            "# HELP aura_papers_liked_total Total papers with positive rating",
            "# TYPE aura_papers_liked_total gauge",
            f"aura_papers_liked_total {db['thumbs_up']}",
            "# HELP aura_papers_disliked_total Total papers with negative rating",
            "# TYPE aura_papers_disliked_total gauge",
            f"aura_papers_disliked_total {db['thumbs_down']}",
            "# HELP aura_model_trained_samples_total Total samples model was trained on",
            "# TYPE aura_model_trained_samples_total counter",
            f"aura_model_trained_samples_total {model['total_trained']}",
            "# HELP aura_model_replay_buffer_size Current size of experience replay buffer",
            "# TYPE aura_model_replay_buffer_size gauge",
            f"aura_model_replay_buffer_size {model['replay_buffer_size']}",
        ]
        from flask import Response
        return Response("\n".join(lines) + "\n", mimetype="text/plain")

    @app.route("/fetch")
    @login_required
    def fetch_page():
        stats_data = engine.get_stats(user_id=_get_current_user_id())
        return render_template("fetch.html", stats=stats_data)

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        uid = _get_current_user_id()
        if request.method == "POST":
            freq = request.form.get("digest_frequency")
            if freq in ["daily", "weekly", "off"]:
                success = engine.db.update_user(uid, digest_frequency=freq) if engine else False
                if success:
                    flash("Settings updated successfully.", "success")
                else:
                    flash("Failed to update settings.", "danger")
            else:
                flash("Invalid digest frequency option.", "danger")
            return redirect(url_for("settings"))

        stats_data = engine.get_stats(user_id=uid)
        config = app.config.get("AI_PAPERS", {})
        tokens = engine.db.get_user_tokens(uid) if engine else []
        user_record = engine.db.get_user_by_id(uid) if engine else None
        return render_template("settings.html", stats=stats_data, config=config, tokens=tokens, user=user_record)

    @app.route("/trends")
    @login_required
    def trends_page():
        if not engine:
            return "Engine not initialized", 500
        from aura.trends import get_trends_data
        uid = _get_current_user_id()
        stats_data = engine.get_stats(user_id=uid)
        trends_data = get_trends_data(engine.data_dir, engine.embedding_model)
        return render_template("trends.html", trends=trends_data, stats=stats_data)

    @app.route("/unsubscribe/<token>")
    def unsubscribe(token):
        if not engine:
            return "Engine not initialized", 500
        user_record = engine.db.get_user_by_unsubscribe_token(token)
        if not user_record:
            return render_template("404.html"), 404
        
        # Turn off digest frequency
        engine.db.update_user(user_record["id"], digest_frequency="off")
        
        html = f"""
        <html>
        <head>
            <title>Unsubscribed</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {{ background: #0f172a; color: #f8fafc; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
                .card {{ background: #1e293b; border: 1px solid #334155; padding: 2.5rem; border-radius: 12px; max-width: 450px; width: 100%; text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06); }}
                h2 {{ margin-bottom: 1rem; color: #38bdf8; }}
                p {{ margin-bottom: 2rem; color: #94a3b8; font-size: 0.95rem; line-height: 1.5; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>Unsubscribed Successfully</h2>
                <p>You have been unsubscribed from the AURA daily digest emails for <strong>{user_record["email"]}</strong>.</p>
                <a href="/login" class="btn btn-primary w-100">Go to Sign in</a>
            </div>
        </body>
        </html>
        """
        from flask import render_template_string
        return render_template_string(html)

    @app.route("/rate-direct")
    def rate_direct():
        if not engine:
            return "Engine not initialized", 500
        
        token = request.args.get("token")
        if not token:
            return "Missing token", 400
            
        from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
        serializer = URLSafeTimedSerializer(app.secret_key)
        
        try:
            # Token valid for 30 days
            payload = serializer.loads(token, max_age=30 * 24 * 3600)
        except SignatureExpired:
            return "The rating link has expired. Ratings links are valid for 30 days.", 400
        except BadSignature:
            return "Invalid signature token.", 400
            
        user_id = payload.get("user_id")
        arxiv_id = payload.get("arxiv_id")
        rating = payload.get("rating")
        
        if not arxiv_id or rating is None or not user_id:
            return "Invalid token payload.", 400
            
        # Get paper info to show in confirmation page
        paper = engine.db.get_paper(arxiv_id)
        paper_title = paper["title"] if paper else arxiv_id
        
        # Apply rating
        engine.rate_paper(arxiv_id, rating, user_id=user_id)
        
        rating_str = "👍 Thumbs Up" if rating == 1 else "👎 Thumbs Down"
        badge_color = "#2e7d32" if rating == 1 else "#c62828"
        
        html = f"""
        <html>
        <head>
            <title>Feedback Received</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            <style>
                body {{ background: #0f172a; color: #f8fafc; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
                .card {{ background: #1e293b; border: 1px solid #334155; padding: 2.5rem; border-radius: 12px; max-width: 550px; width: 100%; text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06); }}
                h2 {{ margin-bottom: 1.5rem; color: #38bdf8; }}
                .paper-box {{ background: #0f172a; border: 1px solid #1e293b; padding: 1.25rem; border-radius: 8px; margin-bottom: 1.5rem; text-align: left; }}
                .paper-title {{ font-weight: 600; font-size: 1.05rem; margin-bottom: 0.5rem; color: #f8fafc; }}
                .badge-rating {{ display: inline-block; padding: 0.35em 0.65em; font-size: .75em; font-weight: 700; line-height: 1; text-align: center; white-space: nowrap; vertical-align: baseline; border-radius: 0.375rem; background-color: {badge_color}; color: #fff; }}
                p.info {{ margin-bottom: 2rem; color: #94a3b8; font-size: 0.95rem; line-height: 1.5; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>Feedback Received</h2>
                <div class="paper-box">
                    <div class="paper-title">{paper_title}</div>
                    <span class="badge-rating">{rating_str}</span>
                </div>
                <p class="info">Thank you! Your feedback has been recorded, and AURA's recommendation models have been updated in real-time.</p>
                <a href="/" class="btn btn-primary w-100">Go to Dashboard</a>
            </div>
        </body>
        </html>
        """
        from flask import render_template_string
        return render_template_string(html)

    @app.route("/api/integrations/slack/command", methods=["POST"])
    @csrf.exempt
    def slack_command():
        if not engine:
            return jsonify({"text": "AURA engine is not initialized."}), 500
            
        command = request.form.get("command")
        text = (request.form.get("text") or "").strip().lower()
        
        if not command:
            return "Missing command parameter", 400
            
        if "recommend" in text:
            parts = text.split()
            limit = 5
            if len(parts) > 1:
                try:
                    limit = int(parts[1])
                except ValueError:
                    pass
            limit = min(max(1, limit), 20)
            
            recs = engine.get_recommendations(limit=limit, user_id=1)
            if not recs:
                return jsonify({
                    "response_type": "ephemeral",
                    "text": "No recommendations found. Try fetching new papers first!"
                })
                
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Here are your top *{len(recs)}* paper recommendations from *AURA*:"
                    }
                },
                {
                    "type": "divider"
                }
            ]
            
            for i, paper in enumerate(recs, 1):
                score_percent = round(float(paper.get("score", 0.0)) * 100)
                title = paper.get("title", "Untitled")
                url = paper.get("url", "")
                authors = ", ".join(paper.get("authors", [])[:3])
                summary = paper.get("summary") or paper.get("abstract", "")
                if len(summary) > 200:
                    summary = summary[:197] + "..."
                    
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{i}. *<{url}|{title}>* [Score: *{score_percent}%*]\n*Authors*: {authors}\n{summary}"
                    }
                })
                
            return jsonify({
                "response_type": "in_channel",
                "blocks": blocks
            })
            
        else:
            return jsonify({
                "response_type": "ephemeral",
                "text": "Usage:\n`/aura recommend [limit]` - List top paper recommendations (default 5)\n`/aura help` - Show this message"
            })

    @app.route("/api/extension/check")
    def extension_check():
        arxiv_id = request.args.get("arxiv_id")
        if not arxiv_id:
            return jsonify({"error": "arxiv_id query parameter is required"}), 400
            
        if not engine:
            return jsonify({"error": "Engine not initialized"}), 500
            
        uid = _get_current_user_id()
        
        # Check database
        paper = engine.db.get_paper(arxiv_id)
        if paper:
            rating = engine.db.get_latest_rating(arxiv_id, user_id=uid)
            
            papers_emb = engine.db.get_papers_with_embeddings([arxiv_id])
            score = 0.5
            if papers_emb:
                _, embedding = papers_emb[0]
                import torch
                pref_model = engine.get_user_preference_model(uid)
                with torch.no_grad():
                    emb_t = torch.tensor(embedding, dtype=torch.float32).unsqueeze(0)
                    score = float(torch.sigmoid(pref_model(emb_t)).item())
                    
            return jsonify({
                "exists": True,
                "title": paper["title"],
                "score": round(score, 4),
                "rating": rating,
                "summary": paper.get("summary")
            })
        else:
            # Fetch and score on the fly
            from ..fetcher import ArxivSource
            source = ArxivSource()
            fetched = source.fetch_by_id(arxiv_id)
            if not fetched:
                return jsonify({"exists": False, "score": 0.5, "error": "Paper not found on arXiv"})
                
            from ..embedder import embed_papers_batch
            embeddings = embed_papers_batch([fetched], model_name=engine.embedding_model)
            
            score = 0.5
            if len(embeddings) > 0:
                import torch
                pref_model = engine.get_user_preference_model(uid)
                with torch.no_grad():
                    emb_t = torch.tensor(embeddings[0], dtype=torch.float32).unsqueeze(0)
                    score = float(torch.sigmoid(pref_model(emb_t)).item())
                    
            return jsonify({
                "exists": False,
                "title": fetched["title"],
                "score": round(score, 4),
                "rating": None,
                "summary": None
            })

    @app.route("/api/extension/add", methods=["POST"])
    @csrf.exempt
    def extension_add():
        if not engine:
            return jsonify({"error": "Engine not initialized"}), 500
            
        data = request.get_json() or {}
        arxiv_id = data.get("arxiv_id")
        if not arxiv_id:
            return jsonify({"error": "arxiv_id is required"}), 400
            
        paper = engine.fetch_and_add_paper(arxiv_id)
        if not paper:
            return jsonify({"error": "Failed to fetch or add paper"}), 400
            
        uid = _get_current_user_id()
        rating = engine.db.get_latest_rating(arxiv_id, user_id=uid)
        
        return jsonify({
            "success": True,
            "title": paper["title"],
            "rating": rating,
            "summary": paper.get("summary")
        })

    @app.route("/papers/<path:arxiv_id>/export/bibtex")
    @login_required
    def export_paper_bibtex(arxiv_id):
        if not engine:
            return "Engine not initialized", 500
        paper = engine.db.get_paper(arxiv_id)
        if not paper:
            return "Paper not found", 404
        
        bibtex_content = _paper_to_bibtex(paper)
        from flask import Response
        filename = f"{arxiv_id.replace('/', '_')}.bib"
        return Response(
            bibtex_content,
            mimetype="application/x-bibtex",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
        )

    @app.route("/papers/<path:arxiv_id>/export/ris")
    @login_required
    def export_paper_ris(arxiv_id):
        if not engine:
            return "Engine not initialized", 500
        paper = engine.db.get_paper(arxiv_id)
        if not paper:
            return "Paper not found", 404
        
        ris_content = _paper_to_ris(paper)
        from flask import Response
        filename = f"{arxiv_id.replace('/', '_')}.ris"
        return Response(
            ris_content,
            mimetype="application/x-research-info-systems",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
        )

    @app.route("/papers/export/bibtex")
    @login_required
    def export_bulk_bibtex():
        if not engine:
            return "Engine not initialized", 500
            
        uid = _get_current_user_id()
        collection_id = request.args.get("collection")
        
        if not collection_id:
            return "Missing collection ID", 400
            
        try:
            coll_id = int(collection_id)
        except ValueError:
            return "Invalid collection ID", 400
            
        collection = engine.db.get_collection(coll_id)
        if not collection or (collection["user_id"] != uid and not collection.get("is_public")):
            return "Collection not found or access denied", 403
            
        papers = engine.db.get_collection_papers(coll_id, limit=1000)
        
        bibtex_entries = []
        for paper in papers:
            bibtex_entries.append(_paper_to_bibtex(paper))
            
        bibtex_content = "\n\n".join(bibtex_entries)
        from flask import Response
        filename = f"collection_{coll_id}.bib"
        return Response(
            bibtex_content,
            mimetype="application/x-bibtex",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
        )

    @app.route("/papers/export/ris")
    @login_required
    def export_ris():
        if not engine:
            return "Engine not initialized", 500
            
        uid = _get_current_user_id()
        arxiv_id = request.args.get("arxiv_id")
        collection_id = request.args.get("collection")
        
        if arxiv_id:
            paper = engine.db.get_paper(arxiv_id)
            if not paper:
                return "Paper not found", 404
            ris_content = _paper_to_ris(paper)
            filename = f"{arxiv_id.replace('/', '_')}.ris"
        elif collection_id:
            try:
                coll_id = int(collection_id)
            except ValueError:
                return "Invalid collection ID", 400
                
            collection = engine.db.get_collection(coll_id)
            if not collection or (collection["user_id"] != uid and not collection.get("is_public")):
                return "Collection not found or access denied", 403
                
            papers = engine.db.get_collection_papers(coll_id, limit=1000)
            ris_entries = []
            for paper in papers:
                ris_entries.append(_paper_to_ris(paper))
            ris_content = "\r\n\r\n".join(ris_entries)
            filename = f"collection_{coll_id}.ris"
        else:
            return "Missing arxiv_id or collection parameter", 400
            
        from flask import Response
        return Response(
            ris_content,
            mimetype="application/x-research-info-systems",
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
        )
