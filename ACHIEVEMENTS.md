# AURA — Project Achievements & Milestones

This document records the major architectural, algorithmic, infrastructure, and product achievements accomplished across the AURA platform.

---

## 1. Production Deployment & Cloud Infrastructure

* **Automated Home Server Continuous Deployment**:
  * Configured GitHub Actions CD pipeline ([.github/workflows/deploy.yml](.github/workflows/deploy.yml)) deploying automatically on semantic git tags (`v*`).
  * Deploys directly to the home server via an isolated, secure **Tailscale** tunnel with zero exposure of SSH ports to the public internet.
  * Containerised multi-service orchestration with Docker Compose: Flask web application, Gunicorn WSGI, Redis task broker, Qdrant vector database, and Caddy reverse proxy.
* **Production Account & Role Verification**:
  * Live production admin account provisioned and verified on the home server.
  * Multi-user role-based access control (RBAC), account suspension, session management, and admin dashboard verified with live MCP testing.

---

## 2. Mobile Ecosystem & Google Play Publishing

* **Modern Android Companion App (`mobile/`)**:
  * Built using **React Native**, **Expo (SDK 52)**, and **TypeScript** with strict type checking.
  * **Triage Deck**: Fluid card-swipe interface designed for rapid one-handed paper triaging (thumbs up, skip/thumbs down, bookmark to reading list, match score badges).
  * **Ranked Feed**: Infinite-scroll paper feed with instant search across titles, authors, and arXiv categories.
  * **Paper Reader & Interactive Q&A**: Mobile reader with AI summaries, arXiv and direct PDF links, and a conversational LLM Q&A assistant ("Ask Paper").
  * **Reading List**: Queue and finished paper tracking with offline support.
  * **Server Connection Manager**: Configurable server endpoint pre-configured with the home server Tailscale address, real-time ping diagnostic tool, and Bearer token auth.
* **Continuous Google Play CI/CD**:
  * Automated Android App Bundle (`.aab`) and release `.apk` compilation with Gradle in GitHub Actions.
  * App version and `versionCode` derived from the git tag (`vX.Y.Z` → `X*10000 + Y*100 + Z`), so codes always increase.
  * Release signing with the upload keystore through Gradle's injected signing properties, and Google Play publishing via `r0adkll/upload-google-play` when the signing and Play secrets are present.
* **Mobile REST API**:
  * JSON API endpoints (`/api/auth/login`, `/api/auth/logout`, `/api/auth/me`, `/api/papers`, `/api/reading-list`) returning JSON 401s instead of login redirects.
  * CSRF is skipped only for requests with a valid Bearer token; login is rate limited (5/min); CORS is limited to an opt-in `AURA_CORS_ORIGINS` allow-list.

---

## 3. Recommendation & Machine Learning Engine

* **Online Incremental Learning**:
  * Small, fast PyTorch feedforward preference network (`PaperPreferenceNet`) trained in real-time from user feedback.
  * Supports 1–5 star ratings, binary thumbs-up/down, and skips.
  * Replay buffer with historical loss tracking and full retraining capability.
* **Vector Similarity & Embeddings**:
  * Sentence-transformers (`all-MiniLM-L6-v2` / `all-mpnet-base-v2`) abstract vectorisation.
  * Dual vector database backends: SQLite BLOB vector fallback and scalable **Qdrant** vector database integration.
  * Multi-factor scoring combining neural preference prediction, publication freshness decay, and AI summary availability bonuses.
* **Unsupervised Topic Discovery**:
  * K-Means clustering over paper embedding spaces discovering emerging research topics and clusters without manual labelling.

---

## 4. Advanced AI & Research Intelligence

* **Multi-LLM Provider Abstraction**:
  * Unified adapter supporting **Groq** (Llama 3.1 8B/70B), **Google Gemini**, **OpenAI**, and **Anthropic**.
* **Deep Dive Paper Summaries**:
  * Automatic PDF download and PyMuPDF full-text extraction.
  * Generates structured summaries across *Background*, *Methods*, *Results*, and *Significance*.
  * Dual summary personas: "Expert" vs. "Graduate Student".
