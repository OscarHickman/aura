#!/usr/bin/env python3
"""AURA - Main entry point and CLI.

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
import os
import sys
from pathlib import Path



def load_config(config_path: str = "config.yaml") -> dict:
    """Load and validate configuration."""
    from aura.config import get_validated_config
    path = Path(config_path)
    if not path.exists():
        print(f"Warning: Config file '{config_path}' not found, using defaults.")
        return {}
    try:
        return get_validated_config(config_path)
    except Exception as e:
        print(f"Configuration Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_migrate(args, config):
    """Run database migrations."""
    import subprocess
    print("Running database migrations...")
    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        print("Migrations complete.")
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_serve(args, config):
    """Start the Flask web server."""
    from aura.web.app import create_app

    if args.migrate:
        cmd_migrate(args, config)

    app = create_app(args.config)

    if args.scheduler:
        _setup_scheduler(app, config)

    host = config.get("host", "127.0.0.1")
    port = config.get("port", 5000)
    debug = config.get("debug", False)

    print(f"\n  AURA server starting at http://{host}:{port}")
    print("  Press Ctrl+C to stop\n")

    app.run(host=host, port=port, debug=debug)


def cmd_fetch(args, config):
    """Fetch new papers from arXiv."""
    from aura.recommender import RecommendationEngine

    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        sources_config=config.get("sources", {}),
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
    from aura.recommender import RecommendationEngine

    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        sources_config=config.get("sources", {}),
    )

    result = engine.generate_missing_summaries(
        limit=args.limit,
        include_failed=not args.only_missing,
    )
    print(json.dumps(result, indent=2))
    engine.close()


def cmd_recommend(args, config):
    """Print top recommendations."""
    from aura.recommender import RecommendationEngine

    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        sources_config=config.get("sources", {}),
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
    from aura.recommender import RecommendationEngine

    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        sources_config=config.get("sources", {}),
    )

    result = engine.retrain_full(epochs=args.epochs)
    print(json.dumps(result, indent=2))
    engine.close()


def cmd_email_digest(args, config):
    """Send a formatted email digest for top recommended papers."""
    from aura.email_digest import send_top_recommendations_email

    result = send_top_recommendations_email(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        email_config_path=args.email_config,
        top_n=args.top_n,
    )
    print(json.dumps(result, indent=2))


def cmd_weekly_brief(args, config):
    """Generate and send the weekly research brief."""
    from aura.briefs import send_weekly_brief_email
    from datetime import date

    date_str = args.date or date.today().isoformat()
    result = send_weekly_brief_email(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        date_str=date_str,
        email_config_path=args.email_config,
    )
    print(json.dumps(result, indent=2))


def cmd_group_digest(args, config):
    """Send a group digest email to all members of a group."""
    from aura.email_digest import send_group_digest_email

    result = send_group_digest_email(
        data_dir=config.get("data_dir", "data"),
        group_id=args.group_id,
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        email_config_path=args.email_config,
        top_n=args.top_n,
    )
    print(json.dumps(result, indent=2))


def cmd_cleanup_topics(args, config):
    """Cleanup junk entries from research_topics.json."""
    from aura.trends import cleanup_topics
    data_dir = config.get("data_dir", "data")
    cleanup_topics(data_dir)


def cmd_init(args, config):
    """Interactively initialize AURA configuration."""
    import subprocess
    subprocess.run(["./setup.sh"], check=True)


def cmd_doctor(args, config):
    """Validate environment, configuration, and dependencies."""
    print("Checking AURA health status...")
    all_ok = True
    
    # 1. Check Python version
    import sys
    print(f"  [+] Python version: {sys.version.split()[0]}", end="")
    if sys.version_info >= (3, 10):
        print(" (OK)")
    else:
        print(" (WARNING: Python >= 3.10 is recommended)")
        
    # 2. Check config file
    from pathlib import Path
    config_path = Path(args.config)
    print(f"  [+] Config file: {config_path}", end="")
    if config_path.exists():
        print(" (OK)")
    else:
        print(" (FAILED: config.yaml is missing!)")
        all_ok = False
        
    # 3. Check LLM provider
    provider = os.environ.get("LLM_PROVIDER") or config.get("llm_provider") or "groq"
    print(f"  [+] LLM Provider: {provider}", end="")
    key_name = f"{provider.upper()}_API_KEY"
    if os.environ.get(key_name) or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        print(" (OK, API key is set)")
    else:
        print(f" (WARNING: {key_name} is not set in environment!)")
        
    # 4. Check data directory and database
    data_dir = Path(config.get("data_dir", "data"))
    print(f"  [+] Data directory: {data_dir}", end="")
    if data_dir.exists():
        print(" (OK)")
    else:
        print(" (OK - will be created on start)")
        
    db_path = data_dir / "papers.db"
    print(f"  [+] SQLite database: {db_path}", end="")
    if db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT count(*) FROM papers")
            conn.close()
            print(" (OK, database is readable/writable)")
        except Exception as e:
            print(f" (FAILED: database check failed: {e})")
            all_ok = False
    else:
        print(" (Not created yet)")
        
    # 5. Check email configuration
    email_cfg = Path("user_credentials/email_config.json")
    print(f"  [+] Email configuration: {email_cfg}", end="")
    if email_cfg.exists():
        try:
            with open(email_cfg) as f:
                json.load(f)
            print(" (OK, configuration is valid JSON)")
        except Exception as e:
            print(f" (FAILED: invalid email JSON: {e})")
            all_ok = False
    else:
        print(" (Optional, not configured)")
        
    if all_ok:
        print("\nAll checks passed! AURA is ready to run.")
    else:
        print("\nSome critical checks failed. Please fix them before starting AURA.")


def cmd_import(args, config):
    """Import papers from a BibTeX file into the database."""
    from pathlib import Path
    bib_path = Path(args.file)
    if not bib_path.exists():
        print(f"Error: file '{bib_path}' not found.")
        sys.exit(1)
        
    with open(bib_path, encoding="utf-8") as f:
        content = f.read()
        
    import re
    entries = []
    blocks = content.split("@")
    for block in blocks:
        if not block.strip():
            continue
        match = re.match(r"^(\w+)\s*\{\s*([\w\-\:\.]+)\s*,", block)
        if not match:
            continue
        _entry_type = match.group(1).lower()
        key = match.group(2)
        
        fields = {}
        field_matches = re.finditer(r"(\w+)\s*=\s*[\"\{](.*?)[\"\}]\s*,?\s*$", block, re.MULTILINE | re.DOTALL)
        for fm in field_matches:
            field_name = fm.group(1).lower()
            field_val = fm.group(2).strip()
            field_val = re.sub(r"[\{\}]", "", field_val)
            fields[field_name] = field_val
            
        if "title" in fields:
            arxiv_id = fields.get("eprint")
            if not arxiv_id:
                url = fields.get("url", "")
                arxiv_match = re.search(r"arxiv\.org/abs/([\w\-\.]+)", url, re.IGNORECASE)
                if arxiv_match:
                    arxiv_id = arxiv_match.group(1)
            
            authors = [a.strip() for a in fields.get("author", "Unknown").split(" and ")]
            
            entries.append({
                "title": fields.get("title"),
                "authors": authors,
                "arxiv_id": arxiv_id or f"imported:{key}",
                "abstract": fields.get("abstract", fields.get("note", "No abstract available.")),
                "categories": fields.get("keywords", "imported"),
                "published": f"{fields.get('year', '2026')}-01-01T00:00:00Z",
                "url": fields.get("url", f"https://doi.org/{fields['doi']}" if "doi" in fields else ""),
                "source": "imported",
            })

    if not entries:
        print("No valid BibTeX entries found.")
        return
        
    from aura.recommender import RecommendationEngine
    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
    )

    if getattr(args, "import_authors", None):
        print(f"Importing authors as tracked '{args.import_authors}'...")
        added_authors = 0
        all_authors = set()
        for entry in entries:
            for author in entry["authors"]:
                author_clean = author.strip()
                if author_clean and author_clean.lower() not in ["unknown", "others", "et al.", "et al"]:
                    all_authors.add(author_clean)
        for author in sorted(all_authors):
            success = engine.db.add_tracked_author(author, relationship=args.import_authors)
            if success:
                added_authors += 1
        print(f"Successfully imported {added_authors} unique tracked authors.")
    
    print(f"Parsed {len(entries)} entries. Importing into AURA...")
    imported_count = 0
    for entry in entries:
        if not entry["arxiv_id"].startswith("imported:"):
            print(f"Fetching full metadata for arXiv:{entry['arxiv_id']}...")
            try:
                engine.fetch_and_add_paper(entry["arxiv_id"])
                imported_count += 1
                continue
            except Exception:
                pass
                
        try:
            from aura.embedder import get_model
            model = get_model(engine.embedding_model)
            text_to_embed = f"{entry['title']} {entry['abstract']}"
            embedding = model.encode(text_to_embed, normalize_embeddings=True)
            
            paper_dict = {
                "arxiv_id": entry["arxiv_id"],
                "title": entry["title"],
                "abstract": entry["abstract"],
                "authors": json.dumps(entry["authors"]),
                "categories": entry["categories"],
                "published": entry["published"],
                "url": entry["url"],
                "pdf_url": "",
                "source": entry["source"],
            }
            engine.db.add_paper(paper_dict, embedding=embedding)
            imported_count += 1
        except Exception as e:
            print(f"Failed to import '{entry['title']}': {e}")
            
    print(f"Successfully imported {imported_count} papers.")
    engine.close()


def cmd_export(args, config):
    """Export papers from AURA database in a specified format."""
    from aura.recommender import RecommendationEngine
    import csv
    
    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
    )
    
    papers = engine.db.get_papers(limit=10000, unrated_only=False)
    if not papers:
        print("No papers found in database to export.")
        engine.close()
        return
        
    out_file = args.output
    fmt = args.format.lower()
    
    if fmt == "json":
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(papers, f, indent=2)
            
    elif fmt == "csv":
        with open(out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=papers[0].keys())
            writer.writeheader()
            for p in papers:
                writer.writerow(p)
                
    elif fmt == "bibtex":
        with open(out_file, "w", encoding="utf-8") as f:
            for p in papers:
                try:
                    authors_list = json.loads(p["authors"])
                    if not isinstance(authors_list, list):
                        authors_list = [authors_list]
                except Exception:
                    authors_list = [p["authors"]]
                authors_str = " and ".join(authors_list)
                
                first_author = authors_list[0].split()[-1] if authors_list else "Unknown"
                year = p["published"][:4]
                key = f"{first_author.lower()}{year}{p['arxiv_id'].replace('.', '')}"
                
                f.write(f"@article{{{key},\n")
                f.write(f"  title = {{{p['title']}}},\n")
                f.write(f"  author = {{{authors_str}}},\n")
                f.write(f"  journal = {{arXiv preprint arXiv:{p['arxiv_id']}}},\n")
                f.write(f"  year = {{{year}}},\n")
                f.write(f"  eprint = {{{p['arxiv_id']}}},\n")
                f.write(f"  url = {{{p['url']}}},\n")
                f.write(f"  abstract = {{{p['abstract']}}}\n")
                f.write("}\n\n")
    else:
        print(f"Error: unsupported format '{fmt}'. Choose from json, csv, bibtex.")
        engine.close()
        sys.exit(1)
        
    print(f"Exported {len(papers)} papers to '{out_file}' in {fmt.upper()} format.")
    engine.close()


def cmd_stats(args, config):
    """Show system statistics."""
    from aura.recommender import RecommendationEngine

    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        sources_config=config.get("sources", {}),
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
            from aura.web.app import engine

            if engine:
                fetch_config = config.get("fetch", {})
                count = engine.fetch_new_papers(
                    max_results=fetch_config.get("max_results", 200),
                    days_back=fetch_config.get("days_back", 2),
                )
                logging.getLogger(__name__).info(f"Scheduled fetch: {count} new papers")
                
                # Trigger Slack daily digest if configured
                try:
                    integrations = config.get("integrations", {})
                    slack_conf = integrations.get("slack", {})
                    if slack_conf.get("enabled", False) and slack_conf.get("webhook_url"):
                        recs = engine.get_recommendations(limit=5, user_id=1)
                        if recs:
                            from aura.notifications import send_slack_digest
                            send_slack_digest(slack_conf["webhook_url"], recs)
                            logging.getLogger(__name__).info("Daily digest posted to Slack channel.")
                except Exception as e:
                    logging.getLogger(__name__).error(f"Failed to post daily digest to Slack: {e}")

    scheduler.add_job(daily_fetch, "cron", hour=hour, minute=minute)

    ads_hour = sched_config.get("ads_refresh_hour")
    ads_minute = sched_config.get("ads_refresh_minute")
    if ads_hour is None:
        ads_hour = (hour + 1) % 24
    if ads_minute is None:
        ads_minute = minute

    def daily_ads_refresh():
        with app.app_context():
            logging.getLogger(__name__).info("Scheduled daily ADS metadata refresh: starting...")
            try:
                from aura.tasks import refresh_ads_metadata_task
                refresh_ads_metadata_task.delay()
                logging.getLogger(__name__).info("Scheduled daily ADS metadata refresh: Celery task queued.")
            except Exception as e:
                logging.getLogger(__name__).error(f"Failed to queue scheduled ADS metadata refresh: {e}")

    scheduler.add_job(daily_ads_refresh, "cron", hour=ads_hour, minute=ads_minute)
    scheduler.start()
    print(f"  Scheduler enabled: daily fetch at {hour:02d}:{minute:02d} UTC")
    print(f"  Scheduler enabled: daily ADS metadata refresh at {ads_hour:02d}:{ads_minute:02d} UTC")


def main():
    parser = argparse.ArgumentParser(
        description="AURA - Personalised arXiv Recommender"
    )

    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start the web UI")
    serve_parser.add_argument(
        "--scheduler", action="store_true", help="Enable daily auto-fetch"
    )
    serve_parser.add_argument(
        "--migrate", action="store_true", help="Run migrations before starting"
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

    # group digest
    group_parser = subparsers.add_parser(
        "group-digest",
        help="Email group recommended papers to group members",
    )
    group_parser.add_argument(
        "--group-id", type=int, required=True, help="ID of the research group"
    )
    group_parser.add_argument(
        "--top-n", type=int, default=5, help="Number of papers to include"
    )
    group_parser.add_argument(
        "--email-config",
        default="user_credentials/email_config.json",
        help="Path to email config JSON",
    )

    # weekly-brief
    brief_parser = subparsers.add_parser(
        "weekly-brief",
        help="Generate and email the weekly research brief",
    )
    brief_parser.add_argument(
        "--date",
        help="Specific date for the brief (YYYY-MM-DD), default is today",
    )
    brief_parser.add_argument(
        "--email-config",
        default="user_credentials/email_config.json",
        help="Path to email config JSON",
    )

    # stats
    subparsers.add_parser("stats", help="Show system stats")

    # cleanup-topics
    subparsers.add_parser("cleanup-topics", help="Remove junk from research_topics.json")

    # migrate
    subparsers.add_parser("migrate", help="Run database migrations")

    # init
    subparsers.add_parser("init", help="Interactively initialise AURA configuration")

    # doctor
    subparsers.add_parser("doctor", help="Validate environment, configuration, and dependencies")

    # import
    import_parser = subparsers.add_parser("import", help="Import papers from a BibTeX file into the database")
    import_parser.add_argument("file", help="Path to BibTeX file to import")
    import_parser.add_argument(
        "--import-authors",
        choices=["follow", "collaborator"],
        help="Also import all authors from the BibTeX file into the tracked_authors table under the specified relationship"
    )

    # export
    export_parser = subparsers.add_parser("export", help="Export papers from AURA database in a specified format")
    export_parser.add_argument("format", choices=["json", "csv", "bibtex"], help="Export format (json, csv, bibtex)")
    export_parser.add_argument("--output", "-o", required=True, help="Path to output file")

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
        "group-digest": cmd_group_digest,
        "weekly-brief": cmd_weekly_brief,
        "retrain": cmd_retrain,
        "stats": cmd_stats,
        "migrate": cmd_migrate,
        "cleanup-topics": cmd_cleanup_topics,
        "init": cmd_init,
        "doctor": cmd_doctor,
        "import": cmd_import,
        "export": cmd_export,
    }

    commands[args.command](args, config)


if __name__ == "__main__":
    main()
