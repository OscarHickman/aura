import unittest
import tempfile
from pathlib import Path
from aura.web.app import sanitise_input, sanitise_tag
from aura.model import PreferenceModel


class TestSecurityAndAtomic(unittest.TestCase):
    def test_sanitise_input(self):
        self.assertEqual(sanitise_input("  hello  "), "hello")
        self.assertEqual(sanitise_input("<script>alert(1)</script>"), "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertEqual(sanitise_input(""), "")
        self.assertEqual(sanitise_input(None), "")

    def test_sanitise_tag(self):
        self.assertEqual(sanitise_tag("  Quantum-Physics_123!@#  "), "quantum-physics_123")
        self.assertEqual(sanitise_tag(""), "")
        self.assertEqual(sanitise_tag(None), "")

    def test_atomic_model_save(self):
        with tempfile.TemporaryDirectory() as td:
            model_path = Path(td) / "test_model.pt"
            pref_model = PreferenceModel(model_path=model_path, embedding_dim=10)
            
            # Save the model
            pref_model.save()
            
            # Check model file exists and has content
            self.assertTrue(model_path.exists())
            self.assertGreater(model_path.stat().st_size, 0)
            
            # Verify it can be loaded back
            loaded_model = PreferenceModel(model_path=model_path, embedding_dim=10)
            loaded_model.load()
            self.assertEqual(loaded_model.embedding_dim, 10)

    def test_load_resilience(self):
        with tempfile.TemporaryDirectory() as td:
            model_path = Path(td) / "corrupt_model.pt"
            
            # Write a corrupted/garbage file
            model_path.write_bytes(b"THIS IS CORRUPTED GARBAGE DATA")
            
            # Try loading it; it should log an error and return without crashing
            pref_model = PreferenceModel(model_path=model_path, embedding_dim=10)
            
            # Calling load should run without raising any exceptions
            try:
                pref_model.load()
            except Exception as e:
                self.fail(f"load() raised an exception on corrupt model: {e}")


if __name__ == "__main__":
    unittest.main()
