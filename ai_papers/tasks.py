import os
import logging
from datetime import datetime, timedelta
import xml.etree.ElementTree as ElementTree
import requests
import yaml
from celery import Celery

from .recommender import RecommendationEngine
from .fetcher import ArxivSource
from .embedder import embed_papers_batch

logger = logging.getLogger(__name__)

# Load config
config_path = os.environ.get("AI_PAPERS_CONFIG", "config.yaml")
config: dict = {}
if os.path.exists(config_path):
    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

celery_config = config.get("celery", {})
default_broker = "sqla+sqlite:///data/celerydb.sqlite"
default_backend = "db+sqlite:///data/celeryresults.sqlite"

# Ensure data directory exists
data_dir = config.get("data_dir", "data")
os.makedirs(data_dir, exist_ok=True)

broker_url = celery_config.get("broker_url", os.environ.get("CELERY_BROKER_URL", default_broker))
result_backend = celery_config.get("result_backend", os.environ.get("CELERY_RESULT_BACKEND", default_backend))

celery_app = Celery("aura_tasks", broker=broker_url, backend=result_backend)

celery_app.conf.update(
    task_track_started=True,
)

@celery_app.task(bind=True)
def fetch_papers_task(self, max_results=200, days_back=2, generate_summaries=False):
    """Orchestrates paper fetching in small batches using countdown retries."""
    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        sources_config=config.get("sources", {}),
    )
    
    task_id = self.request.id
    engine.db.create_task_entry(task_id, "fetch_papers", status="RUNNING")
    engine.db.update_task_progress(task_id, progress=0, total=max_results, status="RUNNING")
    engine.close()
    
    # Trigger first batch page fetch task
    fetch_papers_page_task.delay(
        task_id=task_id,
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        max_results=max_results,
        days_back=days_back,
        generate_summaries=generate_summaries,
        start=0,
        new_papers_count=0
    )
    
    return {"status": "started", "task_id": task_id}

@celery_app.task(bind=True)
def fetch_papers_page_task(self, task_id, categories, max_results, days_back, generate_summaries, start, new_papers_count):
    """Fetches a single page of papers, saves to DB, then schedules the next page."""
    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=categories,
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        sources_config=config.get("sources", {}),
    )
    
    try:
        # Build query
        cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        date_from = start_date.strftime("%Y%m%d")
        date_to = end_date.strftime("%Y%m%d")
        
        batch_size = min(max_results - start, 100)
        if batch_size <= 0:
            # Finish task
            engine.db.complete_task(task_id, status="SUCCESS", result={"new_papers": new_papers_count})
            engine.db.log_fetch(new_papers_count, categories)
            engine.close()
            return {"new_papers": new_papers_count}
            
        query = f"({cat_query}) AND submittedDate:[{date_from}0000 TO {date_to}2359]"
        params = {
            "search_query": query,
            "start": start,
            "max_results": batch_size,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        
        engine.db.update_task_progress(task_id, progress=start, total=max_results)
        
        logger.info(f"Task {task_id}: Fetching arXiv papers start={start}, batch_size={batch_size}")
        source = ArxivSource()
        resp = requests.get(source.ARXIV_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        
        root = ElementTree.fromstring(resp.text)
        entries = root.findall(f"{source.ATOM_NS}entry")
        
        # Fallback to simple if no entries on first page
        if not entries and start == 0:
            logger.info(f"Task {task_id}: Date-filtered fetch returned no papers, trying simple fetch")
            params_simple = {
                "search_query": cat_query,
                "start": start,
                "max_results": batch_size,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            resp = requests.get(source.ARXIV_API_URL, params=params_simple, timeout=30)
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.text)
            entries = root.findall(f"{source.ATOM_NS}entry")
            
        papers = []
        for entry in entries:
            paper = source._parse_entry(entry)
            if paper:
                papers.append(paper)
                
        if not papers:
            engine.db.complete_task(task_id, status="SUCCESS", result={"new_papers": new_papers_count})
            engine.db.log_fetch(new_papers_count, categories)
            engine.close()
            return {"new_papers": new_papers_count}
            
        # Separate new vs existing
        existing_ids = set()
        papers_needing_summary = []
        for paper in papers:
            existing_paper = engine.db.get_paper(paper["arxiv_id"])
            if existing_paper:
                existing_ids.add(paper["arxiv_id"])
                if not existing_paper.get("summary"):
                    papers_needing_summary.append(paper)
                    
        new_papers = [p for p in papers if p["arxiv_id"] not in existing_ids]
        
        added_in_batch = 0
        if new_papers:
            embeddings = embed_papers_batch(new_papers, model_name=engine.embedding_model)
            summaries = None
            if generate_summaries:
                summaries = engine._generate_summaries_for_papers(new_papers)
            added_in_batch = engine.db.add_papers_batch(new_papers, embeddings, summaries)
            
        new_papers_count += added_in_batch
        
        if generate_summaries and papers_needing_summary:
            engine.generate_missing_summaries(limit=len(papers_needing_summary), include_failed=False)
            
        next_start = start + batch_size
        if next_start < max_results:
            # Politeness retry using countdown instead of time.sleep
            fetch_papers_page_task.apply_async(
                kwargs={
                    "task_id": task_id,
                    "categories": categories,
                    "max_results": max_results,
                    "days_back": days_back,
                    "generate_summaries": generate_summaries,
                    "start": next_start,
                    "new_papers_count": new_papers_count
                },
                countdown=3
            )
        else:
            engine.db.complete_task(task_id, status="SUCCESS", result={"new_papers": new_papers_count})
            engine.db.log_fetch(new_papers_count, categories)
            
    except Exception as e:
        logger.exception(f"Error in fetch_papers_page_task: {e}")
        engine.db.complete_task(task_id, status="FAILURE", error=str(e))
    finally:
        engine.close()

@celery_app.task(bind=True)
def generate_missing_summaries_task(self, limit=50, include_failed=True):
    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        sources_config=config.get("sources", {}),
    )
    
    task_id = self.request.id
    engine.db.create_task_entry(task_id, "summarize", status="RUNNING")
    
    def progress_callback(current, total):
        engine.db.update_task_progress(task_id, progress=current, total=total)
        
    try:
        result = engine.generate_missing_summaries(
            limit=limit,
            include_failed=include_failed,
            progress_callback=progress_callback
        )
        engine.db.complete_task(task_id, status="SUCCESS", result=result)
        return result
    except Exception as e:
        logger.exception(f"Error in generate_missing_summaries_task: {e}")
        engine.db.complete_task(task_id, status="FAILURE", error=str(e))
        raise
    finally:
        engine.close()

@celery_app.task(bind=True)
def retrain_full_task(self, epochs=20):
    engine = RecommendationEngine(
        data_dir=config.get("data_dir", "data"),
        categories=config.get("categories", ["astro-ph.CO", "astro-ph.GA"]),
        embedding_model=config.get("embedding_model", "all-MiniLM-L6-v2"),
        sources_config=config.get("sources", {}),
    )
    
    task_id = self.request.id
    engine.db.create_task_entry(task_id, "retrain", status="RUNNING")
    
    def progress_callback(current, total):
        engine.db.update_task_progress(task_id, progress=current, total=total)
        
    try:
        result = engine.retrain_full(epochs=epochs, progress_callback=progress_callback)
        engine.db.complete_task(task_id, status="SUCCESS", result=result)
        return result
    except Exception as e:
        logger.exception(f"Error in retrain_full_task: {e}")
        engine.db.complete_task(task_id, status="FAILURE", error=str(e))
        raise
    finally:
        engine.close()
