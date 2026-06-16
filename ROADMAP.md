# AURA Roadmap — From Research Tool to Full Product

**Current state:** Single-user local Flask app. Fetches arXiv papers, generates sentence-transformer embeddings, trains a small preference neural network from thumbs-up/down feedback, generates LLM summaries, and sends email digests. Solid core. Rough edges everywhere else.

**Goal:** A self-hostable, feature-rich research discovery platform that a lab or individual researcher would reach for every day.

---

## Phase 1 — Foundation & Developer Experience

*Make the codebase production-grade before building on top of it.*

### 1.1 Logging & Error Observability
**Why it matters:** Errors currently get swallowed or logged to stdout with no structure. Impossible to diagnose production issues.

- [ ] Add structured JSON logging via `python-json-logger`
- [ ] Add `X-Request-ID` header and thread-local context to all log lines
- [ ] Add a `/api/logs` endpoint (last N lines, admin-only) for self-hosted debugging
- [ ] Integrate Sentry SDK (optional, behind `SENTRY_DSN` env var)

---

## Phase 2 — Core UX Polish

*Make the daily workflow actually pleasant.*

### 2.1 Full-Text Paper Search
**Why it matters:** Users currently have no way to find a specific paper they remember reading. With thousands of papers in the DB, browsing is the only option.

- [ ] Add SQLite FTS5 virtual table mirroring `title + abstract`
- [ ] Add `/api/search?q=...` endpoint with ranked results
- [ ] Add a search bar to the navigation in `base.html`
- [ ] Support category and date range filters on search results
- [ ] Highlight matching terms in results

### 2.2 Paper Detail Page
**Why it matters:** Clicking a paper title currently opens arXiv in a new tab. There is no in-app view of a paper's full information, related papers, or rating history.

- [ ] Add `/papers/<arxiv_id>` route with full metadata view
- [ ] Show full abstract, all authors, all categories
- [ ] Show all ratings history for the paper
- [ ] Show similar papers (cosine similarity against stored embeddings)
- [ ] Embed an arXiv abstract iframe or link to ar5iv (HTML version)
- [ ] Show "papers by same authors" from the local database

### 2.3 Tagging & Collections
**Why it matters:** A researcher needs to organize papers — "papers for my thesis", "papers to discuss at journal club", "papers I cited". Currently there is no way to do this.

- [ ] Add `tags` and `collections` tables to the database
- [ ] API: `POST /papers/{id}/tags`, `GET /tags`, `DELETE /papers/{id}/tags/{tag}`
- [ ] API: `POST /collections`, `POST /collections/{id}/papers`
- [ ] UI: inline tag editor on paper cards
- [ ] UI: collections sidebar in the papers view
- [ ] UI: filter papers view by tag or collection

### 2.4 Reading List / Queue
**Why it matters:** "Read later" is the most common research workflow action. No such concept exists in AURA today.

- [ ] Add a `reading_list` table (paper_id, added_at, read_at)
- [ ] "Save for later" button on every paper card
- [ ] `/reading-list` page with unread/read tabs
- [ ] Mark as read action removes from unread queue

### 2.5 UI Modernisation
**Why it matters:** The current Bootstrap UI has two duplicate "Model Info" cards on the dashboard, hardcoded category strings in templates, and no keyboard shortcuts — all friction for daily use.

- [ ] Fix duplicate Model Info cards on dashboard
- [ ] Add keyboard shortcuts: `j`/`k` navigate papers, `u`/`d` rate thumbs up/down, `/` focus search
- [ ] Add infinite scroll or virtual list for the papers page (remove manual pagination)
- [ ] Add a dark mode toggle (localStorage-persisted)
- [ ] Make the layout responsive / mobile-friendly (PWA-ready)
- [ ] Add skeleton loading states instead of blocking page loads

---

## Phase 3 — ML & Recommendation Improvements

*Make the recommendations actually learn better and faster.*

### 3.1 Cold Start Bootstrap
**Why it matters:** A fresh user with zero ratings sees no differentiation — every paper scores ~0.5. They need to rate ≥5 papers before recommendations diverge. This kills first-run experience.

- [ ] Add an onboarding wizard: show 20 diverse papers across categories for initial rating
- [ ] Cluster papers by topic (k-means on embeddings) and sample one from each cluster
- [ ] Show "What are you interested in?" topic picker that pre-seeds ratings
- [ ] Document the minimum ratings needed for each confidence level

