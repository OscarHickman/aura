"""Generate monthly trends for specific research topics."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from .database import PaperDatabase
from .embedder import get_model
from .llm import _load_providers_order, _resolve_api_key

logger = logging.getLogger(__name__)

DEFAULT_TOPICS = {
    "sbi": [
        "simulation based inference",
        "neural posterior estimation",
        "normalizing flows cosmology",
        "field level inference",
        "neural compression",
        "likelihood free inference",
        "implicit likelihood inference",
        "amortized inference"
    ],
    "galaxy_statistics": [
        "galaxy clustering",
        "large scale structure",
        "galaxy correlations function",
        "two point statistics",
        "galaxy power spectrum",
        "higher order statistics cosmology",
        "summary statistics inference"
    ],
    "ml_methods": [
        "Machine learning",
        "emulators",
        "pure ai inference"
    ]
}


def load_topics(data_dir: str | Path) -> dict[str, list[str]]:
    """Load research topics to track, grouped by section."""
    path = Path(data_dir) / "research_topics.json"
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_TOPICS, indent=2))
        return DEFAULT_TOPICS
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            # Ensure all default sections exist
            for sec, defaults in DEFAULT_TOPICS.items():
                if sec not in data:
                    data[sec] = defaults
            return data
        elif isinstance(data, list):
            # Migrate old flat list to grouped dictionary
            migrated: dict[str, list[str]] = {sec: [] for sec in DEFAULT_TOPICS}
            for topic in data:
                categorized = False
                for sec, topics in DEFAULT_TOPICS.items():
                    if topic in topics:
                        migrated[sec].append(topic)
                        categorized = True
                        break
                if not categorized:
                    t_lower = topic.lower()
                    if any(x in t_lower for x in ["inference", "posterior", "flows", "compression"]):
                        migrated["sbi"].append(topic)
                    elif any(x in t_lower for x in ["galaxy", "statistics", "spectrum", "structure"]):
                        migrated["galaxy_statistics"].append(topic)
                    else:
                        migrated["ml_methods"].append(topic)
            return migrated
        return DEFAULT_TOPICS
    except Exception as e:
        logger.error(f"Failed to load topics: {e}")
        return DEFAULT_TOPICS


def save_topics(data_dir: str | Path, topics: dict[str, list[str]] | list[str]):
    """Save research topics."""
    path = Path(data_dir) / "research_topics.json"
    path.write_text(json.dumps(topics, indent=2))


def _generate_generic_text(prompt: str) -> str:
    """A generic wrapper to send an arbitrary prompt to the preferred LLM."""
    providers_to_try = _load_providers_order()
    
    for p in providers_to_try:
        if p == "groq":
            try:
                from groq import Groq
                api_key = _resolve_api_key(None, "GROQ_API_KEY", "groq")
                if not api_key:
                    continue
                client = Groq(api_key=api_key)
                # use 8b instant for speed
                message = client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.1-8b-instant",
                    max_tokens=300,
                    temperature=0.5,
                )
                content = message.choices[0].message.content
                return content.strip() if content else ""
            except Exception as e:
                logger.warning(f"Groq generic text generation failed: {e}")
        elif p == "openai":
            try:
                from openai import OpenAI
                api_key = _resolve_api_key(None, "OPENAI_API_KEY", "openai")
                if not api_key:
                    continue
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=300,
                    temperature=0.5,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"OpenAI generic text generation failed: {e}")
        elif p == "anthropic":
            try:
                import anthropic
                api_key = _resolve_api_key(None, "ANTHROPIC_API_KEY", "anthropic")
                if not api_key:
                    continue
                client = anthropic.Anthropic(api_key=api_key)
                message = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                )
                return message.content[0].text.strip()
            except Exception as e:
                logger.warning(f"Anthropic generic text generation failed: {e}")
        elif p == "google":
            try:
                import requests as _requests
                api_key = _resolve_api_key(None, "GOOGLE_API_KEY", "google")
                if not api_key:
                    api_key = _resolve_api_key(None, "GEMINI_API_KEY", "google")
                if not api_key:
                    continue
                endpoint = (
                    "https://generativelanguage.googleapis.com/v1beta/"
                    f"models/gemini-2.0-flash:generateContent?key={api_key}"
                )
                payload: dict = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.5, "maxOutputTokens": 300},
                }
                resp = _requests.post(endpoint, json=payload, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                text = "".join(part.get("text", "") for part in parts).strip()
                if text:
                    return text
            except Exception as e:
                logger.warning(f"Google/Gemini generic text generation failed: {e}")

    return "No AI provider available to generate trends."


def generate_monthly_trends(data_dir: str | Path, embedding_model: str = "all-MiniLM-L6-v2") -> dict[str, str]:
    """Analyze papers from the last 30 days and generate summaries for topics.
    
    Returns a dict mapping topic -> summary text.
    """
    grouped_topics = load_topics(data_dir)
    # Flatten grouped topics to a list for analysis
    if isinstance(grouped_topics, dict):
        topics = []
        for sec_topics in grouped_topics.values():
            topics.extend(sec_topics)
    else:
        topics = grouped_topics

    db = PaperDatabase(Path(data_dir) / "papers.db")
    
    # Get all papers from last 30 days
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    
    papers_with_emb = db.get_papers_with_embeddings()
    recent_papers = []
    
    for paper, emb in papers_with_emb:
        try:
            pub_date = datetime.fromisoformat(paper["published"].replace("Z", "+00:00"))
            if pub_date.replace(tzinfo=None) >= cutoff_date:
                recent_papers.append((paper, emb))
        except Exception:
            continue

    if not recent_papers:
        logger.info("No recent papers found for trends analysis.")
        return {t: "No new papers published in this field in the last 30 days." for t in topics}

    # Embed topics
    model = get_model(embedding_model)
    topic_embeddings = model.encode(topics, normalize_embeddings=True)
    
    paper_embs = np.stack([emb for _, emb in recent_papers])
    
    trends = {}
    
    for i, topic in enumerate(topics):
        topic_emb = topic_embeddings[i]
        
        # Calculate cosine similarities
        similarities = np.dot(paper_embs, topic_emb)
        
        # Get top 5 papers
        top_indices = np.argsort(similarities)[-5:][::-1]
        
        top_papers_text = ""
        for idx in top_indices:
            p = recent_papers[idx][0]
            score = similarities[idx]
            if score < 0.3: # Minimum relevance threshold
                continue
            top_papers_text += f"- Title: {p['title']}\n  Abstract: {p['abstract'][:500]}...\n\n"
            
        if not top_papers_text:
            trends[topic] = "No highly relevant papers found in the last 30 days."
            continue
            
        prompt = (
            f"You are a scientific research assistant. Summarize how the field of '{topic}' "
            f"has developed over the last month based ONLY on these recent papers. "
            f"Write exactly 2-3 concise sentences focusing on new methods, findings, or trends.\n\n"
            f"Recent Papers:\n{top_papers_text}"
        )
        
        logger.info(f"Generating trend summary for topic: {topic}")
        summary = _generate_generic_text(prompt)
        trends[topic] = summary
        
    # Attempt to discover new emerging topics from the 20 most recent papers
    recent_papers.sort(key=lambda x: x[0].get("published", ""), reverse=True)
    freshest_papers_text = ""
    for p, _ in recent_papers[:20]:
        freshest_papers_text += f"- {p['title']}: {p['abstract'][:200]}...\n"
        
    discovery_prompt = (
        f"You are a scientific research assistant tracking emerging trends. "
        f"The current tracked topics are: {', '.join(topics)}.\n\n"
        f"Based ONLY on the following very recent papers, are there any clearly emerging "
        f"new subfields or methodologies that are completely distinct from the current topics? "
        f"If so, suggest at most 1 or 2 new concise keywords to track (just the keywords separated by commas, nothing else). "
        f"If there are no major new topics, output exactly 'NONE'.\n\n"
        f"Recent Papers:\n{freshest_papers_text}"
    )
    
    new_topics_str = _generate_generic_text(discovery_prompt)
    normalized = new_topics_str.strip().upper() if new_topics_str else ""
    no_provider = "NO AI PROVIDER AVAILABLE"
    if normalized and normalized != "NONE" and no_provider not in normalized:
        suggested = [t.strip().lower() for t in new_topics_str.split(",") if t.strip()]
        existing_lower = {e.lower() for e in topics}
        
        # Enhanced validation regex/logic
        import re
        # Rejects starting with conjunctions, or having punctuation markers
        junk_pattern = re.compile(r"^(and|the|a|an|with|from|to|for|of|by|in|on|at|as|but|or)\b|[.:;!?\n]", re.IGNORECASE)
        
        candidates = []
        for t in suggested:
            words = t.split()
            if (2 <= len(words) <= 5 and 
                3 < len(t) <= 60 and 
                t not in existing_lower and 
                not junk_pattern.search(t)):
                candidates.append(t)
        
        valid_new = []
        for t in candidates[:2]:
            # LLM-as-judge confirmation
            judge_prompt = (
                f"Is '{t}' a real and distinct scientific research area or methodology? "
                f"Answer exactly 'YES' or 'NO'."
            )
            confirmation = _generate_generic_text(judge_prompt)
            if confirmation and "YES" in confirmation.upper():
                valid_new.append(t)

        if valid_new:
            logger.info(f"Discovered new dynamic topics: {valid_new}")
            if isinstance(grouped_topics, dict):
                for t in valid_new:
                    # Dynamically classify topic
                    sec = "ml_methods"
                    t_lower = t.lower()
                    if any(x in t_lower for x in ["inference", "posterior", "flows", "compression", "likelihood", "amortized", "sbi"]):
                        sec = "sbi"
                    elif any(x in t_lower for x in ["galaxy", "statistics", "spectrum", "structure", "point", "correlation"]):
                        sec = "galaxy_statistics"
                    
                    if sec not in grouped_topics:
                        grouped_topics[sec] = []
                    if t not in grouped_topics[sec]:
                        grouped_topics[sec].append(t)
                save_topics(data_dir, grouped_topics)
            else:
                grouped_topics.extend(valid_new)
                save_topics(data_dir, grouped_topics)
            
    return trends


def cleanup_topics(data_dir: str | Path):
    """One-time cleanup script to purge existing junk entries from research_topics.json."""
    grouped_topics = load_topics(data_dir)
    import re
    junk_pattern = re.compile(r"^(and|the|a|an|with|from|to|for|of|by|in|on|at|as|but|or)\b|[.:;!?\n]", re.IGNORECASE)
    
    # Flatten default topics for membership check
    flat_defaults = []
    if isinstance(DEFAULT_TOPICS, dict):
        for val in DEFAULT_TOPICS.values():
            flat_defaults.extend(val)
    else:
        flat_defaults = DEFAULT_TOPICS

    if isinstance(grouped_topics, dict):
        cleaned_grouped = {}
        for section, topics_list in grouped_topics.items():
            cleaned = []
            for t in topics_list:
                words = t.split()
                if (len(words) >= 2 and 
                    not junk_pattern.search(t) and 
                    t not in cleaned):
                    cleaned.append(t)
                elif t in flat_defaults and t not in cleaned:
                    cleaned.append(t)
            cleaned_grouped[section] = cleaned
        save_topics(data_dir, cleaned_grouped)
    else:
        # Legacy list cleanup
        cleaned = []
        for t in grouped_topics:
            words = t.split()
            if (len(words) >= 2 and 
                not junk_pattern.search(t) and 
                t not in cleaned):
                cleaned.append(t)
            elif t in flat_defaults and t not in cleaned:
                cleaned.append(t)
        save_topics(data_dir, cleaned)


def get_trends_data(
    data_dir: str | Path,
    embedding_model: str = "all-MiniLM-L6-v2",
    num_weeks: int = 12,
    baseline_weeks: int = 8,
) -> dict:
    """Analyze paper publication frequencies and velocities for tracked topics.
    
    Identifies topics showing significant publication spikes compared to a baseline.
    """
    # 1. Load topics
    grouped_topics = load_topics(data_dir)
    topics = []
    topic_to_section = {}
    
    if isinstance(grouped_topics, dict):
        for sec, sec_topics in grouped_topics.items():
            for t in sec_topics:
                topics.append(t)
                topic_to_section[t] = sec
    else:
        topics = grouped_topics
        for t in topics:
            topic_to_section[t] = "ml_methods"

    if not topics:
        return {}

    # 2. Load papers from database
    db = PaperDatabase(Path(data_dir) / "papers.db")
    papers_with_emb = db.get_papers_with_embeddings()
    if not papers_with_emb:
        return {}

    # Filter to papers within the timeframe (plus a small buffer)
    now = datetime.utcnow()
    total_days = (num_weeks + 2) * 7
    cutoff_date = now - timedelta(days=total_days)

    recent_papers = []
    for paper, emb in papers_with_emb:
        try:
            pub_date = datetime.fromisoformat(paper["published"].replace("Z", "+00:00")).replace(tzinfo=None)
            if pub_date >= cutoff_date:
                recent_papers.append((paper, emb, pub_date))
        except Exception:
            continue

    if not recent_papers:
        return {}

    # 3. Define weekly boundaries (recent to oldest)
    intervals = []
    for i in range(num_weeks):
        start = now - timedelta(days=(i + 1) * 7)
        end = now - timedelta(days=i * 7)
        intervals.append((start, end))

    # 4. Embed topics
    model = get_model(embedding_model)
    topic_embeddings = model.encode(topics, normalize_embeddings=True)
    paper_embs = np.stack([emb for _, emb, _ in recent_papers])

    # 5. Populate the grid of counts
    matching_grid: list[list[list[dict]]] = [[[] for _ in range(num_weeks)] for _ in range(len(topics))]

    for t_idx, topic in enumerate(topics):
        topic_emb = topic_embeddings[t_idx]
        similarities = np.dot(paper_embs, topic_emb)
        
        for p_idx, (paper, _, pub_date) in enumerate(recent_papers):
            score = similarities[p_idx]
            if score >= 0.33:  # Relevance threshold for match
                # Determine which week this falls into
                for w_idx, (start, end) in enumerate(intervals):
                    if start <= pub_date < end:
                        matching_grid[t_idx][w_idx].append(paper)
                        break

    # 6. Build trend metrics for each topic
    trends_by_topic = []
    for t_idx, topic in enumerate(topics):
        # Counts ordered from current week (index 0) to oldest
        counts = [len(matching_grid[t_idx][w]) for w in range(num_weeks)]
        
        # Chronological order for plotting (oldest to current)
        sparkline_counts = list(reversed(counts))
        current_count = counts[0]
        
        # Baseline analysis on preceding weeks
        baseline_slice = counts[1:1 + baseline_weeks]
        if baseline_slice:
            baseline_mean = float(np.mean(baseline_slice))
            baseline_std = float(np.std(baseline_slice))
        else:
            baseline_mean = 0.0
            baseline_std = 0.0

        # Spike detection: current week is significantly higher than historical std dev
        threshold = max(3.0, baseline_mean + 2.0 * (baseline_std if baseline_std > 0 else 0.5))
        is_spike = current_count >= threshold
        
        trends_by_topic.append({
            "topic": topic,
            "section": topic_to_section.get(topic, "ml_methods"),
            "counts": counts,
            "sparkline": sparkline_counts,
            "current_count": current_count,
            "baseline_mean": round(baseline_mean, 2),
            "is_spike": is_spike,
            "spike_threshold": round(threshold, 2),
            "recent_papers": [
                {
                    "arxiv_id": p["arxiv_id"],
                    "title": p["title"],
                    "authors": p["authors"] if isinstance(p["authors"], list) else json.loads(p["authors"]),
                    "published": p["published"]
                }
                for p in matching_grid[t_idx][0][:3]
            ]
        })

    # Chronological week labels for UI headers
    week_labels = []
    for start, end in intervals:
        week_labels.append(end.strftime("%d %b"))
    week_labels = list(reversed(week_labels))

    return {
        "topics": trends_by_topic,
        "week_labels": week_labels,
        "num_weeks": num_weeks,
    }

