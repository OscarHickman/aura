# AURA Master Development Plan & Architectural Roadmap

**Current State (v1.3.x — October 2026):**
AURA (Automated Understanding of Research Articles) is a full-stack research discovery and intelligence platform tailored for astrophysics, cosmology, and machine learning. It spans a Flask + Gunicorn web server, a PyTorch online preference neural network (`PaperPreferenceNet`), sentence-transformer embeddings (`all-MiniLM-L6-v2` / `all-mpnet-base-v2`), SQLite + FTS5 + optional Qdrant vector storage, multi-source ingestion (arXiv, NASA ADS, Semantic Scholar, bioRxiv, RSS), multi-provider LLM synthesis (Groq, OpenAI, Anthropic, Gemini), a Manifest V3 browser extension (`extension/`), and a React Native / Expo (SDK 57) Android companion app (`mobile/`) with an offline-first mutation queue and Google Play CI/CD pipeline.

**Objective of This Document:**
Following a full-system audit of the backend, web UI, mobile app, database, ML pipeline, deployment stack, and test suites (228 backend tests + 58 mobile unit tests + live mobile-to-Flask contract test), this roadmap records:
1. **Completed Foundations (Phases 8–18)**
2. **Audit Findings & Critical Remediation Plan (Phases 19–22)** — exact file-and-line bugs, security vulnerabilities, multi-worker/database bottlenecks, and mobile contract mismatches discovered during review.
3. **Testing & MCP Verification Strategy (Phase 23)** — end-to-end Puppeteer MCP browser testing, expanded mobile screen/contract coverage, and property-based testing.
4. **Next-Generation Platform Maximisation (Phases 24–26)** — hybrid cross-encoder ranking, active learning, section-aware PDF RAG, mobile UX polish, and ecosystem expansion.

---

## Summary of Completed Foundations (Phases 8–18)

### Phase 8 — Scale & Production Hardening (Completed)
- [x] Optional Qdrant vector backend (`aura/vector_store.py`) with automatic startup migration and NumPy fallback.
- [x] `flask-limiter` rate limiting, `flask-wtf` CSRF protection, and `flask-talisman` CSP/security headers (`aura/web/app.py`).
- [x] Grafana dashboard JSON (`deploy/grafana_dashboard.json`) and Docker `HEALTHCHECK` (`Dockerfile`).
- [x] Atomic file replacement (`os.replace`) for preference model weights (`aura/model.py`) and per-user model partitioning (`preference_model_u{id}.pt`).

### Phase 9 — Advanced AI Features (Completed)
- [x] Full-text PDF download and extraction (`aura/pdf_scanner.py`) with structured Deep Dive Summaries (*Background / Methods / Results / Significance*) in `grad_student` and `expert` personas (`aura/llm.py`).
- [x] Streaming Server-Sent Events (SSE) Research Q&A (`/api/papers/<id>/ask`).
- [x] Visual Trend Radar (`/trends`) with weekly topic heatmaps, velocity sparklines, and spike alerts (`aura/trends.py`).
- [x] Semantic Scholar Citation Graph integration (`citations` table, bidirectional citation UI, and citation-based score boosting).
- [x] Weekly Research Briefs (`/briefs` and email delivery via `aura/briefs.py`).

### Phase 10 — Distribution & Ecosystem (Completed)
- [x] Interactive OpenAPI 3.0 documentation at `/api/docs` (`aura/web/static/openapi.json`).
- [x] Formal `PaperSource` plugin interface and entry-point registry (`aura/fetcher.py`, `docs/custom_sources.md`).
- [x] Multi-container `docker-compose.yml`, interactive `setup.sh`, and `run.py init` / `doctor` / `import` / `export` CLI commands.

### Phase 11 & 12 — Astronomy & Computational Cosmology Intelligence (Completed)
- [x] NASA ADS integration (`ADSSource`) with `bibcode`, `citation_count`, `read_count`, and `refereed` status tracking.
- [x] Survey & mission tracking (`surveys` table: DESI, Euclid, Rubin LSST, SKA, Simons Observatory, CMB-S4, HSC, DES, Planck).
- [x] Cosmological observable, dataset, and inference method extraction (SBI, neural posterior estimation, MCMC, emulators).
- [x] Tracked authors and collaborator network badges (`/settings/authors`, BibTeX author import).
- [x] GitHub repository release detection and live star/commit metadata (`aura/github.py`).

### Phase 13–18 — Mobile Platform, API Hardening, Resilience & Research Workflow (Mostly Completed)
- [x] React Native + Expo SDK 57 Android app (`mobile/`) with Triage Deck, Feed, Paper Reader, Q&A, Reading List, My Papers, and Server Connection Manager.
- [x] Hardened Bearer token lifecycle (`expires_at`, per-device rotation, revocation on logout, SHA/token management, 5/min IP + per-email login lockouts, opt-in CORS allow-list).
- [x] API versioning (`/api/v1/*`, `X-API-Version`, `X-Min-App-Version`).
- [x] Scoped offline mutation queue (`${serverUrl}|${userId}`) with serialised storage writes, idempotent note replay (`client_mutation_id` unique constraint), offline reading-list/note projection, and `ErrorBoundary` + `RecoveryView`.
- [x] Jest + React Native Testing Library suite (58 unit/component tests, >88% statement coverage on `src/api` and `src/context`) and live mobile-to-Flask/SQLite IPC contract test (`mobile/src/api/__tests__/contract.test.js`).
- [x] "My Papers" citation diffing (`citation_events`, `citation_history` sparklines, auto-ingestion of citing papers) and LaTeX/BibTeX thesis chapter export (`aura/latex_export.py`).
- [x] Production Android `.aab` / `.apk` signing and initial upload to Google Play Console Internal Testing track (`com.oscarhickman.aura`, documented in `mobile/RELEASE.md`).

---

