"""SQLite database for storing papers, embeddings, and user ratings."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class PaperDatabase:
    """SQLite database for papers, embeddings, and user feedback."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        """Create database tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS papers (
                arxiv_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                abstract TEXT NOT NULL,
                authors TEXT NOT NULL,
                categories TEXT NOT NULL,
                published TEXT NOT NULL,
                url TEXT,
                pdf_url TEXT,
                fetched_at TEXT NOT NULL,
                embedding BLOB,
                summary TEXT
            );

            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arxiv_id TEXT NOT NULL,
                rating INTEGER NOT NULL,
                rated_at TEXT NOT NULL,
                FOREIGN KEY (arxiv_id) REFERENCES papers(arxiv_id)
            );

            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at TEXT NOT NULL,
                num_papers INTEGER NOT NULL,
                categories TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_history (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                result TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_papers_published ON papers(published);
            CREATE INDEX IF NOT EXISTS idx_ratings_arxiv_id ON ratings(arxiv_id);
            CREATE INDEX IF NOT EXISTS idx_ratings_rated_at ON ratings(rated_at);
            CREATE INDEX IF NOT EXISTS idx_task_history_status ON task_history(status);

            -- FTS5 virtual table for full-text search
            CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
                arxiv_id UNINDEXED,
                title,
                abstract
            );

            -- Triggers to keep FTS table in sync
            CREATE TRIGGER IF NOT EXISTS papers_ai AFTER INSERT ON papers BEGIN
                INSERT INTO papers_fts(arxiv_id, title, abstract)
                VALUES (new.arxiv_id, new.title, new.abstract);
            END;

            CREATE TRIGGER IF NOT EXISTS papers_ad AFTER DELETE ON papers BEGIN
                DELETE FROM papers_fts WHERE arxiv_id = old.arxiv_id;
            END;

            CREATE TRIGGER IF NOT EXISTS papers_au AFTER UPDATE OF title, abstract ON papers BEGIN
                UPDATE papers_fts SET
                    title = new.title,
                    abstract = new.abstract
                WHERE arxiv_id = old.arxiv_id;
            END;
        """)
        self.conn.commit()

        # Backfill existing papers into the FTS virtual table
        self.conn.execute("""
            INSERT INTO papers_fts(arxiv_id, title, abstract)
            SELECT arxiv_id, title, abstract FROM papers
            WHERE NOT EXISTS (
                SELECT 1 FROM papers_fts WHERE papers_fts.arxiv_id = papers.arxiv_id
            )
        """)
        self.conn.commit()

    def add_paper(
        self,
        paper: dict,
        embedding: Optional[np.ndarray] = None,
        summary: Optional[str] = None,
    ) -> bool:
        """Add a paper to the database. Returns True if newly inserted."""
        try:
            emb_blob = embedding.tobytes() if embedding is not None else None
            cursor = self.conn.execute(
                """INSERT OR IGNORE INTO papers
                   (arxiv_id, title, abstract, authors, categories, published, url, pdf_url, fetched_at, embedding, summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    paper["arxiv_id"],
                    paper["title"],
                    paper["abstract"],
                    json.dumps(paper["authors"]),
                    json.dumps(paper["categories"]),
                    paper["published"],
                    paper.get("url", ""),
                    paper.get("pdf_url", ""),
                    datetime.utcnow().isoformat(),
                    emb_blob,
                    summary,
                ),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to add paper {paper.get('arxiv_id')}: {e}")
            return False

    def add_papers_batch(
        self,
        papers: list[dict],
        embeddings: Optional[list[np.ndarray]] = None,
        summaries: Optional[list[str]] = None,
    ) -> int:
        """Add multiple papers. Returns count of newly inserted papers."""
        now = datetime.utcnow().isoformat()
        count = 0
        for i, paper in enumerate(papers):
            emb_blob = (
                embeddings[i].tobytes() if embeddings and i < len(embeddings) else None
            )
            summary = summaries[i] if summaries and i < len(summaries) else None
            try:
                cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO papers
                       (arxiv_id, title, abstract, authors, categories, published, url, pdf_url, fetched_at, embedding, summary)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        paper["arxiv_id"],
                        paper["title"],
                        paper["abstract"],
                        json.dumps(paper["authors"]),
                        json.dumps(paper["categories"]),
                        paper["published"],
                        paper.get("url", ""),
                        paper.get("pdf_url", ""),
                        now,
                        emb_blob,
                        summary,
                    ),
                )
                if cursor.rowcount > 0:
                    count += 1
            except sqlite3.Error as e:
                logger.error(f"Failed to add paper {paper.get('arxiv_id')}: {e}")
        self.conn.commit()
        return count

    def update_embedding(self, arxiv_id: str, embedding: np.ndarray):
        """Update the embedding for an existing paper."""
        self.conn.execute(
            "UPDATE papers SET embedding = ? WHERE arxiv_id = ?",
            (embedding.tobytes(), arxiv_id),
        )
        self.conn.commit()

    def update_summary(self, arxiv_id: str, summary: str):
        """Update the summary for an existing paper.

        'AI Fail' will never overwrite an existing non-empty, non-failed summary.
        """
        if summary == "AI Fail":
            # Only write AI Fail when there is no real summary already stored
            self.conn.execute(
                """
                UPDATE papers SET summary = ?
                WHERE arxiv_id = ?
                  AND (summary IS NULL OR summary = '' OR summary = 'AI Fail')
                """,
                (summary, arxiv_id),
            )
        else:
            self.conn.execute(
                "UPDATE papers SET summary = ? WHERE arxiv_id = ?",
                (summary, arxiv_id),
            )
        self.conn.commit()

    def get_paper(self, arxiv_id: str) -> Optional[dict]:
        """Get a single paper by arXiv ID."""
        row = self.conn.execute(
            "SELECT * FROM papers WHERE arxiv_id = ?", (arxiv_id,)
        ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_papers(
        self,
        limit: int = 100,
        offset: int = 0,
        unrated_only: bool = False,
        rated_only: bool = False,
    ) -> list[dict]:
        """Get papers with optional filtering."""
        if unrated_only:
            query = """
                SELECT p.* FROM papers p
                LEFT JOIN ratings r ON p.arxiv_id = r.arxiv_id
                WHERE r.id IS NULL
                ORDER BY p.published DESC
                LIMIT ? OFFSET ?
            """
        elif rated_only:
            query = """
                SELECT DISTINCT p.* FROM papers p
                INNER JOIN ratings r ON p.arxiv_id = r.arxiv_id
                ORDER BY p.published DESC
                LIMIT ? OFFSET ?
            """
        else:
            query = "SELECT * FROM papers ORDER BY published DESC LIMIT ? OFFSET ?"

        rows = self.conn.execute(query, (limit, offset)).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_papers_needing_summary(
        self, limit: int = 100, include_failed: bool = True
    ) -> list[dict]:
        """Get papers whose summaries should be generated or retried."""
        if include_failed:
            query = """
                SELECT * FROM papers
                WHERE summary IS NULL OR summary = '' OR summary = 'AI Fail'
                ORDER BY published DESC
                LIMIT ?
            """
        else:
            query = """
                SELECT * FROM papers
                WHERE summary IS NULL OR summary = ''
                ORDER BY published DESC
                LIMIT ?
            """

        rows = self.conn.execute(query, (limit,)).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_papers_with_embeddings(
        self, arxiv_ids: Optional[list[str]] = None
    ) -> list[tuple[dict, np.ndarray]]:
        """Get papers that have embeddings, optionally filtered by IDs."""
        if arxiv_ids:
            placeholders = ",".join("?" * len(arxiv_ids))
            rows = self.conn.execute(
                f"SELECT * FROM papers WHERE embedding IS NOT NULL AND arxiv_id IN ({placeholders})",
                arxiv_ids,
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM papers WHERE embedding IS NOT NULL"
            ).fetchall()

        results = []
        for row in rows:
            paper = self._row_to_dict(row)
            embedding = np.frombuffer(row["embedding"], dtype=np.float32)
            results.append((paper, embedding))
        return results

    def rate_paper(self, arxiv_id: str, rating: int) -> bool:
        """Rate a paper: 1 = thumbs up, 0 = thumbs down.

        Multiple ratings for the same paper are allowed (tracks history),
        but only the latest is used for training.
        """
        if rating not in (0, 1):
            raise ValueError("Rating must be 0 (thumbs down) or 1 (thumbs up)")

        try:
            self.conn.execute(
                "INSERT INTO ratings (arxiv_id, rating, rated_at) VALUES (?, ?, ?)",
                (arxiv_id, rating, datetime.utcnow().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to rate paper {arxiv_id}: {e}")
            return False

    def get_latest_rating(self, arxiv_id: str) -> Optional[int]:
        """Get the most recent rating for a paper."""
        row = self.conn.execute(
            "SELECT rating FROM ratings WHERE arxiv_id = ? ORDER BY rated_at DESC LIMIT 1",
            (arxiv_id,),
        ).fetchone()
        return row["rating"] if row else None

    def get_rated_papers(self) -> list[tuple[dict, np.ndarray, int]]:
        """Get all rated papers with their embeddings and latest ratings.

        Returns list of (paper_dict, embedding, rating) tuples.
        Only includes papers that have embeddings.
        """
        rows = self.conn.execute("""
            SELECT p.*, r.rating
            FROM papers p
            INNER JOIN (
                SELECT arxiv_id, rating, MAX(rated_at) as max_rated
                FROM ratings
                GROUP BY arxiv_id
            ) r ON p.arxiv_id = r.arxiv_id
            WHERE p.embedding IS NOT NULL
        """).fetchall()

        results = []
        for row in rows:
            paper = self._row_to_dict(row)
            embedding = np.frombuffer(row["embedding"], dtype=np.float32)
            rating = row["rating"]
            results.append((paper, embedding, rating))
        return results

    def get_training_data(self) -> tuple[list[np.ndarray], list[float]]:
        """Get all training data (embeddings and labels) for model retraining."""
        rated = self.get_rated_papers()
        if not rated:
            return [], []
        embeddings = [emb for _, emb, _ in rated]
        labels = [float(rating) for _, _, rating in rated]
        return embeddings, labels

    def get_stats(self) -> dict:
        """Get database statistics."""
        total_papers = self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        total_rated = self.conn.execute(
            "SELECT COUNT(DISTINCT arxiv_id) FROM ratings"
        ).fetchone()[0]
        thumbs_up = self.conn.execute("""
            SELECT COUNT(DISTINCT arxiv_id) FROM (
                SELECT arxiv_id, rating FROM ratings
                GROUP BY arxiv_id HAVING MAX(rated_at)
            ) WHERE rating = 1
        """).fetchone()[0]
        thumbs_down = self.conn.execute("""
            SELECT COUNT(DISTINCT arxiv_id) FROM (
                SELECT arxiv_id, rating FROM ratings
                GROUP BY arxiv_id HAVING MAX(rated_at)
            ) WHERE rating = 0
        """).fetchone()[0]
        with_embeddings = self.conn.execute(
            "SELECT COUNT(*) FROM papers WHERE embedding IS NOT NULL"
        ).fetchone()[0]
        with_summaries = self.conn.execute(
            "SELECT COUNT(*) FROM papers WHERE summary IS NOT NULL AND summary != 'AI Fail'"
        ).fetchone()[0]

        return {
            "total_papers": total_papers,
            "total_rated": total_rated,
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
            "with_embeddings": with_embeddings,
            "with_summaries": with_summaries,
        }

    def log_fetch(self, num_papers: int, categories: list[str]):
        """Log a fetch operation."""
        self.conn.execute(
            "INSERT INTO fetch_log (fetched_at, num_papers, categories) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat(), num_papers, json.dumps(categories)),
        )
        self.conn.commit()

    def create_task_entry(self, task_id: str, task_type: str, status: str = "PENDING") -> bool:
        """Create a new task entry in the task_history table."""
        now = datetime.utcnow().isoformat()
        try:
            self.conn.execute(
                """INSERT OR REPLACE INTO task_history
                   (task_id, task_type, status, progress, total, created_at, updated_at)
                   VALUES (?, ?, ?, 0, 0, ?, ?)""",
                (task_id, task_type, status, now, now),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to create task entry {task_id}: {e}")
            return False

    def update_task_progress(self, task_id: str, progress: int, total: int, status: Optional[str] = None) -> bool:
        """Update progress and status of a background task."""
        now = datetime.utcnow().isoformat()
        try:
            if status:
                self.conn.execute(
                    """UPDATE task_history
                       SET progress = ?, total = ?, status = ?, updated_at = ?
                       WHERE task_id = ?""",
                    (progress, total, status, now, task_id),
                )
            else:
                self.conn.execute(
                    """UPDATE task_history
                       SET progress = ?, total = ?, updated_at = ?
                       WHERE task_id = ?""",
                    (progress, total, now, task_id),
                )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to update task progress {task_id}: {e}")
            return False

    def complete_task(
        self,
        task_id: str,
        status: str = "SUCCESS",
        result: Optional[dict | str] = None,
        error: Optional[str] = None,
    ) -> bool:
        """Mark task as complete with optional result or error."""
        now = datetime.utcnow().isoformat()
        res_str = json.dumps(result) if isinstance(result, (dict, list)) else result
        try:
            self.conn.execute(
                """UPDATE task_history
                   SET status = ?, result = ?, error = ?, updated_at = ?, progress = total
                   WHERE task_id = ?""",
                (status, res_str, error, now, task_id),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to complete task {task_id}: {e}")
            return False

    def get_task_status(self, task_id: str) -> Optional[dict]:
        """Get the status of a background task."""
        row = self.conn.execute(
            "SELECT * FROM task_history WHERE task_id = ?", (task_id,)
        ).fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("result"):
            try:
                res["result"] = json.loads(res["result"])
            except json.JSONDecodeError:
                pass
        return res

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a paper dict."""
        d = dict(row)
        d["authors"] = json.loads(d["authors"])
        d["categories"] = json.loads(d["categories"])
        # Don't include raw embedding blob in dict
        d.pop("embedding", None)
        return d

    def search_papers(
        self,
        query: str,
        category: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search papers using SQLite FTS5.

        Args:
            query: The search terms (will be sanitised).
            category: Optional category filter.
            date_from: Optional starting date (YYYY-MM-DD).
            date_to: Optional ending date (YYYY-MM-DD).
            limit: Maximum number of results to return.
        """
        import re
        words = re.findall(r'\w+', query)
        if not words:
            return []

        # Sanitise: wrap each word in double quotes and join with AND
        fts_query = ' AND '.join(f'"{w}"' for w in words)

        where_clauses = ["papers_fts MATCH ?"]
        params: list[str | int] = [fts_query]

        if category:
            # Match category inside the JSON array representation
            where_clauses.append("p.categories LIKE ?")
            params.append(f'%"{category}"%')

        if date_from:
            where_clauses.append("p.published >= ?")
            params.append(date_from)

        if date_to:
            # If date_to is YYYY-MM-DD, expand it to include the whole day
            if len(date_to) == 10:
                where_clauses.append("p.published <= ?")
                params.append(f"{date_to}T23:59:59")
            else:
                where_clauses.append("p.published <= ?")
                params.append(date_to)

        where_clause = " AND ".join(where_clauses)

        # Use SQLite FTS5 highlight function to highlight matches.
        # Columns are: 0: arxiv_id (unindexed), 1: title, 2: abstract.
        sql = f"""
            SELECT 
                p.arxiv_id,
                highlight(papers_fts, 1, '<mark>', '</mark>') as title,
                highlight(papers_fts, 2, '<mark>', '</mark>') as abstract,
                p.authors,
                p.categories,
                p.published,
                p.url,
                p.pdf_url,
                p.fetched_at,
                p.summary
            FROM papers_fts
            JOIN papers p ON p.arxiv_id = papers_fts.arxiv_id
            WHERE {where_clause}
            ORDER BY rank
            LIMIT ?
        """
        params.append(limit)

        try:
            rows = self.conn.execute(sql, params).fetchall()
            return [self._row_to_dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"FTS search failed for query '{query}': {e}")
            return []

    def close(self):
        """Close the database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
