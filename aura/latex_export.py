"""LaTeX thesis chapter and BibTeX export with stable cite keys and synthesis."""

import io
import logging
import re
import zipfile
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def latex_escape(text: str) -> str:
    """Escape LaTeX special characters to ensure valid compilation."""
    if not text:
        return ""
    # Order matters: replace backslash first
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for char, escaped in replacements:
        text = text.replace(char, escaped)
    return text


def generate_cite_key(paper: Dict[str, Any], existing_keys: Set[str]) -> str:
    """Generate a deterministic AuthorYear cite key with collision disambiguation.

    Examples:
        - "Lovelace, Ada" (2024) -> "Lovelace2024"
        - Second paper by same author in same year -> "Lovelace2024a", "Lovelace2024b"
    """
    authors = paper.get("authors") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in authors.split(",") if a.strip()]

    first_author = authors[0] if authors else "Unknown"
    if "," in first_author:
        last_name = first_author.split(",")[0].strip()
    else:
        parts = first_author.strip().split()
        last_name = parts[-1] if parts else "Unknown"

    last_name_clean = re.sub(r"[^A-Za-z]", "", last_name) or "Author"
    last_name_clean = last_name_clean.capitalize()

    pub_date = str(paper.get("published", "") or "")
    year = "2026"
    match = re.search(r"\b(19\d\d|20\d\d)\b", pub_date)
    if match:
        year = match.group(1)

    base_key = f"{last_name_clean}{year}"
    candidate = base_key

    suffix_idx = 0
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    while candidate in existing_keys:
        suffix = alphabet[suffix_idx] if suffix_idx < len(alphabet) else f"_{suffix_idx}"
        candidate = f"{base_key}{suffix}"
        suffix_idx += 1

    existing_keys.add(candidate)
    return candidate


def paper_to_bibtex_entry(paper: Dict[str, Any], cite_key: str) -> str:
    """Format a paper dictionary into a clean BibTeX entry with the provided cite key."""
    title = (paper.get("title") or "Untitled").replace("\n", " ").strip()
    escaped_title = latex_escape(title)

    raw_authors = paper.get("authors") or []
    if isinstance(raw_authors, str):
        authors_list = [a.strip() for a in raw_authors.split(",") if a.strip()]
    else:
        authors_list = raw_authors
    authors_str = " and ".join(authors_list) if authors_list else "Unknown"

    pub_date = str(paper.get("published", "") or "")
    year = "2026"
    match = re.search(r"\b(19\d\d|20\d\d)\b", pub_date)
    if match:
        year = match.group(1)

    eprint = paper.get("arxiv_id", "")
    categories = paper.get("categories", [])
    primary_class = categories[0] if categories and isinstance(categories, list) else ""

    lines = [
        f"@article{{{cite_key},",
        f"  author        = {{{authors_str}}},",
        f"  title         = {{{{{escaped_title}}}}},",
        f"  year          = {{{year}}},",
    ]
    if eprint:
        lines.append(f"  journal       = {{arXiv preprint arXiv:{eprint}}},")
        lines.append(f"  eprint        = {{{eprint}}},")
        lines.append("  archivePrefix = {arXiv},")
    else:
        lines.append("  journal       = {Preprint},")

    if primary_class:
        lines.append(f"  primaryClass  = {{{primary_class}}},")
    if paper.get("doi"):
        lines.append(f"  doi           = {{{paper['doi']}}},")
    if paper.get("url"):
        lines.append(f"  url           = {{{paper['url']}}},")

    lines[-1] = lines[-1].rstrip(",")
    lines.append("}")
    return "\n".join(lines)


def _extract_note_info(n: Dict[str, Any]) -> Tuple[str, str]:
    """Extract note type and body from either content or note field."""
    body = n.get("content") or n.get("note") or ""
    ntype = n.get("note_type")
    if not ntype:
        low = body.strip().lower()
        if low.startswith("critique:") or low.startswith("[critique]"):
            ntype = "critique"
            body = re.sub(r"^(?:critique:|\[critique\])\s*", "", body, flags=re.IGNORECASE)
        elif low.startswith("idea:") or low.startswith("[idea]"):
            ntype = "idea"
            body = re.sub(r"^(?:idea:|\[idea\])\s*", "", body, flags=re.IGNORECASE)
        elif low.startswith("summary:") or low.startswith("[summary]"):
            ntype = "summary"
            body = re.sub(r"^(?:summary:|\[summary\])\s*", "", body, flags=re.IGNORECASE)
        else:
            ntype = "note"
    return ntype, body