## Phase 19 — Critical Bug & Security Remediation (P0 Immediate)

*Resolve concrete runtime crashes, security vulnerabilities, and broken features discovered during the October 2026 codebase audit.*

### 19.1 Fix `PreferenceModel` Call Crash & Double-Sigmoid Bug
**Audit finding:** `aura/web/app.py:2585, 2611` (`extension_check`) and `aura/notifications.py:138` (`notify_high_scoring_papers`) call `pref_model(emb_t)` directly on `PreferenceModel` (which is a wrapper class in `aura/model.py:44`, not an `nn.Module`, raising `TypeError: 'PreferenceModel' object is not callable`) and then pass the result through `torch.sigmoid()`, even though `PaperPreferenceNet` (`aura/model.py:40`) already terminates with `nn.Sigmoid()`. In `notifications.py:139`, a broad `except Exception:` silently swallows this crash on every run so high-score notifications never fire.
- [x] Replace `raw_score = pref_model(emb_t)` + `torch.sigmoid(raw_score)` in `aura/web/app.py:2585, 2611` and `aura/notifications.py:138` with `pref_model.predict(emb_np)`.
- [x] Add unit tests for `/api/extension/check` (both cached-embedding and live-arXiv-fetch branches) and `notify_high_scoring_papers` with a trained `PreferenceModel`.

### 19.2 Fix Mobile `askPaper` SSE vs JSON Protocol Mismatch
**Audit finding:** `mobile/src/api/client.ts:327–332` calls `this.request<{ answer: string }>('/api/papers/${arxivId}/ask')`, which invokes `await response.json()` (`client.ts:183`). However, `aura/web/app.py:1150–1174` (`ask_paper_question`) unconditionally returns `Response(generate(), mimetype="text/event-stream")` formatted as `data: {"chunk": "..."}\n\n`. Every mobile Q&A query throws a JSON `SyntaxError` at runtime.
- [x] Update `ask_paper_question` in `aura/web/app.py:1150–1174` so that when `request.headers.get("Accept") == "application/json"` or `data.get("stream") is False`, it collects chunks and returns `jsonify({"answer": full_answer, "arxiv_id": arxiv_id})`, while preserving SSE streaming for the web UI.
- [ ] Alternatively (or additionally), support incremental SSE chunk reading in `mobile/src/screens/PaperDetailScreen.tsx` for real-time mobile streaming.
- [x] Add `askPaper` to the live Flask contract test (`mobile/src/api/__tests__/contract.test.js` and `tests/support/mobile_contract_bridge.py`).

### 19.3 Fix Broken Scheduler Import & Background Task Execution Pipeline
**Audit finding:**
1. `aura/scheduler.py:79` executes `from aura.email_digest import send_daily_digest`, which does not exist in `aura/email_digest.py` (the function is `send_digest`), crashing `daily_job` with `ImportError`.
2. `deploy/docker-compose.yml:22` sets `CELERY_BROKER_URL=redis://redis:6379/0`. When set, `/api/fetch` (`app.py:1461`), `/api/summarize` (`app.py:1473`), `/api/retrain` (`app.py:1637`), and `scheduler.py:106, 130` enqueue Celery tasks via `.delay()`, but **no Celery worker container is defined** in `docker-compose.yml` or `deploy/docker-compose.yml`. Tasks sit in Redis `PENDING` forever.
3. Furthermore, `Dockerfile` starts `cron` (`docker/crontab`), while `run.py serve --scheduler` runs `APScheduler`, creating duplicate/conflicting scheduling systems.
- [x] Fix `aura/scheduler.py:79` to import and call `send_digest` with the appropriate config arguments.
- [ ] Add a dedicated `aura-worker` (Celery worker) service to `docker-compose.yml` and `deploy/docker-compose.yml` (or unset `CELERY_BROKER_URL` by default until the worker service is enabled so `_dispatch_background_task` falls back cleanly to background threads).
- [ ] Unify `aura/tasks.py` (`fetch_papers_page_task`) with `engine.fetch_new_papers()` so Celery fetches include all configured sources (NASA ADS, Semantic Scholar, bioRxiv, RSS), survey/cosmology tagging, GitHub metadata, Qdrant indexing, and notifications—not just arXiv.
- [ ] Consolidate scheduling to a single source of truth (either Celery Beat / `cron` in Docker or `APScheduler` in standalone mode, never both simultaneously).

### 19.4 Eliminate SSTI, Stored XSS, CSRF Gaps & Privilege Escalation
**Audit finding:**
1. **SSTI & XSS (`aura/web/app.py:2421, 2489`):** `unsubscribe_digest()` and `rate_direct()` interpolate `{user_record["email"]}`, `{paper_title}`, and `{arxiv_id}` into Python f-strings and pass the result to `render_template_string(html)`. Any paper title containing `{{ ... }}` executes server-side Jinja2 expressions (SSTI), and unescaped HTML triggers XSS. Both endpoints also mutate state on `GET` requests (vulnerable to email link prefetchers).
2. **Stored XSS in Templates (`papers.html:315, 480`, `paper_detail.html:2, 39, 422, 449, 472, 497, 545, 631`, `brief_detail.html:27`):** `{{ paper.title | safe }}` and `{{ paper.abstract | safe }}` render unescaped HTML from external feeds/uploads, and LLM outputs are injected via `.innerHTML` / `| safe` without sanitisation.
3. **Unauthenticated & Under-Authorised Routes (`aura/web/app.py`):**
   - `/api/extension/check` (`L2561`) and `/api/extension/add` (`L2621`, `@csrf.exempt`) lack `@login_required`, defaulting to `user_id = 1` and allowing unauthenticated callers to inject arbitrary papers into the database.
   - `/api/integrations/slack/command` (`L2491`, `@csrf.exempt`) does not verify Slack signing secrets.
   - `/settings` (`L2064, 2135`), `/settings/authors` (`L2185`), `/api/fetch` (`L1453`), `/api/summarize` (`L1466`), and `/api/daily-job/run` (`L2157`) check `@login_required` instead of `current_user.is_admin`, allowing any non-admin user to overwrite global `config.yaml` (including SMTP credentials and API keys).
   - `/api/papers/upload` (`L1502`) and `/api/daily-job/run` (`L2159`) have `@csrf.exempt` while accepting cookie session auth.
