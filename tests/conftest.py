import pytest
import tempfile
from pathlib import Path
import numpy as np
from ai_papers.database import PaperDatabase
from ai_papers.web.app import create_app

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def seeded_db(temp_dir):
    db_path = temp_dir / "papers.db"
    db = PaperDatabase(db_path)
    
    # Add some dummy papers
    papers = [
        {
            "arxiv_id": "2401.00001",
            "title": "A cosmology breakthrough",
            "abstract": "We discover a new galaxy cluster.",
            "authors": ["Alice", "Bob"],
            "categories": ["astro-ph.CO"],
            "published": "2026-01-01T00:00:00Z",
            "url": "http://arxiv.org/abs/2401.00001",
            "pdf_url": "http://arxiv.org/pdf/2401.00001.pdf",
        },
        {
            "arxiv_id": "2401.00002",
            "title": "Planetary system evolution",
            "abstract": "We simulate planetary disk collisions.",
            "authors": ["Charlie"],
            "categories": ["astro-ph.EP"],
            "published": "2026-01-02T00:00:00Z",
            "url": "http://arxiv.org/abs/2401.00002",
            "pdf_url": "http://arxiv.org/pdf/2401.00002.pdf",
        },
        {
            "arxiv_id": "2401.00003",
            "title": "Stellar flares analysis",
            "abstract": "We observe high energy solar flares.",
            "authors": ["Diana"],
            "categories": ["astro-ph.SR"],
            "published": "2026-01-03T00:00:00Z",
            "url": "http://arxiv.org/abs/2401.00003",
            "pdf_url": "http://arxiv.org/pdf/2401.00003.pdf",
        }
    ]
    embs = [
        np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        np.array([0.5, 0.6, 0.7, 0.8], dtype=np.float32),
        np.array([0.9, 0.0, 0.1, 0.2], dtype=np.float32)
    ]
    db.add_papers_batch(papers, embs)
    db.rate_paper("2401.00001", 1)  # Liked
    db.rate_paper("2401.00002", 0)  # Disliked
    
    yield db
    db.close()

@pytest.fixture
def test_app(temp_dir):
    # Create a dummy config
    config_content = f"""
categories:
  - astro-ph.CO
  - astro-ph.EP
  - astro-ph.SR
data_dir: {temp_dir}
embedding_model: all-MiniLM-L6-v2
fetch:
  max_results: 10
  days_back: 2
summaries:
  generate_on_fetch: false
  batch_size: 5
"""
    config_path = temp_dir / "test_config.yaml"
    config_path.write_text(config_content)
    
    app = create_app(config_path=str(config_path))
    app.config["TESTING"] = True
    return app

@pytest.fixture
def test_client(test_app):
    return test_app.test_client()
