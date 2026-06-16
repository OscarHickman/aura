"""Neural network model for paper preference prediction.

The model takes a paper embedding vector and outputs a preference score (0-1).
It is trained incrementally from user thumbs-up/thumbs-down feedback.
This model IS the user's preference config - saved and loaded as a .pt file.
"""

import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)


class PaperPreferenceNet(nn.Module):
    """Small feedforward network that predicts paper interest score from embeddings.

    Architecture: embedding_dim -> 128 -> 64 -> 32 -> 1 (sigmoid)
    """

    def __init__(self, embedding_dim: int = 384):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(embedding_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


class PreferenceModel:
    """Wrapper around PaperPreferenceNet for training and inference.

    This is the user's ML-based preference config. The model weights file
    stores all learned preferences from thumbs up/down feedback.
    """

    def __init__(
        self,
        model_path: str | Path,
        embedding_dim: int = 384,
        learning_rate: float = 1e-3,
        device: str = "cpu",
    ):
        self.model_path = Path(model_path)
        self.embedding_dim = embedding_dim
        self.device = torch.device(device)
        self.learning_rate = learning_rate

        self.model = PaperPreferenceNet(embedding_dim).to(self.device)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=learning_rate)
        self.criterion = nn.BCELoss()

        # Training stats
        self.total_trained = 0
        self.train_history: list[dict] = []

        # Load existing model if available
        if self.model_path.exists():
            self.load()

    def predict(self, embedding: np.ndarray) -> float:
        """Predict preference score for a single paper embedding. Returns 0-1."""
        self.model.eval()
        with torch.no_grad():
            x = (
                torch.tensor(embedding, dtype=torch.float32)
                .unsqueeze(0)
                .to(self.device)
            )
            score = self.model(x).item()
        return score

    def predict_batch(self, embeddings: list[np.ndarray]) -> list[float]:
        """Predict preference scores for a batch of embeddings."""
        self.model.eval()
        with torch.no_grad():
            x = torch.tensor(np.stack(embeddings), dtype=torch.float32).to(self.device)
            scores = self.model(x).cpu().numpy().tolist()
        return scores

    def train_step(
        self,
        embeddings: list[np.ndarray],
        labels: list[float],
        epochs: int = 5,
        progress_callback = None,
    ) -> float:
        """Train the model on a batch of (embedding, label) pairs.

        Args:
            embeddings: List of paper embedding vectors.
            labels: List of labels (1.0 = thumbs up, 0.0 = thumbs down).
            epochs: Number of epochs to train on this batch.
            progress_callback: Optional callback receiving (epoch + 1, epochs).

        Returns:
            Final loss value.
        """
        self.model.train()

        x = torch.tensor(np.stack(embeddings), dtype=torch.float32).to(self.device)
        y = torch.tensor(labels, dtype=torch.float32).to(self.device)

        final_loss = 0.0
        for epoch in range(epochs):
            self.optimizer.zero_grad()
            predictions = self.model(x)
            loss = self.criterion(predictions, y)
            loss.backward()
            self.optimizer.step()
            final_loss = loss.item()
            if progress_callback:
                progress_callback(epoch + 1, epochs)

        self.total_trained += len(labels)
        self.train_history.append(
            {
                "batch_size": len(labels),
                "loss": final_loss,
                "total_trained": self.total_trained,
            }
        )

        logger.info(
            f"Training step: batch_size={len(labels)}, loss={final_loss:.4f}, "
            f"total_trained={self.total_trained}"
        )

        # Auto-save after training
        self.save()
        return final_loss

    def train_single(
        self, embedding: np.ndarray, label: float, epochs: int = 10
    ) -> float:
        """Train on a single paper feedback (online learning)."""
        return self.train_step([embedding], [label], epochs=epochs)

    def save(self):
        """Save model weights and training state to disk."""
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "embedding_dim": self.embedding_dim,
            "total_trained": self.total_trained,
            "learning_rate": self.learning_rate,
        }
        torch.save(checkpoint, self.model_path)
        logger.info(f"Model saved to {self.model_path}")

    def load(self):
        """Load model weights and training state from disk."""
        if not self.model_path.exists():
            logger.warning(f"No model found at {self.model_path}, using fresh model")
            return

        checkpoint = torch.load(
            self.model_path, map_location=self.device, weights_only=True
        )

        # Rebuild model if embedding dim changed
        saved_dim = checkpoint.get("embedding_dim", self.embedding_dim)
        if saved_dim != self.embedding_dim:
            logger.warning(
                f"Embedding dim mismatch: saved={saved_dim}, current={self.embedding_dim}. "
                "Starting fresh model."
            )
            return

        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        self.total_trained = checkpoint.get("total_trained", 0)
        self.learning_rate = checkpoint.get("learning_rate", self.learning_rate)
        logger.info(
            f"Model loaded from {self.model_path} (total_trained={self.total_trained})"
        )

    def get_stats(self) -> dict:
        """Return model training statistics."""
        return {
            "model_path": str(self.model_path),
            "embedding_dim": self.embedding_dim,
            "total_trained": self.total_trained,
            "learning_rate": self.learning_rate,
            "parameters": sum(p.numel() for p in self.model.parameters()),
            "recent_losses": [h["loss"] for h in self.train_history[-10:]],
        }
