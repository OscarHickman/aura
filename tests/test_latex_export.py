"""Unit tests for LaTeX thesis chapter and BibTeX export."""

import io
import os
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from aura.database import PaperDatabase
from aura.latex_export import (
    generate_cite_key,
    latex_escape,
    paper_to_bibtex_entry,
    generate_latex_chapter,
    synthesize_related_work,
    export_collection_latex_zip,
)
from aura.web.app import create_app


class TestLatexExport(unittest.TestCase):
    """Test suite for LaTeX generation, BibTeX formatting, and zip packaging."""

    def test_latex_escape(self):
        """Test escaping special characters."""
        self.assertEqual(latex_escape("Normal title"), "Normal title")
        self.assertEqual(latex_escape("Dark Matter & Energy: 50% of Total"), r"Dark Matter \& Energy: 50\% of Total")
        self.assertEqual(latex_escape("Cosmology_Theory $100"), r"Cosmology\_Theory \$100")

    def test_generate_cite_key(self):
        """Test AuthorYear cite key generation and collision disambiguation."""
        existing_keys = set()

        p1 = {"authors": ["Ada Lovelace"], "published": "2024-03-01"}
        k1 = generate_cite_key(p1, existing_keys)
        self.assertEqual(k1, "Lovelace2024")

        # Second paper by same author in same year -> Lovelace2024a
        p2 = {"authors": ["Lovelace, Ada"], "published": "2024-08-15"}
        k2 = generate_cite_key(p2, existing_keys)
        self.assertEqual(k2, "Lovelace2024a")

        # Third paper -> Lovelace2024b
        p3 = {"authors": ["Ada Lovelace"], "published": "2024-11-20"}
        k3 = generate_cite_key(p3, existing_keys)
        self.assertEqual(k3, "Lovelace2024b")

        # Unknown author fallback
        p4 = {"authors": [], "published": "2025-01-01"}
        k4 = generate_cite_key(p4, existing_keys)
        self.assertEqual(k4, "Unknown2025")

    def test_paper_to_bibtex_entry(self):
        """Test BibTeX formatting with custom cite key."""
        paper = {
            "arxiv_id": "2401.00001",
            "title": "Machine Learning in Astronomy & Astrophysics",
            "authors": ["Albert Einstein", "Arthur Eddington"],
            "published": "2024-05-10T12:00:00Z",
            "categories": ["astro-ph.CO"],
            "doi": "10.1000/182",
            "url": "https://arxiv.org/abs/2401.00001",
        }
        bib = paper_to_bibtex_entry(paper, "Einstein2024")
        self.assertIn("@article{Einstein2024,", bib)
        self.assertIn("author        = {Albert Einstein and Arthur Eddington}", bib)
        self.assertIn(r"title         = {{Machine Learning in Astronomy \& Astrophysics}}", bib)
        self.assertIn("year          = {2024}", bib)
        self.assertIn("eprint        = {2401.00001}", bib)
        self.assertIn("doi           = {10.1000/182}", bib)

    def test_synthesize_related_work_fallback(self):
        """Test related work synthesis generates formatted LaTeX with cite keys."""
        papers = [
            {
                "arxiv_id": "2401.00001",
                "title": "Deep Neural Emulators",
                "authors": ["Carl Sagan"],
                "abstract": "We introduce deep neural emulators for power spectra calculation.",
                "cite_key": "Sagan2024",
            }
        ]
        notes = {
            "2401.00001": [
                {"note_type": "summary", "note": "Demonstrates 100x speedup in MCMC."},
                {"note_type": "critique", "note": "Limited to flat LCDM cosmologies."},
                {"note_type": "idea", "note": "Extend to massive neutrinos."},
            ]
        }
        synthesis = synthesize_related_work(papers, notes)
        self.assertIn(r"\section{Related Work and Literature Synthesis}", synthesis)
        self.assertIn(r"\cite{Sagan2024}", synthesis)
        self.assertIn("Demonstrates 100x speedup in MCMC.", synthesis)
        self.assertIn("Limited to flat LCDM cosmologies.", synthesis)
        self.assertIn("Extend to massive neutrinos.", synthesis)

    def test_generate_latex_chapter(self):
        """Test chapter.tex structure, packages, and notes rendering."""
        collection = {"name": "Cosmological Inference", "description": "Key papers on simulation-based inference"}
        papers = [
            {
                "arxiv_id": "2401.00001",
                "title": "Neural Posterior Estimation",
                "authors": ["George Gamow"],
                "abstract": "Density estimation for cosmological parameters.",
                "cite_key": "Gamow2024",
            }
        ]
        notes = {
            "2401.00001": [
                {"note_type": "critique", "note": "High dimensional prior coverage is tricky."},
            ]
        }
        tex = generate_latex_chapter(collection, papers, notes)
        self.assertIn(r"\documentclass[11pt,a4paper]{report}", tex)
        self.assertIn(r"\chapter{Cosmological Inference}", tex)
        self.assertIn(r"\subsection{Neural Posterior Estimation \cite{Gamow2024}}", tex)
        self.assertIn("High dimensional prior coverage is tricky.", tex)
        self.assertIn(r"\bibliography{references}", tex)

    def test_export_collection_latex_zip(self):
        """Test building the full zip archive with chapter.tex and references.bib."""
        mock_engine = MagicMock()
        mock_engine.db.get_collection.return_value = {
            "id": 1,
            "user_id": 1,
            "name": "Thesis Chapter 1",
            "description": "Background literature",
        }
        mock_engine.db.get_collection_papers.return_value = [
            {
                "arxiv_id": "2401.00001",
                "title": "Cosmological Emulators",
                "authors": ["Ada Lovelace"],
                "published": "2024-01-01",
                "abstract": "Fast surrogates for N-body simulations.",
            }
        ]
        mock_engine.db.get_paper_notes.return_value = [
            {"note_type": "summary", "note": "Essential baseline for Chapter 2."}
        ]

        filename, zip_bytes = export_collection_latex_zip(
            collection_id=1,
            user_id=1,
            engine=mock_engine,
            include_synthesis=True,
        )

        self.assertTrue(filename.endswith(".zip"))
        self.assertIn("thesis_chapter_1", filename)

        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
            names = z.namelist()
            self.assertIn("chapter.tex", names)
            self.assertIn("references.bib", names)
            self.assertIn("related_work.tex", names)

            bib_text = z.read("references.bib").decode("utf-8")
            self.assertIn("@article{Lovelace2024,", bib_text)

            tex_text = z.read("chapter.tex").decode("utf-8")
            self.assertIn(r"\chapter{Thesis Chapter 1}", tex_text)
            self.assertIn(r"\cite{Lovelace2024}", tex_text)


