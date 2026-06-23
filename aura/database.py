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

    def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                digest_frequency TEXT DEFAULT 'daily',
                unsubscribe_token TEXT UNIQUE DEFAULT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                name TEXT,
                scope TEXT DEFAULT 'read',
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT DEFAULT 'member',
                joined_at TEXT NOT NULL,
                FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(group_id, user_id)
            );

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
                summary TEXT,
                source TEXT DEFAULT 'arxiv',
                citation_count INTEGER DEFAULT 0,
                has_code INTEGER DEFAULT 0,
                has_data INTEGER DEFAULT 0,
                bibcode TEXT,
                read_count INTEGER DEFAULT 0,
                refereed INTEGER DEFAULT 0,
                citations_fetched INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS citations (
                citing_arxiv_id TEXT NOT NULL,
                cited_arxiv_id TEXT NOT NULL,
                PRIMARY KEY (citing_arxiv_id, cited_arxiv_id)
            );

            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                arxiv_id TEXT NOT NULL,
                rating INTEGER NOT NULL,
                rated_at TEXT NOT NULL,
                FOREIGN KEY (arxiv_id) REFERENCES papers(arxiv_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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

            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                arxiv_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, arxiv_id, tag)
            );

            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                description TEXT,
                is_public INTEGER DEFAULT 0,
                slug TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, name)
            );

            CREATE TABLE IF NOT EXISTS collection_papers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL,
                arxiv_id TEXT NOT NULL,
                added_at TEXT NOT NULL,
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                FOREIGN KEY (arxiv_id) REFERENCES papers(arxiv_id) ON DELETE CASCADE,
                UNIQUE(collection_id, arxiv_id)
            );

            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                arxiv_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reading_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                arxiv_id TEXT NOT NULL,
                added_at TEXT NOT NULL,
                read_at TEXT,
                UNIQUE(user_id, arxiv_id)
            );

            CREATE TABLE IF NOT EXISTS full_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arxiv_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(arxiv_id, mode)
            );

            CREATE TABLE IF NOT EXISTS paper_texts (
                arxiv_id TEXT PRIMARY KEY,
                full_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS briefs (
                date TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        self.conn.commit()

        # Phase 2: run column migrations before creating indexes that reference new columns
        self._run_migrations()

        # Phase 3: create indexes and FTS (now safe — user_id columns exist)
        self.conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_unsubscribe_token ON users(unsubscribe_token);
            CREATE INDEX IF NOT EXISTS idx_api_tokens_token ON api_tokens(token);
            CREATE INDEX IF NOT EXISTS idx_api_tokens_user_id ON api_tokens(user_id);
            CREATE INDEX IF NOT EXISTS idx_papers_published ON papers(published);
            CREATE INDEX IF NOT EXISTS idx_ratings_arxiv_id ON ratings(arxiv_id);
            CREATE INDEX IF NOT EXISTS idx_ratings_user_id ON ratings(user_id);
            CREATE INDEX IF NOT EXISTS idx_ratings_rated_at ON ratings(rated_at);
            CREATE INDEX IF NOT EXISTS idx_task_history_status ON task_history(status);
            CREATE INDEX IF NOT EXISTS idx_tags_arxiv_id ON tags(arxiv_id);
            CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
            CREATE INDEX IF NOT EXISTS idx_tags_user_id ON tags(user_id);
            CREATE INDEX IF NOT EXISTS idx_collections_user_id ON collections(user_id);
            CREATE INDEX IF NOT EXISTS idx_collection_papers_collection_id ON collection_papers(collection_id);
            CREATE INDEX IF NOT EXISTS idx_collection_papers_arxiv_id ON collection_papers(arxiv_id);
            CREATE INDEX IF NOT EXISTS idx_notes_arxiv_id ON notes(arxiv_id);
            CREATE INDEX IF NOT EXISTS idx_notes_user_id ON notes(user_id);
            CREATE INDEX IF NOT EXISTS idx_reading_list_user_id ON reading_list(user_id);
            CREATE INDEX IF NOT EXISTS idx_reading_list_added_at ON reading_list(added_at);
            CREATE INDEX IF NOT EXISTS idx_full_summaries_arxiv_id ON full_summaries(arxiv_id);
            CREATE INDEX IF NOT EXISTS idx_citations_citing ON citations(citing_arxiv_id);
            CREATE INDEX IF NOT EXISTS idx_citations_cited ON citations(cited_arxiv_id);

            CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
                arxiv_id UNINDEXED,
                title,
                abstract
            );

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

    def _run_migrations(self) -> None:
        """Apply incremental schema migrations for existing databases."""
        self._add_column_if_missing("papers", "source", "TEXT DEFAULT 'arxiv'")
        self._add_column_if_missing("papers", "citation_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing("ratings", "user_id", "INTEGER DEFAULT 1")
        self._add_column_if_missing("notes", "user_id", "INTEGER DEFAULT 1")
        self._add_column_if_missing("collections", "user_id", "INTEGER DEFAULT 1")
        self._add_column_if_missing("collections", "is_public", "INTEGER DEFAULT 0")
        self._add_column_if_missing("collections", "slug", "TEXT")
        self._add_column_if_missing("papers", "bibcode", "TEXT")
        self._add_column_if_missing("papers", "read_count", "INTEGER DEFAULT 0")
        self._add_column_if_missing("papers", "refereed", "INTEGER DEFAULT 0")
        self._add_column_if_missing("users", "digest_frequency", "TEXT DEFAULT 'daily'")
        self._add_column_if_missing("users", "unsubscribe_token", "TEXT DEFAULT NULL")
        self._add_column_if_missing("papers", "citations_fetched", "INTEGER DEFAULT 0")
        try:
            self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_unsubscribe_token ON users(unsubscribe_token)")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass

        # Populate missing tokens
        import uuid
        users = self.conn.execute("SELECT id FROM users WHERE unsubscribe_token IS NULL").fetchall()
        for user in users:
            token = uuid.uuid4().hex
            self.conn.execute("UPDATE users SET unsubscribe_token = ? WHERE id = ?", (token, user["id"]))
        self.conn.commit()

        # Tables that need structural migration (UNIQUE constraint changes)
        self._migrate_reading_list()
        self._migrate_tags()

    def _add_column_if_missing(self, table: str, column: str, definition: str) -> None:
        """Add a column to a table if it does not already exist."""
        cols = [row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")]
        if column not in cols:
            try:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass

    def _migrate_reading_list(self) -> None:
        """Migrate reading_list from single-user PK schema to multi-user schema."""
        cols = [row[1] for row in self.conn.execute("PRAGMA table_info(reading_list)")]
        if "user_id" in cols:
            return
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS reading_list_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                arxiv_id TEXT NOT NULL,
                added_at TEXT NOT NULL,
                read_at TEXT,
                UNIQUE(user_id, arxiv_id)
            );
            INSERT INTO reading_list_new (user_id, arxiv_id, added_at, read_at)
            SELECT 1, arxiv_id, added_at, read_at FROM reading_list;
            DROP TABLE reading_list;
            ALTER TABLE reading_list_new RENAME TO reading_list;
        """)
        self.conn.commit()

    def _migrate_tags(self) -> None:
        """Migrate tags UNIQUE constraint from (arxiv_id, tag) to (user_id, arxiv_id, tag)."""
        cols = [row[1] for row in self.conn.execute("PRAGMA table_info(tags)")]
        if "user_id" in cols:
            return
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS tags_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 1,
                arxiv_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, arxiv_id, tag)
            );
            INSERT INTO tags_new (user_id, arxiv_id, tag, created_at)
            SELECT 1, arxiv_id, tag, created_at FROM tags;
            DROP TABLE tags;
            ALTER TABLE tags_new RENAME TO tags;
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
            source = paper.get("source", "arxiv")
            citation_count = paper.get("citation_count", 0)
            has_code = paper.get("has_code", 0)
            has_data = paper.get("has_data", 0)
            cursor = self.conn.execute(
                """INSERT OR IGNORE INTO papers
                   (arxiv_id, title, abstract, authors, categories, published, url, pdf_url, fetched_at, embedding, summary, source, citation_count, has_code, has_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                    source,
                    citation_count,
                    has_code,
                    has_data,
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
            source = paper.get("source", "arxiv")
            citation_count = paper.get("citation_count", 0)
            has_code = paper.get("has_code", 0)
            has_data = paper.get("has_data", 0)
            try:
                cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO papers
                       (arxiv_id, title, abstract, authors, categories, published, url, pdf_url, fetched_at, embedding, summary, source, citation_count, has_code, has_data)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                        source,
                        citation_count,
                        has_code,
                        has_data,
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

    def rate_paper(self, arxiv_id: str, rating: int, user_id: int = 1) -> bool:
        """Rate a paper: 1-5 for stars, -1 for skip.

        Multiple ratings for the same paper are allowed (tracks history),
        but only the latest is used for training.
        """
        if rating not in (-1, 0, 1, 2, 3, 4, 5):
            raise ValueError("Rating must be -1 (skip) or 1-5 (stars)")

        try:
            self.conn.execute(
                "INSERT INTO ratings (user_id, arxiv_id, rating, rated_at) VALUES (?, ?, ?, ?)",
                (user_id, arxiv_id, rating, datetime.utcnow().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to rate paper {arxiv_id}: {e}")
            return False

    def get_latest_rating(self, arxiv_id: str, user_id: int = 1) -> Optional[int]:
        """Get the most recent rating for a paper by the given user."""
        row = self.conn.execute(
            "SELECT rating FROM ratings WHERE arxiv_id = ? AND user_id = ? ORDER BY rated_at DESC LIMIT 1",
            (arxiv_id, user_id),
        ).fetchone()
        return row["rating"] if row else None

    def get_rated_papers(self, user_id: int = 1) -> list[tuple[dict, np.ndarray, int]]:
        """Get all rated papers for a user with their embeddings and latest ratings.

        Returns list of (paper_dict, embedding, rating) tuples.
        Only includes papers that have embeddings.
        """
        rows = self.conn.execute("""
            SELECT p.*, r.rating
            FROM papers p
            INNER JOIN (
                SELECT arxiv_id, rating, MAX(rated_at) as max_rated
                FROM ratings
                WHERE user_id = ?
                GROUP BY arxiv_id
            ) r ON p.arxiv_id = r.arxiv_id
            WHERE p.embedding IS NOT NULL
        """, (user_id,)).fetchall()

        results = []
        for row in rows:
            paper = self._row_to_dict(row)
            embedding = np.frombuffer(row["embedding"], dtype=np.float32)
            rating = row["rating"]
            results.append((paper, embedding, rating))
        return results

    def get_training_data(self, user_id: int = 1) -> tuple[list[np.ndarray], list[float]]:
        """Get all training data (embeddings and labels) for model retraining."""
        rated = self.get_rated_papers(user_id=user_id)
        if not rated:
            return [], []

        embeddings = []
        labels = []
        for _, emb, rating in rated:
            if rating == -1:
                continue
            if rating == 0:
                label = 0.0
            elif rating == 1:
                label = 1.0
            else:
                label = (rating - 1) / 4.0
            embeddings.append(emb)
            labels.append(label)

        return embeddings, labels

    def get_stats(self, user_id: int = 1) -> dict:
        """Get database statistics for a user."""
        total_papers = self.conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        total_rated = self.conn.execute(
            "SELECT COUNT(DISTINCT arxiv_id) FROM ratings WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        thumbs_up = self.conn.execute("""
            SELECT COUNT(DISTINCT arxiv_id) FROM (
                SELECT arxiv_id, rating FROM ratings
                WHERE user_id = ?
                GROUP BY arxiv_id HAVING MAX(rated_at)
            ) WHERE rating >= 4 OR rating = 1
        """, (user_id,)).fetchone()[0]
        thumbs_down = self.conn.execute("""
            SELECT COUNT(DISTINCT arxiv_id) FROM (
                SELECT arxiv_id, rating FROM ratings
                WHERE user_id = ?
                GROUP BY arxiv_id HAVING MAX(rated_at)
            ) WHERE (rating <= 2 AND rating != -1) OR rating = 0
        """, (user_id,)).fetchone()[0]
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

    def add_citations_batch(self, links: list[tuple[str, str]]) -> None:
        """Add citation links in batch (citing_arxiv_id, cited_arxiv_id)."""
        self.conn.executemany(
            "INSERT OR IGNORE INTO citations (citing_arxiv_id, cited_arxiv_id) VALUES (?, ?)",
            links,
        )
        self.conn.commit()

    def get_papers_citing(self, arxiv_id: str) -> list[dict]:
        """Get papers in the database that cite the given paper."""
        rows = self.conn.execute(
            """
            SELECT p.* FROM papers p
            JOIN citations c ON p.arxiv_id = c.citing_arxiv_id
            WHERE c.cited_arxiv_id = ?
            ORDER BY p.published DESC
            """,
            (arxiv_id,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_papers_cited_by(self, arxiv_id: str) -> list[dict]:
        """Get papers in the database that are cited by the given paper."""
        rows = self.conn.execute(
            """
            SELECT p.* FROM papers p
            JOIN citations c ON p.arxiv_id = c.cited_arxiv_id
            WHERE c.citing_arxiv_id = ?
            ORDER BY p.published DESC
            """,
            (arxiv_id,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def mark_citations_fetched(self, arxiv_id: str, fetched: bool = True) -> None:
        """Mark a paper's citations as fetched/processed."""
        val = 1 if fetched else 0
        self.conn.execute(
            "UPDATE papers SET citations_fetched = ? WHERE arxiv_id = ?",
            (val, arxiv_id),
        )
        self.conn.commit()

    def get_liked_citations_counts(self, liked_arxiv_ids: list[str]) -> dict[str, int]:
        """Return a mapping of arxiv_id to the number of liked papers that cite it."""
        if not liked_arxiv_ids:
            return {}
        placeholders = ",".join("?" for _ in liked_arxiv_ids)
        rows = self.conn.execute(
            f"""
            SELECT cited_arxiv_id, COUNT(*) as cnt
            FROM citations
            WHERE citing_arxiv_id IN ({placeholders})
            GROUP BY cited_arxiv_id
            """,
            liked_arxiv_ids,
        ).fetchall()
        return {row["cited_arxiv_id"]: row["cnt"] for row in rows}

    def get_liked_references_counts(self, liked_arxiv_ids: list[str]) -> dict[str, int]:
        """Return a mapping of arxiv_id to the number of liked papers that it cites."""
        if not liked_arxiv_ids:
            return {}
        placeholders = ",".join("?" for _ in liked_arxiv_ids)
        rows = self.conn.execute(
            f"""
            SELECT citing_arxiv_id, COUNT(*) as cnt
            FROM citations
            WHERE cited_arxiv_id IN ({placeholders})
            GROUP BY citing_arxiv_id
            """,
            liked_arxiv_ids,
        ).fetchall()
        return {row["citing_arxiv_id"]: row["cnt"] for row in rows}

    def search_papers(
        self,
        query: str,
        category: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        has_code: Optional[int] = None,
        has_data: Optional[int] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Search papers using SQLite FTS5."""
        import re
        words = re.findall(r'\w+', query)
        if not words:
            return []

        fts_query = ' AND '.join(f'"{w}"' for w in words)

        where_clauses = ["papers_fts MATCH ?"]
        params: list[str | int] = [fts_query]

        if category:
            where_clauses.append("p.categories LIKE ?")
            params.append(f'%"{category}"%')

        if date_from:
            where_clauses.append("p.published >= ?")
            params.append(date_from)

        if date_to:
            if len(date_to) == 10:
                where_clauses.append("p.published <= ?")
                params.append(f"{date_to}T23:59:59")
            else:
                where_clauses.append("p.published <= ?")
                params.append(date_to)

        if has_code is not None:
            where_clauses.append("p.has_code = ?")
            params.append(has_code)

        if has_data is not None:
            where_clauses.append("p.has_data = ?")
            params.append(has_data)

        where_clause = " AND ".join(where_clauses)

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
                p.summary,
                p.citation_count,
                p.has_code,
                p.has_data
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

    def get_ratings_history(self, arxiv_id: str, user_id: int = 1) -> list[dict]:
        """Get the rating history for a paper for a user, ordered from newest to oldest."""
        rows = self.conn.execute(
            "SELECT rating, rated_at FROM ratings WHERE arxiv_id = ? AND user_id = ? ORDER BY rated_at DESC",
            (arxiv_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_papers_by_authors(
        self, authors: list[str], exclude_arxiv_id: str, limit: int = 5
    ) -> list[dict]:
        """Get other papers written by any of the specified authors."""
        if not authors:
            return []

        where_clauses = []
        params: list[str | int] = []
        for author in authors:
            where_clauses.append("authors LIKE ?")
            params.append(f'%"{author}"%')

        where_clause = " OR ".join(where_clauses)
        sql = f"""
            SELECT * FROM papers
            WHERE ({where_clause}) AND arxiv_id != ?
            ORDER BY published DESC
            LIMIT ?
        """
        params.append(exclude_arxiv_id)
        params.append(limit)

        try:
            rows = self.conn.execute(sql, params).fetchall()
            return [self._row_to_dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get papers by authors: {e}")
            return []

    def add_tag(self, arxiv_id: str, tag: str, user_id: int = 1) -> bool:
        """Add a tag to a paper for a user. Returns True if added."""
        clean_tag = tag.strip().lower()
        if not clean_tag:
            return False
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO tags (user_id, arxiv_id, tag, created_at) VALUES (?, ?, ?, ?)",
                (user_id, arxiv_id, clean_tag, datetime.utcnow().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to add tag {tag} to paper {arxiv_id}: {e}")
            return False

    def remove_tag(self, arxiv_id: str, tag: str, user_id: int = 1) -> bool:
        """Remove a user's tag from a paper. Returns True if deleted."""
        clean_tag = tag.strip().lower()
        try:
            cursor = self.conn.execute(
                "DELETE FROM tags WHERE user_id = ? AND arxiv_id = ? AND tag = ?",
                (user_id, arxiv_id, clean_tag),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to remove tag {tag} from paper {arxiv_id}: {e}")
            return False

    def get_paper_tags(self, arxiv_id: str, user_id: int = 1) -> list[str]:
        """Get all tags a user has applied to a specific paper."""
        rows = self.conn.execute(
            "SELECT tag FROM tags WHERE user_id = ? AND arxiv_id = ? ORDER BY tag ASC",
            (user_id, arxiv_id),
        ).fetchall()
        return [row["tag"] for row in rows]

    def get_all_tags(self, user_id: int = 1) -> list[str]:
        """Get all unique tags created by a user."""
        rows = self.conn.execute(
            "SELECT DISTINCT tag FROM tags WHERE user_id = ? ORDER BY tag ASC",
            (user_id,),
        ).fetchall()
        return [row["tag"] for row in rows]

    def get_papers_by_tag(
        self, tag: str, user_id: int = 1, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """Get all papers with a specific tag for a user."""
        rows = self.conn.execute(
            """
            SELECT p.* FROM papers p
            INNER JOIN tags t ON p.arxiv_id = t.arxiv_id
            WHERE t.tag = ? AND t.user_id = ?
            ORDER BY p.published DESC
            LIMIT ? OFFSET ?
            """,
            (tag.strip().lower(), user_id, limit, offset),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def create_collection(
        self,
        name: str,
        description: Optional[str] = None,
        user_id: int = 1,
        is_public: bool = False,
        slug: Optional[str] = None,
    ) -> Optional[int]:
        """Create a collection for a user. Returns the collection ID if successful."""
        import re
        clean_name = name.strip()
        if not clean_name:
            return None
        if slug is None and is_public:
            slug = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-")
        try:
            cursor = self.conn.execute(
                "INSERT INTO collections (user_id, name, description, is_public, slug, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, clean_name, description, int(is_public), slug, datetime.utcnow().isoformat()),
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to create collection {name}: {e}")
            return None

    def delete_collection(self, collection_id: int, user_id: int = 1) -> bool:
        """Delete a user's collection. Returns True if deleted."""
        try:
            cursor = self.conn.execute(
                "DELETE FROM collections WHERE id = ? AND user_id = ?",
                (collection_id, user_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete collection {collection_id}: {e}")
            return False

    def add_paper_to_collection(self, collection_id: int, arxiv_id: str, user_id: int = 1) -> bool:
        """Add a paper to a collection (ownership verified). Returns True if added."""
        # Verify the collection belongs to this user
        row = self.conn.execute(
            "SELECT id FROM collections WHERE id = ? AND user_id = ?",
            (collection_id, user_id),
        ).fetchone()
        if not row:
            return False
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO collection_papers (collection_id, arxiv_id, added_at) VALUES (?, ?, ?)",
                (collection_id, arxiv_id, datetime.utcnow().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to add paper {arxiv_id} to collection {collection_id}: {e}")
            return False

    def remove_paper_from_collection(self, collection_id: int, arxiv_id: str, user_id: int = 1) -> bool:
        """Remove a paper from a collection (ownership verified). Returns True if removed."""
        row = self.conn.execute(
            "SELECT id FROM collections WHERE id = ? AND user_id = ?",
            (collection_id, user_id),
        ).fetchone()
        if not row:
            return False
        try:
            cursor = self.conn.execute(
                "DELETE FROM collection_papers WHERE collection_id = ? AND arxiv_id = ?",
                (collection_id, arxiv_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to remove paper {arxiv_id} from collection {collection_id}: {e}")
            return False

    def get_collections(self, user_id: int = 1) -> list[dict]:
        """Get all collections for a user, including paper counts."""
        rows = self.conn.execute(
            """
            SELECT c.*, COUNT(cp.arxiv_id) as paper_count
            FROM collections c
            LEFT JOIN collection_papers cp ON c.id = cp.collection_id
            WHERE c.user_id = ?
            GROUP BY c.id
            ORDER BY c.name ASC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_public_collections(self) -> list[dict]:
        """Get all public collections with paper counts."""
        rows = self.conn.execute(
            """
            SELECT c.*, COUNT(cp.arxiv_id) as paper_count, u.email as owner_email
            FROM collections c
            LEFT JOIN collection_papers cp ON c.id = cp.collection_id
            JOIN users u ON c.user_id = u.id
            WHERE c.is_public = 1
            GROUP BY c.id
            ORDER BY c.name ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_collection_by_slug(self, slug: str) -> Optional[dict]:
        """Get a public collection by its slug."""
        row = self.conn.execute(
            "SELECT * FROM collections WHERE slug = ? AND is_public = 1",
            (slug,),
        ).fetchone()
        return dict(row) if row else None

    def fork_collection(self, collection_id: int, user_id: int, new_name: Optional[str] = None) -> Optional[int]:
        """Copy a public collection into the user's own library."""
        src = self.conn.execute(
            "SELECT * FROM collections WHERE id = ? AND is_public = 1",
            (collection_id,),
        ).fetchone()
        if not src:
            return None
        name = new_name or f"Fork of {src['name']}"
        new_id = self.create_collection(name, user_id=user_id, description=src["description"])
        if new_id is None:
            return None
        papers = self.conn.execute(
            "SELECT arxiv_id, added_at FROM collection_papers WHERE collection_id = ?",
            (collection_id,),
        ).fetchall()
        for p in papers:
            self.conn.execute(
                "INSERT OR IGNORE INTO collection_papers (collection_id, arxiv_id, added_at) VALUES (?, ?, ?)",
                (new_id, p["arxiv_id"], p["added_at"]),
            )
        self.conn.commit()
        return new_id

    def update_collection(
        self,
        collection_id: int,
        user_id: int = 1,
        is_public: Optional[bool] = None,
        slug: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        """Update collection metadata. Returns True if updated."""
        row = self.conn.execute(
            "SELECT * FROM collections WHERE id = ? AND user_id = ?",
            (collection_id, user_id),
        ).fetchone()
        if not row:
            return False
        updates: list[str] = []
        params: list = []
        if is_public is not None:
            updates.append("is_public = ?")
            params.append(int(is_public))
            if is_public and not row["slug"] and slug is None:
                import re
                auto_slug = re.sub(r"[^a-z0-9]+", "-", row["name"].lower()).strip("-")
                updates.append("slug = ?")
                params.append(auto_slug)
        if slug is not None:
            updates.append("slug = ?")
            params.append(slug)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if not updates:
            return True
        params.append(collection_id)
        try:
            self.conn.execute(
                f"UPDATE collections SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to update collection {collection_id}: {e}")
            return False

    def get_collection(self, collection_id: int) -> Optional[dict]:
        """Get metadata for a single collection."""
        row = self.conn.execute(
            "SELECT * FROM collections WHERE id = ?", (collection_id,)
        ).fetchone()
        return dict(row) if row else None

    def add_note(self, arxiv_id: str, content: str, user_id: int = 1) -> Optional[int]:
        """Add a note to a paper for a user. Returns the note ID."""
        now = datetime.utcnow().isoformat()
        try:
            cursor = self.conn.execute(
                "INSERT INTO notes (user_id, arxiv_id, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, arxiv_id, content, now, now),
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to add note to paper {arxiv_id}: {e}")
            return None

    def update_note(self, note_id: int, content: str, user_id: int = 1) -> bool:
        """Update a user's note. Returns True if updated."""
        now = datetime.utcnow().isoformat()
        try:
            cursor = self.conn.execute(
                "UPDATE notes SET content = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (content, now, note_id, user_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to update note {note_id}: {e}")
            return False

    def delete_note(self, note_id: int, user_id: int = 1) -> bool:
        """Delete a user's note. Returns True if deleted."""
        try:
            cursor = self.conn.execute(
                "DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id)
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete note {note_id}: {e}")
            return False

    def get_paper_notes(self, arxiv_id: str, user_id: int = 1) -> list[dict]:
        """Get all notes a user has written for a specific paper."""
        rows = self.conn.execute(
            "SELECT * FROM notes WHERE user_id = ? AND arxiv_id = ? ORDER BY created_at DESC",
            (user_id, arxiv_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_to_reading_list(self, arxiv_id: str, user_id: int = 1) -> bool:
        """Add a paper to a user's reading list."""
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO reading_list (user_id, arxiv_id, added_at) VALUES (?, ?, ?)",
                (user_id, arxiv_id, datetime.utcnow().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to add paper {arxiv_id} to reading list: {e}")
            return False

    def remove_from_reading_list(self, arxiv_id: str, user_id: int = 1) -> bool:
        """Remove a paper from a user's reading list."""
        try:
            cursor = self.conn.execute(
                "DELETE FROM reading_list WHERE user_id = ? AND arxiv_id = ?",
                (user_id, arxiv_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to remove paper {arxiv_id} from reading list: {e}")
            return False

    def mark_as_read(self, arxiv_id: str, user_id: int = 1) -> bool:
        """Mark a paper in a user's reading list as read."""
        try:
            cursor = self.conn.execute(
                "UPDATE reading_list SET read_at = ? WHERE user_id = ? AND arxiv_id = ?",
                (datetime.utcnow().isoformat(), user_id, arxiv_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to mark paper {arxiv_id} as read: {e}")
            return False

    def get_reading_list(
        self, user_id: int = 1, only_unread: bool = False, only_read: bool = False
    ) -> list[dict]:
        """Get papers in a user's reading list with optional filtering."""
        where = "WHERE rl.user_id = ?"
        params: list = [user_id]
        if only_unread:
            where += " AND rl.read_at IS NULL"
        elif only_read:
            where += " AND rl.read_at IS NOT NULL"

        rows = self.conn.execute(
            f"""
            SELECT p.*, rl.added_at, rl.read_at
            FROM papers p
            JOIN reading_list rl ON p.arxiv_id = rl.arxiv_id
            {where}
            ORDER BY rl.added_at DESC
            """,
            params,
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def is_in_reading_list(self, arxiv_id: str, user_id: int = 1) -> bool:
        """Check if a paper is in a user's reading list."""
        row = self.conn.execute(
            "SELECT 1 FROM reading_list WHERE user_id = ? AND arxiv_id = ?",
            (user_id, arxiv_id),
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------

    def create_user(self, email: str, password_hash: str, is_admin: bool = False) -> Optional[int]:
        """Create a new user. Returns the user ID or None on failure."""
        import uuid
        token = uuid.uuid4().hex
        now = datetime.utcnow().isoformat()
        try:
            cursor = self.conn.execute(
                "INSERT INTO users (email, password_hash, is_admin, is_active, digest_frequency, unsubscribe_token, created_at) VALUES (?, ?, ?, 1, 'daily', ?, ?)",
                (email.strip().lower(), password_hash, int(is_admin), token, now),
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to create user {email}: {e}")
            return None

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        """Look up a user by primary key."""
        row = self.conn.execute(
            "SELECT id, email, password_hash, is_admin, is_active, digest_frequency, unsubscribe_token, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[dict]:
        """Look up a user by email address."""
        row = self.conn.execute(
            "SELECT id, email, password_hash, is_admin, is_active, digest_frequency, unsubscribe_token, created_at FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_unsubscribe_token(self, token: str) -> Optional[dict]:
        """Look up a user by unsubscribe token."""
        row = self.conn.execute(
            "SELECT id, email, password_hash, is_admin, is_active, digest_frequency, unsubscribe_token, created_at FROM users WHERE unsubscribe_token = ?",
            (token,),
        ).fetchone()
        return dict(row) if row else None

    def get_all_users(self) -> list[dict]:
        """Return all users (admin use only)."""
        rows = self.conn.execute(
            "SELECT id, email, is_admin, is_active, created_at FROM users ORDER BY created_at ASC"
        ).fetchall()
        return [dict(row) for row in rows]

    def update_user(
        self,
        user_id: int,
        is_active: Optional[bool] = None,
        is_admin: Optional[bool] = None,
        password_hash: Optional[str] = None,
        digest_frequency: Optional[str] = None,
        unsubscribe_token: Optional[str] = None,
    ) -> bool:
        """Update user fields. Returns True if updated."""
        updates: list[str] = []
        params: list = []
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(int(is_active))
        if is_admin is not None:
            updates.append("is_admin = ?")
            params.append(int(is_admin))
        if password_hash is not None:
            updates.append("password_hash = ?")
            params.append(password_hash)
        if digest_frequency is not None:
            updates.append("digest_frequency = ?")
            params.append(digest_frequency)
        if unsubscribe_token is not None:
            updates.append("unsubscribe_token = ?")
            params.append(unsubscribe_token)
        if not updates:
            return True
        params.append(user_id)
        try:
            self.conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to update user {user_id}: {e}")
            return False

    def delete_user(self, user_id: int) -> bool:
        """Delete a user and all their scoped data. Returns True if deleted."""
        try:
            cursor = self.conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to delete user {user_id}: {e}")
            return False

    def count_users(self) -> int:
        """Return the total number of registered users."""
        return self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    # ------------------------------------------------------------------
    # API tokens
    # ------------------------------------------------------------------

    def create_api_token(
        self, user_id: int, name: str, scope: str = "read"
    ) -> Optional[str]:
        """Generate and store a new API token. Returns the token string."""
        import secrets
        token = secrets.token_urlsafe(32)
        now = datetime.utcnow().isoformat()
        try:
            self.conn.execute(
                "INSERT INTO api_tokens (user_id, token, name, scope, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, token, name, scope, now),
            )
            self.conn.commit()
            return token
        except sqlite3.Error as e:
            logger.error(f"Failed to create API token for user {user_id}: {e}")
            return None

    def get_user_by_token(self, token: str) -> Optional[dict]:
        """Look up a user by a valid (non-revoked) API token; updates last_used_at."""
        row = self.conn.execute(
            """
            SELECT u.*, t.scope, t.id as token_id
            FROM api_tokens t
            JOIN users u ON t.user_id = u.id
            WHERE t.token = ? AND t.revoked_at IS NULL AND u.is_active = 1
            """,
            (token,),
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE api_tokens SET last_used_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), row["token_id"]),
            )
            self.conn.commit()
        return dict(row) if row else None

    def get_user_tokens(self, user_id: int) -> list[dict]:
        """List all active tokens for a user."""
        rows = self.conn.execute(
            """
            SELECT id, name, scope, created_at, last_used_at
            FROM api_tokens
            WHERE user_id = ? AND revoked_at IS NULL
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def revoke_api_token(self, token_id: int, user_id: int) -> bool:
        """Revoke a specific API token. Returns True if revoked."""
        try:
            cursor = self.conn.execute(
                "UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND user_id = ?",
                (datetime.utcnow().isoformat(), token_id, user_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to revoke token {token_id}: {e}")
            return False

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    def create_group(self, name: str, description: Optional[str] = None) -> Optional[int]:
        """Create a group. Returns the group ID."""
        now = datetime.utcnow().isoformat()
        try:
            cursor = self.conn.execute(
                "INSERT INTO groups (name, description, created_at) VALUES (?, ?, ?)",
                (name.strip(), description, now),
            )
            self.conn.commit()
            return cursor.lastrowid
        except sqlite3.Error as e:
            logger.error(f"Failed to create group {name}: {e}")
            return None

    def get_all_groups(self) -> list[dict]:
        """Return all groups."""
        rows = self.conn.execute(
            "SELECT * FROM groups ORDER BY name ASC"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_group(self, group_id: int) -> Optional[dict]:
        """Get a single group by ID."""
        row = self.conn.execute(
            "SELECT * FROM groups WHERE id = ?", (group_id,)
        ).fetchone()
        return dict(row) if row else None

    def add_group_member(self, group_id: int, user_id: int, role: str = "member") -> bool:
        """Add a member to a group. Returns True if added."""
        now = datetime.utcnow().isoformat()
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO group_members (group_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
                (group_id, user_id, role, now),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to add user {user_id} to group {group_id}: {e}")
            return False

    def remove_group_member(self, group_id: int, user_id: int) -> bool:
        """Remove a member from a group. Returns True if removed."""
        try:
            cursor = self.conn.execute(
                "DELETE FROM group_members WHERE group_id = ? AND user_id = ?",
                (group_id, user_id),
            )
            self.conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to remove user {user_id} from group {group_id}: {e}")
            return False

    def get_group_members(self, group_id: int) -> list[dict]:
        """List all members of a group with their role and email."""
        rows = self.conn.execute(
            """
            SELECT u.id, u.email, u.is_admin, gm.role, gm.joined_at
            FROM group_members gm
            JOIN users u ON gm.user_id = u.id
            WHERE gm.group_id = ?
            ORDER BY gm.joined_at ASC
            """,
            (group_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_user_groups(self, user_id: int) -> list[dict]:
        """List all groups a user belongs to."""
        rows = self.conn.execute(
            """
            SELECT g.*, gm.role, gm.joined_at
            FROM groups g
            JOIN group_members gm ON g.id = gm.group_id
            WHERE gm.user_id = ?
            ORDER BY g.name ASC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_group_paper_feed(self, group_id: int, limit: int = 100) -> list[dict]:
        """Get papers highly rated by any member of the group."""
        rows = self.conn.execute(
            """
            SELECT DISTINCT p.*, MAX(r.rating) as best_rating
            FROM papers p
            JOIN ratings r ON p.arxiv_id = r.arxiv_id
            JOIN group_members gm ON r.user_id = gm.user_id
            WHERE gm.group_id = ? AND r.rating >= 4
            GROUP BY p.arxiv_id
            ORDER BY best_rating DESC, p.published DESC
            LIMIT ?
            """,
            (group_id, limit),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_fetch_log(self, limit: int = 20) -> list[dict]:
        """Get recent fetch history (admin panel)."""
        rows = self.conn.execute(
            "SELECT * FROM fetch_log ORDER BY fetched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            try:
                d["categories"] = json.loads(d["categories"])
            except (json.JSONDecodeError, TypeError):
                pass
            result.append(d)
        return result

    def get_collection_papers(
        self, collection_id: int, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """Get all papers in a collection."""
        rows = self.conn.execute(
            """
            SELECT p.* FROM papers p
            INNER JOIN collection_papers cp ON p.arxiv_id = cp.arxiv_id
            WHERE cp.collection_id = ?
            ORDER BY cp.added_at DESC
            LIMIT ? OFFSET ?
            """,
            (collection_id, limit, offset),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_paper_collections(self, arxiv_id: str, user_id: int = 1) -> list[dict]:
        """Get all collections that a paper belongs to for a given user."""
        rows = self.conn.execute(
            """
            SELECT c.* FROM collections c
            INNER JOIN collection_papers cp ON c.id = cp.collection_id
            WHERE cp.arxiv_id = ? AND c.user_id = ?
            ORDER BY c.name ASC
            """,
            (arxiv_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_all_papers_for_metadata_refresh(self) -> list[dict]:
        """Get all papers stored in the database for metadata refresh."""
        rows = self.conn.execute("SELECT arxiv_id, bibcode FROM papers").fetchall()
        return [dict(row) for row in rows]

    def update_paper_ads_metadata(
        self,
        arxiv_id: str,
        bibcode: Optional[str],
        citation_count: int,
        read_count: int,
        refereed: int,
    ) -> bool:
        """Update a paper's ADS metadata fields. Returns True if updated."""
        try:
            self.conn.execute(
                """
                UPDATE papers
                SET bibcode = ?, citation_count = ?, read_count = ?, refereed = ?
                WHERE arxiv_id = ?
                """,
                (bibcode, citation_count, read_count, refereed, arxiv_id),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to update ADS metadata for {arxiv_id}: {e}")
            return False

    def get_full_summary(self, arxiv_id: str, mode: str) -> Optional[str]:
        """Fetch cached full-paper summary for a paper and mode."""
        try:
            row = self.conn.execute(
                "SELECT summary FROM full_summaries WHERE arxiv_id = ? AND mode = ?",
                (arxiv_id, mode),
            ).fetchone()
            return row["summary"] if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to fetch full summary for {arxiv_id} (mode: {mode}): {e}")
            return None

    def add_full_summary(self, arxiv_id: str, mode: str, summary: str) -> bool:
        """Cache a full-paper summary. Returns True if successful."""
        try:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO full_summaries (arxiv_id, mode, summary, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (arxiv_id, mode, summary, datetime.utcnow().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to cache full summary for {arxiv_id} (mode: {mode}): {e}")
            return False

    def get_paper_text(self, arxiv_id: str) -> Optional[str]:
        """Fetch cached full text for a paper."""
        try:
            row = self.conn.execute(
                "SELECT full_text FROM paper_texts WHERE arxiv_id = ?",
                (arxiv_id,),
            ).fetchone()
            return row["full_text"] if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to fetch paper text for {arxiv_id}: {e}")
            return None

    def add_paper_text(self, arxiv_id: str, full_text: str) -> bool:
        """Cache full text for a paper. Returns True if successful."""
        try:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO paper_texts (arxiv_id, full_text, created_at)
                VALUES (?, ?, ?)
                """,
                (arxiv_id, full_text, datetime.utcnow().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to cache paper text for {arxiv_id}: {e}")
            return False

    def get_brief(self, date: str) -> Optional[dict]:
        """Fetch research brief for a specific date (YYYY-MM-DD)."""
        try:
            row = self.conn.execute(
                "SELECT date, content, created_at FROM briefs WHERE date = ?",
                (date,),
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to fetch brief for {date}: {e}")
            return None

    def add_brief(self, date: str, content: str) -> bool:
        """Add or replace a research brief for a specific date. Returns True if successful."""
        try:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO briefs (date, content, created_at)
                VALUES (?, ?, ?)
                """,
                (date, content, datetime.utcnow().isoformat()),
            )
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Failed to save brief for {date}: {e}")
            return False

    def get_all_briefs(self) -> list[dict]:
        """Fetch all research briefs, sorted by date descending."""
        try:
            rows = self.conn.execute(
                "SELECT date, content, created_at FROM briefs ORDER BY date DESC"
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to fetch all briefs: {e}")
            return []

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
