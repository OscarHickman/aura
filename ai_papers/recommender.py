"""Recommendation engine that ties together fetching, embedding, and model scoring."""

import logging
from pathlib import Path

from .database import PaperDatabase
from .embedder import embed_papers_batch, get_embedding_dim
from .fetcher import fetch_papers, fetch_papers_simple
from .llm import generate_summary, get_default_provider, _load_providers_order
from .model import PreferenceModel

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Main engine that orchestrates paper fetching, embedding, scoring, and training."""

    def __init__(self, data_dir: str | Path, categories: list[str], embedding_model: str = "all-MiniLM-L6-v2"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.categories = categories
        self.embedding_model = embedding_model

        # Initialize components
        self.db = PaperDatabase(self.data_dir / "papers.db")

        embedding_dim = get_embedding_dim(embedding_model)
        self.preference_model = PreferenceModel(
            model_path=self.data_dir / "preference_model.pt",
            embedding_dim=embedding_dim,
        )

    def fetch_new_papers(self, max_results: int = 200, days_back: int = 2, generate_summaries: bool = False) -> int:
        """Fetch new papers from arXiv, embed them, and store in database.

        Returns the number of new papers added.
        """
        logger.info(f"Fetching papers for categories: {self.categories}")

        # Try date-filtered fetch first, fall back to simple fetch
        papers = fetch_papers(self.categories, max_results=max_results, days_back=days_back)
        if not papers:
            logger.info("Date-filtered fetch returned no papers, trying simple fetch")
            papers = fetch_papers_simple(self.categories, max_results=max_results)

        if not papers:
            logger.warning("No papers fetched")
            return 0

        # Split fetched papers into new records and existing records that still
        # need summaries.
        existing_ids = set()
        papers_needing_summary = []
        for paper in papers:
            existing_paper = self.db.get_paper(paper["arxiv_id"])
            if existing_paper:
                existing_ids.add(paper["arxiv_id"])
                if not existing_paper.get("summary"):
                    papers_needing_summary.append(paper)

        new_papers = [p for p in papers if p["arxiv_id"] not in existing_ids]

        if not new_papers and not papers_needing_summary:
            logger.info("All fetched papers already in database with summaries")
            self.db.log_fetch(0, self.categories)
            return 0

        # Generate embeddings for new papers
        embeddings = embed_papers_batch(new_papers, model_name=self.embedding_model)

        summaries = None
        if generate_summaries and new_papers:
            logger.info("Fetch requested with summary generation enabled")
            summaries = self._generate_summaries_for_papers(new_papers)

        # Store in database
        count = self.db.add_papers_batch(new_papers, embeddings, summaries)
        self.db.log_fetch(count, self.categories)

        if generate_summaries and papers_needing_summary:
            self.generate_missing_summaries(limit=len(papers_needing_summary), include_failed=False)

        logger.info(f"Added {count} new papers to database")
        return count

    def _generate_summaries_for_papers(self, papers: list[dict], retry: bool = True) -> list[str]:
        """Generate summaries for a specific list of papers."""
        summaries = []
        providers = _load_providers_order()
        logger.info(f"Generating summaries (provider order: {providers})...")
        for index, paper in enumerate(papers):
            summaries.append(
                generate_summary(
                    title=paper["title"],
                    abstract=paper["abstract"],
                    retry=retry,
                )
            )
            if (index + 1) % 5 == 0:
                import time
                time.sleep(1)

        return summaries

    def generate_missing_summaries(self, limit: int = 50, include_failed: bool = True) -> dict:
        """Launch LLM summary requests separately for stored papers."""
        papers = self.db.get_papers_needing_summary(limit=limit, include_failed=include_failed)
        if not papers:
            return {
                "status": "no_work",
                "processed": 0,
                "updated": 0,
            }

        summaries = self._generate_summaries_for_papers(papers)
        updated = 0
        failed = 0
        for paper, summary in zip(papers, summaries):
            self.db.update_summary(paper["arxiv_id"], summary)
            updated += 1
            if summary == "AI Fail":
                failed += 1

        return {
            "status": "ok",
            "processed": len(papers),
            "updated": updated,
            "failed": failed,
            "provider": get_default_provider(),
        }

    def generate_summary_for_paper(self, arxiv_id: str) -> dict:
        """Generate or retry the summary for a single paper."""
        paper = self.db.get_paper(arxiv_id)
        if not paper:
            return {
                "status": "not_found",
                "arxiv_id": arxiv_id,
            }

        summary = self._generate_summaries_for_papers([paper], retry=False)[0]
        self.db.update_summary(arxiv_id, summary)

        # Re-read the DB so we return whatever is actually stored (update_summary
        # may have declined to overwrite a pre-existing real summary with AI Fail)
        stored_paper = self.db.get_paper(arxiv_id)
        stored_summary = (stored_paper or {}).get("summary") or summary

        return {
            "status": "ok",
            "arxiv_id": arxiv_id,
            "summary": stored_summary,
            "provider": get_default_provider(),
            "failed": stored_summary == "AI Fail" or not stored_summary,
        }

    def get_recommendations(self, limit: int = 50, unrated_only: bool = True) -> list[dict]:
        """Get papers ranked by predicted interest score with freshness boost.

        Ranking factors:
        - Preference model score (trained from user ratings)
        - Publication date (newer papers ranked higher)
        - Summary availability (papers with AI summaries ranked higher)

        Args:
            limit: Maximum number of papers to return.
            unrated_only: If True, only show papers not yet rated.

        Returns:
            List of paper dicts with added 'score' key, sorted by score descending.
        """
        from datetime import datetime, timedelta
        import numpy as np

        papers = self.db.get_papers(limit=500, unrated_only=unrated_only)
        if not papers:
            return []

        arxiv_ids = [p["arxiv_id"] for p in papers]
        papers_with_emb = self.db.get_papers_with_embeddings(arxiv_ids)

        if not papers_with_emb:
            for p in papers:
                p["score"] = 0.5
            return papers[:limit]

        emb_map = {p["arxiv_id"]: emb for p, emb in papers_with_emb}
        embeddings = []
        scorable_papers = []

        for paper in papers:
            if paper["arxiv_id"] in emb_map:
                embeddings.append(emb_map[paper["arxiv_id"]])
                scorable_papers.append(paper)

        # Get preference model scores
        if embeddings:
            model_scores = self.preference_model.predict_batch(embeddings)
            for paper, score in zip(scorable_papers, model_scores):
                paper["model_score"] = float(score)
        else:
            for paper in scorable_papers:
                paper["model_score"] = 0.5

        # Add unscorable papers
        scored_ids = {p["arxiv_id"] for p in scorable_papers}
        for paper in papers:
            if paper["arxiv_id"] not in scored_ids:
                paper["model_score"] = 0.5
                scorable_papers.append(paper)

        # Calculate composite score with freshness and summary bonuses
        now = datetime.fromisoformat(datetime.now().isoformat())
        for paper in scorable_papers:
            base_score = paper["model_score"]

            # Freshness boost: papers from last 7 days get a boost
            try:
                pub_date = datetime.fromisoformat(paper["published"].replace('Z', '+00:00'))
                days_old = (now - pub_date.replace(tzinfo=None)).days
                freshness_bonus = max(0, 0.15 * (1 - min(days_old / 7, 1)))
            except (ValueError, TypeError):
                freshness_bonus = 0

            # Summary bonus: papers with summaries get a small boost
            summary_bonus = 0.05 if paper.get("summary") and paper["summary"] != "AI Fail" else 0

            # Combine scores
            paper["score"] = round(min(1.0, base_score + freshness_bonus + summary_bonus), 4)
            paper["freshness_bonus"] = round(freshness_bonus, 4)

        # Sort by composite score, then by date (newest first)
        scorable_papers.sort(
            key=lambda p: (
                p["score"],
                p.get("published", ""),
            ),
            reverse=True
        )

        return scorable_papers[:limit]

    def rate_paper(self, arxiv_id: str, rating: int) -> dict:
        """Rate a paper and immediately update the model (online learning).

        Args:
            arxiv_id: The arXiv paper ID.
            rating: 1 for thumbs up, 0 for thumbs down.

        Returns:
            Dict with training result info.
        """
        # Save rating to database
        self.db.rate_paper(arxiv_id, rating)

        # Get paper embedding
        papers_emb = self.db.get_papers_with_embeddings([arxiv_id])
        if not papers_emb:
            return {"status": "rated", "trained": False, "reason": "no embedding"}

        _, embedding, = papers_emb[0]

        # Online learning: train on this single example
        loss = self.preference_model.train_single(embedding, float(rating))

        return {
            "status": "rated",
            "trained": True,
            "loss": loss,
            "total_trained": self.preference_model.total_trained,
        }

    def retrain_full(self, epochs: int = 20) -> dict:
        """Retrain the model on all rated papers from scratch.

        Useful after accumulating many ratings to get a better model.
        """
        embeddings, labels = self.db.get_training_data()

        if not embeddings:
            return {"status": "no_data", "message": "No rated papers with embeddings found"}

        # Reset model for full retrain
        embedding_dim = self.preference_model.embedding_dim
        self.preference_model = PreferenceModel(
            model_path=self.data_dir / "preference_model.pt",
            embedding_dim=embedding_dim,
        )
        # Don't load existing weights - fresh start
        self.preference_model.model_path = self.data_dir / "preference_model.pt"

        loss = self.preference_model.train_step(embeddings, labels, epochs=epochs)

        return {
            "status": "retrained",
            "num_samples": len(labels),
            "thumbs_up": sum(1 for label in labels if label > 0.5),
            "thumbs_down": sum(1 for label in labels if label <= 0.5),
            "final_loss": loss,
        }

    def get_stats(self) -> dict:
        """Get comprehensive statistics about the system."""
        db_stats = self.db.get_stats()
        model_stats = self.preference_model.get_stats()
        return {
            "database": db_stats,
            "model": model_stats,
            "categories": self.categories,
            "data_dir": str(self.data_dir),
        }

    def close(self):
        """Clean up resources."""
        self.db.close()