### 3.2 Recommendation Explainability
**Why it matters:** Users don't know *why* AURA ranks a paper highly. Is it because of the topic? A similar paper they liked? The opacity erodes trust.

- [ ] For each recommendation, find the 3 most similar liked papers (nearest neighbors in embedding space)
- [ ] Show "Because you liked: [paper title]" on each card
- [ ] Expose `GET /api/explain/{arxiv_id}` endpoint returning influencing papers
- [ ] Add visual score breakdown: model score + freshness boost + summary bonus

### 3.3 Better Model Architecture
**Why it matters:** The current 384→128→64→32→1 network is tiny and trained with online SGD one sample at a time — it forgets earlier ratings when it overtrains on recent ones (catastrophic forgetting).

- [ ] Implement experience replay: keep a sliding window buffer of past ratings; include them in every `train_single` call
- [ ] Add learning rate scheduling (`CosineAnnealingLR`) for full retrains
- [ ] Expose model confidence / uncertainty via MC Dropout at inference
- [ ] Add A/B testing capability: shadow model trained on different hyperparameters
- [ ] Persist `train_history` to the database for loss curve visualization

### 3.4 Semantic Search & Topic Clustering
**Why it matters:** Beyond keyword search, researchers want "find papers like this one" and "what is the field talking about this week?"

- [ ] Implement "find similar" via cosine similarity across all stored embeddings (no external vector DB needed at this scale)
- [ ] Add a `/topics` page with auto-discovered topic clusters (k-means, elbow method for k)
- [ ] Show per-topic paper counts and trend arrows (week-over-week)
- [ ] Link topics to the existing trends engine in `trends.py`

### 3.5 Feedback Quality Improvements
**Why it matters:** Binary thumbs up/down is too coarse. Researchers have nuanced opinions: "relevant topic but bad paper", "not my field now but save for later."

- [ ] Add 5-star granular rating (maps to 0.0–1.0 labels for the model)
- [ ] Add "skip" action (excludes paper from training, not just unrated)
- [ ] Add "save for later" (soft positive signal for the model)
- [ ] Track rating change events (re-rating) as model update signals

---

## Phase 4 — Multi-Source Paper Ingestion

*Break out of arXiv-only.*

### 4.1 Source Abstraction Layer
**Why it matters:** Everything in `fetcher.py` is arXiv-specific. Adding a new source requires rewriting the fetcher.

- [ ] Define a `PaperSource` protocol (abstract base) with `fetch(categories, max_results, days_back) -> list[Paper]`
- [ ] Refactor `fetcher.py` as `ArxivSource` implementing the protocol
- [ ] Add `source` column to `papers` table (tracks origin for deduplication and display)
- [ ] Update `RecommendationEngine` to accept a list of sources

### 4.2 Semantic Scholar Integration
- [ ] Implement `SemanticScholarSource` using the free S2 API
- [ ] Map S2 fields to the common `Paper` schema
- [ ] Add citation count to the paper schema and show it on cards
- [ ] Use citation count as an optional secondary ranking signal

### 4.3 RSS / Journal Feed Support
- [ ] Implement a generic `RSSSource` that parses journal RSS feeds (Nature, Science, MNRAS, ApJ, etc.)
- [ ] Allow users to add custom RSS URLs via the settings page
- [ ] Store feed metadata so papers can be linked back to their journal

### 4.4 bioRxiv / medRxiv Support
- [ ] Implement `BiorxivSource` using the bioRxiv API
- [ ] Allow users to configure which preprint servers to include

---

## Phase 5 — Multi-User & Authentication

*Turn a solo tool into a shared lab resource.*

### 5.1 User Accounts
**Why it matters:** AURA has a global singleton `engine` in `app.py`. All users share one preference model and one rating history. This is incompatible with shared deployments.

- [ ] Add `users` table: `id`, `email`, `password_hash`, `created_at`
- [ ] Implement session auth via `flask-login` with bcrypt password hashing
- [ ] Scope all ratings, tags, collections, and reading lists to `user_id`
- [ ] Each user gets their own preference model file (`data/models/{user_id}.pt`)
- [ ] Add `/login`, `/logout`, `/register` routes

### 5.2 API Tokens
- [ ] Add `api_tokens` table for programmatic access
- [ ] `POST /api/tokens` to create tokens (scoped: read, write, admin)
- [ ] Support `Authorization: Bearer <token>` header on all API routes
- [ ] Token revocation endpoint

