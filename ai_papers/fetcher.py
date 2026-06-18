"""Paper ingestion framework with multiple source support."""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Any, Protocol
from xml.etree import ElementTree

import requests

import re

logger = logging.getLogger(__name__)


def detect_code_and_data(text: str) -> tuple[int, int]:
    """Scan text for code and data repository URLs. Returns (has_code, has_data)."""
    if not text:
        return 0, 0
        
    code_patterns = [
        r"github\.com/[\w\-\.]+/\w+",
        r"gitlab\.com/[\w\-\.]+/\w+",
        r"bitbucket\.org/[\w\-\.]+/\w+",
    ]
    
    data_patterns = [
        r"zenodo\.org/record/\d+",
        r"doi\.org/10\.5281/zenodo\.\d+",
        r"figshare\.com/articles?/[\w\-\.]+/\d+",
        r"cds\.cern\.ch/record/\d+",
        r"datadryad\.org/stash/dataset/doi:\d+\.\d+/[\w\-\.]+",
        r"huggingface\.co/datasets/[\w\-\.]+/\w+",
    ]
    
    has_code = 1 if any(re.search(p, text, re.IGNORECASE) for p in code_patterns) else 0
    has_data = 1 if any(re.search(p, text, re.IGNORECASE) for p in data_patterns) else 0
    
    return has_code, has_data


class PaperSource(Protocol):
    """Protocol defining the interface for paper sources."""
    
    def fetch(self, categories: list[str], max_results: int = 200, days_back: int = 1) -> list[dict]:
        """Fetch recent papers."""
        ...
        
    def fetch_simple(self, categories: list[str], max_results: int = 200) -> list[dict]:
        """Fetch papers without strict date filtering."""
        ...


