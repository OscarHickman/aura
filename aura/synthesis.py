"""Comparative Synthesis Matrix Engine for Multi-Paper Literature Analysis.

Performs structured side-by-side analysis across 2 to 10 selected cosmology/astrophysics papers,
comparing observational probes, target tracers, methodologies (SBI, HOD, SAMs),
parameter constraints (sigma_8, S_8, H_0), code availability, and key findings.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .latex_export import generate_cite_key
from .llm import execute_llm

logger = logging.getLogger(__name__)


class ComparativeSynthesisEngine:
    """Orchestrates structured LLM-driven comparative analysis across research papers."""

    def __init__(self, llm_runner: Optional[Any] = None):
        self.llm_runner = llm_runner or execute_llm

    def generate_matrix(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate a comparative synthesis matrix and narrative across selected papers."""
        if not papers or len(papers) < 2:
            return {
                "ok": False,
                "error": "At least 2 papers are required for a comparative synthesis matrix.",
            }

        if len(papers) > 10:
            papers = papers[:10]

        # Prepare paper dossiers
        dossiers = []
        for p in papers:
            cite_key = generate_cite_key(p, set())
            summary = p.get("summary") or "No pre-computed summary."
            dossiers.append(
                f"Paper [{cite_key}] (arXiv:{p.get('arxiv_id')}):\n"
                f"Title: {p.get('title')}\n"
                f"Authors: {', '.join(p.get('authors', [])[:4]) if isinstance(p.get('authors'), list) else p.get('authors')}\n"
                f"Published: {p.get('published')}\n"
                f"Abstract: {p.get('abstract')}\n"
                f"Summary: {summary}\n"
            )

        prompt = (
            "You are an expert cosmologist and senior astrophysicist pair-programming with a PhD researcher.\n"
            "Analyse the following cosmology/astrophysics papers and produce a structured comparative matrix and an executive synthesis narrative.\n\n"
            "PAPERS:\n"
            f"{'---'.join(dossiers)}\n\n"
            "REQUIREMENTS:\n"
            "Return a strictly valid JSON object with exactly two keys: 'matrix' and 'synthesis_markdown'.\n\n"
            "1. 'matrix': A JSON array of objects (one per paper) with these exact fields:\n"
            "   - 'arxiv_id': string\n"
            "   - 'cite_key': string\n"
            "   - 'probe_dataset': Observational survey or simulation suite (e.g. DESI DR1, BOSS, CAMELS, FLAMINGO, HST, Planck)\n"
            "   - 'tracer_sample': Galaxy tracer or halo sample (e.g. ELG, LRG, dark matter halos, subhalos)\n"
            "   - 'methodology': Primary statistical or modelling framework (e.g. SBI / Neural Posterior, HOD, SHAM, Field-Level, Merger Clocks)\n"
            "   - 'parameter_constraints': Key parameter bounds mentioned (e.g. sigma_8, S_8, H_0, f_sub, or 'N/A' if methodology-only)\n"
            "   - 'code_availability': Software, code repository, or simulation package used\n"
            "   - 'key_takeaway': 1-2 sentence core conclusion\n\n"
            "2. 'synthesis_markdown': A comprehensive GitHub Flavored Markdown narrative structured into:\n"
            "   - ### Executive Synthesis: Core agreements and complementary aspects across the papers\n"
            "   - ### Methodological Divergences: How assumptions, clock models, or likelihood-free estimators differ\n"
            "   - ### Cosmological Implications: Tensions or agreements on sigma_8 / S_8 / H_0 / modified gravity\n"
            "   - ### PhD Strategic Takeaways: Specific implications for small-scale clustering, SBI pipelines, and mock calibration\n\n"
            "Respond ONLY with the JSON object, wrapped in ```json ... ``` code fences."
        )

        try:
            raw_response = self.llm_runner(prompt, max_tokens=2500)
            if not raw_response:
                raise ValueError("LLM returned empty response")
            json_text = raw_response.strip()
            # Clean markdown code fences if present
            if "```json" in json_text:
                json_text = json_text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in json_text:
                json_text = json_text.split("```", 1)[1].split("```", 1)[0].strip()

            parsed = json.loads(json_text)
            return {
                "ok": True,
                "matrix": parsed.get("matrix", []),
                "synthesis_markdown": parsed.get("synthesis_markdown", ""),
                "papers_count": len(papers),
            }
        except Exception as e:
            logger.error(f"Comparative synthesis generation failed: {e}")
            # Fallback deterministic structured matrix
            fallback_matrix = []
            for p in papers:
                fallback_matrix.append({
                    "arxiv_id": p.get("arxiv_id", ""),
                    "cite_key": generate_cite_key(p, set()),
                    "probe_dataset": "Cosmological Survey / Simulation",
                    "tracer_sample": "Galaxies / Halos",
                    "methodology": "Galaxy Clustering / Likelihood Inference",
                    "parameter_constraints": "Reported in manuscript",
                    "code_availability": p.get("github_repo") or "Refer to manuscript",
                    "key_takeaway": (p.get("abstract") or "")[:140] + "...",
                })
            fallback_markdown = (
                "### Comparative Summary\n\n"
                f"Comparative analysis across {len(papers)} selected papers. "
                "See the structured parameter matrix above for individual survey probes, methodologies, and code availability."
            )
            return {
                "ok": True,
                "matrix": fallback_matrix,
                "synthesis_markdown": fallback_markdown,
                "papers_count": len(papers),
                "fallback": True,
            }