### 5.3 Admin Panel
- [ ] `/admin` route showing all users, fetch history, system health
- [ ] Admin can trigger global fetch, summarize, and retrain
- [ ] User management: suspend, delete, reset password

---

## Phase 6 — Collaboration & Sharing

*Research is social.*

### 6.1 Paper Annotations & Notes
- [ ] Add `annotations` table: `user_id`, `arxiv_id`, `text`, `highlight_range`, `created_at`
- [ ] Show inline note editor on the paper detail page
- [ ] Export notes to markdown or BibTeX comment fields

### 6.2 Shared Collections
- [ ] Collections can be made public or shared with specific users
- [ ] Public collections get a shareable URL (`/collections/{slug}`)
- [ ] Allow "forking" a public collection into your own library

### 6.3 Lab/Team Groups
- [ ] Add `groups` table: users can belong to multiple groups
- [ ] Group paper feed: shows papers highly rated by any group member
- [ ] Group digest email: aggregated recommendations for the whole lab

---

## Phase 7 — Notifications & Integrations

*Meet researchers where they already are.*

### 7.1 Email Digest Improvements
**Why it matters:** The current digest email is plain HTML with inline styles. It has no unsubscribe link, no open tracking, and no way to rate papers from the email.

- [ ] Add one-click rating links in the email (authenticated via signed JWT in URL)
- [ ] Add unsubscribe link (`/unsubscribe/{token}`) stored in `users` table
- [ ] Add configurable digest frequency: daily, weekly, or off
- [ ] Improve HTML template: better typography, paper cover images from arXiv

### 7.2 Slack / Discord Integration
- [ ] Webhook-based notification when a high-scoring paper is fetched
- [ ] `/aura recommend` Slack slash command (OAuth app)
- [ ] Daily digest posted to a configured Slack channel

### 7.3 Reference Manager Export
**Why it matters:** Researchers live in Zotero and Mendeley. Discovered papers should flow directly into their citation manager.

- [ ] Add `/papers/{id}/export/bibtex` endpoint
- [ ] Add `/papers/export/bibtex?collection={id}` for bulk export
- [ ] Add `/papers/export/ris` for RIS format
- [ ] Add Zotero Connector compatibility header so the browser extension works

### 7.4 Browser Extension
- [ ] Simple Chrome/Firefox extension: "Add to AURA" button on arXiv paper pages
- [ ] Fetches the paper and adds it directly to the user's library
- [ ] Shows AURA score for the current page if already in the database

---

## Phase 8 — Scale & Production Hardening

*Make it reliable enough to run on a server.*

### 8.1 Vector Database Migration (Optional)
**Why it matters:** SQLite BLOB storage for embeddings works up to ~50k papers but becomes slow for similarity queries at scale.

- [ ] Add optional ChromaDB or Qdrant backend (feature-flagged)
- [ ] Migrate existing embeddings on startup if vector DB is configured
- [ ] Fall back to numpy cosine similarity if no vector DB is configured

### 8.2 Rate Limiting & Security
- [ ] Add `flask-limiter` to all API endpoints (100 req/min per IP default)
- [ ] Add CSRF protection to all form-based routes via `flask-wtf`
- [ ] Add `Content-Security-Policy` and other security headers via `flask-talisman`
- [ ] Sanitize all user input before storing (tags, collection names, notes)
- [ ] Add SQL injection audit (parameterized queries are used, but verify fully)

### 8.3 Database Migrations
**Why it matters:** Adding new columns currently requires manual SQLite surgery. There is no migration history.

- [ ] Add Alembic for schema migrations
- [ ] Write migration scripts for all schema changes going forward
- [ ] Add `--migrate` flag to startup to auto-apply pending migrations

### 8.4 Monitoring & Health
- [ ] Extend `/health` to return degraded status if embedding model failed to load or DB is unresponsive
- [ ] Add `/metrics` endpoint in Prometheus exposition format (paper counts, rating counts, task queue depth)
- [ ] Add Grafana dashboard JSON to `deploy/`
- [ ] Add container health check in `Dockerfile`

### 8.5 Horizontal Scaling
- [ ] Move preference model save/load to atomic file replace (prevent race conditions with multiple workers)
- [ ] Add `user_id` partitioning so model files don't contend
- [ ] Validate Gunicorn multi-worker correctness (SQLite `check_same_thread=False` is already set, but test under load)