class ArxivSource:
    """Fetches papers from the arXiv API."""
    
    ARXIV_API_URL = "http://export.arxiv.org/api/query"
    ATOM_NS = "{http://www.w3.org/2005/Atom}"
    ARXIV_NS = "{http://arxiv.org/schemas/atom}"

    def fetch(
        self,
        categories: list[str],
        max_results: int = 200,
        days_back: int = 1,
    ) -> list[dict]:
        """Fetch recent papers from arXiv for given categories."""
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
                resp = requests.get(self.ARXIV_API_URL, params=params, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.error(f"arXiv API request failed: {e}")
                break

            root = ElementTree.fromstring(resp.text)
            entries = root.findall(f"{self.ATOM_NS}entry")

            if not entries:
                break

            for entry in entries:
                paper = self._parse_entry(entry)
                if paper and paper["arxiv_id"] not in seen_ids:
                    seen_ids.add(paper["arxiv_id"])
                    papers.append(paper)

            start += batch_size

            # Be polite to arXiv API
            if start < max_results:
                time.sleep(3)

        logger.info(f"Fetched {len(papers)} papers total from arXiv")
        return papers

    def fetch_simple(
        self,
        categories: list[str],
        max_results: int = 200,
    ) -> list[dict]:
        """Simpler fetch that just gets the most recent papers without date filtering."""
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
                resp = requests.get(self.ARXIV_API_URL, params=params, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.error(f"arXiv API request failed: {e}")
                break

            root = ElementTree.fromstring(resp.text)
            entries = root.findall(f"{self.ATOM_NS}entry")

            if not entries:
                break

            for entry in entries:
                paper = self._parse_entry(entry)
                if paper and paper["arxiv_id"] not in seen_ids:
                    seen_ids.add(paper["arxiv_id"])
                    papers.append(paper)

            start += batch_size

            if start < max_results:
                time.sleep(3)

        logger.info(f"Fetched {len(papers)} papers total from arXiv")
        return papers

    def _parse_entry(self, entry: ElementTree.Element) -> Optional[dict]:
        """Parse a single arXiv Atom entry into a paper dict."""
        try:
            id_elem = entry.find(f"{self.ATOM_NS}id")
            if id_elem is None or not id_elem.text:
                return None
            arxiv_id_raw = id_elem.text.strip()
            # Extract just the ID part: "http://arxiv.org/abs/2401.12345v1" -> "2401.12345"
            arxiv_id = arxiv_id_raw.split("/abs/")[-1]
            # Remove version suffix
            if "v" in arxiv_id:
                arxiv_id = arxiv_id.rsplit("v", 1)[0]

            title_elem = entry.find(f"{self.ATOM_NS}title")
            title = title_elem.text.strip() if (title_elem is not None and title_elem.text) else ""
            title = " ".join(title.split())  # Normalize whitespace

            summary_elem = entry.find(f"{self.ATOM_NS}summary")
            abstract = summary_elem.text.strip() if (summary_elem is not None and summary_elem.text) else ""
            abstract = " ".join(abstract.split())

            authors = []
            for author_elem in entry.findall(f"{self.ATOM_NS}author"):
                name_elem = author_elem.find(f"{self.ATOM_NS}name")
                if name_elem is not None and name_elem.text:
                    name = name_elem.text.strip()
                    authors.append(name)

            categories = []
            for cat_elem in entry.findall(f"{self.ARXIV_NS}primary_category"):
                categories.append(cat_elem.get("term"))
            for cat_elem in entry.findall(f"{self.ATOM_NS}category"):
                term = cat_elem.get("term")
                if term not in categories:
                    categories.append(term)

            pub_elem = entry.find(f"{self.ATOM_NS}published")
            published = pub_elem.text.strip() if (pub_elem is not None and pub_elem.text) else ""

            # Get URLs
            url = arxiv_id_raw
            pdf_url = ""
            for link in entry.findall(f"{self.ATOM_NS}link"):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href", "")

            # Detect code/data
            has_code, has_data = detect_code_and_data(abstract)

            return {
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "categories": categories,
                "published": published,
                "url": url,
                "pdf_url": pdf_url,
                "source": "arxiv",
                "has_code": has_code,
                "has_data": has_data,
            }
        except (AttributeError, IndexError) as e:
            logger.warning(f"Failed to parse arXiv entry: {e}")
            return None


class SemanticScholarSource:
    """Fetches papers from the Semantic Scholar API."""

    S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

    def fetch(
        self,
        categories: list[str],
        max_results: int = 100,
        days_back: int = 1,
    ) -> list[dict]:
        """Fetch papers from Semantic Scholar using category keywords."""
        # Semantic Scholar doesn't have strict categories like arXiv,
        # so we search by keywords based on categories.
        papers = []
        seen_ids = set()

        # Map some common arXiv categories to keywords
        query_map = {
            "astro-ph.CO": "Cosmology",
            "astro-ph.GA": "Galaxies",
            "astro-ph.SR": "Stars",
            "astro-ph.EP": "Exoplanets",
            "astro-ph.HE": "High Energy Astrophysics",
            "astro-ph.IM": "Astrophysical Instrumentation",
            "cs.LG": "Machine Learning",
            "cs.AI": "Artificial Intelligence",
            "cs.CV": "Computer Vision",
            "cs.CL": "Natural Language Processing",
        }

        keywords = [query_map.get(cat, cat) for cat in categories]
        search_query = " | ".join(keywords)

        params: dict[str, str | int] = {
            "query": search_query,
            "limit": min(max_results, 100),
            "fields": "externalIds,title,abstract,authors,year,publicationDate,url,citationCount,s2FieldsOfStudy",
        }

        logger.info(f"Fetching Semantic Scholar papers: query='{search_query}'")

        try:
            resp = requests.get(self.S2_SEARCH_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            for entry in data.get("data", []):
                paper = self._parse_entry(entry)
                if paper and paper["arxiv_id"] not in seen_ids:
                    seen_ids.add(paper["arxiv_id"])
                    papers.append(paper)
                    
        except requests.RequestException as e:
            logger.error(f"Semantic Scholar API request failed: {e}")

        logger.info(f"Fetched {len(papers)} papers total from Semantic Scholar")
        return papers

    def fetch_simple(self, categories: list[str], max_results: int = 100) -> list[dict]:
        """Simple fetch for Semantic Scholar (same as fetch for now)."""
        return self.fetch(categories, max_results=max_results)

    def _parse_entry(self, entry: dict) -> Optional[dict]:
        """Parse a Semantic Scholar API entry into a paper dict."""
        try:
            # We prefer papers that have an arXiv ID for consistency, 
            # but can fall back to S2 paperId if needed.
            ext_ids = entry.get("externalIds", {})
            arxiv_id = ext_ids.get("ArXiv")
            
            if not arxiv_id:
                # Use S2 ID as a fallback if no arXiv ID
                # We prefix it to avoid collisions with arXiv IDs
                arxiv_id = f"s2:{entry['paperId']}"

            authors = [a["name"] for a in entry.get("authors", [])]
            
            # Map S2 fields of study back to a categories list
            categories = [f["category"] for f in entry.get("s2FieldsOfStudy", [])]
            if not categories:
                categories = ["Unknown"]

            # Format published date
            pub_date = entry.get("publicationDate")
            if not pub_date:
                year = entry.get("year")
                pub_date = f"{year}-01-01" if year else datetime.utcnow().isoformat()[:10]

            abstract = entry.get("abstract", "No Abstract")
            has_code, has_data = detect_code_and_data(abstract)

            return {
                "arxiv_id": arxiv_id,
                "title": entry.get("title", "No Title"),
                "abstract": abstract,
                "authors": authors,
                "categories": categories,
                "published": pub_date,
                "url": entry.get("url", ""),
                "pdf_url": "", # S2 doesn't always provide PDF direct link
                "source": "semanticscholar",
                "citation_count": entry.get("citationCount", 0),
                "has_code": has_code,
                "has_data": has_data,
            }
        except Exception as e:
            logger.warning(f"Failed to parse Semantic Scholar entry: {e}")
            return None


class BiorxivSource:
    """Fetches papers from the bioRxiv API."""

    BIORXIV_API_URL = "https://api.biorxiv.org/details/biorxiv"

    def fetch(
        self,
        categories: list[str],
        max_results: int = 50,
        days_back: int = 1,
    ) -> list[dict]:
        """Fetch papers from bioRxiv."""
        papers = []
        seen_dois = set()

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        
        date_from = start_date.strftime("%Y-%m-%d")
        date_to = end_date.strftime("%Y-%m-%d")

        # bioRxiv API is date-based: /details/biorxiv/YYYY-MM-DD/YYYY-MM-DD/cursor
        cursor = 0
        while len(papers) < max_results:
            url = f"{self.BIORXIV_API_URL}/{date_from}/{date_to}/{cursor}/json"
            logger.info(f"Fetching bioRxiv papers: {url}")

            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"bioRxiv API request failed: {e}")
                break

            collection = data.get("collection", [])
            if not collection:
                break

            for entry in collection:
                # Filter by category if possible
                paper_cat = entry.get("category", "").lower()
                
                # If categories are provided, check if this paper matches any of them
                if categories:
                    match = False
                    for cat in categories:
                        if cat.lower() in paper_cat or paper_cat in cat.lower():
                            match = True
                            break
                    if not match:
                        continue

                paper = self._parse_entry(entry)
                if paper and paper["arxiv_id"] not in seen_dois:
                    seen_dois.add(paper["arxiv_id"])
                    papers.append(paper)
                    if len(papers) >= max_results:
                        break
            
            cursor += len(collection)
            if len(collection) < 100:
                break
            
            # Be polite
            time.sleep(1)

        return papers

    def fetch_simple(self, categories: list[str], max_results: int = 50) -> list[dict]:
        """Simple fetch for bioRxiv (last 7 days)."""
        return self.fetch(categories, max_results=max_results, days_back=7)

    def _parse_entry(self, entry: dict) -> Optional[dict]:
        """Parse a bioRxiv entry into a paper dict."""
        try:
            doi = entry.get("doi")
            if not doi:
                return None
                
            # Clean ID for database
            clean_id = doi.replace("/", "-")
            
            # Authors (bioRxiv returns a comma-separated string)
            authors_str = entry.get("authors", "")
            authors = [a.strip() for a in authors_str.split(",") if a.strip()]

            abstract = entry.get("abstract", "No Abstract")
            has_code, has_data = detect_code_and_data(abstract)

            return {
                "arxiv_id": f"biorxiv-{clean_id}",
                "title": entry.get("title", "No Title"),
                "abstract": abstract,
                "authors": authors,
                "categories": [entry.get("category", "bioRxiv")],
                "published": entry.get("date", ""),
                "url": f"https://doi.org/{doi}",
                "pdf_url": f"https://www.biorxiv.org/content/{doi}.full.pdf",
                "source": "biorxiv",
                "citation_count": 0,
                "has_code": has_code,
                "has_data": has_data,
            }
        except Exception as e:
            logger.warning(f"Failed to parse bioRxiv entry: {e}")
            return None


class RSSSource:
    """Fetches papers from generic journal RSS feeds."""

    def __init__(self, feed_urls: list[str] | None = None):
        self.feed_urls = feed_urls or []

    def fetch(
        self,
        categories: list[str],
        max_results: int = 100,
        days_back: int = 7,
    ) -> list[dict]:
        """Fetch papers from configured RSS feeds."""
        import feedparser

        papers: list[dict] = []
        seen_ids = set()
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)

        for url in self.feed_urls:
            logger.info(f"Fetching RSS feed: {url}")
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    if len(papers) >= max_results:
                        break
                        
                    paper = self._parse_entry(entry, feed.feed.get("title", "RSS Feed"))
                    if not paper:
                        continue
                        
                    # Basic date filtering
                    try:
                        pub_date = datetime.fromisoformat(paper["published"].replace("Z", "+00:00"))
                        if pub_date.replace(tzinfo=None) < cutoff_date:
                            continue
                    except (ValueError, TypeError):
                        pass

                    if paper["arxiv_id"] not in seen_ids:
                        seen_ids.add(paper["arxiv_id"])
                        papers.append(paper)
            except Exception as e:
                logger.error(f"Failed to fetch RSS feed {url}: {e}")

        logger.info(f"Fetched {len(papers)} papers total from RSS feeds")
        return papers

    def fetch_simple(self, categories: list[str], max_results: int = 100) -> list[dict]:
        """Simple fetch without date filtering."""
        return self.fetch(categories, max_results=max_results, days_back=365)

    def _parse_entry(self, entry: Any, feed_title: str) -> Optional[dict]:
        """Parse an RSS entry into a paper dict."""
        try:
            # RSS feeds don't have stable IDs like arXiv. 
            # We use the link as a unique ID if nothing better exists.
            guid = entry.get("id") or entry.get("link")
            if not guid:
                return None
                
            # Clean up ID for database (replace / with -)
            clean_id = guid.replace("http://", "").replace("https://", "").replace("/", "-")
            
            # Authors parsing (format varies wildly in RSS)
            authors = []
            if "authors" in entry:
                authors = [a.get("name") for a in entry.authors if a.get("name")]
            elif "author" in entry:
                authors = [entry.author]
            
            # Published date
            published = ""
            if "published_parsed" in entry:
                published = time.strftime("%Y-%m-%dT%H:%M:%SZ", entry.published_parsed)
            elif "updated_parsed" in entry:
                published = time.strftime("%Y-%m-%dT%H:%M:%SZ", entry.updated_parsed)

            abstract = entry.get("summary") or entry.get("description", "No Abstract")
            has_code, has_data = detect_code_and_data(abstract)

            return {
                "arxiv_id": clean_id,
                "title": entry.get("title", "No Title"),
                "abstract": abstract,
                "authors": authors,
                "categories": [feed_title],
                "published": published,
                "url": entry.get("link", ""),
                "pdf_url": "",
                "source": "rss",
                "has_code": has_code,
                "has_data": has_data,
            }
        except Exception as e:
            logger.warning(f"Failed to parse RSS entry: {e}")
            return None