class TestLatexExportWebRoutes(unittest.TestCase):
    """Test suite for Flask routes serving LaTeX zip and synthesis."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_papers.db")
        self.db = PaperDatabase(db_path=self.db_path)

        self.mock_engine = MagicMock()
        self.mock_engine.db = self.db
        self.mock_engine.get_stats.return_value = {
            "database": {"total_rated": 10},
            "model": {},
        }

        with patch("aura.web.app.RecommendationEngine", return_value=self.mock_engine):
            self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

        user_id = self.db.create_user("thesis@example.com", "Password123!")
        self.token = self.db.create_api_token(user_id, "Thesis Device")

        # Create collection and add a paper
        self.coll_id = self.db.create_collection("Chapter 3", "Literature", user_id=user_id)
        self.db.add_paper({
            "arxiv_id": "2401.00001",
            "title": "Galaxy Clustering with Graph Neural Networks",
            "authors": ["Fritz Zwicky"],
            "published": "2024-04-01",
            "abstract": "We apply GNNs to galaxy catalogues.",
            "categories": ["astro-ph.CO"],
            "url": "https://arxiv.org/abs/2401.00001",
        })
        self.db.add_paper_to_collection(self.coll_id, "2401.00001", user_id=user_id)
        self.db.add_note("2401.00001", "Critique: GNN architecture robust against redshift-space distortions.", user_id=user_id)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_export_collection_latex_route(self):
        """Test GET /collections/<id>/export/latex downloads a valid zip file."""
        headers = {"Authorization": f"Bearer {self.token}"}
        res = self.client.get(f"/collections/{self.coll_id}/export/latex?synthesize=true", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "application/zip")
        self.assertIn("attachment", res.headers.get("Content-Disposition", ""))

        with zipfile.ZipFile(io.BytesIO(res.data), "r") as z:
            names = z.namelist()
            self.assertIn("chapter.tex", names)
            self.assertIn("references.bib", names)
            tex_content = z.read("chapter.tex").decode("utf-8")
            self.assertIn("Galaxy Clustering with Graph Neural Networks", tex_content)
            self.assertIn("Zwicky2024", tex_content)

    def test_synthesize_related_work_route(self):
        """Test POST /api/collections/<id>/synthesize-related-work."""
        headers = {"Authorization": f"Bearer {self.token}"}
        res = self.client.post(f"/api/collections/{self.coll_id}/synthesize-related-work", headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIn(r"\section{Related Work", data["latex"])
        self.assertIn("Zwicky2024", data["latex"])


if __name__ == "__main__":
    unittest.main()
