#!/usr/bin/env python3
"""AI Papers - Main entry point and CLI.

Usage:
    python run.py serve              # Start the web UI
    python run.py fetch              # Fetch new papers from arXiv
    python run.py summarize          # Launch LLM summaries separately
    python run.py recommend          # Print top recommendations to terminal
    python run.py email-digest       # Email top recommendations with summaries
    python run.py retrain            # Full retrain of preference model
    python run.py stats              # Show database and model stats
    python run.py serve --scheduler  # Start web UI with daily auto-fetch
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    print(f"Warning: Config file '{config_path}' not found, using defaults.")
    return {}


def cmd_serve(args, config):
    """Start the Flask web server."""
    from ai_papers.web.app import create_app

    app = create_app(args.config)

    if args.scheduler:
        _setup_scheduler(app, config)

    host = config.get("host", "127.0.0.1")
    port = config.get("port", 5000)
    debug = config.get("debug", False)

    print(f"\n  AI Papers server starting at http://{host}:{port}")
    print("  Press Ctrl+C to stop\n")

    app.run(host=host, port=port, debug=debug)


def cmd_fetch(args, config):
    """Fetch new papers from arXiv."""
    from ai_papers.recommender import RecommendationEngine

    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
    )

    fetch_config = config.get("fetch", {})
    max_results = args.max_results or fetch_config.get("max_results", 200)
    days_back = args.days_back or fetch_config.get("days_back", 2)

    print(f"Fetching papers (max={max_results}, days_back={days_back})...")
    count = engine.fetch_new_papers(
        max_results=max_results,
        days_back=days_back,
        generate_summaries=args.with_summaries,
    )
    print(f"Added {count} new papers to database.")
    engine.close()


def cmd_summarize(args, config):
    """Launch summary API requests separately for stored papers."""
    from ai_papers.recommender import RecommendationEngine

    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
    )

    result = engine.generate_missing_summaries(
        limit=args.limit,
        include_failed=not args.only_missing,
    )
    print(json.dumps(result, indent=2))
    engine.close()


def cmd_recommend(args, config):
    """Print top recommendations."""
    from ai_papers.recommender import RecommendationEngine

    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
    )

    papers = engine.get_recommendations(limit=args.limit, unrated_only=True)

    if not papers:
        print("No papers to recommend. Run 'python run.py fetch' first.")
        engine.close()
        return

    print(f"\nTop {len(papers)} recommended papers:\n")
    print("-" * 80)
    for i, paper in enumerate(papers, 1):
        score_pct = paper.get("score", 0) * 100
        print(f"\n{i}. [{score_pct:.0f}%] {paper['title']}")
        print(f"   Authors: {', '.join(paper['authors'][:3])}")
        print(f"   Categories: {', '.join(paper['categories'][:3])}")
        print(f"   {paper['url']}")
        print(f"   {paper['abstract'][:200]}...")
    print("\n" + "-" * 80)

    engine.close()


def cmd_retrain(args, config):
    """Full retrain of the preference model."""
    from ai_papers.recommender import RecommendationEngine

    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
    )

    result = engine.retrain_full(epochs=args.epochs)
    print(json.dumps(result, indent=2))
    engine.close()


def cmd_email_digest(args, config):
    """Send a formatted email digest for top recommended papers."""
    from ai_papers.email_digest import send_top_recommendations_email

    result = send_top_recommendations_email(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        email_config_path=args.email_config,
        top_n=args.top_n,
    )
    print(json.dumps(result, indent=2))


def cmd_stats(args, config):
    """Show system statistics."""
    from ai_papers.recommender import RecommendationEngine

    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
    )

    stats = engine.get_stats()
    print(json.dumps(stats, indent=2))
    engine.close()


def _setup_scheduler(app, config):
    """Set up APScheduler for daily paper fetching."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        print(
            "Warning: apscheduler not installed. Install with: pip install apscheduler"
        )
        return

    sched_config = config.get("scheduler", {})
    if not sched_config.get("enabled", False) and "--scheduler" not in sys.argv:
        return

    scheduler = BackgroundScheduler()
    hour = sched_config.get("fetch_hour", 6)
    minute = sched_config.get("fetch_minute", 0)

    def daily_fetch():
        with app.app_context():
            from ai_papers.web.app import engine

            if engine:
                fetch_config = config.get("fetch", {})
                count = engine.fetch_new_papers(
                    max_results=fetch_config.get("max_results", 200),
                    days_back=fetch_config.get("days_back", 2),
                )
                logging.getLogger(__name__).info(f"Scheduled fetch: {count} new papers")

    scheduler.add_job(daily_fetch, "cron", hour=hour, minute=minute)
    scheduler.start()
    print(f"  Scheduler enabled: daily fetch at {hour:02d}:{minute:02d} UTC")


def main():
    parser = argparse.ArgumentParser(
        description="AI Papers - Personalized arXiv Recommender"
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the web UI")
    serve_parser.add_argument(
        "--scheduler", action="store_true", help="Enable daily auto-fetch scheduler"
    )

    # fetch
    fetch_parser = subparsers.add_parser("fetch", help="Fetch new papers from arXiv")
    fetch_parser.add_argument("--max-results", type=int, help="Max papers to fetch")
    fetch_parser.add_argument("--days-back", type=int, help="Days back to search")
    fetch_parser.add_argument(
        "--with-summaries",
        action="store_true",
        help="Also generate summaries during fetch",
    )

    # summarize
    summarize_parser = subparsers.add_parser(
        "summarize", help="Launch LLM summaries separately"
    )
    summarize_parser.add_argument(
        "--limit", type=int, default=20, help="Number of papers to summarize"
    )
    summarize_parser.add_argument(
        "--only-missing", action="store_true", help="Skip papers already marked AI Fail"
    )

    # recommend
    rec_parser = subparsers.add_parser("recommend", help="Print top recommendations")
    rec_parser.add_argument(
        "--limit", type=int, default=20, help="Number of papers to show"
    )

    # retrain
    retrain_parser = subparsers.add_parser("retrain", help="Full model retrain")
    retrain_parser.add_argument(
        "--epochs", type=int, default=20, help="Training epochs"
    )

    # email digest
    email_parser = subparsers.add_parser(
        "email-digest",
        help="Email top recommended papers with AI summaries",
    )
    email_parser.add_argument(
        "--top-n", type=int, default=3, help="Number of top papers to include"
    )
    email_parser.add_argument(
        "--email-config",
        default="user_credentials/email_config.json",
        help="Path to email config JSON",
    )

    # stats
    subparsers.add_parser("stats", help="Show system stats")

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = load_config(args.config)

    commands = {
        "serve": cmd_serve,
        "fetch": cmd_fetch,
        "summarize": cmd_summarize,
        "recommend": cmd_recommend,
        "email-digest": cmd_email_digest,
        "retrain": cmd_retrain,
        "stats": cmd_stats,
    }

    commands[args.command](args, config)


if __name__ == "__main__":
    main()
