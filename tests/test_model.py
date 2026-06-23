import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from aura.model import PreferenceModel


class TestPreferenceModel(unittest.TestCase):
    def test_train_predict_and_stats(self):
        with tempfile.TemporaryDirectory() as td:
            model_path = Path(td) / "m.pt"
            model = PreferenceModel(model_path=model_path, embedding_dim=4)

            x1 = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
            x2 = np.array([0.9, 0.8, 0.7, 0.6], dtype=np.float32)
            loss = model.train_step([x1, x2], [0.0, 1.0], epochs=2)

            self.assertIsInstance(loss, float)
            self.assertTrue(model_path.exists())

            mean_pred, std_pred = model.predict(x1, num_samples=10)
            self.assertGreaterEqual(mean_pred, 0.0)
            self.assertLessEqual(mean_pred, 1.0)
            self.assertIsInstance(std_pred, float)

            # Test train_single and replay buffer
            model.train_single(x1, 1.0)
            self.assertEqual(len(model.replay_buffer), 1)
            model.train_single(x2, 0.0)
            self.assertEqual(len(model.replay_buffer), 2)

            preds, uncs = model.predict_batch([x1, x2])
            self.assertEqual(len(preds), 2)
            self.assertEqual(len(uncs), 2)

            stats = model.get_stats()
            self.assertEqual(stats["embedding_dim"], 4)
            self.assertEqual(stats["total_trained"], 5)
            self.assertEqual(stats["replay_buffer_size"], 2)

    def test_load_skips_mismatched_embedding_dim(self):
        with tempfile.TemporaryDirectory() as td:
            model_path = Path(td) / "mismatch.pt"
            checkpoint = {
                "model_state_dict": {},
                "optimizer_state_dict": {},
                "embedding_dim": 8,
                "total_trained": 123,
                "learning_rate": 1e-3,
            }
            torch.save(checkpoint, model_path)

            model = PreferenceModel(model_path=model_path, embedding_dim=4)
            self.assertEqual(model.total_trained, 0)


if __name__ == "__main__":
    unittest.main()