def synthesize_related_work(
    papers: List[Dict[str, Any]],
    notes_by_paper: Dict[str, List[Dict[str, Any]]],
    engine: Optional[Any] = None,
) -> str:
    """Synthesise collection papers and research notes into a cohesive literature review narrative."""
    if not papers:
        return "\\section{Related Work}\n\nNo papers available in this collection to synthesise.\n"

    # Try LLM synthesis if available
    try:
        from aura.trends import _generate_generic_text

        paper_summaries = []
        for p in papers:
            ck = p.get("cite_key", "Reference")
            title = p.get("title", "Untitled")
            abstract = p.get("abstract", "")[:300]
            notes = notes_by_paper.get(p.get("arxiv_id", ""), [])
            notes_str = "; ".join([_extract_note_info(n)[1] for n in notes]) if notes else "No notes"
            paper_summaries.append(
                f"- Cite Key: \\cite{{{ck}}}\n  Title: {title}\n  Abstract: {abstract}\n  User Notes: {notes_str}"
            )

        prompt = (
            "You are a principal researcher writing a doctoral dissertation chapter in LaTeX. "
            "Synthesise the following papers and researcher notes into a structured, highly scholarly Related Work narrative. "
            "Use \\cite{cite_key} citations everywhere you mention findings or methodologies. "
            "Discuss methodological themes, compare approaches, and highlight critical insights from the notes. "
            "Output valid LaTeX text (use \\subsection and paragraphs, without markdown code fences).\n\n"
            + "\n\n".join(paper_summaries)
        )

        result = _generate_generic_text(prompt)
        if result and len(result.strip()) > 100:
            cleaned = result.strip()
            if cleaned.startswith("```latex"):
                cleaned = cleaned[8:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return f"\\section{{Related Work and Literature Synthesis}}\n\n{cleaned.strip()}\n"
    except Exception as e:
        logger.debug(f"LLM synthesis fallback: {e}")

    # Fallback structured narrative
    sections = [
        "\\section{Related Work and Literature Synthesis}\n",
        "This section reviews the core literature compiled in this collection, "
        "synthesising primary methodological developments, foundational findings, and critique.\n",
    ]

    for p in papers:
        ck = p.get("cite_key", "Reference")
        title = latex_escape(p.get("title", "Untitled"))
        authors_val = p.get("authors") or []
        first_author = authors_val[0] if authors_val else "Authors"
        notes = notes_by_paper.get(p.get("arxiv_id", ""), [])

        critiques = []
        ideas = []
        summaries = []
        for n in notes:
            ntype, nbody = _extract_note_info(n)
            esc_body = latex_escape(nbody)
            if ntype == "critique":
                critiques.append(esc_body)
            elif ntype == "idea":
                ideas.append(esc_body)
            elif ntype == "summary":
                summaries.append(esc_body)
            else:
                critiques.append(esc_body)

        para = f"\\subsection*{{{title} \\cite{{{ck}}}}}\n"
        para += f"In \\cite{{{ck}}}, {latex_escape(first_author)} et al.\\ investigate key phenomena relevant to this enquiry. "

        if summaries:
            para += f"Specifically, {summaries[0]} "
        elif p.get("abstract"):
            first_sentence = p["abstract"].split(".")[0].strip() + "."
            para += f"{latex_escape(first_sentence)} "

        if critiques:
            para += f"\n\n\\noindent\\textbf{{Critical Assessment:}} {critiques[0]} "

        if ideas:
            para += f"\n\n\\noindent\\textbf{{Open Directions:}} {ideas[0]} "

        sections.append(para + "\n")

    return "\n".join(sections)


def generate_latex_chapter(
    collection: Dict[str, Any],
    papers: List[Dict[str, Any]],
    notes_by_paper: Dict[str, List[Dict[str, Any]]],
    related_work_synthesis: Optional[str] = None,
) -> str:
    """Generate chapter.tex containing the complete LaTeX document."""
    coll_name = latex_escape(collection.get("name") or "Collection")
    coll_desc = latex_escape(collection.get("description") or "")

    doc = [
        r"\documentclass[11pt,a4paper]{report}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{amsmath,amssymb}",
        r"\usepackage{booktabs}",
        r"\usepackage{microtype}",
        r"\usepackage[colorlinks=true,linkcolor=blue,citecolor=teal,urlcolor=magenta]{hyperref}",
        r"\usepackage{cite}",
        "",
        f"\\title{{{coll_name}}}",
        r"\author{AURA Automated Research Assistant}",
        r"\date{\today}",
        "",
        r"\begin{document}",
        r"\maketitle",
        "",
        f"\\chapter{{{coll_name}}}",
        "",
    ]

    if coll_desc:
        doc.append(f"\\begin{{quote}}\n\\textit{{{coll_desc}}}\n\\end{{quote}}\n")

    doc.append(
        f"This chapter compiles and reviews {len(papers)} selected publications from the collection, "
        "incorporating detailed reading annotations, critical analysis, and bibliographic references.\n"
    )

    if related_work_synthesis:
        doc.append(related_work_synthesis.strip() + "\n")

    doc.append(r"\section{Detailed Paper Annotations}")
    doc.append("")

    for p in papers:
        ck = p.get("cite_key", "Reference")
        title = latex_escape(p.get("title", "Untitled"))
        arxiv_id = p.get("arxiv_id", "")
        raw_authors = p.get("authors") or []
        if isinstance(raw_authors, str):
            authors_list = [a.strip() for a in raw_authors.split(",") if a.strip()]
        else:
            authors_list = raw_authors
        authors_esc = latex_escape(", ".join(authors_list[:5]))
        if len(authors_list) > 5:
            authors_esc += " et al."

        abstract_esc = latex_escape(p.get("abstract", "No abstract available."))

        doc.append(f"\\subsection{{{title} \\cite{{{ck}}}}}")
        doc.append(f"\\textbf{{Authors:}} {authors_esc} \\\\")
        if arxiv_id:
            doc.append(f"\\textbf{{Identifier:}} \\href{{https://arxiv.org/abs/{arxiv_id}}}{{arXiv:{latex_escape(arxiv_id)}}} \\\\")
        doc.append("")
        doc.append(f"\\textbf{{Abstract:}} \\small{{{abstract_esc}}}\n")

        notes = notes_by_paper.get(arxiv_id, [])
        if notes:
            doc.append(r"\subsubsection*{Research Notes \& Critique}")
            doc.append(r"\begin{itemize}")
            for n in notes:
                ntype, nbody = _extract_note_info(n)
                ntype_esc = latex_escape(ntype.capitalize())
                nbody_esc = latex_escape(nbody)
                doc.append(f"  \\item \\textbf{{{ntype_esc}:}} {nbody_esc}")
            doc.append(r"\end{itemize}")
        else:
            doc.append(r"\textit{No user notes recorded for this paper.}\n")

    doc.extend([
        "",
        r"\bibliographystyle{plain}",
        r"\bibliography{references}",
        "",
        r"\end{document}",
    ])

    return "\n".join(doc)


def export_collection_latex_zip(
    collection_id: int,
    user_id: int,
    engine: Any,
    include_synthesis: bool = False,
) -> Tuple[str, bytes]:
    """Package a collection as a LaTeX chapter zip archive (chapter.tex + references.bib).

    Returns:
        tuple of (filename, zip_bytes)
    """
    collection = engine.db.get_collection(collection_id)
    if not collection:
        raise ValueError(f"Collection {collection_id} not found")

    if collection["user_id"] != user_id and not collection.get("is_public"):
        raise PermissionError(f"Access denied to collection {collection_id}")

    papers = engine.db.get_collection_papers(collection_id, limit=500)

    # Fetch notes and assign stable AuthorYear cite keys
    notes_by_paper: Dict[str, List[Dict[str, Any]]] = {}
    existing_keys: Set[str] = set()

    for p in papers:
        arxiv_id = p.get("arxiv_id", "")
        p["cite_key"] = generate_cite_key(p, existing_keys)
        if arxiv_id:
            notes = engine.db.get_paper_notes(arxiv_id, user_id=user_id)
            notes_by_paper[arxiv_id] = notes or []

    # Generate references.bib
    bib_entries = [paper_to_bibtex_entry(p, p["cite_key"]) for p in papers]
    bib_content = "\n\n".join(bib_entries) + "\n"

    # Optional related work synthesis
    related_work = None
    if include_synthesis:
        related_work = synthesize_related_work(papers, notes_by_paper, engine=engine)

    chapter_content = generate_latex_chapter(
        collection=collection,
        papers=papers,
        notes_by_paper=notes_by_paper,
        related_work_synthesis=related_work,
    )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("chapter.tex", chapter_content)
        zip_file.writestr("references.bib", bib_content)
        if related_work:
            zip_file.writestr("related_work.tex", related_work)

    safe_title = re.sub(r"[^A-Za-z0-9_-]", "_", collection.get("name") or "collection").lower()
    filename = f"{safe_title}_latex.zip"

    return filename, zip_buffer.getvalue()
