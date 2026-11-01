"""Mac-Expertenzahlen ohne Hardware, Setup-Imports oder Downloads pruefen."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strata_control import dsv41_fit as fit


class MacExpertCounts(unittest.TestCase):
    def report(self, model, ram):
        card = {"vendor": "apple", "name": "synthetic-apple", "unified_gb": ram}
        return fit.plan([card], ram, model=model)

    def test_full_residency_counts_every_expert_once(self):
        for model in fit.MAC_SET_PACK:
            for ram in (256, 512):
                with self.subTest(model=model, ram=ram):
                    report = self.report(model, ram)
                    self.assertEqual(report["experts_in_vram"], fit.EXPERTS)
                    self.assertEqual(report["cards"][0]["experts"], fit.EXPERTS)
                    self.assertEqual(report["streamed_gb"], 0.0)

    def test_partial_residency_uses_unrounded_capacity(self):
        # Eingefrorene Sollwerte aus ungerundetem Budget, nicht angezeigten GB.
        expected = {
            "IST-DAS-2.00bpw": (2921, 8078),
            "IST-DAS-2.25bpw": (2588, 7157),
            "UD-IQ1_S": (3348, 9259),
            "UD-IQ1_M": (2918, 8070),
        }
        for model, counts in expected.items():
            for ram, count in zip((64, 128), counts):
                with self.subTest(model=model, ram=ram):
                    report = self.report(model, ram)
                    self.assertEqual(report["experts_in_vram"], count)
                    self.assertEqual(report["cards"][0]["experts"], count)
                    self.assertLess(count, report["experts_total"])

    def test_mac_and_variant_expert_sizes_agree(self):
        for model, quant in fit.MAC_SET_PACK.items():
            with self.subTest(model=model):
                self.assertEqual(fit.variant(model)["experts_gb"],
                                 fit.MAC_PACKS[quant]["routed_gb"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
