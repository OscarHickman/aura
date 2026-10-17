import unittest
from aura.pdf_scanner import chunk_paper_text, retrieve_context_for_query


class TestPdfScannerChunking(unittest.TestCase):
    def test_chunk_paper_text_empty(self):
        self.assertEqual(chunk_paper_text(""), [])

    def test_chunk_paper_text_sections(self):
        sample_doc = (
            "Abstract\nThis paper introduces an emulator for cosmological simulations.\n\n"
            "1 Introduction\nCosmological simulations are computationally expensive.\n\n"
            "2 Methods\nWe use neural posterior estimation with normalizing flows.\n\n"
            "3 Results\nThe method achieves high accuracy and fast sampling.\n\n"
            "4 Conclusions\nOur emulator is ready for Rubin LSST analysis.\n\n"
            "References\nSmith et al. 2024."
        )
        chunks = chunk_paper_text(sample_doc, chunk_size=100, overlap=20)
        self.assertGreater(len(chunks), 4)
        sections = [c["section"] for c in chunks]
        self.assertIn("Abstract", sections)
        self.assertIn("Introduction", sections)
        self.assertIn("Methods", sections)
        self.assertIn("Results", sections)
        self.assertIn("Conclusions", sections)

    def test_retrieve_context_for_query_under_max_chars(self):
        text = "Short paper content."
        result = retrieve_context_for_query(text, "query", max_chars=1000)
        self.assertEqual(result, text)

    def test_retrieve_context_for_query_over_max_chars(self):
        sample_doc = (
            "Abstract\nThis paper introduces an emulator for cosmological simulations.\n\n"
            "1 Introduction\nCosmological simulations are computationally expensive to run.\n\n"
            "2 Methods\nWe employ simulation based inference and deep neural architectures.\n\n"
            "3 Results\nThe parameter constraints on Omega_m and sigma_8 are unbiased.\n\n"
            "4 Conclusions\nFuture surveys will benefit from this inference framework.\n\n"
            "References\nSmith et al. 2024.\n" + ("Filler text citation.\n" * 50)
        )
        # Force a small max_chars
        result = retrieve_context_for_query(sample_doc, "Omega_m parameter constraints", max_chars=250)
        self.assertIn("Omega_m", result)
        self.assertIn("Abstract", result)