4. **Plaintext API Tokens & Unenforced Scopes (`aura/database.py:1776`, `aura/web/app.py:293`):** API tokens are stored in plaintext in `api_tokens.token`, and `token_scopes` (`read`, `write`, `admin`) are never enforced on routes.
- [x] Replace `render_template_string(f"...")` in `/unsubscribe/<token>` and `/rate-direct` with parameterised `render_template_string(template_str, email=..., paper_title=...)` (auto-escaped) and require a `POST` confirmation step (or `List-Unsubscribe-Post` one-click POST header) for state changes.
- [ ] Remove `| safe` from `paper.title` and `paper.abstract` across all templates; for FTS5 `<mark>` highlights (`aura/database.py:1129`), HTML-escape the underlying text before wrapping matches in `<mark>`, and sanitise all LLM/Markdown HTML with `nh3` / `bleach` or client-side DOMPurify.
- [x] Require `@login_required` on `/api/extension/check` and `/api/extension/add`, require `current_user.is_admin` on `/settings`, `/settings/authors`, `/api/fetch`, `/api/summarize`, and `/api/daily-job/run`, verify `X-Slack-Signature` on `/api/integrations/slack/command`, and enforce `_csrf_exempt_with_bearer` instead of unconditional `@csrf.exempt` on `/api/papers/upload` and `/api/daily-job/run`.
- [ ] Hash API tokens with SHA-256 at rest (`token_hash` column with prefix lookup) and enforce `read` / `write` / `admin` scopes in a request decorator.

### 19.5 Fix Weekly Brief & LaTeX Synthesis 300-Token Truncation
**Audit finding:** `generate_weekly_brief()` (`aura/briefs.py:93`) and `synthesize_related_work()` (`aura/latex_export.py:175`) call `_generate_generic_text(prompt)` in `aura/trends.py:90–160`, which hardcodes `max_tokens=300` for Groq, OpenAI, and Anthropic. Multi-section weekly research briefs and LaTeX related-work chapters are truncated mid-sentence after ~220 words.
- [x] Add a `max_tokens: int = 300` parameter to `_generate_generic_text(prompt, max_tokens=300)` in `aura/trends.py:90`.
- [x] Pass `max_tokens=2500` in `aura/briefs.py:93` and `aura/latex_export.py:175`.

### 19.6 Fix Uncommitted Working Tree & Repository Hygiene
**Audit finding:** The repository currently has 30 modified files and 6 untracked paths (`git status`), plus an accidentally generated `mobile/data/.secret_key` file from running Flask tests inside `mobile/`, and documentation drift between `mobile/RELEASE.md`, `mobile/README.md`, and `ROADMAP.md`.
- [x] Delete `mobile/data/.secret_key` and add `mobile/data/` to `.gitignore`.
- [ ] Replace `datetime.utcnow()` and `datetime.utcfromtimestamp()` in `aura/logging_config.py:19` and `tests/` with timezone-aware `datetime.now(timezone.utc)` / `datetime.fromtimestamp(..., timezone.utc)` (eliminating 1,358 pytest deprecation warnings).
- [ ] Commit the mobile offline queue, contract test bridge, Alembic migration (`d813f210abcd_add_note_mutation_ids.py`), and API fixes as clean, atomic conventional commits.

---

## Phase 20 — Database, Multi-User Isolation & Multi-Worker Architecture (P1)

*Eliminate N+1 query bottlenecks, startup full-table scans, multi-user data leaks, and multi-worker state corruption.*

### 20.1 Eliminate Full-Table Scans on `PaperDatabase.__init__()` & Paper Ingestion
**Audit finding:**
1. `PaperDatabase.__init__()` (`aura/database.py:27`) runs `self.auto_tag_all_existing_papers_simulations()`, which scans `SELECT arxiv_id, title, abstract FROM papers` across the entire database on every app startup, every CLI invocation, every Celery task, and every `/trends` page view (`aura/trends.py:187, 390`).
2. `add_paper()` (`database.py:598`) and `add_papers_batch()` (`database.py:684`) call `self.update_weekly_velocity_history()` on every call, recomputing historical weekly velocity across all papers, and `add_papers_batch()` (`L676–678`) calls `self.add_tag()`, which executes `self.conn.commit()` on every tag inside the batch loop.
- [ ] Remove `auto_tag_all_existing_papers_simulations()` from `PaperDatabase.__init__()`; run it only via an explicit one-time migration flag in `system_meta` or CLI command.
- [ ] Remove `update_weekly_velocity_history()` from `add_paper()` / `add_papers_batch()` and invoke it once at the end of `engine.fetch_new_papers()`.
- [ ] Add `commit: bool = True` to `add_tag()` so `add_papers_batch()` executes inside a single atomic transaction with one `conn.commit()`.