* **Interactive Paper Q&A (RAG)**:
  * In-memory full-text retrieval allowing users to ask precise methodology and dataset questions about any ingested paper.
* **Weekly Research Briefs**:
  * Automated weekly brief synthesis delivering structured field overviews (top discoveries, emerging topics, methodology trends) via email and `/briefs`.
* **Trend Radar**:
  * Topic publication velocity tracking with sparklines, heatmap visualisation, and automated topic spike detection.

---

## 5. Astronomy Domain Specialisation

* **NASA ADS Integration**:
  * Native connector to the NASA Astrophysics Data System API.
  * Citation count tracking, read metrics, and peer-reviewed (`refereed`) status tagging.
* **Survey & Instrument Tracking**:
  * Automatic survey and telescope mission identification (DESI, Euclid, Rubin LSST, SKA, Simons Observatory, CMB-S4, HSC, Planck).
* **Network & Author Tracking**:
  * Tracked collaborators and followed authors with visual badges and digest prioritisation.
* **Cosmological Method & Observable Extraction**:
  * Automatic extraction of cosmological observables (power spectrum, weak lensing, bispectrum) and inference methods (SBI, neural posterior estimation, MCMC, emulators).

---

## 6. Security, Scale & Reliability

* **Rate Limiting & Protection**: `flask-limiter` on all API endpoints; `flask-talisman` security headers; Content Security Policy (CSP).
* **Multi-User Partitioning**: Independent model weights, user collections, tags, reading lists, and notes partitioned by user ID.
* **Zero-Downtime Atomic Model Swapping**: Atomic file operations preventing race conditions under multi-worker Gunicorn deployments.
* **Comprehensive Test Suite**:
  * 196 passing automated unit and integration tests across core engine, database, web UI, mobile API, and tasks.
  * Strict linting and formatting enforced with `ruff`.
  * TypeScript compilation verified on the mobile application with zero type errors.


## Mobile reliability and verification — 2026-10-14

- Fixed real feed pagination and stale-response handling. The API reports stable totals/`has_more` within its 200-paper result window and includes high-star papers in the liked filter.
- Preserved authentication through network outages; HTTP 401 invalidates the visible session. Server changes clear active credentials, and device token names are installation-specific.
- Scoped offline caches/queues to server and user. Concurrent writes and replay preserve pending work; raw replay requests cannot silently requeue and discard actions. Reading lists, details and notes work from cached content, and mark-read can be queued.
- Added note mutation IDs with a database uniqueness constraint and additive migration. Retrying after a lost response returns the existing note. Reading-list removal is also safe to replay.
- Added error recovery screens, a render error boundary, screen interaction tests, coverage gates, and a real mobile-to-Flask/SQLite contract test in CI.
- Verified Android JavaScript export and native prebuild. The release manifest explicitly supports HTTP home servers and disables app backup.
- Documented key custody, release steps, data behavior, and remaining device/store verification in [mobile/RELEASE.md](mobile/RELEASE.md). No signed artifact or store release is claimed by these checks.

---

## Release v1.6.0 — Cosmology SBI Research Portfolio Tailoring & Platform Hardening (2026-10-18)

- **Cosmology SBI Portfolio Tailoring (P1–P15)**:
  - Deep architectural alignment with Oscar Hickman's PhD research portfolio across Simulation-Based Inference (SBI), galaxy clustering, and semi-analytic galaxy formation.
  - Overhauled Research Topic Radar across 6 core pillars: SBI & Field-Level Inference, Galaxy Clustering & HOD, Semi-Analytic Models (GALFORM), Hydro & Modified Gravity, Cosmological Parameters & $\sigma_8$ Tensions, High-$z$ JWST & Strong Lensing.
  - Aligned publication velocity alerts with active cosmological simulation codes and surveys (`GALFORM`, `SaUCE`, `CAMELS`, `FLAMINGO`, `COLIBRE`, `FORGE`, `BRIDGE`, `DESI`, `sbi`, `HOD`, `assembly bias`, `dynamical friction`).
- **Research Group & Collaborator Network Tracking**:
  - Direct tracking of Durham University supervisors, co-authors, and group collaborators with automatic `+0.20` network bonus and badge annotations in web and mobile feeds.
