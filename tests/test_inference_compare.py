from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "infrastructure/scripts/inference_bench"

spec = importlib.util.spec_from_file_location("inference_compare", BENCH / "compare.py")
compare_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_mod)
THRESHOLDS = json.loads((BENCH / "profiles.json").read_text())["thresholds"]


def result(metrics: dict, gates: dict | None = None) -> dict:
    return {"profile": "main", "metrics": metrics, "gates": gates or {"perf.no_errors": True}}


class InferenceCompareVerdictTests(unittest.TestCase):
    def verdict(self, base: dict, cand: dict) -> str:
        return compare_mod.compare(base, cand, THRESHOLDS)[0]

    def test_identical_results_pass(self):
        r = result({"perf.c1.ttft_p50_ms": 100.0, "perf.c1.agg_output_tps": 50.0})
        self.assertEqual(self.verdict(r, r), "PASS")

    def test_latency_regression_past_fail_threshold_fails(self):
        base = result({"perf.c1.ttft_p50_ms": 100.0})
        self.assertEqual(self.verdict(base, result({"perf.c1.ttft_p50_ms": 130.0})), "FAIL")
        self.assertEqual(self.verdict(base, result({"perf.c1.ttft_p50_ms": 115.0})), "WARN")

    def test_throughput_drop_is_a_regression_and_gain_is_not(self):
        base = result({"perf.c4.agg_output_tps": 100.0})
        self.assertEqual(self.verdict(base, result({"perf.c4.agg_output_tps": 70.0})), "FAIL")
        self.assertEqual(self.verdict(base, result({"perf.c4.agg_output_tps": 140.0})), "PASS")

    def test_small_absolute_jitter_on_fast_path_is_ignored(self):
        base = result({"perf.c1.itl_p50_ms": 4.0})
        self.assertEqual(self.verdict(base, result({"perf.c1.itl_p50_ms": 5.5})), "PASS")

    def test_new_gate_failure_fails_but_preexisting_one_warns(self):
        ok = result({}, {"soak.no_stalls": True})
        bad = result({}, {"soak.no_stalls": False})
        self.assertEqual(self.verdict(ok, bad), "FAIL")
        self.assertEqual(self.verdict(bad, bad), "WARN")

    def test_request_errors_fail(self):
        base = result({"perf.c1.errors_count": 0})
        self.assertEqual(self.verdict(base, result({"perf.c1.errors_count": 2})), "FAIL")

    def test_profile_mismatch_fails(self):
        base = result({})
        cand = {**result({}), "profile": "fast"}
        self.assertEqual(self.verdict(base, cand), "FAIL")


if __name__ == "__main__":
    unittest.main()
