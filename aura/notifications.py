"""Slack and Discord webhook notifications for AURA."""

import logging
import requests
from typing import Any, List, Dict, Optional

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def is_valid_expo_push_token(token: str) -> bool:
    """Validate whether token matches Expo Push Token format."""
    if not isinstance(token, str):
        return False
    token = token.strip()
    return (token.startswith("ExponentPushToken[") and token.endswith("]")) or (
        token.startswith("ExpoPushToken[") and token.endswith("]")
    )


def send_expo_push_notifications(
    messages: List[Dict[str, Any]],
    timeout: int = 10,
) -> Dict[str, Any]:
    """Send batch push notifications via Expo Push Notification service."""
    if not messages:
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    stale_tokens: List[str] = []
    success_count = 0
    failure_count = 0

    batch_size = 100
    for i in range(0, len(messages), batch_size):
        chunk = messages[i : i + batch_size]
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(EXPO_PUSH_URL, json=chunk, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            tickets = data.get("data", [])
            for msg, ticket in zip(chunk, tickets):
                status = ticket.get("status")
                if status == "ok":
                    success_count += 1
                else:
                    failure_count += 1
                    details = ticket.get("details", {})
                    if details.get("error") == "DeviceNotRegistered":
                        stale_tokens.append(str(msg.get("to")))
                    logger.warning(
                        f"Expo push ticket error for token {msg.get('to')}: {ticket.get('message')}"
                    )
        except Exception as e:
            logger.error(f"Failed to post push notification chunk to Expo: {e}")
            failure_count += len(chunk)

    return {
        "success_count": success_count,
        "failure_count": failure_count,
        "stale_tokens": [t for t in stale_tokens if t],
    }


def send_push_notification_to_user(
    db: Any,
    user_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    sound: str = "default",
    badge: Optional[int] = None,
) -> Dict[str, Any]:
    """Send push notification to all active devices registered to a user."""
    if not db or not hasattr(db, "get_user_device_tokens"):
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    try:
        raw_tokens = db.get_user_device_tokens(user_id)
    except Exception as e:
        logger.warning(f"Failed to fetch device tokens for user {user_id}: {e}")
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    if not isinstance(raw_tokens, (list, tuple)):
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    device_tokens = [t for t in raw_tokens if isinstance(t, dict)]
    if not device_tokens:
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    messages = []
    for dt in device_tokens:
        token = dt.get("device_token")
        if not token:
            continue
        msg: Dict[str, Any] = {
            "to": token,
            "title": title,
            "body": body,
            "sound": sound,
            "priority": "high",
            "data": data or {},
        }
        if badge is not None:
            msg["badge"] = badge
        messages.append(msg)

    if not messages:
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    result = send_expo_push_notifications(messages)
    if result["stale_tokens"]:
        db.delete_stale_device_tokens(result["stale_tokens"])
    return result


def notify_push_digest_ready(
    engine: Any,
    user_id: int,
    top_papers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Send a push notification informing the user that their research digest is ready."""
    if not top_papers:
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    lead_paper = top_papers[0]
    lead_title = lead_paper.get("title", "Research Digest")
    score_pct = round(float(lead_paper.get("score", 0.0)) * 100)
    extra_count = len(top_papers) - 1

    title = "📚 Daily Research Digest Ready"
    if extra_count > 0:
        body = f"Top match: {lead_title} ({score_pct}%) + {extra_count} more papers"
    else:
        body = f"Top match: {lead_title} ({score_pct}%)"

    data = {
        "url": f"aura://papers/{lead_paper.get('arxiv_id', '')}",
        "arxiv_id": lead_paper.get("arxiv_id", ""),
        "type": "digest",
    }

    return send_push_notification_to_user(
        engine.db,
        user_id=user_id,
        title=title,
        body=body,
        data=data,
    )


def notify_velocity_spike(
    db: Any,
    keyword: str,
    paper_count: int,
    window_start: str,
    window_end: str,
) -> Dict[str, Any]:
    """Broadcast a push notification when a keyword/simulation code publication velocity spikes."""
    if not db or not hasattr(db, "get_all_device_tokens"):
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    try:
        raw_devices = db.get_all_device_tokens()
    except Exception as e:
        logger.warning(f"Failed to fetch device tokens for velocity spike: {e}")
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    if not isinstance(raw_devices, (list, tuple)):
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    devices = [d for d in raw_devices if isinstance(d, dict)]
    if not devices:
        return {"success_count": 0, "failure_count": 0, "stale_tokens": []}

    title = "📈 Research Spike Detected"
    body = f"Surge in {keyword} publications: {paper_count} papers identified in the last 7 days."
    data = {
        "url": "aura://intel",
        "keyword": keyword,
        "type": "velocity_spike",
    }

    messages = [
        {
            "to": d["device_token"],
            "title": title,
            "body": body,
            "sound": "default",
            "priority": "high",
            "data": data,
        }
        for d in devices
        if d.get("device_token")
    ]

    result = send_expo_push_notifications(messages)
    if result["stale_tokens"]:
        db.delete_stale_device_tokens(result["stale_tokens"])
    return result


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

        payload: Dict[str, Any] = {
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

        payload: Dict[str, Any] = {
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
            
        payload: Dict[str, Any] = {"blocks": blocks}
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Slack digest: {e}")
        return False


def notify_high_scoring_papers(engine: Any, new_papers: List[Dict[str, Any]], config: Dict[str, Any]) -> None:
    """Check scores of new papers for all active users and dispatch notifications."""
    integrations = config.get("integrations", {})
    slack_conf = integrations.get("slack", {})
    discord_conf = integrations.get("discord", {})
    
    slack_enabled = slack_conf.get("enabled", False) and slack_conf.get("webhook_url")
    discord_enabled = discord_conf.get("enabled", False) and discord_conf.get("webhook_url")
    
    # Get primary/active users
    users = engine.db.get_all_users()
    user_ids = [u["id"] for u in users] if users else [1]
    
    push_threshold = float(config.get("notifications", {}).get("score_threshold", 0.8))
    
    for uid in user_ids:
        pref_model = engine.get_user_preference_model(uid)
        
        for paper in new_papers:
            arxiv_id = paper.get("arxiv_id")
            if not arxiv_id:
                continue
                
            papers_emb = engine.db.get_papers_with_embeddings([arxiv_id])
            if not papers_emb:
                continue
                
            _, embedding = papers_emb[0]
            
            import numpy as np
            score, _ = pref_model.predict(np.asarray(embedding, dtype=np.float32), num_samples=1)
                
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

            # Native mobile push notification
            if score >= push_threshold and engine and hasattr(engine, "db") and engine.db:
                score_percent = round(score * 100)
                send_push_notification_to_user(
                    engine.db,
                    user_id=uid,
                    title="🔥 High-Scoring Paper Matched",
                    body=f"{paper.get('title', 'Untitled')} (Score: {score_percent}%)",
                    data={
                        "url": f"aura://papers/{arxiv_id}",
                        "arxiv_id": arxiv_id,
                        "type": "high_score",
                    },
                )


def send_slack_citation_alert(webhook_url: str, event: Dict[str, Any]) -> bool:
    """Send a Slack notification for a newly detected paper citation."""
    try:
        my_title = event.get("my_paper_title", "Your paper")
        citing_title = event.get("citing_title", "Untitled")
        citing_arxiv = event.get("citing_arxiv_id", "")
        citing_url = (
            f"https://arxiv.org/abs/{citing_arxiv}"
            if citing_arxiv and not citing_arxiv.startswith("http")
            else citing_arxiv
        )
        authors = event.get("citing_authors") or "Unknown authors"

        payload: Dict[str, Any] = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"🎓 *New Citation Detected!*\n\n"
                            f"Your publication *{my_title}* has been cited by:\n"
                            f"*<{citing_url}|{citing_title}>*\n"
                            f"*Authors*: {authors}"
                        ),
                    },
                }
            ]
        }
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Slack citation alert: {e}")
        return False


def send_discord_citation_alert(webhook_url: str, event: Dict[str, Any]) -> bool:
    """Send a Discord notification for a newly detected paper citation."""
    try:
        my_title = event.get("my_paper_title", "Your paper")
        citing_title = event.get("citing_title", "Untitled")
        citing_arxiv = event.get("citing_arxiv_id", "")
        citing_url = (
            f"https://arxiv.org/abs/{citing_arxiv}"
            if citing_arxiv and not citing_arxiv.startswith("http")
            else citing_arxiv
        )
        authors = event.get("citing_authors") or "Unknown authors"

        payload: Dict[str, Any] = {
            "content": (
                f"🎓 **New Citation Detected!**\n\n"
                f"Your publication **{my_title}** has been cited by:\n"
                f"**[{citing_title}]({citing_url})**\n"
                f"*Authors*: {authors}"
            )
        }
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to send Discord citation alert: {e}")
        return False


def notify_citation_events(
    engine: Any, events: List[Dict[str, Any]], config: Dict[str, Any]
) -> None:
    """Send webhook and native push notifications for newly detected citation events."""
    if not events:
        return

    integrations = config.get("integrations", {})
    slack_conf = integrations.get("slack", {})
    discord_conf = integrations.get("discord", {})

    slack_enabled = slack_conf.get("enabled", False) and slack_conf.get("webhook_url")
    discord_enabled = discord_conf.get("enabled", False) and discord_conf.get("webhook_url")

    for event in events:
        if slack_enabled:
            send_slack_citation_alert(slack_conf["webhook_url"], event)
        if discord_enabled:
            send_discord_citation_alert(discord_conf["webhook_url"], event)

        # Native mobile push notification for the cited paper author
        if engine and hasattr(engine, "db") and engine.db:
            user_id = event.get("user_id", 1)
            my_title = event.get("my_paper_title", "Your paper")
            citing_title = event.get("citing_title", "Untitled")
            citing_arxiv = event.get("citing_arxiv_id", "")
            send_push_notification_to_user(
                engine.db,
                user_id=user_id,
                title="🎓 New Citation Detected!",
                body=f"'{my_title[:45]}' was cited by '{citing_title[:45]}'",
                data={
                    "url": "aura://my-papers",
                    "arxiv_id": citing_arxiv,
                    "type": "citation",
                },
            )

