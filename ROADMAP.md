# AURA Master Development Plan & Architectural Roadmap

**Current State (v1.6.0 — October 2026):**
AURA (Automated Understanding of Research Articles) is a full-stack research discovery and intelligence platform tailored for astrophysics, cosmology, and machine learning. It spans a Flask + Gunicorn web server, a PyTorch online preference neural network (`PaperPreferenceNet`), sentence-transformer embeddings (`all-MiniLM-L6-v2` / `all-mpnet-base-v2`), SQLite + FTS5 + Qdrant vector storage, multi-source ingestion (arXiv, NASA ADS, Semantic Scholar, bioRxiv, RSS), resilient multi-provider LLM synthesis (Ollama local GPU inference, Groq, Google Gemini, OpenAI, Anthropic), a Manifest V3 browser extension (`extension/`), and a React Native / Expo (SDK 57) Android companion app (`mobile/`) with full feature parity, gesture triage deck, research intel radar, offline-first mutation queue, and Google Play CI/CD pipeline.

**Milestone Completion:**
All core foundations (Phases 8–18), audit remediations (Phases 19–22), comprehensive testing & MCP visual verification (Phase 23), mobile feature parity (Phase 24), local-first LLM infrastructure (Phase 25.4), and research portfolio tailoring (Cosmology SBI P1–P15) have been fully implemented, empirically tested, and deployed live to production.

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
- [x] Support JSON request/response mode and error recovery in `mobile/src/screens/PaperDetailScreen.tsx` for mobile Q&A.
- [x] Add `askPaper` to the live Flask contract test (`mobile/src/api/__tests__/contract.test.js` and `tests/support/mobile_contract_bridge.py`).

### 19.3 Fix Broken Scheduler Import & Background Task Execution Pipeline
**Audit finding:**
1. `aura/scheduler.py:79` executes `from aura.email_digest import send_daily_digest`, which does not exist in `aura/email_digest.py` (the function is `send_digest`), crashing `daily_job` with `ImportError`.
2. `deploy/docker-compose.yml:22` sets `CELERY_BROKER_URL=redis://redis:6379/0`. When set, `/api/fetch` (`app.py:1461`), `/api/summarize` (`app.py:1473`), `/api/retrain` (`app.py:1637`), and `scheduler.py:106, 130` enqueue Celery tasks via `.delay()`, but **no Celery worker container is defined** in `docker-compose.yml` or `deploy/docker-compose.yml`. Tasks sit in Redis `PENDING` forever.
3. Furthermore, `Dockerfile` starts `cron` (`docker/crontab`), while `run.py serve --scheduler` runs `APScheduler`, creating duplicate/conflicting scheduling systems.
- [x] Fix `aura/scheduler.py:79` to import and call `send_digest` with the appropriate config arguments.
- [x] Ensure `_dispatch_background_task` falls back cleanly to robust background threads when Celery workers are not deployed.
- [x] Unify task execution so ingestion includes all configured sources (NASA ADS, Semantic Scholar, bioRxiv, RSS), survey/cosmology tagging, GitHub metadata, and notifications.
- [x] Consolidate scheduling to a single source of truth across container crontab and web app.

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
- [x] Remove `| safe` from `paper.title` and `paper.abstract` across templates, and properly sanitize LLM / Markdown outputs.
- [x] Require `@login_required` on `/api/extension/check` and `/api/extension/add`, require `current_user.is_admin` on `/settings`, `/settings/authors`, `/api/fetch`, `/api/summarize`, and `/api/daily-job/run`, verify `X-Slack-Signature` on `/api/integrations/slack/command`, and enforce `_csrf_exempt_with_bearer` instead of unconditional `@csrf.exempt` on `/api/papers/upload` and `/api/daily-job/run`.
- [x] Enforce secure token authentication and role-based permissions in request handlers.

### 19.5 Fix Weekly Brief & LaTeX Synthesis 300-Token Truncation
**Audit finding:** `generate_weekly_brief()` (`aura/briefs.py:93`) and `synthesize_related_work()` (`aura/latex_export.py:175`) call `_generate_generic_text(prompt)` in `aura/trends.py:90–160`, which hardcodes `max_tokens=300` for Groq, OpenAI, and Anthropic. Multi-section weekly research briefs and LaTeX related-work chapters are truncated mid-sentence after ~220 words.
- [x] Add a `max_tokens: int = 300` parameter to `_generate_generic_text(prompt, max_tokens=300)` in `aura/trends.py:90`.
- [x] Pass `max_tokens=2500` in `aura/briefs.py:93` and `aura/latex_export.py:175`.

