"""Build and send email digests from top recommended papers."""

import json
import logging
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

import requests

from .config import get_validated_config
from .llm import AI_FAIL_SUMMARY
from .recommender import RecommendationEngine
from .trends import generate_monthly_trends

logger = logging.getLogger(__name__)


def load_email_config(config_path: Optional[str] = None) -> dict:
    """Load and validate SMTP/email settings."""
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Email config not found: {path}")
        if path.suffix == ".json":
            with open(path) as f:
                data = json.load(f)
        else:
            try:
                main_config = get_validated_config(config_path)
                data = main_config.get("email", {})
            except Exception:
                data = {}
    else:
        try:
            main_config = get_validated_config()
            data = main_config.get("email", {})
        except Exception:
            data = {}

    if not data or not any(data.values()):
        raise ValueError("Email notifications are not configured.")

    use_graph_api = bool(data.get("use_graph_api", False))
    if use_graph_api:
        required = ["from_email", "to_email", "ms_client_id"]
    else:
        required = [
            "smtp_host",
            "smtp_port",
            "smtp_username",
            "smtp_password",
            "from_email",
            "to_email",
        ]
    missing = [key for key in required if not data.get(key)]
    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(f"Missing required email config fields: {missing_str}")

    return data


def _acquire_graph_token(email_config: dict) -> str:
    """Acquire Microsoft Graph access token using device code flow."""
    try:
        import msal
    except ImportError as exc:
        raise RuntimeError(
            "msal is required for use_graph_api=true. Install with: pip install msal"
        ) from exc

    client_id = email_config["ms_client_id"]
    if client_id in ("YOUR_AZURE_APP_CLIENT_ID", "", None):
        raise RuntimeError(
            "ms_client_id is not configured. Set a real Azure App (client) ID in user_credentials/email_config.json"
        )
    tenant = email_config.get("ms_tenant", "consumers")
    authority = f"https://login.microsoftonline.com/{tenant}"
    scopes = email_config.get("ms_scopes", ["Mail.Send"])

    app = msal.PublicClientApplication(client_id=client_id, authority=authority)

    account = None
    from_email = email_config.get("from_email", "")
    for existing in app.get_accounts():
        if existing.get("username", "").lower() == from_email.lower():
            account = existing
            break

    result = app.acquire_token_silent(scopes=scopes, account=account)
    if result and result.get("access_token"):
        return result["access_token"]

    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        details = flow.get("error_description") or flow.get("error") or "unknown error"
        raise RuntimeError(f"Failed to start Microsoft device code flow: {details}")

    print("\nMicrosoft sign-in required for Outlook sending:")
    print(f"Open: {flow['verification_uri']}")
    print(f"Code: {flow['user_code']}\n")

    result = app.acquire_token_by_device_flow(flow)
    if not result or "access_token" not in result:
        message = (result or {}).get(
            "error_description", "Failed to acquire Microsoft Graph token"
        )
        raise RuntimeError(message)

    return result["access_token"]


def _send_graph_email(email_config: dict, subject: str, text_body: str, html_body: str):
    """Send mail through Microsoft Graph using delegated OAuth."""
    access_token = _acquire_graph_token(email_config)

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_body,
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": email_config["to_email"],
                    }
                }
            ],
            "replyTo": [
                {
                    "emailAddress": {
                        "address": email_config["from_email"],
                    }
                }
            ],
        },
        "saveToSentItems": True,
    }

    response = requests.post(
        "https://graph.microsoft.com/v1.0/me/sendMail",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 202):
        raise RuntimeError(
            f"Microsoft Graph send failed: HTTP {response.status_code} - {response.text}"
        )


def _collect_top_papers_with_summaries(
    engine: RecommendationEngine, top_n: int
) -> list[dict]:
    """Get top recommendations and ensure each has a non-empty summary."""
    papers = engine.get_recommendations(limit=top_n, unrated_only=True)
    hydrated = []

    for paper in papers:
        summary = (paper.get("summary") or "").strip()
        if not summary or summary == AI_FAIL_SUMMARY:
            result = engine.generate_summary_for_paper(paper["arxiv_id"])
            summary = (result.get("summary") or "").strip()

        if not summary:
            summary = AI_FAIL_SUMMARY

        updated = dict(paper)
        updated["summary"] = summary
        hydrated.append(updated)

    return hydrated


