# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AURA (Automated Understanding of Research Articles)** — A local tool that fetches papers from arXiv, ranks them based on user preferences, and sends daily email digests with AI-generated summaries.


**Stack:** Python 3.10+, Flask, PyTorch, sentence-transformers

## Quick Commands

### Setup
```bash
pip install -r requirements.txt
python run.py fetch          # Initial fetch
python run.py serve          # Start web UI at http://127.0.0.1:5000
```

### Development & Testing
```bash
python -m unittest discover -s tests -v                                        # Run all tests
python -m unittest tests.test_model -v                                        # Run single test file
python -m unittest tests.test_model.TestPreferenceModel.test_train_predict -v # Run single test case
ruff check .                                                                   # Lint with ruff
```

### Main CLI Commands
```bash
python run.py serve                        # Start Flask web UI
python run.py fetch                        # Fetch new papers from arXiv
python run.py fetch --with-summaries       # Fetch papers and generate summaries
python run.py recommend --limit 10         # Print top recommendations to terminal
python run.py summarize --limit 20         # Generate LLM summaries for papers
python run.py summarize --limit 20 --only-missing  # Skip papers marked as failed
python run.py email-digest --top-n 3       # Send email with top papers
python run.py retrain --epochs 20          # Retrain preference model from feedback
python run.py stats                        # Show database and model statistics

# Optional: Start web UI with automatic daily fetch
python run.py serve --scheduler
```

## Architecture

### Core Modules (`aura/`)

- **`recommender.py`** — Main `RecommendationEngine` orchestrating the entire pipeline. Coordinates fetching, embedding, preference prediction, and summary generation.

- **`fetcher.py`** — Fetches papers from arXiv API based on configured categories and time range. Returns raw paper metadata (title, abstract, authors, etc.).

- **`embedder.py`** — Converts paper abstracts to embedding vectors using sentence-transformers (default: `all-MiniLM-L6-v2` for speed, or `all-mpnet-base-v2` for quality).

- **`model.py`** — `PaperPreferenceNet`: a small PyTorch feedforward network (embedding_dim → 128 → 64 → 32 → 1 with sigmoid). Trained incrementally from user thumbs-up/thumbs-down feedback. Model weights file (`*.pt`) is the user's preference config.

- **`database.py`** — SQLite database storing papers, embeddings, ratings, summaries, and feedback. Handles paper deduplication and feedback persistence.

- **`llm.py`** — LLM provider abstraction supporting Groq, OpenAI, and Anthropic. Generates summaries for papers. Configured via `LLM_PROVIDER` and `LLM_API_KEY` environment variables.

- **`email_digest.py`** — Sends email digests with top-ranked papers and summaries. Reads SMTP config from `user_credentials/email_config.json`.

### Web UI (`aura/web/app.py`)
Flask REST API with routes for:
- `GET /papers` — List papers with filters and pagination
- `POST /papers/{id}/rate` — Save user feedback (thumbs up/down)
- `GET /recommend` — Get ranked recommendations
- `GET /stats` — Database and model statistics

## Configuration & CLI Flags

**CLI Flags** — Commands accept override flags:
- `python run.py fetch --max-results 100 --days-back 7` — Override fetch limits
- `python run.py recommend --limit 5` — Show only 5 papers
- `python run.py summarize --limit 10 --only-missing` — Skip papers marked as failed
- `python run.py retrain --epochs 30` — Train for 30 epochs (default 20)
- `python run.py --config custom.yaml serve` — Use alternate config file
- `python run.py -v serve` — Enable verbose logging

**`config.yaml`** — Main configuration file controlling:
- `categories` — List of arXiv categories to monitor (e.g., `astro-ph.CO`, `astro-ph.GA`)
- `embedding_model` — Sentence-transformer model ID
- `fetch.max_results` — Papers per fetch (default 200)
- `fetch.days_back` — Look back period (default 2 days)
- `summaries.generate_on_fetch` — Whether to generate summaries during fetch
- `host`, `port` — Flask server settings

**Environment Variables:**
```bash
LLM_PROVIDER=groq              # LLM provider: groq, openai, anthropic
GROQ_API_KEY=...              # Groq API key (free tier available)
# OPENAI_API_KEY=...          # Optional
# ANTHROPIC_API_KEY=...       # Optional
```

