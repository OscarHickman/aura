"""Weekly research brief generation and distribution."""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from .recommender import RecommendationEngine
from .trends import _generate_generic_text

logger = logging.getLogger(__name__)


def get_weekly_recommendations(engine: RecommendationEngine, limit: int = 5) -> list[dict]:
    """Retrieve top-scored recommendations published in the last 7 days.
    
    If fewer than 3 papers are found from the last 7 days, falls back to top overall recommendations
    to ensure we have content to generate a brief.
    """
    papers = engine.get_recommendations(limit=200, unrated_only=False)
    now = datetime.utcnow()
    cutoff = now - timedelta(days=7)
    
    weekly_papers = []
    for p in papers:
        try:
            pub_date = datetime.fromisoformat(p["published"].replace("Z", "+00:00")).replace(tzinfo=None)
            if pub_date >= cutoff:
                weekly_papers.append(p)
        except Exception:
            continue
            
    if len(weekly_papers) < min(limit, 3):
        logger.warning("Fewer than 3 papers found from the last 7 days. Falling back to top recommendations overall.")
        weekly_papers = papers
        
    return weekly_papers[:limit]


def generate_weekly_brief_content(engine: RecommendationEngine, date_str: str) -> str:
    """Generate weekly brief content using LLM based on recommended papers."""
    papers = get_weekly_recommendations(engine, limit=8)
    
    if not papers:
        return "<p>No recent papers available to generate a weekly brief. Please fetch new papers first.</p>"
        
    papers_text = ""
    for idx, p in enumerate(papers):
        authors_list = p.get("authors", "[]")
        if isinstance(authors_list, str):
            try:
                authors_list = json.loads(authors_list)
            except Exception:
                authors_list = [authors_list]
        authors_str = ", ".join(authors_list[:3])
        if len(authors_list) > 3:
            authors_str += " et al."
            
        summary = p.get("summary") or p.get("abstract") or ""
        if len(summary) > 800:
            summary = summary[:800] + "..."
            
        papers_text += f"Paper #{idx+1}:\n"
        papers_text += f"Title: {p['title']}\n"
        papers_text += f"Authors: {authors_str}\n"
        papers_text += f"ArXiv ID: {p['arxiv_id']}\n"
        papers_text += f"Categories: {p['categories']}\n"
        papers_text += f"Abstract/Summary: {summary}\n\n"

    prompt = f"""You are a scientific research assistant. Write a weekly research brief titled "Here's what happened in your fields this week" for the date: {date_str}.
    
Based ONLY on the following key papers from the past week, generate a structured brief. 
Format your output as clean, semantic HTML suitable for embedding in a web page or an email. Do NOT include a full HTML document (no `<html>`, `<head>`, or `<body>` tags), just the core structured elements (divs, headings, paragraphs, lists).

Your brief must include:
1. **Top Papers**: Summarise 3-5 of the most significant papers in the list below, explain their core findings/significance, and why they are recommended. Include the ArXiv ID or links where appropriate.
2. **Emerging Topics**: Synthesise 1-2 new directions, concepts, or themes emerging from these papers.
3. **Notable Authors**: Identify 2-3 key researchers or groups behind this week's work and highlight their contribution.
4. **Methodology Trends**: What main experimental, computational, or theoretical methods/datasets are driving these papers?

CRITICAL SPELLING CONSTRAINT:
You MUST use British English spelling for all user-facing text. Examples:
- "personalised", "optimised", "analysing", "synthesising", "categorised"
- "colour", "behaviour", "organisation"
Do NOT use American spellings.

Key Papers:
{papers_text}
"""

    logger.info(f"Generating weekly research brief for {date_str} using LLM")
    html_content = _generate_generic_text(prompt)
    
    if not html_content or html_content == "No AI provider available to generate trends.":
        logger.warning("LLM brief generation failed or returned empty. Using fallback template.")
        html_content = build_fallback_brief_html(papers, date_str)
        
    return html_content


