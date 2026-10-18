"""Audio Briefing and Podcast Mode Engine for AURA.

Generates broadcast-quality spoken audio research briefings from top paper recommendations
and weekly research syntheses using neural speech synthesis (edge-tts British voices).
"""

import asyncio
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from aura.timeutil import utcnow

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "en-GB-SoniaNeural"  # Professional British English voice


class AudioBriefingEngine:
    """Orchestrates script generation and audio synthesis for daily/weekly briefings."""

    def __init__(self, data_dir: Optional[Path] = None, voice: str = DEFAULT_VOICE):
        self.data_dir = Path(data_dir or Path(__file__).resolve().parent.parent / "data")
        self.audio_dir = self.data_dir / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.voice = voice

    def generate_briefing_script(
        self,
        papers: List[Dict[str, Any]],
        briefing_type: str = "daily",
        date_str: Optional[str] = None,
    ) -> str:
        """Create a conversational, natural spoken script for the audio briefing."""
        today = date_str or utcnow().strftime("%A, %d %B %Y")
        count = len(papers)

        if not papers:
            return (
                f"Welcome to your AURA research audio briefing for {today}. "
                "There are currently no new unread recommendations matching your threshold today. "
                "Enjoy your research day!"
            )

        intro = (
            f"Welcome to your AURA research briefing for {today}. "
            f"Today, we are highlighting {count} essential new papers tailored to your cosmology portfolio.\n\n"
        )

        items = []
        for i, paper in enumerate(papers, 1):
            title = paper.get("title", "Untitled paper")
            # Clean title
            title_clean = re.sub(r"[\$\\]", "", title)

            authors = paper.get("authors") or []
            if isinstance(authors, str):
                first_author = authors.split(",")[0].strip()
            elif isinstance(authors, list) and authors:
                first_author = str(authors[0]).strip()
            else:
                first_author = "Unknown author"

            score = paper.get("score")
            score_text = f" with a match score of {int(score * 100)} percent" if score else ""

            summary = paper.get("summary") or paper.get("abstract") or ""
            # Truncate summary to ~2-3 conversational sentences
            summary_clean = re.sub(r"[\$\\]", "", summary).replace("\n", " ").strip()
            sentences = [s.strip() for s in re.split(r"(?<=[.!?]) +", summary_clean) if s.strip()]
            spoken_summary = " ".join(sentences[:3])

            item_text = (
                f"Paper number {i}: {title_clean}, led by {first_author}{score_text}. "
                f"{spoken_summary}\n\n"
            )
            items.append(item_text)

        outro = (
            "That concludes your AURA audio briefing for today. "
            "All papers, notes, and citations are available in your reading list. "
            "Have a productive session."
        )

        return intro + "".join(items) + outro

    async def _synthesise_async(self, text: str, output_path: Path) -> bool:
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, voice=self.voice)
            await communicate.save(str(output_path))
            return True
        except Exception as e:
            logger.error(f"Async edge-tts synthesis failed: {e}")
            return False

    def synthesise(self, script: str, output_path: Path) -> bool:
        """Synthesise text script into an MP3 file."""
        try:
            return asyncio.run(self._synthesise_async(script, output_path))
        except Exception as e:
            logger.error(f"TTS synthesis execution error: {e}")
            return False

    def get_or_create_daily_briefing(
        self, papers: List[Dict[str, Any]], user_id: int = 1, force: bool = False
    ) -> Dict[str, Any]:
        """Fetch existing daily briefing or generate a new one."""
        today_date = utcnow().strftime("%Y-%m-%d")
        filename = f"briefing_{today_date}_user_{user_id}.mp3"
        meta_filename = f"briefing_{today_date}_user_{user_id}.json"
        audio_path = self.audio_dir / filename
        meta_path = self.audio_dir / meta_filename

        if audio_path.exists() and meta_path.exists() and not force:
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read existing audio metadata: {e}")

        top_papers = papers[:5] if papers else []
        script = self.generate_briefing_script(top_papers)
        success = self.synthesise(script, audio_path)

        duration_est = max(10, len(script.split()) // 2)  # Approx 130 words/minute
        metadata = {
            "ok": success,
            "filename": filename,
            "audio_url": f"/api/audio/stream/{filename}",
            "title": f"AURA Daily Briefing - {utcnow().strftime('%d %b %Y')}",
            "date": today_date,
            "user_id": user_id,
            "paper_count": len(top_papers),
            "duration_seconds": duration_est,
            "script": script,
            "created_at": utcnow().isoformat(),
            "papers": [
                {
                    "arxiv_id": p.get("arxiv_id"),
                    "title": p.get("title"),
                    "score": p.get("score"),
                }
                for p in top_papers
            ],
        }

        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save audio metadata: {e}")

        return metadata