### 20.2 Fix Multi-User Data Isolation Leaks Across Database, Recommender & Digests
**Audit finding:**
1. `PaperDatabase.get_papers(unrated_only=True)` (`aura/database.py:732–745`) joins `ratings` without filtering by `user_id` (`LEFT JOIN ratings r ON p.arxiv_id = r.arxiv_id WHERE r.id IS NULL`). Once User 1 rates a paper, it disappears from User 2's unrated recommendations!
2. `RecommendationEngine.get_recommendations()` (`aura/recommender.py:530`) calls `self.db.get_rated_papers()` without `user_id=user_id`, so "Because you liked" explanations for all users are computed against User 1's ratings.
3. `get_similar_liked_papers()` (`recommender.py:697`), `get_similar_papers()` (`L844`), `semantic_search()` (`L863`), and `email_digest.py:804, 843` (`_collect_network_papers`, `_collect_group_papers`) hardcode `user_id=1`.
4. `get_group_paper_feed()` (`database.py:2020–2030`) joins `ratings` without deduplicating to the latest rating per user/paper.
- [ ] Add `user_id: int = 1` parameter to `db.get_papers()` and scope the `LEFT JOIN ratings` / `INNER JOIN ratings` clauses by `r.user_id = ?`.
- [ ] Pass `user_id=user_id` to `self.db.get_papers()`, `self.db.get_rated_papers()`, `get_similar_liked_papers()`, `get_similar_papers()`, `semantic_search()`, and `email_digest.py` queries.
- [ ] Fix `get_group_paper_feed()` to join only the latest rating (`MAX(id)`) per `(user_id, arxiv_id)`.
- [ ] Add a dedicated multi-user isolation test suite (`tests/test_multi_user_isolation.py`) verifying that User A's ratings, reading list, notes, and explanations never leak into User B's feed or digest.

### 20.3 Eliminate N+1 Queries on `/papers`, `/api/papers`, and `/reading-list`
**Audit finding:** Rendering `/papers` (`aura/web/app.py:670–676`), `/api/papers` (`L776–787`), or `/reading-list` (`L923–928`) loops over up to 200 papers and runs 4 separate SQL queries per paper (`get_latest_rating`, `get_paper_tags`, `get_paper_collections`, `is_in_reading_list`), generating up to 800 SQL queries per HTTP request.
- [x] Implement `PaperDatabase.enrich_papers_batch(papers: list[dict], user_id: int) -> list[dict]` using 4 bulk `WHERE arxiv_id IN (...)` queries for ratings, tags, collections, and reading-list status.
- [x] Replace the per-paper enrichment loops in `aura/web/app.py` with `db.enrich_papers_batch(papers, user_id)`.
- [x] Fix HTML `/papers` `liked` and `disliked` filters (`app.py:631–646`) to filter in SQL (including 4–5 star ratings for `liked` and `-1, 0, 2` for `disliked`) *before* `LIMIT/OFFSET` pagination.

### 20.4 SQLite Thread-Safety, Connection Lifecycle & Alembic Unification
**Audit finding:**
1. `PaperDatabase` shares a single `sqlite3.Connection` (`check_same_thread=False`) across threads without a `busy_timeout` PRAGMA or thread-local cursor/transaction isolation, risking `ProgrammingError` or interleaved commits under concurrent requests.
2. `aura/trends.py:187, 390` creates `PaperDatabase(db_path)` on every `/trends` request and never calls `db.close()`.
3. `migrations/versions/5b0234fff970_initial_schema.py` is a no-op (`pass`), so running `alembic upgrade head` on a blank DB before `PaperDatabase._create_tables()` fails, and `docker/entrypoint.sh:14` calls `python run.py migrate --check` which does not exist.
- [ ] Configure `PRAGMA busy_timeout=5000;` and `PRAGMA foreign_keys=ON;` on connection creation, and use `threading.local()` connections (or a thread-safe connection context manager) inside `PaperDatabase`.
- [ ] Close `PaperDatabase` connections in `aura/trends.py:187, 390` via `try/finally` (or pass `engine.db` directly).
- [ ] Unify `PaperDatabase._create_tables()` and Alembic so `python run.py migrate` cleanly bootstraps base tables, stamps/runs revisions, and supports `--check` as invoked by `docker/entrypoint.sh`.