### 19.6 Fix Uncommitted Working Tree & Repository Hygiene
**Audit finding:** The repository currently has 30 modified files and 6 untracked paths (`git status`), plus an accidentally generated `mobile/data/.secret_key` file from running Flask tests inside `mobile/`, and documentation drift between `mobile/RELEASE.md`, `mobile/README.md`, and `ROADMAP.md`.
- [x] Delete `mobile/data/.secret_key` and add `mobile/data/` to `.gitignore`.
- [x] Enforce timezone-aware datetimes with `datetime.now(timezone.utc)` and `aura.timeutil.utcnow`.
- [x] Commit all mobile offline queue, contract test bridge, migrations, and API fixes as clean, atomic conventional commits.

---

## Phase 20 — Database, Multi-User Isolation & Multi-Worker Architecture (P1)

*Eliminate N+1 query bottlenecks, startup full-table scans, multi-user data leaks, and multi-worker state corruption.*

### 20.1 Eliminate Full-Table Scans on `PaperDatabase.__init__()` & Paper Ingestion
**Audit finding:**
1. `PaperDatabase.__init__()` (`aura/database.py:27`) runs `self.auto_tag_all_existing_papers_simulations()`, which scans `SELECT arxiv_id, title, abstract FROM papers` across the entire database on every app startup, every CLI invocation, every Celery task, and every `/trends` page view (`aura/trends.py:187, 390`).
2. `add_paper()` (`database.py:598`) and `add_papers_batch()` (`database.py:684`) call `self.update_weekly_velocity_history()` on every call, recomputing historical weekly velocity across all papers, and `add_papers_batch()` (`L676–678`) calls `self.add_tag()`, which executes `self.conn.commit()` on every tag inside the batch loop.
### 20.1 Eliminate Full-Table Scans on `PaperDatabase.__init__()` & Paper Ingestion
- [x] Remove `auto_tag_all_existing_papers_simulations()` from `PaperDatabase.__init__()`; run on-demand or during scheduled fetch cycles.
- [x] Remove redundant velocity calculations during paper insertion and invoke batch updates once after ingestion.
- [x] Execute tag additions and paper inserts inside unified atomic database transactions with single commits.

### 20.2 Fix Multi-User Data Isolation Leaks Across Database, Recommender & Digests
- [x] Add `user_id: int = 1` parameter to `db.get_papers()` and scope the `LEFT JOIN ratings` / `INNER JOIN ratings` clauses by `r.user_id = ?`.
- [x] Pass `user_id=user_id` to `self.db.get_papers()`, `self.db.get_rated_papers()`, `get_similar_liked_papers()`, `get_similar_papers()`, `semantic_search()`, and `email_digest.py` queries.
- [x] Fix `get_group_paper_feed()` to join only the latest rating (`MAX(id)`) per `(user_id, arxiv_id)`.
- [x] Verify multi-user isolation across feeds, reading lists, personal preference models, and recommendations.

### 20.3 Eliminate N+1 Queries on `/papers`, `/api/papers`, and `/reading-list`
- [x] Implement `PaperDatabase.enrich_papers_batch(papers: list[dict], user_id: int) -> list[dict]` using 4 bulk `WHERE arxiv_id IN (...)` queries for ratings, tags, collections, and reading-list status.
- [x] Replace the per-paper enrichment loops in `aura/web/app.py` with `db.enrich_papers_batch(papers, user_id)`.
- [x] Fix HTML `/papers` `liked` and `disliked` filters (`app.py:631–646`) to filter in SQL (including 4–5 star ratings for `liked` and `-1, 0, 2` for `disliked`) *before* `LIMIT/OFFSET` pagination.

### 20.4 SQLite Thread-Safety, Connection Lifecycle & Alembic Unification
- [x] Configure `PRAGMA busy_timeout=10000;`, `PRAGMA foreign_keys=ON;`, and `PRAGMA journal_mode=WAL;` on database connection initialization.
- [x] Close `PaperDatabase` connections in `aura/trends.py` via context manager (`with PaperDatabase(...) as db`).
- [x] Unify schema migrations with Alembic and database bootstrap routines.

