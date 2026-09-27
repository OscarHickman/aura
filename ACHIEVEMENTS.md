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
