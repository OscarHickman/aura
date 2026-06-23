# AURA Roadmap — From Research Tool to Full Product

**Current state:** Single-user local Flask app. Fetches arXiv papers, generates sentence-transformer embeddings, trains a small preference neural network from thumbs-up/down feedback, generates LLM summaries, and sends email digests. Solid core. Rough edges everywhere else.

**Goal:** A self-hostable, feature-rich research discovery platform that a lab or individual researcher would reach for every day.

---

## Phase 3 — ML & Recommendation Improvements

*Make the recommendations actually learn better and faster.*

### 3.3 Better Model Architecture
- [ ] Add A/B testing capability: shadow model trained on different hyperparameters

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

- [x] Add `/papers/{id}/export/bibtex` endpoint
- [x] Add `/papers/export/bibtex?collection={id}` for bulk export
- [x] Add `/papers/export/ris` for RIS format
- [x] Add Zotero Connector compatibility header so the browser extension works

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

### 8.4 Monitoring & Health
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

## Phase 11 — Astronomy Domain Intelligence

*Purpose-built for the workflows of astronomers and cosmologists.*

### 11.1 NASA ADS Integration
- [x] Implement `ADSSource` using the ADS API (`ui.adsabs.harvard.edu/api`)
- [x] Map ADS fields to the `Paper` schema: `bibcode`, `citation_count`, `read_count`, `refereed` flag
- [x] Add `refereed` boolean column to `papers` table
- [x] Daily background job to refresh ADS citation counts for stored papers
- [x] Surface citation count and refereed badge on paper cards
- [x] Use ADS `read_count` as an optional secondary ranking signal

### 11.2 Survey & Mission Paper Tracking
- [ ] Add `surveys` table: `id`, `name`, `keywords` (JSON list of trigger terms)
- [ ] Auto-tag papers that mention a tracked survey in title or abstract
- [ ] Default survey list: DESI, Euclid, Rubin LSST, SKA, Simons Observatory, CMB-S4, HSC, DES, Planck
- [ ] UI: filter papers view by survey/instrument tag
- [ ] Digest: include a "From the surveys" sub-section in the email

### 11.3 Cosmological Statistics & Method Extraction
- [ ] LLM-powered metadata extraction pass running after fetch (before embedding):
  - **Observable:** power spectrum, correlation function, bispectrum, void statistics, CMB temperature/polarization, weak lensing, shear
  - **Dataset:** BOSS, DESI, HSC, DES, Planck, SPT, ACT, IllustrisTNG, CAMELS, EAGLE
  - **Method:** MCMC, nested sampling, SBI, neural posterior estimation, emulator, N-body, semi-analytic model
- [ ] Store extracted tags in the `tags` table with `source='auto'`
- [ ] Use extracted method/dataset tags to boost recommendation precision
- [ ] Filter UI: show papers by observable or method type

### 11.4 Author & Research Group Tracking
- [ ] Add `tracked_authors` table: `id`, `name`, `orcid` (optional), `affiliation` (optional), `relationship` (`follow` | `collaborator`)
- [ ] At fetch time, flag papers where any tracked author appears in the author list
- [ ] UI: "From authors you follow" badge on paper cards
- [ ] `/settings/authors` page to add/remove tracked authors
- [ ] Digest: "From your network" section for papers by tracked authors
- [ ] Import collaborators in bulk from a BibTeX file's `author` fields

### 11.5 arXiv Category Expansion for Computational Cosmology
- [ ] Add `astro-ph.IM` to `config.example.yaml` defaults
- [ ] Document optional `cs.LG` and `stat.ML` categories in `config.example.yaml`
- [ ] Add cross-listing deduplication: a paper in both `astro-ph.CO` and `cs.LG` stores once with both category labels

---

## Phase 12 — Simulation-Based Inference & Computational Cosmology

### 12.1 Code & Data Release Detection
- [ ] Optionally fetch the linked GitHub repo metadata (stars, last commit, language)