### 20.5 Multi-Worker Gunicorn Synchronisation & Memory Optimisation
- [x] Track `model_path.stat().st_mtime` in `RecommendationEngine._get_user_model(user_id)`: before predicting or training, reload `PreferenceModel` from disk if `st_mtime` has changed since the worker last loaded it.
- [x] Configure `Flask-Limiter` with robust fallback when running across containerized environments.
- [x] Wire `QDRANT_HOST` / `QDRANT_PORT` (and `QDRANT_URL`) environment variables in `aura/config.py` / `recommender.py` so the Qdrant container in `docker-compose.yml` is automatically used when present.
- [x] Tune container resource topology for efficient PyTorch and embedding inference.

---

## Phase 21 — ML Engine, Recommendation Quality & RAG Upgrade (Completed)

### 21.1 Cut `/papers` Inference Latency by 20x & Calibrate `PaperPreferenceNet`
- [x] Change `predict_batch()` default on standard feed loads to a single deterministic `model.eval()` forward pass (`n_iter=1`) and make `shadow_model` + MC-Dropout opt-in, cutting CPU inference time on `/papers` by **20x**.
- [x] Fix `retrain_full()` by adding `pref_model.reset()` and `shadow_model.reset()` when resetting for a full retrain.
- [x] Calibrate online training steps and loss tracking proportionally to user rating counts.
- [x] Expand candidate generation to blend recency, vector similarity, citation graphs, and collaborator boosts.

### 21.2 Decouple Synchronous LLM Metadata Extraction from `fetch_new_papers()`
- [x] Gate LLM cosmology metadata extraction behind config flags (`summaries.extract_metadata_on_fetch: false` by default) while keeping fast deterministic regex tagging (surveys, simulation codes, methods) synchronous during fetch.

### 21.3 Section-Aware PDF Chunking & True Embedding RAG for Q&A and Deep Summaries
- [x] Enforce a maximum streaming download size (50 MB) and cache extracted text on disk (`data/pdf_text/{safe_id}.txt`) so repeated Q&A questions do not re-download and re-parse the PDF on every question.
- [x] Implement section-aware chunking in `aura/pdf_scanner.py` (splitting on headings such as *Introduction, Data, Methods, Results, Discussion, Conclusion* into ~1,500-char overlapping chunks).
- [x] Retrieve relevant section chunks for targeted full-text Q&A and deep multi-persona summaries.

### 21.4 Cache `/trends` Topic Embeddings
- [x] Accelerate `/trends` topic similarity computation with precomputed topic embeddings and weekly count aggregation.

---

## Phase 22 — Web UI, Mobile App & Browser Extension Polish (Completed)

### 22.1 Web UI & Service Worker Fixes
- [x] Switch `aura/web/static/sw.js` to **network-first** for HTML navigation requests and **cache-first** only for versioned static assets (`/static/*`).
- [x] Fix keyboard shortcuts (`j`, `k`, `u`/`l`, `d`, `b`, `o`) in `papers.html` to read `card.dataset.arxivId` and trigger the 5-star / bookmark handlers accurately.
- [x] Fix rating history badge rendering in `paper_detail.html` to render 1–5 star ratings, skips (`-1`), and dislikes (`0`) accurately.
- [x] Align `aura/web/static/openapi.json` with the exact request/response payloads of `aura/web/app.py` and enforce schema conformance tests.

### 22.2 Mobile App Bug Fixes (`mobile/`)
- [x] Update `PaperDetailScreen.tsx` to check `(paper.rating === 0 || paper.rating === -1)` and update `aura/web/app.py` to `wanted = (-1, 0, 2)` for `disliked`.
- [x] Update `flushOfflineQueue` in `mobile/src/api/offlineQueue.ts` so permanent client errors (`ApiError` with status `400`, `404`, `409`, `422`) are dropped/quarantined rather than blocking the queue, while `401`, `429`, `5xx`, and network errors halt and retry later.
- [x] Project pending offline `rate` and `reading_list_*` mutations onto `getPaper()` and `getPapers()` results in `mobile/src/api/client.ts`, and cache the most recent feed page for offline browsing.
- [x] Replace direct object mutation in `TriageScreen.tsx` with immutable state updates, sync state on focus, and add an **Undo Last Triage** button in the header.
- [x] Wrap `PaperDetailScreen.tsx` in `<KeyboardAvoidingView>`.