- **Resilient AI Summaries & Zero-Fail Extractive NLP**:
  - High-availability multi-provider AI pipeline with automatic local Ollama model fallback, multi-candidate retry, and deterministic extractive failsafe. Completely cured database summary failures.
- **Verification & Rigour**:
  - 250 unit and integration tests passing at 100% with >66% coverage.
  - Full mobile test suite (65 tests), contract bridge tests, Expo Android bundle export, strict ruff linting, and 66 mypy source files passing.

---

## 7. Native Push Notifications & Deep Linking Infrastructure (2026-10-18)

- **Device Registry & Lifecycle (`device_push_tokens`)**:
  - Provisioned SQLite `device_push_tokens` schema with user partitioning, platform tags, device names, and `last_used_at` timestamps.
  - Added REST API endpoints (`GET /api/devices`, `POST /api/devices`, `DELETE /api/devices`, `DELETE /api/devices/<token>`, `POST /api/devices/test`).
- **Expo Push Service Integration & Stale Token Pruning**:
  - Multi-batch Expo push notification service client (`https://exp.host/--/api/v2/push/send`).
  - Automatic detection and pruning of invalid or uninstalled devices via `DeviceNotRegistered` ticket introspection.
- **Contextual Notification Triggers**:
  - **Daily Digest Readiness**: Dispatches push notifications when top recommendations are calculated.
  - **High-Scoring Papers**: Real-time push alerts when incoming papers exceed user preference score thresholds.
  - **Publication Velocity Spikes**: Immediate broadcasts when monitored simulation codes experience publication surges.
  - **Citation Alerts**: Notifies authors when new publications cite their tracked works.
- **Deep Linking Protocol (`aura://`)**:
  - Deep-link routing configured in React Navigation (`aura://papers/:arxivId`, `aura://my-papers`, `aura://intel`, `aura://feed`).
  - Notification response listeners seamlessly routing taps to relevant screens.
  - Settings UI card with device registration status and one-tap test alert verification.

---

## 8. Release v1.7.0 — Active Learning, Spoken Audio Briefings, Lab Reference Sync & Tablet Layout (2026-10-18)

- **Commute Audio Briefings ("Podcast Mode")**:
  - Conversational spoken research briefing synthesis using British neural voices (`en-GB-SoniaNeural`) via `edge-tts`.
  - Background audio playback controls in the mobile companion app using `expo-av` with playback rate controls (1x, 1.25x, 1.5x, 2x), ±15s seeking, and docked player card.
  - Streaming audio endpoint (`GET /api/audio/stream/<filename>`) and daily briefing generation endpoint (`GET /api/audio/daily`, `POST /api/audio/generate`).
- **Multi-Interest Prototype Embeddings & Active Learning**:
  - K-Means prototype clustering discovering distinct research centroids with cosmology keyword extraction (`GET /api/user/clusters`).
  - Active learning "Explore Boundary" triage mode prioritising papers near preference decision boundaries with high epistemic uncertainty (`GET /api/papers?filter=explore`).
  - Calibrated negative signal weighting: skips (`rating = -1`) weighted at `0.25` vs explicit downvotes at `1.0` to prevent over-penalising broader sub-disciplines.
- **Reference Manager & Lab Synchronisation**:
  - Two-way Zotero sync (`aura/zotero.py`): export reading list papers with AI summaries and user notes; import existing library to bootstrap preferences (`GET /api/zotero/status`, `POST /api/zotero/sync`, `POST /api/zotero/import`).
  - Overleaf / Git export (`aura/git_sync.py`): automated export of `.bib` bibliographies and LaTeX literature review matrices to remote repositories (`POST /api/export/git-sync`).
  - Multi-paper comparative synthesis (`aura/synthesis.py`): side-by-side matrix comparing probes, tracers, datasets, methodologies, cosmological parameter bounds ($\sigma_8, S_8, H_0$), and code links (`POST /api/papers/compare`).
- **Responsive Tablet & Foldable Split Layout**:
  - Responsive master-detail split layout for tablets and foldables (`width >= 768`) across Feed and Paper Detail screens.

