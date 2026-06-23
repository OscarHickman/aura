"""Slack and Discord webhook notifications for AURA."""

import logging
import requests
from typing import Any, List, Dict, Optional

logger = logging.getLogger(__name__)

def send_slack_notification(webhook_url: str, paper: Dict[str, Any], score: float) -> bool:
    """Send a single high-scoring paper notification to a Slack webhook."""
    try:
        score_percent = round(score * 100)
        title = paper.get("title", "Untitled")
        url = paper.get("url", "")
        authors = ", ".join(paper.get("authors", [])[:3])
        summary = paper.get("summary") or paper.get("abstract", "")
        if len(summary) > 300:
            summary = summary[:297] + "..."

        payload = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🔥 *New high-scoring paper matched!* (Score: *{score_percent}%*)\n\n*<{url}|{title}>*\n*Authors*: {authors}\n\n{summary}"
                    }
                }
            ]
        }
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")
        return False

def send_discord_notification(webhook_url: str, paper: Dict[str, Any], score: float) -> bool:
    """Send a single high-scoring paper notification to a Discord webhook."""
    try:
        score_percent = round(score * 100)
        title = paper.get("title", "Untitled")
        url = paper.get("url", "")
        authors = ", ".join(paper.get("authors", [])[:3])
        summary = paper.get("summary") or paper.get("abstract", "")
        if len(summary) > 300:
            summary = summary[:297] + "..."

        payload = {
            "content": f"🔥 **New high-scoring paper matched!** (Score: **{score_percent}%**)\n\n**[{title}]({url})**\n*Authors*: {authors}\n\n{summary}"
        }
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Discord notification: {e}")
        return False

def send_slack_digest(webhook_url: str, papers: List[Dict[str, Any]]) -> bool:
    """Send a daily digest list to a Slack webhook."""
    try:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📚 AURA Recommendations Daily Digest",
                    "emoji": True
                }
            },
            {
                "type": "divider"
            }
        ]
        
        for i, paper in enumerate(papers, 1):
            score_percent = round(float(paper.get("score", 0.0)) * 100)
            title = paper.get("title", "Untitled")
            url = paper.get("url", "")
            authors = ", ".join(paper.get("authors", [])[:3])
            summary = paper.get("summary") or paper.get("abstract", "")
            if len(summary) > 180:
                summary = summary[:177] + "..."
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{i}. *<{url}|{title}>* [Score: *{score_percent}%*]\n*Authors*: {authors}\n{summary}"
                }
            })
            
        payload = {"blocks": blocks}
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Slack digest: {e}")
        return False

def notify_high_scoring_papers(engine: Any, new_papers: List[Dict[str, Any]], config: Dict[str, Any]) -> None:
    """Check scores of new papers for all active users (or default user) and send notifications."""
    integrations = config.get("integrations", {})
    slack_conf = integrations.get("slack", {})
    discord_conf = integrations.get("discord", {})
    
    slack_enabled = slack_conf.get("enabled", False) and slack_conf.get("webhook_url")
    discord_enabled = discord_conf.get("enabled", False) and discord_conf.get("webhook_url")
    
    if not slack_enabled and not discord_enabled:
        return
        
    # Get primary/active users
    users = engine.db.get_all_users()
    user_ids = [u["id"] for u in users] if users else [1]
    
    for uid in user_ids:
        # Score the new papers for this user
        # We can score them by matching their embeddings with the user's preference model
        pref_model = engine.get_user_preference_model(uid)
        
        for paper in new_papers:
            arxiv_id = paper.get("arxiv_id")
            if not arxiv_id:
                continue
                
            # Get paper embedding
            papers_emb = engine.db.get_papers_with_embeddings([arxiv_id])
            if not papers_emb:
                continue
                
            _, embedding = papers_emb[0]
            
            # Predict preference score
            import torch
            with torch.no_grad():
                emb_t = torch.tensor(embedding, dtype=torch.float32).unsqueeze(0)
                score = float(torch.sigmoid(pref_model(emb_t)).item())
                
            # Slack check
            if slack_enabled:
                threshold = slack_conf.get("score_threshold", 0.8)
                if score >= threshold:
                    send_slack_notification(slack_conf["webhook_url"], paper, score)
                    
            # Discord check
            if discord_enabled:
                threshold = discord_conf.get("score_threshold", 0.8)
                if score >= threshold:
                    send_discord_notification(discord_conf["webhook_url"], paper, score)
