# AURA Roadmap — From Research Tool to Full Product

**Current state:** Production-grade research discovery and intelligence platform auto-deployed to home server via Tailscale. Features multi-source discovery (arXiv, NASA ADS, Semantic Scholar), PyTorch online preference neural network, Qdrant/ChromaDB vector backends, full-text PDF deep summaries, interactive LLM Q&A, astronomy domain tracking, and a companion Android mobile app. The Google Play pipeline is written but has not yet completed a real release (Phase 14).

**Goal:** A self-hostable, feature-rich research discovery platform that a lab or individual researcher would reach for every day.

---

## Phase 8 — Scale & Production Hardening

*Make it reliable enough to run on a server.*

### 8.1 Vector Database Migration (Optional)
**Why it matters:** SQLite BLOB storage for embeddings works up to ~50k papers but becomes slow for similarity queries at scale.

- [x] Add optional ChromaDB or Qdrant backend (feature-flagged)
- [x] Migrate existing embeddings on startup if vector DB is configured
- [x] Fall back to numpy cosine similarity if no vector DB is configured

### 8.2 Rate Limiting & Security
- [x] Add `flask-limiter` to all API endpoints (100 req/min per IP default)
- [x] Add CSRF protection to all form-based routes via `flask-wtf`
- [x] Add `Content-Security-Policy` and other security headers via `flask-talisman`
- [x] Sanitize all user input before storing (tags, collection names, notes)
- [x] Add SQL injection audit (parameterized queries are used, but verify fully)

### 8.4 Monitoring & Health
- [x] Add Grafana dashboard JSON to `deploy/`
- [x] Add container health check in `Dockerfile`

### 8.5 Horizontal Scaling
- [x] Move preference model save/load to atomic file replace (prevent race conditions with multiple workers)
- [x] Add `user_id` partitioning so model files don't contend
- [x] Validate Gunicorn multi-worker correctness (SQLite `check_same_thread=False` is already set, but test under load)

---

## Phase 9 — Advanced AI Features

*The differentiating features that make AURA a research assistant, not just a filter.*

### 9.1 Deep Dive Summaries
**Why it matters:** Current summaries are 2-3 sentences from the abstract only. A real research assistant reads the methods and results.

- [x] Add PDF download + text extraction (PyMuPDF or pdfminer)
- [x] Generate structured summaries: Background / Methods / Results / Significance
- [x] Cache full-paper summaries separately from abstract summaries
- [x] Add "explain like I'm a grad student" vs "expert" summary modes

### 9.2 Research Q&A
- [x] Add `/papers/{id}/ask` endpoint: "What dataset did they use?", "Did they compare to X?"
- [x] Use LLM with the paper's full text as context (RAG over the stored paper text)
- [x] Stream responses via Server-Sent Events

### 9.3 Trend Radar
**Why it matters:** The `trends.py` module generates monthly trend summaries but they're buried in the email. There's no visual trend view in the UI.

- [x] Add `/trends` page showing topic heatmap (papers per week per topic)
- [x] Plot publication velocity per topic as a sparkline
- [x] Alert user when a tracked topic spikes significantly
- [x] Compare trend velocity against a configurable baseline period

### 9.4 Citation Graph Integration
- [x] Pull citation and reference data from Semantic Scholar for stored papers
- [x] Store in a `citations` table (`citing_arxiv_id`, `cited_arxiv_id`)
- [x] Add "papers that cite this" and "papers cited by this" to the detail page
- [x] Use citation graph for recommendation boosting (a paper cited by many liked papers is likely good)

### 9.5 Research Brief Generation
- [x] Weekly auto-generated brief: "Here's what happened in your fields this week"
- [x] Structured: top papers, emerging topics, notable authors, methodology trends
- [x] Delivered via email and viewable at `/briefs/{date}`

---

## Phase 10 — Distribution & Ecosystem

*Make AURA something others can build on.*

### 10.1 REST API Documentation
- [x] Add `flask-restx` or generate OpenAPI 3.0 spec from existing routes
- [x] Serve interactive docs at `/api/docs`
- [x] Document all endpoints, request/response schemas, error codes

### 10.2 Plugin / Source SDK
- [x] Define a formal `PaperSource` plugin interface (from Phase 4.1)
- [x] Document how to write a custom source as a Python package
- [x] Create a `PaperSource` registry: sources register via `entry_points` in `setup.cfg`

