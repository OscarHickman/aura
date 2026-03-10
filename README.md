# arXiv Paper Recommender

Local tool to fetch arXiv papers, rank them from your ratings, and send a daily email digest.

## Quick Start

```bash
pip install -r requirements.txt
python run.py fetch
python run.py serve
```

Open `http://127.0.0.1:5000`.

## Main Commands

- `python run.py fetch`
- `python run.py serve`
- `python run.py recommend`
- `python run.py summarize --limit 20`
- `python run.py email-digest --top-n 3`
- `python run.py retrain`
- `python run.py stats`

## Summary Provider Setup

For `summarize` and email summaries, set provider credentials in your shell.

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
