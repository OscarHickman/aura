"""Recommendation engine that ties together fetching, embedding, and model scoring."""

import logging
import numpy as np
from pathlib import Path
from typing import cast, Optional

from .database import PaperDatabase
from .embedder import embed_papers_batch, get_embedding_dim
from .fetcher import PaperSource, ArxivSource, SemanticScholarSource, RSSSource, BiorxivSource, ADSSource
from .llm import generate_summary, get_default_provider, _load_providers_order
from .model import PreferenceModel

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Main engine that orchestrates paper fetching, embedding, scoring, and training."""

    def __init__(
        self,
        data_dir: str | Path,
        categories: list[str],
        embedding_model: str = "all-MiniLM-L6-v2",
        sources: list[PaperSource] | None = None,
        rss_urls: list[str] | None = None,
        sources_config: dict[str, bool] | None = None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.categories = categories
        self.embedding_model = embedding_model
        
        if sources:
            self.sources = sources
        else:
            self.sources = []
            sc = sources_config or {"arxiv": True, "semantic_scholar": True, "biorxiv": True, "rss": True}
            
            if sc.get("arxiv", True):
                self.sources.append(ArxivSource())
            if sc.get("semantic_scholar", True):
                self.sources.append(SemanticScholarSource())
            if sc.get("biorxiv", True):
                self.sources.append(BiorxivSource())
            if sc.get("rss", True):
                self.sources.append(RSSSource(feed_urls=rss_urls))
            if sc.get("ads", False):
                self.sources.append(ADSSource())

        # Initialize components
        self.db = PaperDatabase(self.data_dir / "papers.db")

        self._embedding_dim = get_embedding_dim(embedding_model)
        # Legacy default model (user_id=1 / single-user deployments)
        self.preference_model = PreferenceModel(
            model_path=self.data_dir / "preference_model.pt",
            embedding_dim=self._embedding_dim,
        )
        self.shadow_model = PreferenceModel(
            model_path=self.data_dir / "preference_model_shadow.pt",
            embedding_dim=self._embedding_dim,
            learning_rate=5e-4,
            hidden_dims=[64, 32],
        )
        # Per-user model cache: {user_id: PreferenceModel}
        self._user_models: dict[int, PreferenceModel] = {1: self.preference_model}
        self._user_shadow_models: dict[int, PreferenceModel] = {1: self.shadow_model}

        # Initialize Vector Store
        try:
            from .config import get_validated_config
            from .vector_store import NumpyVectorStore, QdrantVectorStore
            cfg = get_validated_config()
            vs_conf = cfg.get("vector_store", {})
            if vs_conf.get("provider") == "qdrant" and vs_conf.get("url"):
                self.vector_store = QdrantVectorStore(
                    url=vs_conf["url"],
                    api_key=vs_conf.get("api_key"),
                    collection_name=vs_conf.get("collection_name", "aura_papers"),
                    embedding_dim=self._embedding_dim
                )
                self._migrate_to_vector_store()
            else:
                self.vector_store = NumpyVectorStore(self.db)
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            from .vector_store import NumpyVectorStore
            self.vector_store = NumpyVectorStore(self.db)

    def _migrate_to_vector_store(self) -> None:
        """Migrate existing paper embeddings to Qdrant vector database on startup if empty."""
        from .vector_store import QdrantVectorStore
        if not hasattr(self, "vector_store") or not isinstance(self.vector_store, QdrantVectorStore) or not self.vector_store.client:
            return
            
        try:
            collection_info = self.vector_store.client.get_collection(self.vector_store.collection_name)
            if collection_info.points_count > 0:
                logger.info("Vector database collection already populated. Skipping migration.")
                return
                
            logger.info("Migrating existing SQLite paper embeddings to Qdrant...")
            all_papers = self.db.get_papers_with_embeddings()
            if not all_papers:
                logger.info("No papers in SQLite database to migrate.")
                return
                
            arxiv_ids = [p["arxiv_id"] for p, _ in all_papers]
            embeddings = [emb for _, emb in all_papers]
            
            batch_size = 100
            for i in range(0, len(arxiv_ids), batch_size):
                batch_ids = arxiv_ids[i:i+batch_size]
                batch_embs = embeddings[i:i+batch_size]
                self.vector_store.add_papers_batch(batch_ids, batch_embs)
                
            logger.info(f"Successfully migrated {len(arxiv_ids)} paper embeddings to Qdrant vector database.")
        except Exception as e:
            logger.error(f"Failed to migrate paper embeddings to Qdrant: {e}")

    def get_user_preference_model(self, user_id: int) -> PreferenceModel:
        """Return the preference model for a given user, creating it if needed."""
        if user_id in self._user_models:
            return self._user_models[user_id]
        models_dir = self.data_dir / "models"
        models_dir.mkdir(exist_ok=True)
        model = PreferenceModel(
            model_path=models_dir / f"{user_id}.pt",
            embedding_dim=self._embedding_dim,
        )
        self._user_models[user_id] = model
        return model

    def get_user_shadow_model(self, user_id: int) -> PreferenceModel:
        """Return the shadow preference model for a given user, creating it if needed."""
        if user_id in self._user_shadow_models:
            return self._user_shadow_models[user_id]
        models_dir = self.data_dir / "models"
        models_dir.mkdir(exist_ok=True)
        model = PreferenceModel(
            model_path=models_dir / f"{user_id}_shadow.pt",
            embedding_dim=self._embedding_dim,
            learning_rate=5e-4,
            hidden_dims=[64, 32],
        )
        self._user_shadow_models[user_id] = model
        return model

    def fetch_new_papers(
        self,
        max_results: int = 200,
        days_back: int = 2,
        generate_summaries: bool = False,
    ) -> int:
        """Fetch new papers from all sources, embed them, and store in database.

        Returns the number of new papers added.
        """
        logger.info(f"Fetching papers for categories: {self.categories}")

        all_papers = []
        for source in self.sources:
            try:
                # Try date-filtered fetch first, fall back to simple fetch
                papers = source.fetch(
                    self.categories, max_results=max_results, days_back=days_back
                )
                if not papers:
                    logger.info(f"Date-filtered fetch returned no papers for {source.__class__.__name__}, trying simple fetch")
                    papers = source.fetch_simple(self.categories, max_results=max_results)
                
                if papers:
                    all_papers.extend(papers)
            except Exception as e:
                logger.error(f"Error fetching from {source.__class__.__name__}: {e}")

        if not all_papers:
            logger.warning("No papers fetched from any source")
            return 0

        # Split fetched papers into new records and existing records that still
        # need summaries.
        existing_ids = set()
        papers_needing_summary = []
        for paper in all_papers:
            existing_paper = self.db.get_paper(paper["arxiv_id"])
            if existing_paper:
                existing_ids.add(paper["arxiv_id"])
                if not existing_paper.get("summary"):
                    papers_needing_summary.append(paper)

        new_papers = [p for p in all_papers if p["arxiv_id"] not in existing_ids]

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

        if count > 0:
            try:
                arxiv_ids = [p["arxiv_id"] for p in new_papers]
                self.vector_store.add_papers_batch(arxiv_ids, embeddings)
            except Exception as e:
                logger.error(f"Failed to index papers in vector store: {e}")

        if count > 0:
            try:
                from .config import get_validated_config
                from .notifications import notify_high_scoring_papers
                cfg = get_validated_config()
                notify_high_scoring_papers(self, new_papers, cfg)
            except Exception as e:
                logger.error(f"Failed to dispatch integration notifications: {e}")

        if generate_summaries and papers_needing_summary:
            self.generate_missing_summaries(
                limit=len(papers_needing_summary), include_failed=False
            )

        logger.info(f"Added {count} new papers to database")
        return count

    def fetch_and_add_paper(self, arxiv_id: str) -> Optional[dict]:
        """Fetch a specific paper from arXiv, embed it, summarize it, and add to database."""
        existing = self.db.get_paper(arxiv_id)
        if existing:
            return existing

        from .fetcher import ArxivSource
        source = ArxivSource()
        paper = source.fetch_by_id(arxiv_id)
        if not paper:
            return None

        from .embedder import embed_papers_batch
        embeddings = embed_papers_batch([paper], model_name=self.embedding_model)

        summaries = self._generate_summaries_for_papers([paper])
        summary = summaries[0] if summaries else None

        self.db.add_papers_batch([paper], embeddings, [summary] if summary else None)
        if len(embeddings) > 0:
            try:
                self.vector_store.add_paper(arxiv_id, embeddings[0])
            except Exception as e:
                logger.error(f"Failed to index single paper in vector store: {e}")
        return self.db.get_paper(arxiv_id)

    def _generate_summaries_for_papers(
        self, papers: list[dict], retry: bool = True, progress_callback=None
    ) -> list[str]:
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
            if progress_callback:
                progress_callback(index + 1, len(papers))
            if (index + 1) % 5 == 0:
                import time

                time.sleep(1)

        return summaries

    def generate_missing_summaries(
        self, limit: int = 50, include_failed: bool = True, progress_callback=None
    ) -> dict:
        """Launch LLM summary requests separately for stored papers."""
        papers = self.db.get_papers_needing_summary(
            limit=limit, include_failed=include_failed
        )
        if not papers:
            return {
                "status": "no_work",
                "processed": 0,
                "updated": 0,
            }

        summaries = self._generate_summaries_for_papers(papers, progress_callback=progress_callback)
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

    def get_or_generate_full_summary(self, arxiv_id: str, mode: str = "grad_student") -> str:
        """Fetch the full paper structured summary from cache or generate it."""
        # 1. Check cache
        cached = self.db.get_full_summary(arxiv_id, mode)
        if cached:
            logger.info(f"Loaded cached full summary for {arxiv_id} (mode: {mode})")
            return cached

        # 2. Get paper from DB
        paper = self.db.get_paper(arxiv_id)
        if not paper:
            return f"Error: Paper {arxiv_id} not found in database."

        pdf_url = paper.get("pdf_url")
        if not pdf_url:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        # 3. Generate summary
        from .llm import generate_full_summary
        summary = generate_full_summary(arxiv_id, pdf_url, mode)

        # 4. Cache if successful
        if summary and not summary.startswith("Error:"):
            self.db.add_full_summary(arxiv_id, mode, summary)
            logger.info(f"Cached new full summary for {arxiv_id} (mode: {mode})")

        return summary

    def ask_paper_question(self, arxiv_id: str, question: str):
        """Answer a question about a paper using its full text, caching the text in DB."""
        # 1. Check if paper text is cached in database
        full_text = self.db.get_paper_text(arxiv_id)
        
        # 2. If not cached, we need to extract it
        if not full_text:
            paper = self.db.get_paper(arxiv_id)
            if not paper:
                yield f"Error: Paper {arxiv_id} not found in database."
                return
            
            pdf_url = paper.get("pdf_url")
            if not pdf_url:
                pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                
            try:
                from .llm import extract_text_from_pdf_url
                full_text = extract_text_from_pdf_url(pdf_url)
                if full_text and not full_text.startswith("Error:"):
                    self.db.add_paper_text(arxiv_id, full_text)
                    logger.info(f"Extracted and cached full text for paper {arxiv_id}")
            except Exception as e:
                logger.error(f"Failed to extract full text for paper {arxiv_id}: {e}")
                yield f"Error: Failed to download or parse paper PDF ({e})"
                return
                
        if not full_text or not full_text.strip():
            yield "Error: Extracted text from paper PDF was empty."
            return

        # 3. Stream answer from LLM
        from .llm import stream_ask_paper
        for chunk in stream_ask_paper(arxiv_id, question, full_text):
            yield chunk

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

    def get_recommendations(
        self, limit: int = 50, unrated_only: bool = True, user_id: int = 1
    ) -> list[dict]:
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
        from datetime import datetime

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
        pref_model = self.get_user_preference_model(user_id)
        shadow_model = self.get_user_shadow_model(user_id)
        if embeddings:
            model_scores, uncertainties = pref_model.predict_batch(embeddings)
            shadow_scores, _ = shadow_model.predict_batch(embeddings)
            for paper, score, unc, sh_score in zip(scorable_papers, model_scores, uncertainties, shadow_scores):
                paper["model_score"] = float(score)
                paper["model_uncertainty"] = float(unc)
                paper["shadow_score"] = float(sh_score)
        else:
            for paper in scorable_papers:
                paper["model_score"] = 0.5
                paper["model_uncertainty"] = 0.0
                paper["shadow_score"] = 0.5

        # Add unscorable papers
        scored_ids = {p["arxiv_id"] for p in scorable_papers}
        for paper in papers:
            if paper["arxiv_id"] not in scored_ids:
                paper["model_score"] = 0.5
                paper["model_uncertainty"] = 0.0
                paper["shadow_score"] = 0.5
                scorable_papers.append(paper)

        # Get rated papers to identify liked ones
        rated_papers = self.db.get_rated_papers()
        liked_arxiv_ids = [p["arxiv_id"] for p, emb, rating in rated_papers if rating >= 4 or rating == 1]
        liked_citations_map = self.db.get_liked_citations_counts(liked_arxiv_ids)
        liked_references_map = self.db.get_liked_references_counts(liked_arxiv_ids)

        # Calculate composite score with freshness and summary bonuses
        now = datetime.fromisoformat(datetime.now().isoformat())
        for paper in scorable_papers:
            base_score = paper["model_score"]

            # Freshness boost: papers from last 7 days get a boost
            try:
                pub_date = datetime.fromisoformat(
                    paper["published"].replace("Z", "+00:00")
                )
                days_old = (now - pub_date.replace(tzinfo=None)).days
                freshness_bonus = max(0, 0.15 * (1 - min(days_old / 7, 1)))
            except (ValueError, TypeError):
                freshness_bonus = 0

            # Summary bonus: papers with summaries get a small boost
            summary_bonus = (
                0.05 if paper.get("summary") and paper["summary"] != "AI Fail" else 0
            )

            # Citation bonus: log-scaled boost based on citation count
            import math
            citation_count = paper.get("citation_count") or 0
            citation_bonus = min(0.1, math.log10(citation_count + 1) * 0.02)

            # Read count bonus: log-scaled boost based on ADS read count
            read_count = paper.get("read_count") or 0
            read_bonus = min(0.05, math.log10(read_count + 1) * 0.01)

            # Refereed status bonus: small boost for peer-reviewed publications
            refereed_bonus = 0.03 if paper.get("refereed") else 0

            # Citation graph boost: boost based on liked citing/referenced papers
            liked_cite_cnt = liked_citations_map.get(paper["arxiv_id"], 0)
            liked_ref_cnt = liked_references_map.get(paper["arxiv_id"], 0)
            citation_graph_bonus = min(0.15, liked_cite_cnt * 0.05 + liked_ref_cnt * 0.02)

            # Combine scores
            paper["score"] = round(
                min(1.0, base_score + freshness_bonus + summary_bonus + citation_bonus + read_bonus + refereed_bonus + citation_graph_bonus), 4
            )
            paper["freshness_bonus"] = round(freshness_bonus, 4)
            paper["summary_bonus"] = round(summary_bonus, 4)
            paper["citation_bonus"] = round(citation_bonus, 4)
            paper["read_bonus"] = round(read_bonus, 4)
            paper["refereed_bonus"] = round(refereed_bonus, 4)
            paper["citation_graph_bonus"] = round(citation_graph_bonus, 4)

        # Explainability: attach the most similar liked paper to each recommendation
        liked_papers_emb = [(p, emb) for p, emb, rating in rated_papers if rating >= 4 or rating == 1]

        if liked_papers_emb and scorable_papers:
            liked_embs_mat = np.array([emb for p, emb in liked_papers_emb])
            liked_embs_norm = np.linalg.norm(liked_embs_mat, axis=1, keepdims=True)
            liked_embs_mat_normalized = np.divide(
                liked_embs_mat,
                liked_embs_norm,
                out=np.zeros_like(liked_embs_mat),
                where=liked_embs_norm != 0
            )

            for paper in scorable_papers:
                if paper["arxiv_id"] in emb_map:
                    paper_emb = emb_map[paper["arxiv_id"]]
                    paper_norm = np.linalg.norm(paper_emb)
                    if paper_norm > 0:
                        paper_emb_normalized = paper_emb / paper_norm
                        sims = np.dot(liked_embs_mat_normalized, paper_emb_normalized)
                        best_idx = np.argmax(sims)
                        paper["reason_liked_paper"] = liked_papers_emb[best_idx][0]["title"]
                        paper["reason_liked_sim"] = round(float(sims[best_idx]), 4)

        # Sort by composite score, then by date (newest first)
        scorable_papers.sort(
            key=lambda p: (
                p["score"],
                p.get("published", ""),
            ),
            reverse=True,
        )

        return scorable_papers[:limit]

    def get_similar_liked_papers(self, arxiv_id: str, limit: int = 3) -> list[dict]:
        """Find the most similar papers that the user has previously liked.

        Useful for recommendation explainability via a dedicated endpoint.
        """
        current_data = self.db.get_papers_with_embeddings([arxiv_id])
        if not current_data:
            return []

        _, current_emb = current_data[0]

        rated_papers = self.db.get_rated_papers(user_id=1)
        liked_papers = [(p, emb) for p, emb, rating in rated_papers if rating >= 4 or rating == 1]

        similarities = []
        for paper, emb in liked_papers:
            if paper["arxiv_id"] == arxiv_id:
                continue

            dot = np.dot(current_emb, emb)
            norm_curr = np.linalg.norm(current_emb)
            norm_other = np.linalg.norm(emb)

            sim = float(dot / (norm_curr * norm_other)) if norm_curr > 0 and norm_other > 0 else 0.0

            paper["similarity"] = round(sim, 4)
            similarities.append(paper)

        similarities.sort(key=lambda p: p["similarity"], reverse=True)
        return similarities[:limit]

    def rate_paper(self, arxiv_id: str, rating: int, user_id: int = 1) -> dict:
        """Rate a paper and immediately update the model (online learning).

        Args:
            arxiv_id: The arXiv paper ID.
            rating: 1-5 for stars, -1 for skip.

        Returns:
            Dict with training result info.
        """
        # Save rating to database
        self.db.rate_paper(arxiv_id, rating, user_id=user_id)

        if rating == -1:
            return {"status": "rated", "trained": False, "reason": "skipped"}

        # Get paper embedding
        papers_emb = self.db.get_papers_with_embeddings([arxiv_id])
        if not papers_emb:
            return {"status": "rated", "trained": False, "reason": "no embedding"}

        _, embedding = papers_emb[0]

        # Map legacy 0/1 to 0.0/1.0, and 1-5 stars to 0.0-1.0
        if rating == 0:
            label = 0.0
        elif rating == 1:
            label = 1.0
        else:
            label = (rating - 1) / 4.0

        pref_model = self.get_user_preference_model(user_id)
        loss = pref_model.train_single(embedding, label, arxiv_id=arxiv_id)

        shadow_model = self.get_user_shadow_model(user_id)
        shadow_model.train_single(embedding, label, arxiv_id=arxiv_id)

        return {
            "status": "rated",
            "trained": True,
            "loss": loss,
            "total_trained": pref_model.total_trained,
        }

    def retrain_full(self, epochs: int = 20, user_id: int = 1, progress_callback=None) -> dict:
        """Retrain a user's model on all their rated papers from scratch."""
        embeddings, labels = self.db.get_training_data(user_id=user_id)

        if not embeddings:
            return {
                "status": "no_data",
                "message": "No rated papers with embeddings found",
            }

        pref_model = self.get_user_preference_model(user_id)
        pref_model = PreferenceModel(
            model_path=pref_model.model_path,
            embedding_dim=self._embedding_dim,
        )
        self._user_models[user_id] = pref_model
        if user_id == 1:
            self.preference_model = pref_model

        loss = pref_model.train_step(
            embeddings, labels, epochs=epochs, progress_callback=progress_callback, use_scheduler=True
        )

        # Retrain shadow model
        shadow_model = self.get_user_shadow_model(user_id)
        shadow_model = PreferenceModel(
            model_path=shadow_model.model_path,
            embedding_dim=self._embedding_dim,
            learning_rate=5e-4,
            hidden_dims=[64, 32],
        )
        self._user_shadow_models[user_id] = shadow_model
        shadow_model.train_step(
            embeddings, labels, epochs=epochs, progress_callback=None, use_scheduler=True
        )

        return {
            "status": "retrained",
            "num_samples": len(labels),
            "thumbs_up": sum(1 for label in labels if label > 0.5),
            "thumbs_down": sum(1 for label in labels if label <= 0.5),
            "final_loss": loss,
        }

    def get_stats(self, user_id: int = 1) -> dict:
        """Get comprehensive statistics about the system."""
        db_stats = self.db.get_stats(user_id=user_id)
        pref_model = self.get_user_preference_model(user_id)
        model_stats = pref_model.get_stats()
        return {
            "database": db_stats,
            "model": model_stats,
            "categories": self.categories,
            "data_dir": str(self.data_dir),
        }

    def get_similar_papers(self, arxiv_id: str, limit: int = 5) -> list[dict]:
        """Find papers similar to the one specified by arxiv_id based on cosine similarity of their embeddings.

        Args:
            arxiv_id: The arXiv ID of the paper.
            limit: Maximum number similar papers to return.

        Returns:
            List of paper dicts with an added 'similarity' key, sorted by similarity descending.
        """
        # Fetch current paper's embedding
        current_data = self.db.get_papers_with_embeddings([arxiv_id])
        if not current_data:
            return []

        _, current_emb = current_data[0]

        # Use vector store to query
        similar_ids = self.vector_store.search_similar(current_emb, limit + 1)

        similarities = []
        for other_id, sim in similar_ids:
            if other_id == arxiv_id:
                continue
            paper = self.db.get_paper(other_id)
            if paper:
                paper["similarity"] = round(sim, 4)
                paper["rating"] = self.db.get_latest_rating(other_id)
                similarities.append(paper)

        return similarities[:limit]

    def semantic_search(self, query: str, limit: int = 20) -> list[dict]:
        """Search for papers using semantic similarity to the query string."""
        from .embedder import embed_text
        
        query_emb = embed_text(query, model_name=self.embedding_model)
        
        # Use vector store to query
        similar_ids = self.vector_store.search_similar(query_emb, limit)
        
        similarities = []
        for other_id, sim in similar_ids:
            paper = self.db.get_paper(other_id)
            if paper:
                paper["similarity"] = round(sim, 4)
                paper["rating"] = self.db.get_latest_rating(other_id)
                similarities.append(paper)
                
        return similarities[:limit]

    def get_diverse_papers(self, limit: int = 20) -> list[dict]:
        """Get a diverse set of unrated papers using k-means clustering on embeddings.
        
        Useful for cold-start onboarding to capture broad user interests.
        """
        from sklearn.cluster import KMeans

        papers = self.db.get_papers(limit=1000, unrated_only=True)
        if not papers:
            return []

        if len(papers) <= limit:
            return papers

        arxiv_ids = [p["arxiv_id"] for p in papers]
        papers_with_emb = self.db.get_papers_with_embeddings(arxiv_ids)

        if len(papers_with_emb) < limit:
            # Fallback if not enough embeddings: just return recent papers
            return papers[:limit]

        # Extract embeddings and corresponding paper dicts
        embeddings = []
        emb_papers = []
        emb_map = {p["arxiv_id"]: emb for p, emb in papers_with_emb}
        
        for paper in papers:
            if paper["arxiv_id"] in emb_map:
                embeddings.append(emb_map[paper["arxiv_id"]])
                emb_papers.append(paper)

        X = np.array(embeddings)
        
        # Use k-means to find clusters
        n_clusters = limit
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        # Select one paper from each cluster closest to the centroid
        diverse_papers = []
        for i in range(n_clusters):
            cluster_indices = np.where(labels == i)[0]
            if len(cluster_indices) > 0:
                # Find the paper closest to the cluster center
                centroid = kmeans.cluster_centers_[i]
                cluster_embeddings = X[cluster_indices]
                distances = np.linalg.norm(cluster_embeddings - centroid, axis=1)
                closest_index = cluster_indices[np.argmin(distances)]
                diverse_papers.append(emb_papers[closest_index])

        return diverse_papers

    def discover_topics(self, n_clusters: int = 5, limit_papers: int = 500) -> list[dict]:
        """Auto-discover topic clusters from recent papers using K-Means."""
        from sklearn.cluster import KMeans
        import collections
        import re

        papers = self.db.get_papers(limit=limit_papers)
        if not papers:
            return []

        arxiv_ids = [p["arxiv_id"] for p in papers]
        papers_with_emb = self.db.get_papers_with_embeddings(arxiv_ids)
        
        if len(papers_with_emb) < n_clusters:
            return []

        embeddings = []
        emb_papers = []
        emb_map = {p["arxiv_id"]: emb for p, emb in papers_with_emb}
        
        for paper in papers:
            if paper["arxiv_id"] in emb_map:
                embeddings.append(emb_map[paper["arxiv_id"]])
                emb_papers.append(paper)

        X = np.array(embeddings)
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X)

        topics = []
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "with", "to", "for", "of", "at", "by", "from", "is", "are", "was", "were", "be", "been", "being", "it", "this", "that", "these", "those", "we", "our", "us", "they", "their", "them", "as", "model", "models", "paper", "proposed", "method", "results", "using", "based", "which", "can", "new"}

        for i in range(n_clusters):
            cluster_indices = np.where(labels == i)[0]
            if len(cluster_indices) == 0:
                continue
                
            cluster_papers = [emb_papers[idx] for idx in cluster_indices]
            
            # Simple TF-IDF approximation for topic naming: extract common words from titles/abstracts
            word_counts: collections.Counter[str] = collections.Counter()
            for p in cluster_papers:
                text = (p["title"] + " " + p["abstract"]).lower()
                words = re.findall(r'\b[a-z]{3,}\b', text)
                for w in words:
                    if w not in stop_words:
                        word_counts[w] += 1
            
            # Get top 3 words to form a name
            top_words = [w for w, c in word_counts.most_common(5)]
            topic_name = " ".join(top_words[:3]).title() if top_words else f"Topic {i+1}"
            
            # Find representative papers (closest to centroid)
            centroid = kmeans.cluster_centers_[i]
            cluster_embeddings = X[cluster_indices]
            distances = np.linalg.norm(cluster_embeddings - centroid, axis=1)
            
            # Sort papers by distance to centroid
            sorted_indices = np.argsort(distances)
            top_papers = [cluster_papers[idx] for idx in sorted_indices[:5]]
            
            topics.append({
                "id": i,
                "name": topic_name,
                "keywords": top_words,
                "paper_count": len(cluster_papers),
                "top_papers": top_papers
            })

        # Sort topics by size descending
        topics.sort(key=lambda t: cast(int, t["paper_count"]), reverse=True)
        return topics

    def _get_s2_arxiv_id(self, entry: dict) -> Optional[str]:
        ext_ids = entry.get("externalIds") or {}
        arxiv_id = ext_ids.get("ArXiv")
        if arxiv_id:
            return arxiv_id
        paper_id = entry.get("paperId")
        if paper_id:
            return f"s2:{paper_id}"
        return None

    def fetch_and_store_citations(self, arxiv_id: str) -> None:
        """Fetch citations and references from Semantic Scholar and store them in the database."""
        # Check if already fetched
        paper = self.db.get_paper(arxiv_id)
        if not paper or paper.get("citations_fetched"):
            return

        # Prepare paper ID for Semantic Scholar
        if arxiv_id.startswith("s2:"):
            s2_id = arxiv_id.split(":", 1)[1]
        else:
            s2_id = f"arXiv:{arxiv_id}"

        url = f"https://api.semanticscholar.org/graph/v1/paper/{s2_id}"
        params = {
            "fields": "citations.externalIds,citations.paperId,references.externalIds,references.paperId"
        }

        # Check config or environment for Semantic Scholar API key
        import os
        headers = {}
        s2_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        if s2_key:
            headers["x-api-key"] = s2_key

        logger.info(f"Fetching citations and references for paper {arxiv_id} from Semantic Scholar")
        try:
            import requests
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            # Handle rate limiting politely
            if resp.status_code == 429:
                logger.warning(f"Semantic Scholar API rate limited (429) when fetching citations for {arxiv_id}.")
                return
            resp.raise_for_status()
            data = resp.json()

            links = []
            
            # Citing papers (papers that cite the current paper)
            for cit in data.get("citations") or []:
                cit_id = self._get_s2_arxiv_id(cit)
                if cit_id:
                    links.append((cit_id, arxiv_id))

            # Referenced papers (papers cited by the current paper)
            for ref in data.get("references") or []:
                ref_id = self._get_s2_arxiv_id(ref)
                if ref_id:
                    links.append((arxiv_id, ref_id))

            if links:
                self.db.add_citations_batch(links)

            self.db.mark_citations_fetched(arxiv_id, True)
            logger.info(f"Stored {len(links)} citation connections for paper {arxiv_id}")

        except Exception as e:
            logger.error(f"Failed to fetch citations/references for paper {arxiv_id}: {e}")

    def get_or_fetch_citations(self, arxiv_id: str) -> tuple[list[dict], list[dict]]:
        """Get citing and cited papers from the database.
        If not fetched yet, fetch from Semantic Scholar first.
        Returns:
            tuple of (citing_papers, cited_papers)
        """
        paper = self.db.get_paper(arxiv_id)
        if not paper:
            return [], []

        if not paper.get("citations_fetched"):
            self.fetch_and_store_citations(arxiv_id)

        citing = self.db.get_papers_citing(arxiv_id)
        cited = self.db.get_papers_cited_by(arxiv_id)
        return citing, cited

    def close(self):
        """Clean up resources."""
        self.db.close()