**Email Setup** — Create `user_credentials/email_config.json`:
```json
{
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_username": "your_gmail@gmail.com",
  "smtp_password": "your_16_char_app_password",
  "from_email": "your_gmail@gmail.com",
  "to_email": "recipient@example.com",
  "use_tls": true,
  "use_ssl": false,
  "subject_prefix": "Paper Digest"
}
```

## Data Storage

- **`data/`** — All persistent data:
  - `papers.db` — SQLite database
  - `embeddings.pt` — Cached paper embeddings (torch tensor)
  - `preference_model.pt` — Neural network weights (user's preference config)
  - `summaries/` — Cache of generated summaries
  
## Testing

Unit tests use Python's `unittest` framework. Test files mirror module names (e.g., `test_model.py` tests `aura/model.py`).

Test patterns:
- Mock external APIs (arXiv, LLM providers) to avoid rate limits and dependencies
- Use temporary directories for database and model files
- Set dummy environment variables for LLM tests

Example running a single test:
```bash
python -m unittest tests.test_model.TestPreferenceModel.test_train_predict_and_stats -v
```

## CI/CD

GitHub Actions CI (`.github/workflows/ci.yml`):
- Runs on Python 3.11
- Lints with `ruff check .`
- Runs all unit tests with dummy API keys

## Key Design Notes

- **Incremental Model Training** — The preference model is retrained on each new feedback batch. No periodic batch retraining needed unless using `python run.py retrain`.

- **Embeddings Caching** — Paper embeddings are computed once and cached in `data/embeddings.pt` to avoid redundant sentence-transformer inference.

- **LLM Summaries Optional** — Summaries are generated on-demand via the `/summarize` endpoint or `python run.py summarize`. They can be generated during fetch (`generate_on_fetch: true`) or separately later.

- **Email Flexibility** — Email digest pulls top-N papers from the database and ranks them by preference score. Template can be customized in `email_digest.py`.

- **Stateless Web Server** — Flask app is stateless; all state is in the SQLite database and model weights files. Safe to restart or run multiple instances.

## Development Workflow

1. **Fetching & Testing** — Run `python run.py fetch` to populate the database with test papers.
2. **Interactive UI** — Use `python run.py serve` and open the web UI to manually rate papers and see recommendations update in real-time.
3. **Terminal Testing** — Use `python run.py recommend` to verify ranking without starting the server.
4. **Linting** — `ruff check .` catches style issues before commit.
5. **Unit Tests** — Run tests with `python -m unittest discover -s tests -v` to verify changes.

## Common Tasks

**Add a new arXiv category:**
1. Edit `config.yaml` and add to `categories` list (see https://arxiv.org/category_taxonomy)
2. Run `python run.py fetch` to pull papers
3. Rate papers in the web UI to train the preference model

**Change embedding model:**
1. Edit `config.yaml` → `embedding_model` (e.g., `all-mpnet-base-v2` for higher quality but slower)
2. Delete `data/embeddings.pt` to force re-embedding
3. Run `python run.py fetch` to regenerate embeddings

**Set up automatic daily digests:**
1. Set up `user_credentials/email_config.json` with SMTP details
2. Customize `scheduler.fetch_hour` and `scheduler.fetch_minute` in `config.yaml` if needed
3. Run `python run.py serve --scheduler` to start with automatic daily fetch
4. Or set `scheduler.enabled: true` in config and run `python run.py serve`

**Troubleshoot LLM summaries:**
1. Check `LLM_PROVIDER` and `LLM_API_KEY` are set correctly
2. Run `python run.py summarize --limit 5` to test the API
3. Check `data/summaries/` for cached results
4. Use `--only-missing` to skip retrying papers that previously failed

## Dependencies & Versions

- **Flask 3.0+** — Web framework
- **PyTorch 2.0+** — Neural network training
- **sentence-transformers 2.2+** — Text embeddings
- **Groq SDK 0.4+** — Fast LLM (free tier, recommended for testing)
- **ruff 0.11+** — Fast Python linter
- **APScheduler 3.10** — Optional scheduler for daily auto-fetch
