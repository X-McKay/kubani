#!/usr/bin/env python3
"""Compare a candidate inference benchmark result against a baseline.

    compare.py BASELINE.json CANDIDATE.json [--profiles profiles.json] [--markdown OUT.md]

Verdict:
  FAIL  a gate that passed (or was absent) in the baseline is false in the
        candidate, or a metric regressed past fail_pct
  WARN  a metric regressed past warn_pct, a metric vanished, or a gate is
        false in both (pre-existing defect)
  PASS  otherwise
Exit code 1 on FAIL, 0 otherwise. Improvements are reported but never gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def kind(metric: str) -> tuple[str, int] | None:
    """(threshold class, direction) where direction +1 means higher is better."""
    if metric.endswith("_ms"):
        return "latency_ms", -1
    if metric.endswith("_tps"):
        return "throughput_tps", +1
    return None


def compare(base: dict, cand: dict, thresholds: dict) -> tuple[str, list[dict], list[str]]:
    rows, notes = [], []
    verdict = "PASS"

    def bump(level: str) -> None:
        nonlocal verdict
        order = {"PASS": 0, "WARN": 1, "FAIL": 2}
        verdict = level if order[level] > order[verdict] else verdict

    base_gates = base.get("gates", {})
    for gate, ok in sorted(cand.get("gates", {}).items()):
        if ok:
            continue
        if base_gates.get(gate) is False:
            # Known defect carried over from the baseline: surfaced, not blocking,
            # so one pre-existing failure cannot mask every later comparison.
            bump("WARN")
            notes.append(f"gate `{gate}` false in baseline and candidate (pre-existing)")
        else:
            bump("FAIL")
            notes.append(f"gate `{gate}` is false (new failure)")

    if base.get("profile") != cand.get("profile"):
        bump("FAIL")
        notes.append(f"profile mismatch: {base.get('profile')} vs {cand.get('profile')}")

    bm, cm = base.get("metrics", {}), cand.get("metrics", {})
    for name in sorted(set(bm) | set(cm)):
        if name.endswith("errors_count"):
            if cm.get(name):
                bump("FAIL")
                notes.append(f"`{name}` = {cm[name]}")
            continue
        k = kind(name)
        if k is None:
            continue
        cls, direction = k
        b, c = bm.get(name), cm.get(name)
        if b is None or c is None:
            if b is not None:
                bump("WARN")
                notes.append(f"`{name}` missing from candidate")
            rows.append({"metric": name, "base": b, "cand": c, "delta_pct": None, "status": "new" if b is None else "missing"})
            continue
        t = thresholds[cls]
        delta_pct = ((c - b) / b * 100) if b else 0.0
        worse_pct = -direction * delta_pct  # positive = regression
        abs_delta = abs(c - b)
        status = "ok"
        if worse_pct >= t["fail_pct"] and abs_delta >= t["min_abs"]:
            status = "FAIL"
        elif worse_pct >= t["warn_pct"] and abs_delta >= t["min_abs"]:
            status = "WARN"
        elif -worse_pct >= t["warn_pct"] and abs_delta >= t["min_abs"]:
            status = "better"
        if status in ("FAIL", "WARN"):
            bump(status)
        rows.append({"metric": name, "base": b, "cand": c, "delta_pct": round(delta_pct, 1), "status": status})
    return verdict, rows, notes


def render(base: dict, cand: dict, verdict: str, rows: list[dict], notes: list[str]) -> str:
    def ident(r: dict) -> str:
        meta = r.get("meta", {})
        v = r.get("target", {}).get("engine_version")
        v = v.get("version") if isinstance(v, dict) else v
        return f"`{r.get('label')}` ({r.get('started_at')}, vLLM {v}, image `{meta.get('image', '?')}`)"

    out = [f"## Inference benchmark comparison: **{verdict}**", "",
           f"- Profile: `{cand.get('profile')}`",
           f"- Baseline: {ident(base)}",
           f"- Candidate: {ident(cand)}", ""]
    if cand.get("meta", {}).get("args") != base.get("meta", {}).get("args"):
        out += ["Engine args differ:", "", "```diff"]
        ba = set(base.get("meta", {}).get("args", []))
        ca = set(cand.get("meta", {}).get("args", []))
        out += [f"- {a}" for a in sorted(ba - ca)] + [f"+ {a}" for a in sorted(ca - ba)] + ["```", ""]
    gates = cand.get("gates", {})
    out += ["| Gate | Result |", "|---|---|"]
    bg = base.get("gates", {})
    out += [f"| {g} | {'pass' if ok else ('fail (pre-existing)' if bg.get(g) is False else '**FAIL**')} |"
            for g, ok in sorted(gates.items())]
    out += ["", "| Metric | Baseline | Candidate | Δ% | Status |", "|---|---:|---:|---:|---|"]
    for r in rows:
        d = "" if r["delta_pct"] is None else f"{r['delta_pct']:+.1f}"
        s = f"**{r['status']}**" if r["status"] in ("FAIL", "WARN") else r["status"]
        out.append(f"| {r['metric']} | {r['base']} | {r['cand']} | {d} | {s} |")
    if notes:
        out += ["", "Notes:"] + [f"- {n}" for n in notes]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("baseline")
    ap.add_argument("candidate")
    ap.add_argument("--profiles", default=str(Path(__file__).with_name("profiles.json")))
    ap.add_argument("--markdown", help="also write the report here")
    args = ap.parse_args()
    base = json.loads(Path(args.baseline).read_text())
    cand = json.loads(Path(args.candidate).read_text())
    thresholds = json.loads(Path(args.profiles).read_text())["thresholds"]
    verdict, rows, notes = compare(base, cand, thresholds)
    report = render(base, cand, verdict, rows, notes)
    print(report)
    if args.markdown:
        Path(args.markdown).write_text(report)
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
