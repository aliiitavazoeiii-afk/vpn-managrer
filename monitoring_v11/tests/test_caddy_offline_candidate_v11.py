"""Offline tests for Caddy candidate generation."""
import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/"audit_caddy_offline_candidate_v11.py"
spec=importlib.util.spec_from_file_location("offline_candidate_v11",p)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class CandidateTests(unittest.TestCase):
    def test_inserts_at_one_site_only(self):
        source="other.invalid {\\n}\\nhesab.invalid {\\n  handle {\\n    reverse_proxy web:8000\\n  }\\n}\\n".replace("\\\\n","\\n")
        result=mod.candidate(source)
        self.assertEqual(result.replace(mod.BLOCK,""),source)
        self.assertIn("method POST",result)

    def test_duplicate_site_rejected(self):
        with self.assertRaises(ValueError):
            mod.candidate("hesab.a.invalid {\\n}\\nhesab.b.invalid {\\n}\\n")

if __name__=="__main__":unittest.main()