### 10.3 One-Click Deploy
- [x] Add `docker-compose.yml` that bundles AURA + Redis + optional Qdrant
- [x] Add a `setup.sh` that walks through config interactively
- [x] Add a Coolify / Railway / Render deploy button to README
- [x] Publish Docker image to Docker Hub in addition to GHCR

### 10.4 CLI Improvements
- [x] Add `aura init` wizard that generates a valid `config.yaml` interactively
- [x] Add `aura doctor` command to validate environment and config
- [x] Add `aura import <bibtex_file>` to seed the database from an existing library
- [x] Add `aura export <format>` for bulk export

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
- [x] Add `surveys` table: `id`, `name`, `keywords` (JSON list of trigger terms)
- [x] Auto-tag papers that mention a tracked survey in title or abstract
- [x] Default survey list: DESI, Euclid, Rubin LSST, SKA, Simons Observatory, CMB-S4, HSC, DES, Planck
- [x] UI: filter papers view by survey/instrument tag
- [x] Digest: include a "From the surveys" sub-section in the email

### 11.3 Cosmological Statistics & Method Extraction
- [x] LLM-powered metadata extraction pass running after fetch (before embedding):
  - **Observable:** power spectrum, correlation function, bispectrum, void statistics, CMB temperature/polarization, weak lensing, shear
  - **Dataset:** BOSS, DESI, HSC, DES, Planck, SPT, ACT, IllustrisTNG, CAMELS, EAGLE
  - **Method:** MCMC, nested sampling, SBI, neural posterior estimation, emulator, N-body, semi-analytic model
- [x] Store extracted tags in the `tags` table with `source='auto'`
- [x] Use extracted method/dataset tags to boost recommendation precision
- [x] Filter UI: show papers by observable or method type

### 11.4 Author & Research Group Tracking
- [x] Add `tracked_authors` table: `id`, `name`, `orcid` (optional), `affiliation` (optional), `relationship` (`follow` | `collaborator`)
- [x] At fetch time, flag papers where any tracked author appears in the author list
- [x] UI: "From authors you follow" badge on paper cards
- [x] `/settings/authors` page to add/remove tracked authors
- [x] Digest: "From your network" section for papers by tracked authors
- [x] Import collaborators in bulk from a BibTeX file's `author` fields

### 11.5 arXiv Category Expansion for Computational Cosmology
- [x] Add `astro-ph.IM` to `config.example.yaml` defaults
- [x] Document optional `cs.LG` and `stat.ML` categories in `config.example.yaml`
- [x] Add cross-listing deduplication: a paper in both `astro-ph.CO` and `cs.LG` stores once with both category labels

---

## Phase 12 — Simulation-Based Inference & Computational Cosmology

### 12.1 Code & Data Release Detection
- [x] Optionally fetch the linked GitHub repo metadata (stars, last commit, language)

### 12.2 SBI & Neural Inference Topic Seeds
- [x] Add to `DEFAULT_TOPICS`: `"neural posterior estimation"`, `"normalizing flows cosmology"`, `"field level inference"`, `"neural compression"`, `"likelihood free inference"`, `"implicit likelihood inference"`, `"amortized inference"`
- [x] Add to `DEFAULT_TOPICS`: `"two point statistics"`, `"galaxy power spectrum"`, `"higher order statistics cosmology"`, `"summary statistics inference"`
- [x] Group topics in `research_topics.json` by section (`sbi`, `galaxy_statistics`, `ml_methods`)

---

## Phase 13 — Mobile Platform & App Store Publishing

*Native mobile workflow for on-the-go research triaging and discovery.*

### 13.1 Android Companion App (`mobile/`)
- [x] Modern TypeScript application built with React Native and Expo (SDK 52)
- [x] Card swipe triage deck for rapid, one-handed paper rating and skipping
- [x] Infinite-scroll recommendation feed with pull-to-refresh and search
- [x] Full mobile paper reader with structured AI summaries and arXiv/PDF links
- [x] Interactive mobile Q&A assistant ("Ask Paper") querying backend LLM
- [x] Reading list management (Unread / Read History) with offline caching
- [x] Home server connection manager with live ping diagnostics and Bearer token auth

### 13.2 Backend Mobile API
- [x] Token authentication exchange (`POST /api/auth/login`) returning persistent Bearer tokens
- [x] Session verification endpoint (`GET /api/auth/me`)
- [x] Dedicated mobile feed endpoint (`GET /api/papers`) with pagination and rankings
- [x] Reading list API (`GET /api/reading-list`)
- [x] Universal CORS support and CSRF exemptions for all `/api/*` endpoints

