"""Fetch papers from arXiv API for configured astrophysics categories."""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Any
from xml.etree import ElementTree

import requests

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"

# arXiv astrophysics subcategories
ASTRO_CATEGORIES = {
    "astro-ph.CO": "Cosmology and Nongalactic Astrophysics",
    "astro-ph.EP": "Earth and Planetary Astrophysics",
    "astro-ph.GA": "Astrophysics of Galaxies",
    "astro-ph.HE": "High Energy Astrophysical Phenomena",
    "astro-ph.IM": "Instrumentation and Methods for Astrophysics",
    "astro-ph.SR": "Solar and Stellar Astrophysics",
    "gr-qc": "General Relativity and Quantum Cosmology",
    "hep-ph": "High Energy Physics - Phenomenology",
    "hep-th": "High Energy Physics - Theory",
}

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def fetch_papers(
    categories: list[str],
    max_results: int = 200,
    days_back: int = 1,
) -> list[dict]:
    """Fetch recent papers from arXiv for given categories.

    Args:
        categories: List of arXiv category strings (e.g. ["astro-ph.CO", "astro-ph.GA"])
        max_results: Maximum number of papers to fetch per query batch.
        days_back: How many days back to search.

    Returns:
        List of paper dicts with keys: arxiv_id, title, abstract, authors,
        categories, published, url, pdf_url
    """
    papers = []
    seen_ids = set()

    # Build category query
    cat_query = " OR ".join(f"cat:{cat}" for cat in categories)

    # Use submittedDate range for recent papers
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days_back)
    date_from = start_date.strftime("%Y%m%d")
    date_to = end_date.strftime("%Y%m%d")

    start = 0
    batch_size = min(max_results, 100)

    while start < max_results:
        query = f"({cat_query}) AND submittedDate:[{date_from}0000 TO {date_to}2359]"

        params: dict[str, Any] = {
            "search_query": query,
            "start": start,
            "max_results": batch_size,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        logger.info(f"Fetching arXiv papers: start={start}, batch_size={batch_size}")

        try:
            resp = requests.get(ARXIV_API_URL, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"arXiv API request failed: {e}")
            break

        root = ElementTree.fromstring(resp.text)
        entries = root.findall(f"{ATOM_NS}entry")

        if not entries:
            break

        for entry in entries:
            paper = _parse_entry(entry)
            if paper and paper["arxiv_id"] not in seen_ids:
                seen_ids.add(paper["arxiv_id"])
                papers.append(paper)

        start += batch_size

        # Be polite to arXiv API
        if start < max_results:
            time.sleep(3)

    logger.info(f"Fetched {len(papers)} papers total")
    return papers


def fetch_papers_simple(
    categories: list[str],
    max_results: int = 200,
) -> list[dict]:
    """Simpler fetch that just gets the most recent papers without date filtering.

    This is more reliable as arXiv's date filtering can be inconsistent.
    """
    papers = []
    seen_ids = set()

    cat_query = " OR ".join(f"cat:{cat}" for cat in categories)

    start = 0
    batch_size = min(max_results, 100)

    while start < max_results:
        params: dict[str, Any] = {
            "search_query": cat_query,
            "start": start,
            "max_results": batch_size,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        logger.info(f"Fetching arXiv papers: start={start}, batch_size={batch_size}")

        try:
            resp = requests.get(ARXIV_API_URL, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"arXiv API request failed: {e}")
            break

        root = ElementTree.fromstring(resp.text)
        entries = root.findall(f"{ATOM_NS}entry")

        if not entries:
            break

        for entry in entries:
            paper = _parse_entry(entry)
            if paper and paper["arxiv_id"] not in seen_ids:
                seen_ids.add(paper["arxiv_id"])
                papers.append(paper)

        start += batch_size

        if start < max_results:
            time.sleep(3)

    logger.info(f"Fetched {len(papers)} papers total")
    return papers


def _parse_entry(entry: ElementTree.Element) -> Optional[dict]:
    """Parse a single arXiv Atom entry into a paper dict."""
    try:
        id_elem = entry.find(f"{ATOM_NS}id")
        if id_elem is None or not id_elem.text:
            return None
        arxiv_id_raw = id_elem.text.strip()
        # Extract just the ID part: "http://arxiv.org/abs/2401.12345v1" -> "2401.12345"
        arxiv_id = arxiv_id_raw.split("/abs/")[-1]
        # Remove version suffix
        if "v" in arxiv_id:
            arxiv_id = arxiv_id.rsplit("v", 1)[0]

        title_elem = entry.find(f"{ATOM_NS}title")
        title = title_elem.text.strip() if (title_elem is not None and title_elem.text) else ""
        title = " ".join(title.split())  # Normalize whitespace

        summary_elem = entry.find(f"{ATOM_NS}summary")
        abstract = summary_elem.text.strip() if (summary_elem is not None and summary_elem.text) else ""
        abstract = " ".join(abstract.split())

        authors = []
        for author_elem in entry.findall(f"{ATOM_NS}author"):
            name_elem = author_elem.find(f"{ATOM_NS}name")
            if name_elem is not None and name_elem.text:
                name = name_elem.text.strip()
                authors.append(name)

        categories = []
        for cat_elem in entry.findall(f"{ARXIV_NS}primary_category"):
            categories.append(cat_elem.get("term"))
        for cat_elem in entry.findall(f"{ATOM_NS}category"):
            term = cat_elem.get("term")
            if term not in categories:
                categories.append(term)

        pub_elem = entry.find(f"{ATOM_NS}published")
        published = pub_elem.text.strip() if (pub_elem is not None and pub_elem.text) else ""

        # Get URLs
        url = arxiv_id_raw
        pdf_url = ""
        for link in entry.findall(f"{ATOM_NS}link"):
            if link.get("title") == "pdf":
                pdf_url = link.get("href", "")

        return {
            "arxiv_id": arxiv_id,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "categories": categories,
            "published": published,
            "url": url,
            "pdf_url": pdf_url,
        }
    except (AttributeError, IndexError) as e:
        logger.warning(f"Failed to parse arXiv entry: {e}")
        return None
