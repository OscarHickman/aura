# AURA Development Roadmap

**Current Production Release:** `v1.6.1` (October 2026)  
*All foundational architecture, audit remediations, mobile feature parity, resilient local-first AI, cosmology portfolio tailoring (P1–P15), and native Expo push notifications & deep linking have been implemented and deployed. Historical achievements and release logs are documented in [`ACHIEVEMENTS.md`](ACHIEVEMENTS.md).*

---

## Strategic Horizons & Future Work

### 1. Proactive Mobile Intelligence & Audio Briefings
- **Commute Audio Briefings ("Podcast Mode")**:
  - Spoken audio synthesis (3–5 minute MP3) synthesising the day's top cosmology recommendations and weekly research briefs using local TTS (Piper) or remote speech APIs.
  - Background audio playback controls integrated into the mobile companion app.

### 2. Advanced Ranking & Active Learning
- **Multi-Interest Prototype Embeddings**:
  - Cluster positively rated papers into $K$ distinct research centroids (e.g. *SBI / Field-Level*, *HOD & Assembly Bias*, *Modified Gravity / Lensing*) so candidate scoring and explanations reflect multiple distinct projects rather than a single collapsed centroid.
- **Active Learning / Uncertainty Triage Mode**:
  - Add an "Explore Boundary" triage mode in `TriageScreen` that queries papers with highest epistemic uncertainty (`model_uncertainty` from `PaperPreferenceNet`), allowing rapid calibration of preference boundaries with minimal user feedback.
- **Calibrated Negative Signal Weighting**:
  - Weight explicit skips (`rating = -1`) gently (e.g. weight `0.25`) relative to explicit downvotes (`rating = 0`, weight `1.0`) to avoid over-penalising an entire cosmological sub-field when skipping off-topic papers.

### 3. Reference Manager & Lab Sync
- **Two-Way Zotero Synchronization**:
  - Bidirectional integration via Zotero Web API: automatically push 5-star / reading list papers with AI summaries and research notes to a designated Zotero collection.
  - Ingest existing Zotero collections to bootstrap and refine user preference models.
- **Overleaf & Git Export Webhook**:
  - Automated one-click push of generated `.bib` files and LaTeX related-work skeletons (`aura/latex_export.py`) to linked Git repositories or Overleaf Git bridges.
- **Comparative Synthesis Matrix**:
  - Generate side-by-side comparison tables across 2–10 selected papers comparing probes, datasets (e.g. DESI DR1 vs SDSS), cosmological models, parameter constraints ($\sigma_8$, $S_8$, $H_0$), and code availability.

### 4. Cross-Platform & Tablet Layout
- **Tablet & Foldable Responsive Adaptation**:
  - Two-pane master-detail view for Feed and PaperDetail on wider displays.
- **iOS TestFlight Packaging**:
  - Configure automated iOS build runner in GitHub Actions for TestFlight distribution.

---

## Non-Goals (Explicitly Out of Scope)

- **In-App PDF Annotation Editor:** AURA is an intelligence and discovery engine, not a canvas PDF annotation tool. Annotations belong in Zotero or native tablet readers synced via API.
- **Public Social Network:** AURA is a private, focused personal and research group intelligence platform without public follower feeds or social networking bloat.
- **Manuscript Authoring Suite:** Manuscript drafts belong in Overleaf or LaTeX editors; AURA provides exportable BibTeX and literature synthesis skeletons.
- **Archival Mirroring:** AURA indexes and caches metadata and embeddings, but defers full archival storage to arXiv, NASA ADS, and Semantic Scholar.