### 20.5 Multi-Worker Gunicorn Synchronisation & Memory Optimisation
**Audit finding:** `Dockerfile:33` and `deploy/systemd/aura.service:9` start 4 Gunicorn workers (`-w 4`). Each worker loads its own copy of PyTorch + `sentence-transformers` (~4x RAM), keeps independent in-memory `PreferenceModel` instances in `engine._user_models` (causing Worker B to overwrite Worker A's newly trained weights on disk), and keeps separate `memory://` rate-limit buckets.
- [x] Track `model_path.stat().st_mtime` in `RecommendationEngine._get_user_model(user_id)`: before predicting or training, reload `PreferenceModel` from disk if `st_mtime` has changed since the worker last loaded it.
- [ ] Configure `Flask-Limiter` to use `REDIS_URL` / `CELERY_BROKER_URL` storage when Redis is available, falling back to `memory://` only in local single-process dev.
- [ ] Wire `QDRANT_HOST` / `QDRANT_PORT` (and `QDRANT_URL`) environment variables in `aura/config.py` so the Qdrant container in `docker-compose.yml` is automatically used when present.
- [ ] Update `Dockerfile` to run Gunicorn under a non-root `aura` user and tune worker/thread topology (`--workers 2 --threads 4` or `--preload` with lazy CUDA/fork-safe PyTorch init) to cut memory footprint in half.

---

## Phase 21 — ML Engine, Recommendation Quality & RAG Upgrade (P1/P2)

*Transform the ML and LLM pipeline from a prototype into a fast, calibrated, full-paper intelligence system.*

### 21.1 Cut `/papers` Inference Latency by 20x & Calibrate `PaperPreferenceNet`
**Audit finding:**
1. On every `/papers` and `/api/papers` load, `get_recommendations()` (`aura/recommender.py:508–509`) runs `user_pref_model.predict_batch(embeddings_batch, n_iter=10)` (10 MC-Dropout passes) **plus** `self.shadow_model.predict_batch(embeddings_batch, n_iter=10)` (10 more passes = **20 forward passes** over 500 papers), yet `model_uncertainty` and `shadow_score` are unused in ranking or UI (`recommender.py:639–641`).
2. `PaperPreferenceNet` (`aura/model.py:36–40`) applies `nn.Sigmoid()` inside the network and trains with `nn.BCELoss()`, and runs 10 epochs of Adam (`lr=1e-3`) on every single rating click (`train_single`), causing severe weight saturation during cold start (<10 rated papers).
3. `retrain_full()` (`aura/recommender.py:772–783`) instantiates `PreferenceModel(model_path=target_path)`, which immediately calls `self.load()` in `__init__` (`aura/model.py:83–84`), failing to reset weights before full retraining!
4. `get_recommendations()` (`aura/recommender.py:483`) truncates the candidate pool at `self.db.get_papers(limit=500)` ordered by `published DESC`, starving older relevant papers.
- [x] Change `predict_batch()` default on standard feed loads to a single deterministic `model.eval()` forward pass (`n_iter=1`) and make `shadow_model` + MC-Dropout opt-in (e.g. for an explicit "Exploration / Active Learning" feed mode), cutting CPU inference time on `/papers` by **20x**.
- [x] Fix `retrain_full()` by adding `pref_model.reset()` and `shadow_model.reset()` when resetting for a full retrain.
- [ ] Scale online training steps in `train_single()` proportionally to replay buffer size (e.g. 1–2 gradient steps with weight decay when `len(replay_buffer) < 15`) to prevent cold-start overfitting.
- [ ] Expand candidate generation in `get_recommendations()` to combine recent papers with Qdrant / vector-store top-K nearest neighbours of the user's positive centroids, so older high-relevance papers are never lost beyond the 500-paper recency window.

### 21.2 Decouple Synchronous LLM Metadata Extraction from `fetch_new_papers()`
**Audit finding:** `engine.fetch_new_papers()` (`aura/recommender.py:237`) unconditionally calls `self._extract_and_save_metadata(new_papers)` even when `generate_summaries=False`. Fetching 200 papers triggers 200 sequential synchronous LLM requests (`extract_cosmology_metadata`), blocking `fetch` for several minutes and exhausting rate limits.
- [ ] Gate LLM cosmology metadata extraction behind a config flag (`summaries.extract_metadata_on_fetch: false` by default, or run asynchronously via a background task / batched multi-paper LLM prompt) while keeping fast deterministic regex tagging (surveys, simulation codes, methods) synchronous during fetch.

### 21.3 Section-Aware PDF Chunking & True Embedding RAG for Q&A and Deep Summaries
**Audit finding:** `generate_full_summary()` (`aura/llm.py:445`) and `stream_ask_paper()` (`aura/llm.py:557`) download the PDF with no size cap and slice `full_text[:40000]`. For 15–40 page astrophysics/ML papers, the results, discussion, conclusions, and appendices beyond char 40,000 are completely discarded.
- [ ] Enforce a maximum streaming download size (e.g. 50 MB) and cache extracted text on disk (`data/pdf_text/{safe_id}.txt`) so repeated Q&A questions do not re-download and re-parse the PDF on every question.
- [ ] Implement section-aware chunking in `aura/pdf_scanner.py` (splitting on headings such as *Introduction, Data, Methods, Results, Discussion, Conclusion* into ~1,500-char overlapping chunks).
- [ ] For `stream_ask_paper()`, embed the chunks with `Embedder` (cached per paper) and retrieve the top-K most relevant chunks for the user's question + the abstract/conclusion, enabling accurate RAG across the entire paper length.
- [ ] For `generate_full_summary()`, perform a map-reduce or section-targeted extraction (Abstract + Introduction + Methods + Results + Conclusion sections) rather than blind prefix truncation.

### 21.4 Cache `/trends` Topic Embeddings
**Audit finding:** Every `GET /trends` request synchronously re-encodes all topic strings through `SentenceTransformer` and reloads all paper embeddings from SQLite (`aura/trends.py:361–493`).
- [ ] Cache computed `/trends` data in memory/SQLite with a 1-hour TTL (invalidated on `fetch_new_papers` or topic config edits).

---

## Phase 22 — Web UI, Mobile App & Browser Extension Polish (P1/P2)

*Fix concrete UI defects across the web dashboard, Android app, OpenAPI spec, and Chrome extension.*

### 22.1 Web UI & Service Worker Fixes
**Audit finding:**
1. `aura/web/static/sw.js` intercepts all non-API `GET` requests with a **cache-first** strategy (`caches.match(event.request).then(response => response || fetch(event.request))`), serving stale dashboard HTML on `/` after papers or ratings change.
2. Keyboard shortcuts `u` and `d` in `aura/web/templates/papers.html:560–594` look for removed `.btn-outline-success` / `.btn-outline-danger` selectors and corrupt `arxiv_id` by stripping `paper-` from the sanitised DOM `id`.
3. `aura/web/templates/paper_detail.html:325–329` displays all ratings `!= 1` (including 2–5 stars and `-1` skip) as "Thumbs Down".
4. `aura/web/static/openapi.json` has schema drift on `/api/papers/{arxiv_id}/deep-summary` (`mode` enum `grad` vs `grad_student`), `/api/explain/{arxiv_id}`, and `/api/reading-list`.
- [x] Switch `aura/web/static/sw.js` to **network-first** for HTML navigation requests and **cache-first** only for versioned static assets (`/static/*`).
- [x] Fix keyboard shortcuts (`j`, `k`, `u`/`l`, `d`, `b`, `o`) in `papers.html` to read `card.dataset.arxivId` and trigger the 5-star / bookmark handlers accurately.
- [ ] Fix rating history badge rendering in `paper_detail.html:325–329` to render 1–5 star ratings, skips (`-1`), and dislikes (`0`) accurately.
- [ ] Align `aura/web/static/openapi.json` with the exact request/response payloads of `aura/web/app.py` and add an automated schema conformance test in `tests/test_web_app.py`.

### 22.2 Mobile App Bug Fixes (`mobile/`)
**Audit finding:**
1. **Dislike Highlight Bug (`PaperDetailScreen.tsx:224–230`):** Pressing ThumbsDown sends `handleRate(-1)`, setting `paper.rating = -1`, but the active style checks `paper.rating === 0`, so the ThumbsDown button never highlights! Also, backend `_api_paper_list` (`app.py:742`) filters `disliked` by `wanted = (0, 2)` (excluding `-1`).
2. **Offline Queue 4xx Poison Pill (`mobile/src/api/offlineQueue.ts:93–117`):** In `flushOfflineQueue`, any thrown error breaks the replay loop and leaves the item at the head of the queue. A permanent 4xx error (`400`, `404`, `409`) permanently wedges all subsequent offline mutations for that user.
3. **Missing Offline Queue Projection on `getPapers` / `getPaper` (`mobile/src/api/client.ts:241–278`):** Unlike `getReadingList` and `getPaperNotes`, `getPapers` and `getPaper` do not overlay pending `rate`, `reading_list_add`, or `reading_list_remove` mutations from `getOfflineQueue(scope)`.
4. **In-Place State Mutation & Stale Focus in `TriageScreen.tsx` (`L45–47, 68–75`):** `TriageScreen` mutates `currentPaper.in_reading_list` directly and does not refresh state on screen focus when returning from `PaperDetailScreen`.
5. **Keyboard Occlusion (`PaperDetailScreen.tsx:301, 399`):** Q&A and Note `TextInput` fields at the bottom of `ScrollView` lack a `KeyboardAvoidingView`.
- [x] Update `PaperDetailScreen.tsx:224, 229` to check `(paper.rating === 0 || paper.rating === -1)` and update `aura/web/app.py:742` to `wanted = (-1, 0, 2)` for `disliked`.
- [x] Update `flushOfflineQueue` in `mobile/src/api/offlineQueue.ts` so permanent client errors (`ApiError` with status `400`, `404`, `409`, `422`) are dropped/quarantined rather than blocking the queue, while `401`, `429`, `5xx`, and network errors halt and retry later.
- [x] Project pending offline `rate` and `reading_list_*` mutations onto `getPaper()` and `getPapers()` results in `mobile/src/api/client.ts`, and cache the most recent feed page for offline browsing.
- [x] Replace direct object mutation in `TriageScreen.tsx:68–75` with immutable state updates, sync state on focus, and add an **Undo Last Triage** button in the header.
- [x] Wrap `PaperDetailScreen.tsx` in `<KeyboardAvoidingView>`.

### 22.3 High-Leverage Mobile Feature Completion (`mobile/`)
- [ ] **Swipe Gesture Deck (`TriageScreen.tsx`):** Add `PanResponder` / `Animated` horizontal swipe gestures (swipe right = Like, swipe left = Skip, swipe up = Bookmark) alongside the existing action buttons.
- [ ] **On-Demand AI Summaries & Deep Summaries (`PaperDetailScreen.tsx`):** Wire the existing `api.summarizePaper(arxivId)` method and a new `api.getDeepSummary(arxivId, mode)` method (`GET /api/papers/<id>/deep-summary?mode=grad_student|expert`) to buttons in `PaperDetailScreen` so users can generate missing summaries and toggle between Abstract, Grad Student, and Expert deep summaries on mobile.
- [ ] **Similar Papers, Tags & Collection Management (`PaperDetailScreen.tsx`, `FeedScreen.tsx`):**
  - Render `paper.similar_papers` (already returned by `GET /api/papers/<id>`) as tappable cards at the bottom of `PaperDetailScreen`.
  - Render `paper.tags` and `paper.collections` chips on `PaperDetailScreen` with support for removing a paper from a collection (`api.removePaperFromCollection`) and creating a new collection (`POST /api/collections`).
  - Add collection and tag filter chips to `FeedScreen.tsx`.
- [ ] **Tappable Citation Alerts & Sparklines (`MyPapersScreen.tsx`):** Make citation event banners tappable to navigate to `PaperDetail` for `ev.citing_arxiv_id`, and render citation history (`api.getCitationHistory(paperId)`) on tracked publications.
- [ ] **Deep Linking & Version Check (`App.tsx`, `AuthContext.tsx`):** Configure React Navigation `linking` for the `aura://` URL scheme (`aura://papers/:arxivId`, `aura://my-papers`, `aura://triage`) and surface an update banner when `min_app_version` from `/api/auth/me` exceeds the installed app version.

### 22.4 Browser Extension Upgrade (`extension/`)
- [ ] Add an Extension Options / Settings view in `extension/popup.html` + `popup.js` using `chrome.storage.sync` so users can configure their AURA server URL (e.g. `http://100.88.127.35/aura` or custom domain) and personal Bearer API token (`aura_...`), instead of hardcoding `http://127.0.0.1:5000`.
- [ ] Pass `Authorization: Bearer <token>` on `/api/extension/check` and `/api/extension/add` requests from `popup.js` and `content.js`.

---

## Phase 23 — Comprehensive Testing, Contract Verification & MCP Browser Testing

*Maximise confidence across backend, web UI, and mobile through automated unit, contract, and live MCP browser testing.*

### 23.1 Mobile Screen Coverage & ESLint Gate
**Audit finding:** `mobile/jest.config.js` only collects coverage from `src/api/*.ts` and `src/context/*.tsx`, while `PaperDetailScreen.tsx` (877 lines), `MyPapersScreen.tsx` (617 lines), `SettingsScreen.tsx` (469 lines), and `App.tsx` (142 lines) have **0% test coverage**, and `mobile/` has no ESLint configuration.
- [ ] Add dedicated React Native Testing Library suites:
  - `mobile/src/screens/__tests__/PaperDetailScreen.test.tsx`: rating, bookmarking, Q&A submission/response, note creation/deletion with `[critique|idea|summary]` prefixes, collection modal, summary generation, and similar-paper navigation.
  - `mobile/src/screens/__tests__/MyPapersScreen.test.tsx`: tracked publication list, add-paper modal validation, delete confirmation, citation refresh, and citation alert tap navigation.
  - `mobile/src/screens/__tests__/SettingsScreen.test.tsx`: server URL validation, live `/health` ping diagnostics, login/logout flows, and manual offline queue sync.
- [ ] Expand `collectCoverageFrom` in `mobile/jest.config.js` to include `src/screens/**/*.tsx` and `src/components/**/*.tsx` with enforced CI coverage thresholds.
- [ ] Add ESLint (`eslint`, `@typescript-eslint/*`) and a `pnpm lint` step in `.github/workflows/ci.yml`.

### 23.2 Expanded Mobile-to-Flask Contract Testing
**Audit finding:** `mobile/src/api/__tests__/contract.test.js` did not test `askPaper`, `summarizePaper`, `getCollections` / `addPaperToCollection` / `removePaperFromCollection`, or `getMyPapers` / `addMyPaper` / `deleteMyPaper` / `getCitationEvents` / `getCitationHistory`, which allowed the `askPaper` SSE/JSON mismatch to go unnoticed.
- [ ] Expand `contract.test.js` and `tests/support/mobile_contract_bridge.py` to exercise every single method on `AuraApiClient` against the real Flask application and SQLite database, including 4xx poison-pill resilience in `flushOfflineQueue`.

### 23.3 Live Puppeteer MCP Browser & E2E Visual Verification
**Why it matters:** Backend `FlaskClient` tests (`tests/test_web_app.py`, `tests/test_e2e.py`) verify HTTP status codes and HTML strings, but they do not execute browser JavaScript (`window.fetch` subpath proxy wrapper in `base.html`, SSE streaming reader in `paper_detail.html`, Chart/heatmap rendering in `trends.html`, Service Worker registration in `sw.js`, or keyboard shortcuts in `papers.html`).
- [x] Build and run the **Puppeteer MCP Verification Harness** (verified against local server with registration, login, onboarding 5-star rating, feed keyboard navigation 'j' / 'u' / 'd', and paper detail live Q&A submission).

### 23.4 Backend Coverage & Property-Based Testing
- [ ] Raise `.github/workflows/ci.yml` pytest coverage gate from `--cov-fail-under=65` to `80%`.
- [ ] Enable `mypy --check-untyped-defs` across `aura/` (resolving the 4 untyped function notes in `aura/web/app.py:1237, 1260, 1261, 2004`).

---

## Phase 24 — Next-Generation Push, Mobile & Cross-Platform Ecosystem

*Complete the mobile release lifecycle and turn AURA into a proactive daily companion.*

### 24.1 Production Google Play Rollout & Store Listing Completion
- [ ] Complete store listing assets: high-res app icon, feature graphic, and annotated phone screenshots (Triage Deck, Ranked Feed, Paper Reader + Q&A, Reading List, My Papers Citation Alerts).
- [ ] Complete Google Play Data Safety declaration (documenting self-hosted home-server architecture and opt-in telemetry).
- [ ] Promote `com.oscarhickman.aura` from the Google Play **Internal Testing** track (verified on 2026-10-14) to **Closed/Production** track on tag `v1.4.0`.

### 24.2 Native Push Notifications (`expo-notifications`)
- [ ] Add `device_push_tokens` table (`id`, `user_id`, `token_id`, `expo_push_token`, `platform`, `created_at`, `quiet_hours_json`) and `POST /api/devices` / `DELETE /api/devices` endpoints.
- [ ] Register Expo push tokens in `mobile/` after login and automatically unregister on `POST /api/auth/logout` or token revocation.
- [ ] Extend `aura/notifications.py` to dispatch push notifications alongside Slack/Discord webhooks for:
  - Daily digest ready ("5 new high-match papers today")
  - High-score paper alert (`score >= threshold`)
  - New citation alert on user's tracked publications (`citation_events`)
- [ ] Deep-link push notification taps directly to `aura://papers/:arxivId` or `aura://my-papers`.

### 24.3 Mobile Trends, Weekly Briefs & Audio Digest ("Podcast Mode")
- [ ] Add JSON endpoints `GET /api/briefs` / `GET /api/briefs/<id>` and `GET /api/trends` so weekly research briefs and rising topic alerts can be read natively inside the mobile app.
- [ ] **Audio Briefings (TTS):** Optional generation of a 3–5 minute daily audio summary MP3 from the daily digest / weekly brief (using OpenAI TTS / ElevenLabs / local Piper TTS), playable with background audio controls in the mobile app during a commute.

### 24.4 iOS Build & Tablet/Foldable Responsive Layout
- [ ] Verify layout on iOS Simulator and Android tablets/foldables (two-pane master-detail view for Feed + PaperDetail on wide screens).
- [ ] Add iOS `expo prebuild` job on `macos-latest` in GitHub Actions for TestFlight distribution.

---

## Phase 25 — Frontier Research Intelligence & Academic Ecosystem Integration

*High-leverage differentiators that make AURA indispensable for an academic research group.*

### 25.1 Two-Stage Ranking (Bi-Encoder Retrieval + Cross-Encoder Re-Ranking) & Active Learning
- [ ] **Multi-Interest User Prototypes:** Instead of a single MLP score or single mean vector, cluster the user's positively rated papers into $K$ sub-field prototypes (e.g. *Simulation-Based Inference*, *Weak Lensing*, *21cm Cosmology*) so papers matching any distinct research interest receive high similarity explanations.
- [ ] **Active Learning / Uncertainty Triage Mode:** Use the calibrated epistemic uncertainty from `PaperPreferenceNet` (`model_uncertainty`) in `TriageScreen` to offer an **"Explore Boundary"** mode that surfaces papers where the model is most uncertain, rapidly improving preference boundaries with minimal ratings.
- [ ] **Implicit Negative & Dwell-Time Signals:** Incorporate explicit skips (`rating = -1`) with configurable lower weight (`0.25`) vs explicit dislikes (`rating = 0`, weight `1.0`) so skipping a paper gently nudges the model without over-penalising an entire sub-field.

### 25.2 Two-Way Reference Manager Sync (Zotero & BibTeX Watch)
- [ ] **Zotero Web API Sync:** Optional two-way integration with Zotero (`pyzotero` / REST API):
  - Automatically push bookmarked (`reading_list`) or 5-star papers—along with AURA's AI summary and user research notes—into a designated Zotero collection.
  - Pull existing Zotero collections to bootstrap and continuously update the user's `PreferenceModel` and `tracked_authors`.
- [ ] **Overleaf / Git Export Webhook:** One-click push of a collection's generated `.bib` and LaTeX related-work skeleton (`aura/latex_export.py`) to a linked Git repository or Overleaf Git bridge.

### 25.3 Multi-Paper Comparative Synthesis ("Compare Papers" Matrix)
- [ ] Select 2–10 papers (or an entire collection) and generate a structured **Literature Comparison Matrix** comparing:
  - *Research Objective / Cosmological Probe*
  - *Dataset / Survey Release (e.g. DESI DR1 vs SDSS BOSS)*
  - *Methodology / Model Architecture*
  - *Key Quantitative Constraints (e.g. $\sigma_8$, $S_8$, $H_0$)*
  - *Code / Data Availability*
- [ ] Exportable as Markdown, CSV, or a LaTeX `tabular` environment for direct inclusion in a paper or thesis.

### 25.4 Local-First LLM Support (Ollama / vLLM / llama.cpp)
- [ ] Add an OpenAI-compatible local endpoint configuration (`LLM_BASE_URL`, e.g. `http://localhost:11434/v1` for Ollama) in `aura/llm.py` so self-hosters with a local GPU can run summarization, cosmology metadata extraction, and full-text RAG Q&A with **zero external API cost and 100% data privacy**.

---

## Execution Priority Matrix

| Priority | Phase / Item | Impact | Effort | Rationale |
|----------|--------------|--------|--------|-----------|
| **P0.1** | **19.1** Fix `PreferenceModel` call crash & double sigmoid | Critical | S | Fixes HTTP 500 in `/api/extension/check` and broken high-score notifications |
| **P0.2** | **19.2** Fix mobile `askPaper` SSE vs JSON mismatch | Critical | S | Fixes broken Q&A feature on the mobile app immediately |
| **P0.3** | **19.3** Fix `send_daily_digest` import & Celery worker / task dispatch | Critical | M | Restores scheduled daily digests and background `/api/fetch`, `/api/summarize`, `/api/retrain` |
| **P0.4** | **19.4** Fix SSTI, Stored XSS, CSRF exemptions & admin RBAC checks | Critical | M | Closes SSTI in `/rate-direct` & `/unsubscribe`, XSS in templates, and non-admin config overwrite |
| **P0.5** | **19.5** Fix 300-token truncation in Weekly Briefs & LaTeX synthesis | High | XS | Unlocks complete multi-section weekly briefs and LaTeX related-work chapters |
| **P0.6** | **19.6** Clean up `mobile/data/.secret_key`, UTC warnings & commit tree | High | S | Secures working tree and eliminates 1,358 deprecation warnings |
| **P1.1** | **20.1 & 20.3** Remove `__init__` full-table scan & fix N+1 queries | High | M | Cuts `/papers` & `/api/papers` SQL queries from ~800 to 5 and speeds up every CLI/task startup |
| **P1.2** | **20.2** Multi-user isolation across DB, recommender & digests | High | M | Prevents User 1's ratings from hiding or explaining papers for User 2 |
| **P1.3** | **20.4 & 20.5** SQLite thread-local safety & Gunicorn worker model sync | High | M | Prevents lost weight updates across Gunicorn workers and SQLite thread contention |
| **P1.4** | **21.1** Cut 20x redundant forward passes on `/papers` & fix `retrain_full` | High | S | 20x faster CPU inference on feed loads; ensures `retrain` actually resets weights |
| **P1.5** | **22.2** Fix mobile dislike highlight (`-1` vs `0`), 4xx queue poison pill & offline overlay | High | S | Makes mobile rating visuals and offline sync queue rock-solid |
| **P2.1** | **23.1–23.3** Mobile screen tests, full contract tests & Puppeteer MCP suite | High | M | Brings screen test coverage to >80% and verifies live browser JS/SSE/CSP via MCP |
| **P2.2** | **21.2 & 21.3** Async metadata extraction & section-aware full-PDF RAG | High | L | Makes `fetch` fast and enables full-paper Q&A beyond the 40k-char prefix limit |
| **P2.3** | **22.1, 22.3 & 22.4** Web shortcuts/SW fix, mobile gestures/deep summaries, extension auth | Medium | M | Completes day-to-day UX polish across web, mobile, and browser extension |
| **P3.1** | **24.1–24.4** Play Store production track, Expo push notifications & mobile briefs | Medium | M | Turns the mobile app into a proactive daily companion |
| **P3.2** | **25.1–25.4** Active learning, Zotero 2-way sync, comparative matrix & Ollama support | Medium | L | Differentiates AURA as a complete lab-grade research workspace |

---

## Non-Goals (Explicitly Out of Scope)

- Full interactive PDF canvas annotation editor inside AURA (use Zotero / tablet PDF readers synced via Phase 25.2).
- Public social network or public follower graph (AURA is a private personal/lab research intelligence platform).
- Full manuscript authoring environment (export skeletons to LaTeX/Overleaf instead).
- Replacing arXiv, NASA ADS, or Semantic Scholar as canonical archival repositories.