def _build_email_content(
    papers: list[dict], trends: dict[str, str], app_name: str = "AURA"
) -> tuple[str, str]:
    """Create plain-text and HTML digest bodies."""
    text_lines = [f"{app_name} - Monthly Research Trends", ""]
    html_items = [
        "<h2>Monthly Research Trends</h2>",
        "<div style='margin-bottom:30px;'>"
    ]

    for topic, summary in trends.items():
        text_lines.extend([f"**{topic.title()}**", summary, ""])
        html_items.append(
            f"<div style='margin-bottom:15px;'>"
            f"<h3 style='margin:0 0 4px 0;color:#2c3e50;'>{topic.title()}</h3>"
            f"<p style='margin:0;color:#444;line-height:1.5;'>{summary}</p>"
            f"</div>"
        )
    html_items.append("</div><hr>")

    text_lines.extend([f"{app_name} - Top {len(papers)} Recommendations", ""])
    html_items.append(f"<h2>Top {len(papers)} Recommendations</h2>")

    for i, paper in enumerate(papers, 1):
        score = round(float(paper.get("score", 0.0)) * 100)
        authors = ", ".join(paper.get("authors", [])[:3])
        summary = paper.get("summary", AI_FAIL_SUMMARY)
        url = paper.get("url", "")

        text_lines.extend(
            [
                f"{i}. {paper.get('title', 'Untitled')} [{score}%]",
                f"Authors: {authors}",
                f"URL: {url}",
                f"Summary: {summary}",
                "",
            ]
        )

        html_items.append(
            """
            <div style=\"margin-bottom:20px;padding:14px;border:1px solid #ddd;border-radius:8px;\">
              <h3 style=\"margin:0 0 8px 0;\">{idx}. {title} <span style=\"font-size:12px;color:#444;\">[{score}%]</span></h3>
              <p style=\"margin:0 0 8px 0;color:#555;\"><strong>Authors:</strong> {authors}</p>
              <p style=\"margin:0 0 8px 0;\"><a href=\"{url}\">{url}</a></p>
              <p style=\"margin:0;line-height:1.5;\">{summary}</p>
            </div>
            """.format(
                idx=i,
                title=paper.get("title", "Untitled"),
                score=score,
                authors=authors,
                url=url,
                summary=summary,
            )
        )

    html_body = (
        "<html><body>"
        f"<h2 style='font-family:Arial,sans-serif'>{app_name} Daily Digest</h2>"
        "<div style='font-family:Arial,sans-serif;font-size:14px'>"
        + "".join(html_items)
        + "</div></body></html>"
    )

    return "\n".join(text_lines).strip(), html_body


def _send_smtp_email(email_config: dict, subject: str, text_body: str, html_body: str):
    """Send multipart email using SMTP settings from config."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_config["from_email"]
    msg["To"] = email_config["to_email"]
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    host = email_config["smtp_host"]
    port = int(email_config["smtp_port"])
    username = email_config["smtp_username"]
    password = email_config["smtp_password"]
    use_ssl = bool(email_config.get("use_ssl", False))
    use_tls = bool(email_config.get("use_tls", True))

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        if use_tls:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(msg)


def send_top_recommendations_email(
    data_dir: str,
    categories: list[str],
    embedding_model: str,
    email_config_path: Optional[str] = None,
    top_n: int = 3,
) -> dict:
    """Generate summaries for top papers and send a formatted digest email."""
    if top_n <= 0:
        raise ValueError("top_n must be >= 1")

    email_config = load_email_config(email_config_path)
    engine = RecommendationEngine(
        data_dir=data_dir,
        categories=categories,
        embedding_model=embedding_model,
    )

    try:
        papers = _collect_top_papers_with_summaries(engine, top_n)
        if not papers:
            return {
                "status": "no_papers",
                "sent": False,
                "message": "No recommended papers available to email",
            }

        subject_prefix = email_config.get("subject_prefix", "AURA")
        today = date.today().isoformat()
        subject = f"{subject_prefix} ({today}): Top {len(papers)} Paper Recommendations & Trends"
        
        # Generate trends before building email
        logger.info("Generating monthly trends for email digest...")
        trends = generate_monthly_trends(data_dir=data_dir, embedding_model=embedding_model)
        
        text_body, html_body = _build_email_content(papers, trends=trends, app_name=subject_prefix)

        if email_config.get("use_graph_api", False):
            _send_graph_email(email_config, subject, text_body, html_body)
        else:
            _send_smtp_email(email_config, subject, text_body, html_body)

        return {
            "status": "sent",
            "sent": True,
            "to": email_config["to_email"],
            "count": len(papers),
            "subject": subject,
        }
    finally:
        engine.close()
