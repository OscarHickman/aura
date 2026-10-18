"""Two-way Zotero synchronisation for AURA reading lists and paper collections.

Supports:
- Pushing reading list and top-rated papers with AURA summaries and tags to Zotero collections.
- Attaching AI summary notes to preprints/articles in Zotero.
- Ingesting existing Zotero library items to bootstrap and refine user preference models.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional
import requests

from .latex_export import generate_cite_key

logger = logging.getLogger(__name__)

ZOTERO_API_BASE = "https://api.zotero.org"
ZOTERO_API_VERSION = "3"


class ZoteroClient:
    """Client for bidirectional integration with the Zotero Web API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        user_id: Optional[str] = None,
        library_type: str = "user",
        collection_key: Optional[str] = None,
        timeout: int = 15,
    ):
        self.api_key = api_key or os.environ.get("ZOTERO_API_KEY", "").strip()
        self.user_id = user_id or os.environ.get("ZOTERO_USER_ID", "").strip()
        self.library_type = library_type or os.environ.get("ZOTERO_LIBRARY_TYPE", "user").strip()
        self.collection_key = collection_key or os.environ.get("ZOTERO_COLLECTION_KEY", "").strip()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.user_id)

    @property
    def base_path(self) -> str:
        prefix = "groups" if self.library_type == "group" else "users"
        return f"{ZOTERO_API_BASE}/{prefix}/{self.user_id}"

    def _headers(self) -> Dict[str, str]:
        return {
            "Zotero-API-Key": self.api_key,
            "Zotero-API-Version": ZOTERO_API_VERSION,
            "Content-Type": "application/json",
            "User-Agent": "AURA-Research-Assistant/1.7.0",
        }

    def test_connection(self) -> Dict[str, Any]:
        """Test API connectivity and key permissions."""
        if not self.is_configured:
            return {"ok": False, "error": "Zotero API key or User ID not configured."}

        url = f"{self.base_path}/collections"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=self.timeout)
            if resp.status_code == 200:
                collections = resp.json()
                return {
                    "ok": True,
                    "library_type": self.library_type,
                    "user_id": self.user_id,
                    "collections_count": len(collections),
                    "collections": [
                        {"key": c["key"], "name": c["data"]["name"]}
                        for c in collections[:10]
                    ],
                }
            return {
                "ok": False,
                "status_code": resp.status_code,
                "error": resp.text[:200],
            }
        except Exception as e:
            logger.error(f"Zotero connection check failed: {e}")
            return {"ok": False, "error": str(e)}

    def format_creators(self, authors: Any) -> List[Dict[str, str]]:
        """Parse author list into Zotero creator structures."""
        if not authors:
            return [{"creatorType": "author", "name": "Unknown Author"}]

        if isinstance(authors, str):
            authors_list = [a.strip() for a in authors.split(",") if a.strip()]
        elif isinstance(authors, list):
            authors_list = authors
        else:
            authors_list = [str(authors)]

        creators = []
        for author in authors_list:
            if isinstance(author, dict):
                first = author.get("firstName") or author.get("first_name", "")
                last = author.get("lastName") or author.get("last_name") or author.get("name", "Unknown")
                creators.append({"creatorType": "author", "firstName": first, "lastName": last})
            else:
                author_str = str(author).strip()
                if "," in author_str:
                    parts = author_str.split(",", 1)
                    creators.append({
                        "creatorType": "author",
                        "lastName": parts[0].strip(),
                        "firstName": parts[1].strip(),
                    })
                else:
                    parts = author_str.split()
                    if len(parts) > 1:
                        creators.append({
                            "creatorType": "author",
                            "firstName": " ".join(parts[:-1]),
                            "lastName": parts[-1],
                        })
                    else:
                        creators.append({"creatorType": "author", "name": author_str})
        return creators or [{"creatorType": "author", "name": "Unknown Author"}]

    def export_paper(
        self, paper: Dict[str, Any], collection_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Export a single paper and attach its AURA summary note to Zotero."""
        if not self.is_configured:
            return {"ok": False, "error": "Zotero is not configured"}

        target_coll = collection_key or self.collection_key
        arxiv_id = paper.get("arxiv_id", "")
        cite_key = generate_cite_key(paper, set())

        tags = []
        for t in paper.get("tags", []):
            if isinstance(t, str):
                tags.append({"tag": t})
            elif isinstance(t, dict) and "tag" in t:
                tags.append({"tag": t["tag"]})

        extra_lines = [
            "archive: arXiv",
            f"archive_id: arXiv:{arxiv_id}",
            f"citation key: {cite_key}",
        ]
        if paper.get("score"):
            extra_lines.append(f"AURA Interest Score: {paper['score']:.2f}")

        payload = [
            {
                "itemType": "preprint",
                "title": paper.get("title", "Untitled Research Paper"),
                "creators": self.format_creators(paper.get("authors")),
                "abstractNote": paper.get("abstract", ""),
                "repository": "arXiv",
                "archiveID": f"arXiv:{arxiv_id}",
                "url": paper.get("url") or f"https://arxiv.org/abs/{arxiv_id}",
                "date": str(paper.get("published", ""))[:10],
                "extra": "\n".join(extra_lines),
                "tags": tags,
                "collections": [target_coll] if target_coll else [],
            }
        ]

        url = f"{self.base_path}/items"
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
            if resp.status_code not in (200, 201):
                return {"ok": False, "status_code": resp.status_code, "error": resp.text[:300]}

            res_json = resp.json()
            successes = res_json.get("successful", {})
            if not successes:
                return {"ok": False, "error": "No item was saved", "details": res_json}

            created_key = next(iter(successes.values()))["key"]

            # Attach summary note if available
            summary = paper.get("summary")
            if summary:
                note_html = (
                    f"<h2>AURA Research Summary</h2>"
                    f"<p><strong>ArXiv:</strong> {arxiv_id} | <strong>Cite Key:</strong> {cite_key}</p>"
                    f"<div>{summary.replace(chr(10), '<br/>')}</div>"
                )
                note_payload = [
                    {
                        "itemType": "note",
                        "parentItem": created_key,
                        "note": note_html,
                        "tags": [{"tag": "aura-summary"}],
                    }
                ]
                requests.post(url, headers=self._headers(), json=note_payload, timeout=self.timeout)

            return {"ok": True, "item_key": created_key, "arxiv_id": arxiv_id}
        except Exception as e:
            logger.error(f"Failed to export paper {arxiv_id} to Zotero: {e}")
            return {"ok": False, "error": str(e)}

    def import_library(self, limit: int = 50) -> Dict[str, Any]:
        """Import items from Zotero to extract arXiv IDs and bibliographic metadata."""
        if not self.is_configured:
            return {"ok": False, "error": "Zotero is not configured"}

        url = f"{self.base_path}/items"
        params: Dict[str, str] = {
            "limit": str(limit),
            "sort": "dateModified",
            "direction": "desc",
            "itemType": "-note || -attachment",
        }
        if self.collection_key:
            url = f"{self.base_path}/collections/{self.collection_key}/items"

        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=self.timeout)
            if resp.status_code != 200:
                return {"ok": False, "status_code": resp.status_code, "error": resp.text[:200]}

            items = resp.json()
            extracted_papers = []

            for item in items:
                data = item.get("data", {})
                title = data.get("title", "")
                url_str = data.get("url", "")
                archive_id = data.get("archiveID", "")
                extra = data.get("extra", "")

                arxiv_id = None
                # Check archiveID field
                match = re.search(r"\b(\d{4}\.\d{4,5}(?:v\d+)?)\b", archive_id)
                if match:
                    arxiv_id = match.group(1)
                # Check url
                if not arxiv_id and url_str:
                    match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", url_str)
                    if match:
                        arxiv_id = match.group(1)
                # Check extra field
                if not arxiv_id and extra:
                    match = re.search(r"\b(\d{4}\.\d{4,5}(?:v\d+)?)\b", extra)
                    if match:
                        arxiv_id = match.group(1)

                if arxiv_id:
                    extracted_papers.append({
                        "arxiv_id": arxiv_id,
                        "title": title,
                        "zotero_key": item.get("key"),
                        "date": data.get("date", ""),
                    })

            return {"ok": True, "total_found": len(extracted_papers), "papers": extracted_papers}
        except Exception as e:
            logger.error(f"Failed to import items from Zotero: {e}")
            return {"ok": False, "error": str(e)}
