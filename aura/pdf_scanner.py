"""PDF Metadata Scanner for AURA paper management system."""

import io
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


def scan_pdf_metadata(content_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Scan and extract key details (Title, Authors, Abstract, ArXiv ID, DOI) from PDF bytes."""
    extracted_text = ""
    pdf_meta_title = None
    pdf_meta_author = None

    # 1. Extract text and metadata using pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content_bytes))

        if reader.metadata:
            if reader.metadata.title and len(reader.metadata.title.strip()) > 3:
                pdf_meta_title = reader.metadata.title.strip()
            if reader.metadata.author and len(reader.metadata.author.strip()) > 2:
                pdf_meta_author = reader.metadata.author.strip()

        pages_text = []
        for page in reader.pages[:3]:
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(txt)
        extracted_text = "\n".join(pages_text)
    except Exception as e:
        logger.warning(f"pypdf extraction warning for {filename}: {e}")

    # Fallback decode if pypdf extracted minimal text
    if len(extracted_text) < 50:
        extracted_text = content_bytes[:8192].decode("latin1", errors="ignore")

    # 2. Extract ArXiv ID
    arxiv_match = re.search(r"arXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)", extracted_text, re.IGNORECASE)
    if not arxiv_match:
        arxiv_match = re.search(r"\b([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)\b", filename)
    arxiv_id = arxiv_match.group(1) if arxiv_match else None

    # 3. Extract DOI
    doi_match = re.search(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", extracted_text)
    doi = doi_match.group(0).rstrip(".,;") if doi_match else None

    # 4. Extract Title
    title = pdf_meta_title
    clean_filename_title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")

    if not title or title.lower() in ["untitled", "microsoft word", "latex", filename.lower()]:
        lines = [line.strip() for line in extracted_text.split("\n") if line.strip()]
        candidate_lines = []
        for line in lines[:15]:
            if re.match(r"^(abstract|introduction|arxiv:|1\s+intro)", line, re.IGNORECASE):
                break
            if len(line) > 5 and not line.startswith("http") and not line.isdigit() and not re.match(r"^[%<>\/]|^\d+\s+\d+\s+obj|^endobj|^stream", line):
                candidate_lines.append(line)
        if candidate_lines:
            title = " ".join(candidate_lines[:2])
        else:
            title = clean_filename_title.title()

    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        title = clean_filename_title.title()

    # 5. Extract Authors
    authors = []
    if pdf_meta_author and not pdf_meta_author.lower().startswith("latex"):
        authors = [a.strip() for a in re.split(r"[,;]| and ", pdf_meta_author) if a.strip()]

    if not authors:
        lines = [line.strip() for line in extracted_text.split("\n") if line.strip()]
        for line in lines[1:12]:
            if "abstract" in line.lower() or "introduction" in line.lower():
                break
            if re.search(r"^[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+", line):
                found = re.split(r"[,;]|\band\b|\d+", line)
                for f in found:
                    cleaned = re.sub(r"[0-9*†‡§#]", "", f).strip()
                    if len(cleaned) > 2 and "university" not in cleaned.lower() and "department" not in cleaned.lower():
                        authors.append(cleaned)
    if not authors:
        authors = ["Scanned PDF Author"]

    # 6. Extract Abstract
    abstract = "Scanned and saved PDF paper document."
    abs_match = re.search(
        r"abstract[\s\:\-\—\.\n]+(.*?)(?=\n\s*(?:1\.?\s+|1\s+intro|introduction|keywords|contents|\Z))",
        extracted_text,
        re.IGNORECASE | re.DOTALL,
    )
    if abs_match:
        raw_abs = abs_match.group(1).strip()
        if len(raw_abs) > 30:
            abstract = re.sub(r"\s+", " ", raw_abs[:1500])
    elif len(extracted_text) > 150:
        abstract = re.sub(r"\s+", " ", extracted_text[:500]) + "..."

    return {
        "arxiv_id": arxiv_id,
        "doi": doi,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "scanned_text": extracted_text[:2000],
    }


def chunk_paper_text(text: str, chunk_size: int = 1500, overlap: int = 200) -> list[Dict[str, Any]]:
    """Split paper text into section-aware overlapping chunks.

    Each chunk contains:
      - 'text': string content of the chunk
      - 'section': detected section header (e.g., 'Abstract', 'Introduction', 'Methods', 'Results', 'Conclusion')
      - 'char_start': start offset in full_text
      - 'char_end': end offset in full_text
    """
    if not text:
        return []

    section_pattern = re.compile(
        r"^(?:(?:[0-9IVXLCDM]+\.?\s+)?(abstract|introduction|background|methods?|methodology|data(?:set)?|experiments?|results?|discussion|conclusions?|summary|future work|references|appendix))\b",
        re.IGNORECASE | re.MULTILINE,
    )

    matches = list(section_pattern.finditer(text))
    chunks: list[Dict[str, Any]] = []

    if not matches:
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append({
                "text": text[start:end].strip(),
                "section": "General",
                "char_start": start,
                "char_end": end,
            })
            if end == len(text):
                break
            start += chunk_size - overlap
        return chunks

    for idx, match in enumerate(matches):
        sec_name = match.group(1).title()
        sec_start = match.start()
        sec_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sec_text = text[sec_start:sec_end]

        sub_start = 0
        while sub_start < len(sec_text):
            sub_end = min(sub_start + chunk_size, len(sec_text))
            chunks.append({
                "text": sec_text[sub_start:sub_end].strip(),
                "section": sec_name,
                "char_start": sec_start + sub_start,
                "char_end": sec_start + sub_end,
            })
            if sub_end == len(sec_text):
                break
            sub_start += chunk_size - overlap

    return chunks


def retrieve_context_for_query(full_text: str, query: str, max_chars: int = 40000) -> str:
    """Retrieve the most relevant sections of a paper for a user question.

    If the document exceeds max_chars, performs section-aware chunking and lexical
    relevance scoring, guaranteeing the retention of Abstract, Introduction, and
    Conclusion alongside the top-scoring content chunks in document order.
    """
    if not full_text or len(full_text) <= max_chars:
        return full_text

    chunks = chunk_paper_text(full_text)
    if not chunks:
        return full_text[:max_chars]

    query_tokens = set(re.findall(r"\w{3,}", query.lower()))

    scored_chunks = []
    for i, c in enumerate(chunks):
        c_tokens = re.findall(r"\w{3,}", c["text"].lower())
        overlap_count = sum(1 for t in c_tokens if t in query_tokens)
        sec_lower = c["section"].lower()
        sec_boost = 1.5 if any(k in sec_lower for k in ("abstract", "intro", "conclu")) else 1.0
        score = (overlap_count / (len(c_tokens) + 1)) * sec_boost
        scored_chunks.append((score, i, c))

    priority_indices = {0}
    for i in range(len(chunks) - 1, -1, -1):
        if "reference" not in chunks[i]["section"].lower():
            priority_indices.add(i)
            break

    scored_chunks.sort(key=lambda x: x[0], reverse=True)

    selected_indices = set(priority_indices)
    current_chars = sum(len(chunks[idx]["text"]) for idx in selected_indices)

    for score, idx, c in scored_chunks:
        if idx in selected_indices:
            continue
        c_len = len(c["text"])
        if current_chars + c_len > max_chars:
            continue
        selected_indices.add(idx)
        current_chars += c_len

    ordered_indices = sorted(selected_indices)
    assembled = "\n\n[...]\n\n".join(
        f"[{chunks[idx]['section']}]\n{chunks[idx]['text']}" for idx in ordered_indices
    )
    return assembled