def build_fallback_brief_html(papers: list[dict], date_str: str) -> str:
    """Build a static HTML fallback brief when LLM generation is unavailable."""
    html = f"""<div class="weekly-brief">
    <p><em>Weekly Research Brief for {date_str} (Fallback mode: AI provider unavailable).</em></p>
    
    <h3 class="mt-4 mb-3"><i class="bi bi-file-earmark-text"></i> Top Recommended Papers</h3>
    <div class="list-group">
    """
    for p in papers[:5]:
        authors_list = p.get("authors", "[]")
        if isinstance(authors_list, str):
            try:
                authors_list = json.loads(authors_list)
            except Exception:
                authors_list = [authors_list]
        authors_str = ", ".join(authors_list[:3])
        if len(authors_list) > 3:
            authors_str += " et al."
            
        summary = p.get("summary") or p.get("abstract") or ""
        if len(summary) > 300:
            summary = summary[:300] + "..."
            
        html += f"""
        <div class="list-group-item bg-transparent text-light border-secondary mb-3 p-3" style="border: 1px solid #333; border-radius: 6px; background-color: #1a1a1a;">
            <h5 class="mb-1"><a href="/papers/{p['arxiv_id']}" class="text-warning text-decoration-none">{p['title']}</a></h5>
            <p class="mb-2 text-muted small">By {authors_str} | Categories: {p['categories']}</p>
            <p class="mb-1 text-light-50 small">{summary}</p>
        </div>
        """
    html += """
    </div>
    
    <h3 class="mt-4 mb-3"><i class="bi bi-tags"></i> Categories & Methodology</h3>
    <p class="small text-muted">This week's research focuses primarily on the following categories:</p>
    <ul>
    """
    categories = set()
    all_authors = []
    for p in papers:
        cats = [c.strip() for c in p.get("categories", "").split(",") if c.strip()]
        categories.update(cats)
        
        authors_list = p.get("authors", "[]")
        if isinstance(authors_list, str):
            try:
                authors_list = json.loads(authors_list)
            except Exception:
                authors_list = [authors_list]
        all_authors.extend(authors_list)
        
    for cat in sorted(categories):
        html += f"<li>{cat}</li>"
        
    html += """
    </ul>
    
    <h3 class="mt-4 mb-3"><i class="bi bi-people"></i> Active Authors</h3>
    <p class="small text-muted">Key researchers contributing to this week's literature:</p>
    <ul>
    """
    from collections import Counter
    author_counts = Counter(all_authors)
    for author, count in author_counts.most_common(5):
        html += f"<li>{author} ({count} paper{'s' if count > 1 else ''})</li>"
        
    html += """
    </ul>
</div>
"""
    return html


def send_weekly_brief_email(
    data_dir: str,
    categories: list[str],
    embedding_model: str,
    date_str: str,
    email_config_path: Optional[str] = None,
) -> dict:
    """Generate the weekly brief and send it via email."""
    from .email_digest import load_email_config, _send_smtp_email, _send_graph_email
    
    email_config = load_email_config(email_config_path)
    engine = RecommendationEngine(
        data_dir=data_dir,
        categories=categories,
        embedding_model=embedding_model,
    )
    
    try:
        # Get or generate brief
        brief = engine.db.get_brief(date_str)
        if brief:
            html_content = brief["content"]
        else:
            html_content = generate_weekly_brief_content(engine, date_str)
            engine.db.add_brief(date_str, html_content)
            
        subject_prefix = email_config.get("subject_prefix", "AURA")
        subject = f"{subject_prefix} Weekly Research Brief ({date_str})"
        
        base_url = email_config.get("base_url") or "http://127.0.0.1:5000"
        text_body = f"Please view your weekly research brief at {base_url}/briefs/{date_str}"
        
        email_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: #121212; color: #e0e0e0; padding: 20px; line-height: 1.6; }}
                a {{ color: #ffc107; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                h2, h3 {{ color: #ffffff; }}
                .weekly-brief {{ background-color: #1e1e1e; border: 1px solid #333; padding: 20px; border-radius: 8px; max-width: 800px; margin: 0 auto; }}
                .list-group-item {{ border-bottom: 1px solid #333; padding: 15px 0; }}
                .text-muted {{ color: #888; }}
                .small {{ font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="weekly-brief">
                <h2 style="margin-top: 0; color: #ffc107;">AURA Weekly Research Brief</h2>
                <hr style="border: 0; border-top: 1px solid #444; margin-bottom: 20px;">
                {html_content}
                <hr style="border: 0; border-top: 1px solid #444; margin-top: 30px; margin-bottom: 20px;">
                <p class="small text-muted" style="text-align: center;">
                    You are receiving this because you are subscribed to AURA weekly briefs.
                </p>
            </div>
        </body>
        </html>
        """
        
        if email_config.get("use_graph_api", False):
            _send_graph_email(email_config, subject, text_body, email_html)
        else:
            _send_smtp_email(email_config, subject, text_body, email_html)
            
        return {
            "status": "sent",
            "sent": True,
            "to": email_config["to_email"],
            "subject": subject,
        }
    finally:
        engine.close()