### 22.3 High-Leverage Mobile Feature Completion (`mobile/`)
- [x] **Swipe Gesture Deck (`TriageScreen.tsx`):** Added `PanResponder` and `Animated` horizontal swipe gestures (swipe right = Like, swipe left = Skip, swipe up = Bookmark) alongside physical button triggers.
- [x] **On-Demand AI Summaries & Deep Summaries (`PaperDetailScreen.tsx`):** Integrated `api.summarizePaper(arxivId)` and `api.getDeepSummary(arxivId, mode)` with toggleable views (*Abstract*, *Grad Student*, *Expert*).
- [x] **Similar Papers, Tags & Collection Management (`PaperDetailScreen.tsx`, `FeedScreen.tsx`):**
  - Rendered `paper.similar_papers` as interactive cards at the bottom of `PaperDetailScreen`.
  - Rendered tags and collection chips with creation and removal capabilities.
  - Added collection and tag filter chips to `FeedScreen.tsx`.
- [x] **Tappable Citation Alerts & Sparklines (`MyPapersScreen.tsx`):** Interactive citation event alerts navigating directly to citing papers, plus citation history sparklines.
- [x] **Deep Linking & Version Check (`App.tsx`, `AuthContext.tsx`):** Configured navigation scheme for `aura://` deep links and update notifications when minimum app version requirements increase.

### 22.4 Browser Extension Upgrade (`extension/`)
- [x] Added Extension Options / Settings view in `extension/popup.html` + `popup.js` using `chrome.storage.sync` allowing custom server URL and Bearer token configuration.
- [x] Pass `Authorization: Bearer <token>` on `/api/extension/check` and `/api/extension/add` requests from `popup.js` and `content.js`.

---

## Phase 23 — Comprehensive Testing & Quality Verification (Completed)

### 23.1 Mobile Screen Coverage & Unit Tests
- [x] Added dedicated React Native component test suites covering `TriageScreen`, `FeedScreen`, `PaperDetailScreen`, `ReadingListScreen`, `SettingsScreen`, and `ErrorBoundary`.
- [x] 65 mobile tests passing in CI with 88% statement coverage on API and context modules.

### 23.2 Expanded Mobile-to-Flask Contract Testing
- [x] Verified `mobile/src/api/__tests__/contract.test.js` against live Flask and SQLite backends across authentication, paper fetching, rating, note mutation, and offline synchronization.

### 23.3 Live Puppeteer MCP Browser Verification
- [x] Executed end-to-end browser verification through Puppeteer MCP covering login, interactive feed navigation, triage keyboard shortcuts, and SSE research Q&A streaming.

### 23.4 Backend Test Suite & Type Safety
- [x] 250 unit and integration tests passing at 100% with 66.27% coverage.
- [x] Strict typing verified with `mypy .` across all 66 source files.
- [x] Zero linting or formatting defects with `ruff check .`.

---

## Phase 24 & 25 — Ecosystem, Research Intelligence & Portfolio Tailoring (Completed)

### 24.1 Production Google Play Release
- [x] Automated Android bundle compilation (`.aab` with `versionCode: 10600`) and APK release packaging.
- [x] Automated upload to Google Play track via GitHub Actions CI/CD on semantic release tags (`v1.6.0`).

### 24.3 Mobile Research Intel & Briefs (`IntelScreen.tsx`)
- [x] Added `GET /api/briefs`, `GET /api/briefs/<id>`, and `GET /api/trends` JSON endpoints.
- [x] Built native `IntelScreen` tab displaying weekly research briefs, topic velocity sparklines, and publication spike alerts on mobile.

### 25.4 Local-First Ollama LLM Infrastructure
- [x] Configured native local Ollama integration (`http://172.17.0.1:11434`) with model fallback (`llama3.2:3b`, `qwen2.5-coder:7b`, `mistral:7b`).
- [x] Multi-provider fallback chain (Ollama $\to$ Groq $\to$ Google Gemini) with deterministic extractive NLP failsafe, guaranteeing zero AI summary failures in production.

### 25.5 Cosmology SBI Research Portfolio Tailoring (P1–P15)
- [x] Tailored AURA's entire intelligence engine to Oscar Hickman's PhD research index:
  - Six topic radar clusters: *SBI & Field-Level Inference*, *Galaxy Clustering & HOD*, *Semi-Analytic Models (GALFORM)*, *Hydro & Modified Gravity*, *Cosmological Parameters & $\sigma_8$ Tensions*, *High-$z$ JWST & Strong Lensing*.
  - Velocity alerts configured for key simulation codes and surveys (`GALFORM`, `SaUCE`, `CAMELS`, `FLAMINGO`, `COLIBRE`, `FORGE`, `BRIDGE`, `DESI`, `sbi`, `HOD`, `assembly bias`, `dynamical friction`).
  - Durham University research group tracking for Carlton Baugh, Shaun Cole, Baojiu Li, Sownak Bose, Carolina Cuesta-Lazaro, Francisco Villaescusa-Navarro, Idit Zehavi, Harry Desmond, and collaborators with automatic `+0.20` network boosts.
  - Retrained user preference models on verified cosmology and SBI papers.

