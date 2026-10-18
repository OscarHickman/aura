# AURA Development Roadmap

**Current Production Release:** `v1.7.2` (October 2026)
*All foundational architecture, audit remediations, mobile companion parity, resilient local-first AI, cosmology portfolio tailoring (P1–P15), native Expo push notifications & deep linking, commute audio briefings, multi-interest prototype clustering, active learning boundary exploration, two-way Zotero sync, Git/Overleaf sync, comparative synthesis matrices, and responsive tablet layouts have been implemented, tested, and released. Historical achievements and release logs are documented in [`ACHIEVEMENTS.md`](ACHIEVEMENTS.md).*

---

## Strategic Horizons & Future Work

### 1. On-Device Edge Inference & Multimodal Extraction
- **On-Device Embedding Inference**:
  - Run lightweight ONNX sentence-transformer models directly on mobile via React Native ONNX Runtime for instant client-side similarity scoring without network round-trips.
- **Multimodal Figure & Equation Extraction**:
  - Extract cosmological constraint contour figures and LaTeX parameter equation blocks from arXiv source tarballs or PDFs for inline comparison against Planck/DESI contours.

### 2. Multi-Author Lab & Group Collaboration
- **Lab Group Shared Consensus Feed**:
  - Compute group-level affinity rankings combining feedback from multiple research group members (e.g. Durham cosmology group) with differential weightings for supervisors and collaborators.
- **Automated Journal Club Pack Generator**:
  - Export weekly PDF/Markdown briefing slide decks synthesising selected papers for departmental journal clubs.

### 3. Native iOS Distribution
- **iOS TestFlight Packaging**:
  - Configure automated iOS build runner in GitHub Actions for TestFlight distribution once Apple Developer certificates are configured.

---

## Non-Goals (Explicitly Out of Scope)

- **In-App PDF Annotation Editor:** AURA is an intelligence and discovery engine, not a canvas PDF annotation tool. Annotations belong in Zotero or native tablet readers synced via API.
- **Public Social Network:** AURA is a private, focused personal and research group intelligence platform without public follower feeds or social networking bloat.
- **Manuscript Authoring Suite:** Manuscript drafts belong in Overleaf or LaTeX editors; AURA provides exportable BibTeX and literature synthesis skeletons.
- **Archival Mirroring:** AURA indexes and caches metadata and embeddings, but defers full archival storage to arXiv, NASA ADS, and Semantic Scholar.
