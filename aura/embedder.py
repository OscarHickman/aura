"""Generate embeddings for paper titles and abstracts using sentence-transformers."""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Lazy-loaded model singleton
_model = None
_model_name = None


def get_model(model_name: str = "all-MiniLM-L6-v2"):
    """Load or return cached sentence-transformer model."""
    global _model, _model_name
    if _model is None or _model_name != model_name:
        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading sentence-transformer model: {model_name}")
        _model = SentenceTransformer(model_name)
        _model_name = model_name
    return _model


def embed_text(text: str, model_name: str = "all-MiniLM-L6-v2") -> np.ndarray:
    """Create an embedding vector for arbitrary text (e.g., search queries)."""
    model = get_model(model_name)
    embedding = model.encode(text, normalize_embeddings=True)
    return np.array(embedding, dtype=np.float32)

def embed_paper(
    title: str, abstract: str, model_name: str = "all-MiniLM-L6-v2"
) -> np.ndarray:
    """Create an embedding vector for a single paper.

    Combines title and abstract into a single text for embedding.
    Returns a normalized embedding vector.
    """
    model = get_model(model_name)
    text = f"{title}. {abstract}"
    embedding = model.encode(text, normalize_embeddings=True)
    return np.array(embedding, dtype=np.float32)


def embed_papers_batch(
    papers: list[dict], model_name: str = "all-MiniLM-L6-v2", batch_size: int = 32
) -> list[np.ndarray]:
    """Create embeddings for a batch of papers.

    Args:
        papers: List of paper dicts with 'title' and 'abstract' keys.
        model_name: Name of the sentence-transformer model.
        batch_size: Batch size for encoding.

    Returns:
        List of numpy embedding vectors, one per paper.
    """
    model = get_model(model_name)
    texts = [f"{p['title']}. {p['abstract']}" for p in papers]

    logger.info(f"Embedding {len(texts)} papers...")
    embeddings = model.encode(
        texts, normalize_embeddings=True, batch_size=batch_size, show_progress_bar=True
    )

    return [np.array(e, dtype=np.float32) for e in embeddings]


def get_embedding_dim(model_name: str = "all-MiniLM-L6-v2") -> int:
    """Return the dimensionality of the embedding model."""
    model = get_model(model_name)
    return model.get_sentence_embedding_dimension()