---

## Phase 9 — Advanced AI Features

*The differentiating features that make AURA a research assistant, not just a filter.*

### 9.1 Deep Dive Summaries
**Why it matters:** Current summaries are 2-3 sentences from the abstract only. A real research assistant reads the methods and results.

- [ ] Add PDF download + text extraction (PyMuPDF or pdfminer)
- [ ] Generate structured summaries: Background / Methods / Results / Significance
- [ ] Cache full-paper summaries separately from abstract summaries
- [ ] Add "explain like I'm a grad student" vs "expert" summary modes

### 9.2 Research Q&A
- [ ] Add `/papers/{id}/ask` endpoint: "What dataset did they use?", "Did they compare to X?"
- [ ] Use LLM with the paper's full text as context (RAG over the stored paper text)
- [ ] Stream responses via Server-Sent Events

### 9.3 Trend Radar
**Why it matters:** The `trends.py` module generates monthly trend summaries but they're buried in the email. There's no visual trend view in the UI.

- [ ] Add `/trends` page showing topic heatmap (papers per week per topic)
- [ ] Plot publication velocity per topic as a sparkline
- [ ] Alert user when a tracked topic spikes significantly
- [ ] Compare trend velocity against a configurable baseline period

### 9.4 Citation Graph Integration
- [ ] Pull citation and reference data from Semantic Scholar for stored papers
- [ ] Store in a `citations` table (`citing_arxiv_id`, `cited_arxiv_id`)
- [ ] Add "papers that cite this" and "papers cited by this" to the detail page
- [ ] Use citation graph for recommendation boosting (a paper cited by many liked papers is likely good)

### 9.5 Research Brief Generation
- [ ] Weekly auto-generated brief: "Here's what happened in your fields this week"
- [ ] Structured: top papers, emerging topics, notable authors, methodology trends
- [ ] Delivered via email and viewable at `/briefs/{date}`

---

## Phase 10 — Distribution & Ecosystem

*Make AURA something others can build on.*

### 10.1 REST API Documentation
- [ ] Add `flask-restx` or generate OpenAPI 3.0 spec from existing routes
- [ ] Serve interactive docs at `/api/docs`
- [ ] Document all endpoints, request/response schemas, error codes

### 10.2 Plugin / Source SDK
- [ ] Define a formal `PaperSource` plugin interface (from Phase 4.1)
- [ ] Document how to write a custom source as a Python package
- [ ] Create a `PaperSource` registry: sources register via `entry_points` in `setup.cfg`

### 10.3 One-Click Deploy
- [ ] Add `docker-compose.yml` that bundles AURA + Redis + optional Qdrant
- [ ] Add a `setup.sh` that walks through config interactively
- [ ] Add a Coolify / Railway / Render deploy button to README
- [ ] Publish Docker image to Docker Hub in addition to GHCR

### 10.4 CLI Improvements
- [ ] Add `aura init` wizard that generates a valid `config.yaml` interactively
- [ ] Add `aura doctor` command to validate environment and config
- [ ] Add `aura import <bibtex_file>` to seed the database from an existing library
- [ ] Add `aura export <format>` for bulk export

---

## Priority Order (Suggested)

| Priority | Phase | Reason |
|----------|-------|--------|
| 1 | 2.1 Full-Text Search | Most common missing feature for any paper tool |
| 2 | 2.3 Tags & Collections | Second most impactful daily-use feature |
| 3 | 3.1 Cold Start Bootstrap | Required before sharing with anyone new |
| 4 | 3.2 Explainability | Builds trust in recommendations |
| 5 | 2.2 Paper Detail Page | Makes AURA a destination, not a redirect to arXiv |
| 6 | 5.1 Multi-User Auth | Required for lab/team use |
| 7 | 7.3 BibTeX Export | Closes the loop with existing research workflows |
| 8 | 4.1–4.2 Multi-Source | Expands addressable content meaningfully |
| 9 | 9.1–9.2 Deep Summaries / Q&A | The "wow" feature that no other tool does as well |

---

## Non-Goals (Explicitly Out of Scope)

- Full PDF viewer / annotation inside AURA (too complex; use Zotero for that)
- Social network / follower model (this is a research tool, not a social platform)
- Paper submission or authoring tools
- Replacing arXiv, Semantic Scholar, or any upstream source
