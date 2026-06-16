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

DEFAULT_TOPICS = [
    "galaxy clustering",
    "large scale structure",
    "galaxy correlations function",
    "Machine learning",
    "simulation based inference",
    "emulators",
    "pure ai inference"
]


def load_topics(data_dir: str | Path) -> list[str]:
    """Load research topics to track."""
    path = Path(data_dir) / "research_topics.json"
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_TOPICS, indent=2))
        return DEFAULT_TOPICS
    try:
        return json.loads(path.read_text())
    except Exception as e:
        logger.error(f"Failed to load topics: {e}")
        return DEFAULT_TOPICS


def save_topics(data_dir: str | Path, topics: list[str]):
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
                
    return "No AI provider available to generate trends."


def generate_monthly_trends(data_dir: str | Path, embedding_model: str = "all-MiniLM-L6-v2") -> dict[str, str]:
    """Analyze papers from the last 30 days and generate summaries for topics.
    
    Returns a dict mapping topic -> summary text.
    """
    topics = load_topics(data_dir)
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
    if new_topics_str and new_topics_str.strip().upper() != "NONE":
        suggested = [t.strip().lower() for t in new_topics_str.split(",") if t.strip()]
        valid_new = [t for t in suggested if len(t) > 3 and t not in [existing.lower() for existing in topics]]
        if valid_new:
            logger.info(f"Discovered new dynamic topics: {valid_new}")
            topics.extend(valid_new)
            save_topics(data_dir, topics)
            
    return trends
