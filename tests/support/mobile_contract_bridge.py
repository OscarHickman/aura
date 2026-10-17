"""Drive real Flask routes from Jest over JSON lines, without network sockets.

Only model inference is stubbed. Authentication, SQLite and API handlers are real.
All state is created in a temporary directory and removed when stdin closes.
"""
import contextlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from werkzeug.security import generate_password_hash  # noqa: E402
from aura.database import PaperDatabase  # noqa: E402
from aura.web.app import create_app  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(sys.stderr):
        db = PaperDatabase(Path(directory) / "papers.db")
        db.create_user("contract@aura.test", generate_password_hash("contract-password"))
        db.add_paper({
            "arxiv_id": "2401.00001", "title": "Contract paper", "abstract": "A test abstract.",
            "authors": ["A Researcher"], "categories": ["astro-ph.CO"],
            "published": "2026-01-01T00:00:00Z",
        })
        engine = Mock()
        engine.db = db
        engine.get_recommendations.side_effect = lambda **kwargs: db.get_papers(limit=kwargs["limit"])
        engine.get_similar_papers.return_value = []
        engine.ask_paper_question.return_value = iter(["The ", "contract ", "answer."])
        engine.get_stats.return_value = {"database": {"total_rated": 1}, "model": {}}

        def rate(arxiv_id, rating, user_id=1):
            db.rate_paper(arxiv_id, rating, user_id=user_id)
            return {"status": "ok"}

        engine.rate_paper.side_effect = rate
        config = Path(directory) / "config.yaml"
        config.write_text(f"data_dir: {directory}\nscheduler:\n  enabled: false\n")
        with patch("aura.web.app.RecommendationEngine", return_value=engine):
            app = create_app(str(config))
        # Keep production CSRF/auth behavior; requests use actual bearer tokens.
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=True, RATELIMIT_ENABLED=False)
        client = app.test_client()
        output = sys.__stdout__
        print(json.dumps({"ready": True}), file=output, flush=True)
        try:
            for line in sys.stdin:
                request = json.loads(line)
                target = urlsplit(request["url"])
                path = target.path.removeprefix("/aura")
                if target.query:
                    path += f"?{target.query}"
                response = client.open(
                    path, method=request.get("method", "GET"),
                    data=request.get("body"), headers=request.get("headers", {}),
                    environ_overrides={"SCRIPT_NAME": "/aura"},
                )
                print(json.dumps({"status": response.status_code, "body": response.get_json(silent=True)}), file=output, flush=True)
        finally:
            db.close()


if __name__ == "__main__":
    main()