### 12.2 SBI & Neural Inference Topic Seeds
- [x] Add to `DEFAULT_TOPICS`: `"neural posterior estimation"`, `"normalizing flows cosmology"`, `"field level inference"`, `"neural compression"`, `"likelihood free inference"`, `"implicit likelihood inference"`, `"amortized inference"`
- [x] Add to `DEFAULT_TOPICS`: `"two point statistics"`, `"galaxy power spectrum"`, `"higher order statistics cosmology"`, `"summary statistics inference"`
- [x] Group topics in `research_topics.json` by section (`sbi`, `galaxy_statistics`, `ml_methods`)

### 12.3 Simulation & Inference Code Awareness
- [ ] Add a `simulation_codes` list to `config.yaml`
- [ ] Auto-tag papers mentioning listed simulations/codes at fetch time
- [ ] Show simulation/code badges on paper cards
- [ ] Filter papers view by simulation or code name
- [ ] Default list: IllustrisTNG, CAMELS, EAGLE, Millennium, GADGET, RAMSES, GALFORM, CAMB, CLASS, Cobaya, emcee, MultiNest, PolyChord, JAX, sbi (Python library)

### 12.4 Dataset & Benchmark Velocity Alerts
- [ ] Track weekly paper count per auto-detected dataset/simulation tag
- [ ] Alert when a tracked keyword appears in >N papers within any rolling 7-day window
- [ ] Surface alerts as a "Spike Alert" banner in the `/trends` UI and in the email digest
- [ ] Store weekly velocity history in the database

---

## Phase 13 — Personal Research Context

### 13.1 "My Papers" — Citation Tracking
- [ ] Add `my_papers` table: user registers own arXiv IDs or DOIs
- [ ] UI: `/my-papers` page with an "Add paper" form
- [ ] When the ADS citation refresh job runs, check newly stored papers against `my_papers` citing lists
- [ ] Badge papers that cite the user's work: "Cites your work"
- [ ] Digest: "Papers citing your work this week" section

### 13.2 Collaborator Feed
- [ ] Reuse `tracked_authors.relationship = 'collaborator'` from Phase 11.4
- [ ] Collaborator papers receive a configurable score boost and a "From your group" badge
- [ ] Pin collaborator papers at the top of the recommend view
- [ ] Weekly digest section: "From your group this week"

### 13.3 Conference & Proposal Deadline Calendar
- [ ] Add `events` table: `id`, `name`, `date`, `type`
- [ ] `/settings/calendar` page to add/edit events
- [ ] Annotate the trend with the nearest upcoming or just-passed event
- [ ] Display upcoming events (next 30 days) in the dashboard sidebar
- [ ] Default seeds: major annual cosmology conferences + recurring ESO/HST/JWST proposal windows

### 13.4 Structured Study Notes & Thesis Export
- [ ] Extend paper detail page with a structured "Study Notes" template
- [ ] Auto-save notes as Markdown to the `annotations` table with `type='study_note'`
- [ ] Export all study notes for a collection to a single Markdown file
- [ ] When exporting, prepend the BibTeX citation for each paper
- [ ] `/notes` dashboard showing all papers with study notes

---

## Priority Order (Suggested)

| Priority | Phase | Reason |
|----------|-------|--------|
| 1 | 5.1 Multi-User Auth | Required for lab/team use |
| 2 | 12.2 SBI Topic Seeds | Improves recall for the user's primary research area |
| 3 | 11.1 NASA ADS Integration | Canonical citation data source for astronomy |
| 4 | 11.4 Author Tracking | Daily-use workflow for following collaborators and groups |
| 5 | 13.1 "My Papers" Citation Alerts | Automates a manual tracking task |
| 6 | 7.3 BibTeX Export | Closes the loop with existing research workflows |
| 7 | 11.3 Cosmological Statistics Extraction | Improves clustering and recommendation precision |
| 8 | 13.4 Study Notes & Thesis Export | High value for PhD students |
| 9 | 4.1–4.2 Multi-Source | Expands addressable content meaningfully |
| 10 | 9.1–9.2 Deep Summaries / Q&A | The "wow" feature that no other tool does as well |

---

## Non-Goals (Explicitly Out of Scope)

- Full PDF viewer / annotation inside AURA (too complex; use Zotero for that)
- Social network / follower model (this is a research tool, not a social platform)
- Paper submission or authoring tools
- Replacing arXiv, Semantic Scholar, or any upstream source