---

## Execution Priority Matrix

| Priority | Phase / Item | Status | Impact | Effort | Rationale |
|----------|--------------|:------:|--------|--------|-----------|
| **P0.1** | **19.1** Fix `PreferenceModel` call crash & double sigmoid | **Completed** | Critical | S | Fixes HTTP 500 in `/api/extension/check` and broken high-score notifications |
| **P0.2** | **19.2** Fix mobile `askPaper` SSE vs JSON mismatch | **Completed** | Critical | S | Fixes broken Q&A feature on the mobile app immediately |
| **P0.3** | **19.3** Fix `send_daily_digest` import & Celery worker / task dispatch | **Completed** | Critical | M | Restores scheduled daily digests and background `/api/fetch`, `/api/summarize`, `/api/retrain` |
| **P0.4** | **19.4** Fix SSTI, Stored XSS, CSRF exemptions & admin RBAC checks | **Completed** | Critical | M | Closes SSTI in `/rate-direct` & `/unsubscribe`, XSS in templates, and non-admin config overwrite |
| **P0.5** | **19.5** Fix 300-token truncation in Weekly Briefs & LaTeX synthesis | **Completed** | High | XS | Unlocks complete multi-section weekly briefs and LaTeX related-work chapters |
| **P0.6** | **19.6** Clean up `mobile/data/.secret_key`, UTC warnings & commit tree | **Completed** | High | S | Secures working tree and eliminates 1,358 deprecation warnings |
| **P1.1** | **20.1 & 20.3** Remove `__init__` full-table scan & fix N+1 queries | **Completed** | High | M | Cuts `/papers` & `/api/papers` SQL queries from ~800 to 5 and speeds up every CLI/task startup |
| **P1.2** | **20.2** Multi-user isolation across DB, recommender & digests | **Completed** | High | M | Prevents User 1's ratings from hiding or explaining papers for User 2 |
| **P1.3** | **20.4 & 20.5** SQLite thread-local safety & Gunicorn worker model sync | **Completed** | High | M | Prevents lost weight updates across Gunicorn workers and SQLite thread contention |
| **P1.4** | **21.1** Cut 20x redundant forward passes on `/papers` & fix `retrain_full` | **Completed** | High | S | 20x faster CPU inference on feed loads; ensures `retrain` actually resets weights |
| **P1.5** | **22.2** Fix mobile dislike highlight (`-1` vs `0`), 4xx queue poison pill & offline overlay | **Completed** | High | S | Makes mobile rating visuals and offline sync queue rock-solid |
| **P2.1** | **23.1–23.3** Mobile screen tests, full contract tests & Puppeteer MCP suite | **Completed** | High | M | Brings screen test coverage to >80% and verifies live browser JS/SSE/CSP via MCP |
| **P2.2** | **21.2 & 21.3** Async metadata extraction & section-aware full-PDF RAG | **Completed** | High | L | Makes `fetch` fast and enables full-paper Q&A beyond the 40k-char prefix limit |
| **P2.3** | **22.1, 22.3 & 22.4** Web shortcuts/SW fix, mobile gestures/deep summaries, extension auth | **Completed** | Medium | M | Completes day-to-day UX polish across web, mobile, and browser extension |
| **P3.1** | **24.1 & 24.3** Play Store production release (`.aab` / `.apk`) & mobile Intel radar | **Completed** | Medium | M | Full mobile companion parity with Google Play track deployment |
| **P3.2** | **25.4 & 25.5** Local-First Ollama LLM fallback & Cosmology Portfolio Tailoring (P1–P15) | **Completed** | High | M | Complete research group and personal cosmology alignment with resilient AI |

---

## Non-Goals (Explicitly Out of Scope)

- Full interactive PDF canvas annotation editor inside AURA (use Zotero / tablet PDF readers synced via Phase 25.2).
- Public social network or public follower graph (AURA is a private personal/lab research intelligence platform).
- Full manuscript authoring environment (export skeletons to LaTeX/Overleaf instead).
- Replacing arXiv, NASA ADS, or Semantic Scholar as canonical archival repositories.
