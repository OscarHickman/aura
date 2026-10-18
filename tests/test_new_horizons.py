"""Tests for the new horizons: ML Prototype Clustering, Active Learning, Zotero, Git Sync, Comparative Matrix, and Audio Briefings."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from aura.database import PaperDatabase
from aura.model import PreferenceModel
from aura.recommender import RecommendationEngine
from aura.zotero import ZoteroClient
from aura.git_sync import GitLiteratureSync
from aura.synthesis import ComparativeSynthesisEngine
from aura.audio import AudioBriefingEngine
from aura.web.app import create_app


class TestNewHorizons(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.model_path = Path(self.temp_dir.name) / "model.pt"
        self.db = PaperDatabase(self.db_path)

        # Insert test papers
        self.paper1 = {
            "arxiv_id": "2401.00001",
            "title": "Simulation-Based Inference with Neural Density Estimation for Galaxy Clustering",
            "abstract": "We present cosmological constraints on sigma_8 and Omega_m using small-scale galaxy clustering with simulation-based inference.",
            "authors": ["Oscar Hickman", "Carlton Baugh"],
            "categories": ["astro-ph.CO"],
            "published": "2026-01-15T00:00:00Z",
            "url": "https://arxiv.org/abs/2401.00001",
        }
        self.paper2 = {
            "arxiv_id": "2401.00002",
            "title": "Calibrating Semi-Analytic Models of Galaxy Formation with DESI Clustering",
            "abstract": "GALFORM clustering calibration using sparse merger trees and N-point correlation functions.",
            "authors": ["Oscar Hickman", "Sownak Bose"],
            "categories": ["astro-ph.CO", "astro-ph.GA"],
            "published": "2026-01-16T00:00:00Z",
            "url": "https://arxiv.org/abs/2401.00002",
        }
        self.paper3 = {
            "arxiv_id": "2401.00003",
            "title": "Modified Gravity and Screening Mechanisms in Redshift-Space Distortions",
            "abstract": "Testing nDGP and f(R) gravity models using quadrupole clustering statistics.",
            "authors": ["Baojiu Li", "Oscar Hickman"],
            "categories": ["astro-ph.CO"],
            "published": "2026-01-17T00:00:00Z",
            "url": "https://arxiv.org/abs/2401.00003",
        }
        emb1 = np.ones(384, dtype=np.float32) * 0.1
        emb2 = np.ones(384, dtype=np.float32) * 0.2
        emb3 = np.ones(384, dtype=np.float32) * -0.1
        self.db.add_paper(self.paper1, embedding=emb1)
        self.db.add_paper(self.paper2, embedding=emb2)
        self.db.add_paper(self.paper3, embedding=emb3)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_model_calibrated_weights(self):
        """Verify PreferenceModel supports sample weights in train_step and train_single."""
        model = PreferenceModel(self.model_path, embedding_dim=384)
        embs = [np.ones(384, dtype=np.float32), np.zeros(384, dtype=np.float32)]
        labels = [1.0, 0.0]
        weights = [1.0, 0.25]  # skips have lower weight

        loss = model.train_step(embs, labels, weights=weights, epochs=3)
        self.assertIsInstance(loss, float)
        self.assertGreater(loss, 0.0)

        # Single training with weight
        single_loss = model.train_single(embs[0], 0.0, weight=0.25, epochs=2)
        self.assertIsInstance(single_loss, float)

    def test_database_weighted_training_data(self):
        """Verify get_weighted_training_data returns calibrated sample weights."""
        self.db.rate_paper("2401.00001", rating=5, user_id=1)   # like -> label 1.0, weight 1.0
        self.db.rate_paper("2401.00002", rating=-1, user_id=1)  # skip -> label 0.0, weight 0.25
        self.db.rate_paper("2401.00003", rating=0, user_id=1)   # dislike -> label 0.0, weight 1.0

        embs, labels, weights = self.db.get_weighted_training_data(user_id=1, include_skips=True)
        self.assertEqual(len(labels), 3)
        self.assertIn(0.25, weights)
        self.assertIn(1.0, weights)

        # Default legacy get_training_data excludes skips
        embs_legacy, labels_legacy = self.db.get_training_data(user_id=1)
        self.assertEqual(len(labels_legacy), 2)

    def test_prototype_clustering_and_exploration(self):
        """Verify recommender multi-interest prototype clustering and boundary exploration."""
        engine = RecommendationEngine(categories=["astro-ph.CO"], data_dir=self.temp_dir.name)
        engine.db.add_paper(self.paper1, embedding=np.ones(384, dtype=np.float32) * 0.1)
        engine.db.add_paper(self.paper2, embedding=np.ones(384, dtype=np.float32) * 0.2)
        engine.rate_paper("2401.00001", rating=5, user_id=1)
        engine.rate_paper("2401.00002", rating=4, user_id=1)

        clusters = engine.compute_user_clusters(user_id=1)
        self.assertIsInstance(clusters, list)
        self.assertGreaterEqual(len(clusters), 1)
        self.assertIn("cluster_id", clusters[0])
        self.assertIn("label", clusters[0])
        self.assertIn("keywords", clusters[0])

        # Boundary exploration mode
        exploratory = engine.recommend_exploratory(limit=10, user_id=1)
        self.assertIsInstance(exploratory, list)
        if exploratory:
            self.assertIn("exploration_score", exploratory[0])

    def test_zotero_client(self):
        """Verify Zotero client formatting and methods."""
        client = ZoteroClient(api_key="dummy_key", user_id="12345")
        self.assertTrue(client.is_configured)
        self.assertIn("users/12345", client.base_path)

        creators = client.format_creators(["Oscar Hickman", "Carlton Baugh"])
        self.assertEqual(len(creators), 2)
        self.assertEqual(creators[0]["lastName"], "Hickman")

        with patch("requests.get") as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = [{"key": "coll1", "data": {"name": "Cosmology"}}]
            res = client.test_connection()
            self.assertTrue(res["ok"])
            self.assertEqual(res["collections_count"], 1)

    def test_git_literature_sync(self):
        """Verify GitLiteratureSync packaging and GitHub commit API payloads."""
        syncer = GitLiteratureSync(github_token="ghp_dummy", github_repo="oscarhickman/cosmology-thesis")
        self.assertTrue(syncer.is_configured)

        with patch("requests.get") as mock_get, patch("requests.put") as mock_put:
            mock_get.return_value.status_code = 404  # file does not exist yet
            mock_put.return_value.status_code = 201
            mock_put.return_value.json.return_value = {
                "content": {"html_url": "https://github.com/oscarhickman/cosmology-thesis/blob/main/aura-reading-list.bib"},
                "commit": {"sha": "abcdef123456"},
            }
            res = syncer.sync_literature([self.paper1, self.paper2])
            self.assertTrue(res["ok"])
            self.assertEqual(res["papers_synced"], 2)

    def test_comparative_synthesis_engine(self):
        """Verify ComparativeSynthesisEngine extracts comparison matrix and narrative."""
        mock_llm = MagicMock()
        mock_llm.complete.return_value = (
            '{"matrix": ['
            '{"arxiv_id": "2401.00001", "cite_key": "Hickman2026", "probe_dataset": "CAMELS / FLAMINGO", '
            '"tracer_sample": "Halos", "methodology": "SBI / Neural Posterior", "parameter_constraints": "sigma_8 = 0.81", '
            '"code_availability": "https://github.com/sbi", "key_takeaway": "SBI breaks degeneracies."},'
            '{"arxiv_id": "2401.00002", "cite_key": "Hickman2026a", "probe_dataset": "DESI DR1", '
            '"tracer_sample": "ELGs", "methodology": "GALFORM / SaUCE", "parameter_constraints": "H_0 = 67.4", '
            '"code_availability": "GALFORM", "key_takeaway": "Accurate clustering calibration."}'
            '], "synthesis_markdown": "### Executive Synthesis\\nComplementary SBI and SAM methods."}'
        )

        engine = ComparativeSynthesisEngine(llm_runner=mock_llm.complete)
        res = engine.generate_matrix([self.paper1, self.paper2])
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["matrix"]), 2)
        self.assertIn("Hickman2026", res["matrix"][0]["cite_key"])
        self.assertIn("Executive Synthesis", res["synthesis_markdown"])

    def test_audio_briefing_engine(self):
        """Verify AudioBriefingEngine script generation and metadata creation."""
        audio_engine = AudioBriefingEngine(data_dir=Path(self.temp_dir.name))
        script = audio_engine.generate_briefing_script([self.paper1, self.paper2])
        self.assertIn("Welcome to your AURA research briefing", script)
        self.assertIn("Hickman", script)

        with patch.object(audio_engine, "synthesise", return_value=True):
            briefing = audio_engine.get_or_create_daily_briefing([self.paper1, self.paper2], user_id=1, force=True)
            self.assertTrue(briefing["ok"])
            self.assertIn("briefing_", briefing["filename"])
            self.assertEqual(briefing["paper_count"], 2)

    def test_web_routes_for_new_horizons(self):
        """Verify REST endpoints for clusters, zotero, git-sync, compare, and audio."""
        engine = RecommendationEngine(categories=["astro-ph.CO"], data_dir=self.temp_dir.name)
        engine.db.add_paper(self.paper1, embedding=np.ones(384, dtype=np.float32) * 0.1)
        engine.db.add_paper(self.paper2, embedding=np.ones(384, dtype=np.float32) * 0.2)

        with patch("aura.web.app.RecommendationEngine", return_value=engine):
            app = create_app()

        app.config["TESTING"] = True
        app.config["LOGIN_DISABLED"] = True
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = "1"

        # 1. User clusters endpoint
        resp = client.get("/api/user/clusters")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("clusters", resp.get_json())

        # 2. Papers explore mode
        resp = client.get("/api/papers?filter=explore")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("papers", resp.get_json())

        # 3. Zotero status endpoint
        resp = client.get("/api/zotero/status")
        self.assertEqual(resp.status_code, 200)

        # 4. Compare papers endpoint
        mock_llm_complete = MagicMock(return_value='{"matrix": [], "synthesis_markdown": "Done"}')
        with patch("aura.synthesis.execute_llm", mock_llm_complete):
            resp = client.post("/api/papers/compare", json={"arxiv_ids": ["2401.00001", "2401.00002"]})
            self.assertEqual(resp.status_code, 200)
            self.assertIn("matrix", resp.get_json())

        # 5. Audio daily briefing endpoint
        with patch("aura.audio.AudioBriefingEngine.synthesise", return_value=True):
            resp = client.get("/api/audio/daily")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("audio_url", resp.get_json())


if __name__ == "__main__":
    unittest.main()
