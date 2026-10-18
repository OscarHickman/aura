"""Git and Overleaf Literature Sync for AURA.

Generates structured BibTeX bibliographies and LaTeX literature synthesis matrices
and pushes them to GitHub, GitLab, or Overleaf Git bridges via API or local git.
"""

import base64
import logging
import os
from typing import Any, Dict, List, Optional
import requests

from .latex_export import generate_cite_key, paper_to_bibtex_entry, generate_latex_chapter

logger = logging.getLogger(__name__)


class GitLiteratureSync:
    """Synchronises literature bibliographies and LaTeX matrices to remote Git repositories."""

    def __init__(
        self,
        github_token: Optional[str] = None,
        github_repo: Optional[str] = None,
        branch: str = "main",
        bib_filename: str = "aura-reading-list.bib",
        tex_filename: str = "aura-literature-matrix.tex",
    ):
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "").strip()
        self.github_repo = github_repo or os.environ.get("GITHUB_LITERATURE_REPO", "").strip()
        self.branch = branch
        self.bib_filename = bib_filename
        self.tex_filename = tex_filename

    @property
    def is_configured(self) -> bool:
        return bool(self.github_token and self.github_repo and "/" in self.github_repo)

    def _github_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AURA-Research-Assistant/1.7.0",
        }

    def _get_file_sha(self, path: str) -> Optional[str]:
        """Get the current commit SHA of a file in GitHub to allow updates."""
        url = f"https://api.github.com/repos/{self.github_repo}/contents/{path}?ref={self.branch}"
        try:
            resp = requests.get(url, headers=self._github_headers(), timeout=10)
            if resp.status_code == 200:
                return resp.json().get("sha")
        except Exception as e:
            logger.warning(f"Error checking file sha for {path}: {e}")
        return None

    def push_file(self, path: str, content: str, commit_message: str) -> Dict[str, Any]:
        """Create or update a file in a GitHub repository."""
        if not self.is_configured:
            return {"ok": False, "error": "GitHub token or repository not configured."}

        url = f"https://api.github.com/repos/{self.github_repo}/contents/{path}"
        sha = self._get_file_sha(path)
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")

        payload: Dict[str, Any] = {
            "message": commit_message,
            "content": encoded_content,
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha

        try:
            resp = requests.put(url, headers=self._github_headers(), json=payload, timeout=15)
            if resp.status_code in (200, 201):
                return {
                    "ok": True,
                    "path": path,
                    "html_url": resp.json().get("content", {}).get("html_url"),
                    "commit_sha": resp.json().get("commit", {}).get("sha"),
                }
            return {
                "ok": False,
                "status_code": resp.status_code,
                "error": resp.text[:300],
            }
        except Exception as e:
            logger.error(f"Failed to push {path} to GitHub: {e}")
            return {"ok": False, "error": str(e)}

    def sync_literature(
        self, papers: List[Dict[str, Any]], commit_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate BibTeX and LaTeX chapter from papers and push to repository."""
        if not self.is_configured:
            return {"ok": False, "error": "Git sync credentials not configured."}

        if not papers:
            return {"ok": False, "error": "No papers provided for literature sync."}

        # 1. Generate BibTeX
        existing_keys: set[str] = set()
        bib_entries = []
        for p in papers:
            k = generate_cite_key(p, existing_keys)
            existing_keys.add(k)
            bib_entries.append(paper_to_bibtex_entry(p, k))
        bibtex_content = "\n\n".join(bib_entries)

        # 2. Generate LaTeX matrix
        collection_meta = {
            "name": "Cosmological Literature Synthesis",
            "description": f"Synchronised from AURA reading list containing {len(papers)} selected papers.",
        }
        tex_content = generate_latex_chapter(
            collection=collection_meta,
            papers=papers,
            notes_by_paper={},
        )

        msg = commit_message or f"chore: update literature synthesis ({len(papers)} papers via AURA)"

        res_bib = self.push_file(self.bib_filename, bibtex_content, f"{msg} - BibTeX")
        res_tex = self.push_file(self.tex_filename, tex_content, f"{msg} - LaTeX Matrix")

        return {
            "ok": res_bib.get("ok", False) and res_tex.get("ok", False),
            "bibtex": res_bib,
            "latex": res_tex,
            "papers_synced": len(papers),
        }