### 13.3 Automated Google Play Pipeline
- [x] Automated Android App Bundle (`.aab`) and release `.apk` compilation via Gradle in GitHub Actions
- [x] Dynamic semantic versioning and build code incrementing (`github.run_number`)
- [x] Cryptographic release keystore signing via `r0adkll/sign-android-release`
- [x] Automated Google Play Console publishing via `r0adkll/upload-google-play`
- [x] Simultaneous home server deployment and release asset attachment on git tags

---

## Phase 14 — Ship the Mobile Release

*Take the Phase 13 work from "written" to "installed on a phone from the Play Store".*

### 14.1 Land the Uncommitted Work
- [x] Review and commit the mobile app, mobile API, CI and deploy changes as focused conventional commits
- [x] Scrub `ACHIEVEMENTS.md` of absolute `file:///home/...` links (use repo-relative links)
- [x] Decide whether `SERVER.md` and the Tailscale IP belong in the repo; if not, move to `.gitignore`d local notes
- [ ] Run `/code-review` + security review on the `aura/web/app.py` mobile API diff before merge

### 14.2 Release Secrets & One-Time Setup
- [ ] Generate the upload keystore; store `ANDROID_KEYSTORE_BASE`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_PASSWORD` as repo secrets
- [ ] Create a Play Console service account; store `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`
- [x] Add `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` (or make the Docker Hub push step skip cleanly when absent)
- [ ] Perform the first manual `.aab` upload in Play Console (required before API uploads work)
- [ ] Document the keystore backup and recovery procedure (losing it locks the app listing)

### 14.3 Pipeline Dry Runs
- [ ] Add a `workflow_dispatch` trigger that builds and signs without publishing, to test the pipeline without cutting a tag
- [ ] Verify `expo prebuild` + `./gradlew bundleRelease assembleRelease` locally at least once
- [ ] Publish to the Play **internal testing** track first; promote to production manually
- [x] Make `versionCode` monotonic across workflow re-runs (e.g. derive from tag, not only `run_number`)
- [ ] Cut `v1.0.0` and confirm: server redeploys, GitHub release has `.apk` + `.aab`, Play internal track shows the build

### 14.4 Store Listing
- [ ] App icon, feature graphic, and phone screenshots of Triage / Feed / Reader / Reading List
- [ ] Privacy policy page (served by the Flask app, e.g. `/privacy`) — required by Play
- [ ] Data safety form: document that the app talks only to the user's own server

---

## Phase 15 — Mobile API Hardening

*The mobile API was built for one trusted user; make it safe to expose to a lab.*

### 15.1 Token Lifecycle
- [ ] Add `expires_at` to `api_tokens`; enforce expiry in Bearer auth
- [ ] Reuse or rotate the token per device instead of minting a new one on every `POST /api/auth/login`
- [x] Add `POST /api/auth/logout` that revokes the calling token
- [ ] Show mobile device tokens (name, last used) on the tokens settings page with a revoke button

### 15.2 Abuse Protection
- [x] Strict per-IP rate limit on `POST /api/auth/login` (5/min), separate from the global 100/min default
- [ ] Add a per-email login limit / lockout (per-IP alone lets a distributed attacker keep guessing)
- [x] Replace `Access-Control-Allow-Origin: *` with a configurable allow-list (native apps don't need CORS; only browser clients do)
- [x] Audit every CSRF-exempt `/api/*` route to confirm it requires a Bearer token or session auth

### 15.3 API Contract
- [ ] Add the mobile endpoints to the OpenAPI spec served at `/api/docs`
- [ ] Version the mobile API (`/api/v1/...` or an `X-API-Version` header) so older app builds keep working after server upgrades
- [ ] Return a minimum-supported-app-version from `/api/auth/me` so the app can prompt for updates

---

## Phase 16 — Mobile Quality & Testing

*CI only type-checks the app today. Add real tests before adding features.*

### 16.1 Unit & Component Tests
- [ ] Add Jest (`jest-expo` preset) + React Native Testing Library and a `test` script in `mobile/package.json`
- [ ] Unit test `src/api/client.ts`: auth header injection, error mapping, timeout, 401 → logout
- [ ] Unit test `AuthContext`: token persistence in AsyncStorage, restore on launch, sign-out
- [ ] Component tests for Triage (swipe → rate call), Feed (pagination, search), Reading List (filter toggle, mark read)
- [ ] Coverage target: 80% for `src/api` and `src/context`

### 16.2 CI
- [ ] Run `pnpm test` and ESLint alongside `tsc --noEmit` in the `mobile-check` job
- [ ] Contract test: run the mobile client against the Flask test app in CI to catch API drift

### 16.3 Resilience
- [ ] Queue ratings/reading-list changes made offline and replay on reconnect
- [ ] Error boundary + friendly "server unreachable" screen (Tailscale down is the common failure)
- [ ] Optional crash reporting (Sentry, opt-in, self-hosted DSN configurable)

---

## Phase 17 — Mobile Feature Parity

*Bring the web features people actually use daily onto the phone.*

### 17.1 Notes & My Papers on Mobile
- [ ] Notes: view / add / edit notes on the paper reader (backend `/api/papers/<id>/notes` already exists)
- [ ] My Papers: list registered papers and their citation counts (needs a JSON `/api/my-papers` endpoint)
- [ ] Collections: browse collections and add papers to one from the reader

### 17.2 Push Notifications
- [ ] Integrate `expo-notifications`; register Expo push tokens via a new `POST /api/devices` endpoint
- [ ] Store device push tokens per user; remove on logout / token revoke
- [ ] Push the daily digest ("5 new papers for you") after the scheduled fetch
- [ ] Push high-score paper alerts, reusing the thresholds in `notifications.notify_high_scoring_papers`
- [ ] Per-user notification preferences (digest / high-score / citation alerts / quiet hours)

### 17.3 iOS Build
- [ ] Verify the app on the iOS simulator; fix platform-specific layout issues
- [ ] Add EAS Build (or `expo prebuild` + Xcode on a macOS runner) for iOS
- [ ] TestFlight distribution via `workflow_dispatch`

---

## Phase 18 — Research Workflow Depth

*Build on existing My Papers and Notes features so AURA covers more of the research workflow.*

### 18.1 "My Papers" Citation Alerts
My Papers and a daily ADS citation refresh (`refresh_my_papers_citations`) already exist, but nothing tells the user when something changes.
- [ ] Diff citations before/after each refresh and record new citing papers in a `citation_events` table
- [ ] "New citations of your work" section in the email digest and weekly brief
- [ ] Deliver alerts via Slack/Discord webhooks and mobile push (17.2)
- [ ] Show a citation-count-over-time sparkline per paper on `/my-papers`
- [ ] Auto-add new citing papers to the database so they get embedded and ranked

### 18.2 Notes → Thesis Export
Notes exist per paper and export per collection as Markdown with BibTeX.
- [ ] Export a collection's notes as a LaTeX chapter skeleton with a matching `.bib` file
- [ ] Stable citation keys (`AuthorYear` style) that stay the same across exports
- [ ] Export notes across all collections filtered by tag (e.g. every note tagged `chapter-2`)
- [ ] Optional LLM-assisted "related work" draft from a collection's notes, clearly marked as a draft

---

## Priority Order (Suggested)

| Priority | Item | Reason |
|----------|------|--------|
| 1 | 14.1 Land the uncommitted work | Large uncommitted diff is a risk; blocks everything else |
| 2 | 15.1–15.2 Token lifecycle & login rate limit | Non-expiring tokens and an unthrottled login endpoint are the main security gaps in the new API |
| 3 | 14.2–14.3 Release secrets & dry runs | Pipeline has never run end to end |
| 4 | 16.1–16.2 Mobile tests in CI | Needed before the app grows further |
| 5 | 14.4 Store listing & privacy policy | Required before a public Play release |
| 6 | 18.1 My Papers citation alerts | High value, mostly backend, reuses the existing ADS refresh |
| 7 | 17.2 Push notifications | Turns the app from "open it to check" into a daily-use tool |
| 8 | 17.1 Notes & My Papers on mobile | Backend mostly exists; mostly UI work |
| 9 | 18.2 Thesis export | High value for PhD students; builds on existing notes export |
| 10 | 15.3 API versioning & docs | Matters once more than one app version is in the wild |
| 11 | 16.3 Offline queue & resilience | Polish |
| 12 | 17.3 iOS build | Only if there's demand; needs macOS runner / Apple account |

---

## Non-Goals (Explicitly Out of Scope)

- Full PDF viewer / annotation inside AURA (too complex; use Zotero for that)
- Social network / follower model (this is a research tool, not a social platform)
- Paper submission or authoring tools
- Replacing arXiv, Semantic Scholar, or any upstream source
