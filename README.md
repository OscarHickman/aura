# CI

[![CI](https://github.com/OscarHickman/aura/actions/workflows/ci.yml/badge.svg)](https://github.com/OscarHickman/aura/actions/workflows/ci.yml)
[![Deploy](https://github.com/OscarHickman/aura/actions/workflows/deploy.yml/badge.svg)](https://github.com/OscarHickman/aura/actions/workflows/deploy.yml)

# AURA (Automated Understanding of Research Articles)

A powerful research discovery and organization tool. AURA fetches papers from **multiple sources** (arXiv, Semantic Scholar, RSS feeds), ranks them using a personalized neural network preference model, and provides AI-generated summaries and daily digests.

## Key Features

- **Multi-Source Discovery:** Ingest papers from arXiv, Semantic Scholar (with citation counts), and custom journal RSS feeds.
- **Personalised Ranking:** 5-star rating system with a PyTorch neural network that learns your research interests.
- **Smart Search:** Toggle between Keyword (FTS) and Semantic search (vector similarity).
- **Deep Dive Summaries:** Extract full-text PDFs to generate structured summaries (Background, Methods, Results, Significance) in multiple reading modes (expert vs. graduate student).
- **Research Q&A:** RAG-powered assistant to ask arbitrary questions about a paper's full text, streamed to the UI in real-time.
- **Trend Radar:** Visual heatmap displaying publication density per topic per week, including publication velocity sparklines and automated trend velocity spike detection.
- **Auto-Discovery:** Unsupervised topic clustering (K-Means) to find new trends in your field.
- **Organisation:** Manage personal collections, tags, reading lists (queue), and paper annotations.
- **Explainable AI:** Score breakdowns and "Because you liked" context for all recommendations.
- **Modern UI:** Responsive dark-mode interface with infinite scrolling and keyboard shortcuts.
- **Daily Digest:** Automated daily email digests with AI summaries of top papers.
- **Weekly Research Briefs:** Synthesised weekly briefs outlining top recommended papers, emerging topics, notable authors, and methodology trends (viewable at `/briefs` and delivered via email).

## Quick Start

```bash
pip install -r requirements.txt
python run.py fetch
python run.py serve
```

Open `http://127.0.0.1:5000`.

## Main Commands

- `python run.py fetch` — Discovery from all sources
- `python run.py serve` — Launch the web interface
- `python run.py summarize --limit 20` — Generate AI summaries
- `python run.py email-digest --top-n 3` — Send daily summary email
- `python run.py weekly-brief` — Generate and email the weekly research brief
- `python run.py retrain` — Full model retraining
- `python run.py stats` — System statistics

## Summary Provider Setup

AURA supports multiple LLM providers (Groq, OpenAI, Anthropic, Google). Set your preferred provider and API key:

```bash
export LLM_PROVIDER=groq
export GROQ_API_KEY=your_key_here
```

## Gmail Email Setup

The digest command reads `user_credentials/email_config.json`.

Use Gmail SMTP with an app password (not your normal Gmail password):

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

Then run:

```bash
python run.py email-digest --top-n 3
```

## Notes

- Do not store real passwords in README or commit them to git.
- Python 3.10+ required.

## Deployment (Ubuntu server)

Recommended: run in Docker. Alternative steps for a manual server install are also provided.

Docker (recommended)

- Build and push an image (or let GitHub Actions build & push to GitHub Container Registry):

```bash
# Build locally and tag (replace OWNER/REPO)
docker build -t ghcr.io/OWNER/REPO:latest .
docker push ghcr.io/OWNER/REPO:latest
```

- On your Ubuntu server (or let Actions deploy via SSH):

```bash
ssh deploy-user@your-server
docker pull ghcr.io/OWNER/REPO:latest
docker stop aura_app || true
docker rm aura_app || true
docker run -d --restart unless-stopped -p 80:5000 --name aura_app ghcr.io/OWNER/REPO:latest
```

GitHub Actions deployment

- The workflow `.github/workflows/deploy.yml` builds and pushes to `ghcr.io/${{ github.repository }}`. To enable the SSH deploy step, set these repository secrets:

- `DEPLOY_SSH_HOST` — your server host or IP
- `DEPLOY_SSH_USER` — SSH user
- `SSH_PRIVATE_KEY` — private key (no passphrase) for `DEPLOY_SSH_USER`
- Optional: `DEPLOY_SSH_PORT`

Manual (no Docker)

1. SSH to your Ubuntu server and install system packages:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git build-essential
```

2. Clone the repo, create a virtualenv, and install dependencies:

```bash
git clone https://github.com/OWNER/REPO.git
cd REPO
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

3. Run the app (development):

```bash
python run.py serve --config config.yaml
```

4. For production, run with Gunicorn (recommended) — a WSGI entrypoint is provided at `deploy/wsgi.py`:

```bash
# From the repository root
pip install gunicorn
gunicorn "deploy.wsgi:app" -w 4 -b 0.0.0.0:5000
```

5. (Optional) Create a `systemd` service to run the app on boot. Example service `/etc/systemd/system/aura.service`:

```
[Unit]
Description=AURA service
After=network.target

[Service]
User=youruser
WorkingDirectory=/path/to/REPO
Environment="PATH=/path/to/REPO/.venv/bin"
ExecStart=/path/to/REPO/.venv/bin/gunicorn "aura.web.app:create_app()" -w 4 -b 0.0.0.0:5000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Notes

- Replace `OWNER/REPO` and paths with your repository and server details.
- Keep secrets out of the repo; use environment variables or `user_credentials/` for local config.
- The provided GitHub Actions workflow will build and push the image to GHCR and can deploy via SSH when secrets are set.

