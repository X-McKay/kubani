#!/usr/bin/env python3
"""Inference deployment benchmark: serving latency, throughput, sleep/wake, soak.

Measures the deployment (vLLM version, flags, kernels, image), not the model's
answer quality. Stdlib-only on purpose: it runs inside the vLLM serving image as
an in-cluster Job (run_in_cluster.sh), where nothing can be pip-installed, and
equally from a workstation against port-forwards.

All load goes through the gpu-broker, the path clients use. Sending load
straight to an engine is unsafe: the broker sees no traffic, auto-sleeps the
engine, and requests to a sleeping engine hang forever (vllm#45326).

Output is one JSON document printed between result markers on stdout and
optionally written to --out. compare.py diffs two of them.

    {"schema": 1, "profile", "label", "started_at", "finished_at",
     "target": {...}, "meta": {...}, "suites": {...},
     "metrics": {"perf.c1_short.ttft_p50_ms": 41.2, ...},
     "gates": {"perf.no_errors": true, "soak.no_stalls": true, ...}}

Metric names carry their direction in the suffix: *_ms lower is better, *_tps
higher is better. Gates are hard pass/fail.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import random
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RESULT_BEGIN = "==INFERENCE-BENCH-RESULT-BEGIN=="
RESULT_END = "==INFERENCE-BENCH-RESULT-END=="

# Common English words; filler for synthetic prompts. Token counts are
# calibrated against the live tokenizer, never assumed.
WORDS = (
    "time year people way day man thing woman life child world school state "
    "family student group country problem hand part place case week company "
    "system program question work government number night point home water "
    "room mother area money story fact month lot right study book eye job word "
    "business issue side kind head house service friend father power hour game "
    "line end member law car city community name president team minute idea "
    "kid body information back parent face others level office door health "
    "person art war history party result change morning reason research girl "
    "guy moment air teacher force education river stone light garden window "
    "table paper market field road music color forest island bridge engine"
).split()

# No bytes for this long mid-request is the GB10 EngineCore wedge signature
# (docs/troubleshooting/vllm-main-engine-hang-gb10.md).
STALL_SOCKET_TIMEOUT_S = 60


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return round(ordered[k], 2)


class StallError(Exception):
    """The server went silent mid-request."""


def http_json(method: str, url: str, headers: dict | None = None, timeout: float = 60) -> tuple[int, dict | str]:
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw, status = resp.read().decode(), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read().decode(errors="replace"), exc.code
    try:
        return status, json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return status, raw


def stream(url: str, payload: dict, total_timeout: float) -> dict:
    """POST a streaming completion; return client-side timings."""
    payload = {**payload, "stream": True, "stream_options": {"include_usage": True}}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    chunk_times: list[float] = []
    pieces: list[str] = []
    usage: dict = {}
    try:
        with urllib.request.urlopen(req, timeout=STALL_SOCKET_TIMEOUT_S) as resp:
            for raw in resp:
                if time.perf_counter() - t0 > total_timeout:
                    raise StallError(f"total timeout {total_timeout}s exceeded")
                line = raw.decode().strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    # Keep reading to EOF: hanging up right after [DONE] races the
                    # broker's stream teardown and leaks its in-flight counter
                    # (kubani-gpu-broker proxy.py finally-block ordering).
                    continue
                obj = json.loads(data)
                usage = obj.get("usage") or usage
                for choice in obj.get("choices") or []:
                    if choice.get("text"):
                        chunk_times.append(time.perf_counter())
                        pieces.append(choice["text"])
    except (socket.timeout, TimeoutError) as exc:
        raise StallError(f"no bytes for {STALL_SOCKET_TIMEOUT_S}s") from exc
    t_end = time.perf_counter()
    out_tokens = usage.get("completion_tokens") or len(chunk_times)
    decode_s = (chunk_times[-1] - chunk_times[0]) if len(chunk_times) > 1 else 0
    return {
        "ttft_ms": (chunk_times[0] - t0) * 1000 if chunk_times else None,
        "e2e_ms": (t_end - t0) * 1000,
        "itl_ms": [(b - a) * 1000 for a, b in zip(chunk_times, chunk_times[1:])],
        "decode_tps": (out_tokens - 1) / decode_s if decode_s > 0 else None,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": out_tokens,
        "text": "".join(pieces),
    }


def sane(text: str) -> bool:
    """Catch the corrupted-weights-after-wake failure mode ("!!!!!!!!")."""
    letters = sum(ch.isalpha() for ch in text)
    return bool(text) and letters >= max(1, len(text) // 4) and not re.search(r"(.)\1{15,}", text)


class Bench:
    def __init__(self, profile: dict, broker_url: str, engine_url: str,
                 admin_url: str | None, admin_token: str | None):
        self.p = profile
        self.broker = broker_url.rstrip("/")
        self.engine = engine_url.rstrip("/")
        self.admin = admin_url.rstrip("/") if admin_url else None
        self.admin_token = admin_token
        self.model = profile["served_model"]
        self.timeout = profile["request_timeout_s"]
        self.tokens_per_word = 1.0

    def filler(self, n_tokens: int, rng: random.Random) -> str:
        return " ".join(rng.choice(WORDS) for _ in range(max(1, int(n_tokens / self.tokens_per_word))))

    def calibrate(self) -> None:
        text = self.filler(2000, random.Random(7))
        self.tokens_per_word = self.completion(text, 1)["prompt_tokens"] / len(text.split())
        log(f"calibrated: {self.tokens_per_word:.3f} tokens/word")

    def completion(self, prompt: str, max_tokens: int, ignore_eos: bool = True) -> dict:
        # ignore_eos pins the output length so decode numbers are comparable.
        return stream(f"{self.broker}/v1/completions", {
            "model": self.model, "prompt": prompt, "max_tokens": max_tokens,
            "temperature": 0, "ignore_eos": ignore_eos,
        }, self.timeout)

    def run_perf(self) -> tuple[dict, dict, dict]:
        suite, metrics = {}, {}
        for sc in self.p["perf"]:
            log(f"perf {sc['name']}: c={sc['concurrency']} n={sc['requests']} "
                f"in={sc['prompt_tokens']} out={sc['output_tokens']}")
            rng = random.Random(sc["name"])
            shared = self.filler(sc["prompt_tokens"], rng) if sc.get("shared_prefix") else None

            def prompt(i: int) -> str:
                # A unique leading tag defeats prefix caching unless the
                # scenario deliberately shares the body.
                if shared is not None:
                    return f"{shared}\nPart {i}:"
                return f"[{sc['name']}-{i}-{rng.random():.12f}] " + self.filler(sc["prompt_tokens"], rng)

            prompts = [prompt(i) for i in range(sc["requests"] + 1)]
            self.completion(prompts[0], sc["output_tokens"])  # warmup / prime prefix cache
            results, errors = [], []
            t0 = time.perf_counter()
            with cf.ThreadPoolExecutor(sc["concurrency"]) as pool:
                for f in cf.as_completed([pool.submit(self.completion, pr, sc["output_tokens"]) for pr in prompts[1:]]):
                    try:
                        results.append(f.result())
                    except Exception as exc:  # noqa: BLE001 - recorded, gated below
                        errors.append(repr(exc)[:300])
            wall = time.perf_counter() - t0
            ttft = [r["ttft_ms"] for r in results if r["ttft_ms"] is not None]
            itl = [x for r in results for x in r["itl_ms"]]
            tps = [r["decode_tps"] for r in results if r["decode_tps"]]
            e2e = [r["e2e_ms"] for r in results]
            prompt_tok = [r["prompt_tokens"] for r in results if r["prompt_tokens"]]
            row = {
                "ttft_p50_ms": pct(ttft, 50), "ttft_p95_ms": pct(ttft, 95),
                "itl_p50_ms": pct(itl, 50), "itl_p95_ms": pct(itl, 95),
                "e2e_p50_ms": pct(e2e, 50), "e2e_p95_ms": pct(e2e, 95),
                "decode_p50_tps": pct(tps, 50),
                "agg_output_tps": round(sum(r["completion_tokens"] for r in results) / wall, 2) if results else None,
            }
            metrics.update({f"perf.{sc['name']}.{k}": v for k, v in row.items() if v is not None})
            metrics[f"perf.{sc['name']}.errors_count"] = len(errors)
            suite[sc["name"]] = {"params": sc, "ok": len(results), "errors": errors,
                                 "prompt_tokens_mean": round(sum(prompt_tok) / len(prompt_tok)) if prompt_tok else None,
                                 **row}
            log(f"  ttft p50={row['ttft_p50_ms']}ms itl p50={row['itl_p50_ms']}ms "
                f"decode={row['decode_p50_tps']}tok/s agg={row['agg_output_tps']}tok/s errors={len(errors)}")
        gates = {"perf.no_errors": all(not r["errors"] for r in suite.values())}
        return suite, metrics, gates

    def admin_call(self, method: str, path: str) -> tuple[int, dict | str]:
        return http_json(method, f"{self.admin}{path}",
                         headers={"Authorization": f"Bearer {self.admin_token}"}, timeout=180)

    def run_sleepwake(self, cycles: int) -> tuple[dict, dict, dict]:
        if not (self.admin and self.admin_token):
            raise SystemExit("sleepwake suite needs --admin-url and GPU_BROKER_ADMIN_TOKEN")
        eng = self.p["broker_engine"]
        probe = "The three primary colors of light are"
        # The broker refuses manual sleep while it counts requests in flight.
        # A counter that never drains is a broker leak, not load: say so.
        for _ in range(12):
            _, snap = self.admin_call("GET", "/internal/v1/engines")
            stuck = snap.get(eng, {}).get("in_flight", 0) if isinstance(snap, dict) else 0
            if not stuck:
                break
            time.sleep(5)
        else:
            log(f"broker reports {stuck} in flight with no bench load for 60s: leaked counter; "
                f"restart the {self.p['broker_deployment']} pod and rerun")
            return {"cycles": [], "error": f"broker in_flight stuck at {stuck}"}, {}, \
                {"sleepwake.all_cycles_completed": False, "sleepwake.output_sane_after_wake": False}
        rows = []
        for i in range(cycles):
            deadline = time.time() + 120
            while True:  # broker refuses (409) while inside min_awake_seconds
                t0 = time.perf_counter()
                status, body = self.admin_call("POST", f"/internal/v1/engines/{eng}/sleep?level=1")
                if status != 409 or time.time() > deadline:
                    break
                time.sleep(10)
            sleep_ms = (time.perf_counter() - t0) * 1000
            if status >= 300:
                rows.append({"cycle": i, "error": f"sleep HTTP {status}: {str(body)[:200]}"})
                break
            _, is_sleeping = http_json("GET", f"{self.engine}/is_sleeping", timeout=30)
            # Transparent wake: the broker wakes the engine on this request.
            r = self.completion(probe, 16, ignore_eos=False)
            rows.append({"cycle": i, "sleep_ms": round(sleep_ms, 1), "engine_reported_sleeping": is_sleeping,
                         "wake_ttft_ms": round(r["ttft_ms"] or 0, 1), "wake_e2e_ms": round(r["e2e_ms"], 1),
                         "output_sane": sane(r["text"]), "text": r["text"][:80]})
            log(f"sleepwake cycle {i}: sleep={sleep_ms:.0f}ms wake+ttft={r['ttft_ms']:.0f}ms sane={sane(r['text'])}")
            time.sleep(5)
        self.admin_call("POST", f"/internal/v1/engines/{eng}/wake")
        done = [r for r in rows if "sleep_ms" in r]
        metrics = {}
        if done:
            metrics["sleepwake.sleep_p50_ms"] = pct([r["sleep_ms"] for r in done], 50)
            metrics["sleepwake.wake_ttft_p50_ms"] = pct([r["wake_ttft_ms"] for r in done], 50)
        gates = {"sleepwake.all_cycles_completed": len(done) == cycles,
                 "sleepwake.output_sane_after_wake": bool(done) and all(r["output_sane"] for r in done)}
        return {"cycles": rows}, metrics, gates

    def run_soak(self, seconds: int) -> tuple[dict, dict, dict]:
        cfg = self.p["soak"]
        log(f"soak: {seconds}s at c={cfg['concurrency']} in={cfg['prompt_tokens']} out={cfg['output_tokens']}")
        stop = time.time() + seconds
        lock = threading.Lock()
        st = {"ok": 0, "errors": [], "stalls": [], "tokens": 0, "e2e": [], "minute_tokens": {}}
        t_start = time.time()

        def worker(wid: int) -> None:
            rng = random.Random(f"soak-{wid}")
            n = 0
            while time.time() < stop:
                prompt = f"[soak-{wid}-{n}] " + self.filler(cfg["prompt_tokens"], rng)
                n += 1
                try:
                    r = self.completion(prompt, cfg["output_tokens"])
                    with lock:
                        st["ok"] += 1
                        st["tokens"] += r["completion_tokens"]
                        st["e2e"].append(r["e2e_ms"])
                        minute = int((time.time() - t_start) // 60)
                        st["minute_tokens"][minute] = st["minute_tokens"].get(minute, 0) + r["completion_tokens"]
                except StallError as exc:
                    with lock:
                        st["stalls"].append(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} worker {wid}: {exc}")
                    log(f"STALL worker {wid}: {exc} -- see docs/troubleshooting/vllm-main-engine-hang-gb10.md")
                    return  # a wedged engine does not recover; stop this worker
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        st["errors"].append(repr(exc)[:300])

        with cf.ThreadPoolExecutor(cfg["concurrency"]) as pool:
            list(pool.map(worker, range(cfg["concurrency"])))
        elapsed = time.time() - t_start
        full_minutes = [v for k, v in st["minute_tokens"].items() if (k + 1) * 60 <= elapsed]
        suite = {"config": cfg, "seconds": round(elapsed), "requests_ok": st["ok"],
                 "error_count": len(st["errors"]), "errors": st["errors"][:20], "stalls": st["stalls"],
                 "e2e_max_ms": round(max(st["e2e"]), 1) if st["e2e"] else None,
                 "min_minute_output_tokens": min(full_minutes) if full_minutes else None}
        metrics = {"soak.agg_output_tps": round(st["tokens"] / elapsed, 2) if elapsed else 0}
        if st["e2e"]:
            metrics["soak.e2e_p99_ms"] = pct(st["e2e"], 99)
        gates = {"soak.no_stalls": not st["stalls"], "soak.no_errors": not st["errors"]}
        log(f"soak done: ok={st['ok']} errors={len(st['errors'])} stalls={len(st['stalls'])}")
        return suite, metrics, gates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--profiles", default=str(Path(__file__).with_name("profiles.json")))
    ap.add_argument("--label", required=True, help="e.g. baseline-v0.27.1, candidate-v0.30.0, drift")
    ap.add_argument("--suites", default="perf,sleepwake,soak")
    ap.add_argument("--broker-url", help="override the profile's broker URL")
    ap.add_argument("--engine-url", help="override the profile's engine URL (read-only probes only)")
    ap.add_argument("--admin-url", help="broker admin listener, e.g. http://<broker-pod-ip>:8081")
    ap.add_argument("--sleep-cycles", type=int, default=3)
    ap.add_argument("--soak-seconds", type=int, default=900)
    ap.add_argument("--out")
    args = ap.parse_args()

    profile = json.loads(Path(args.profiles).read_text())["profiles"][args.profile]
    bench = Bench(profile, args.broker_url or profile["broker_url"], args.engine_url or profile["engine_url"],
                  args.admin_url, os.environ.get("GPU_BROKER_ADMIN_TOKEN"))
    result: dict = {"schema": 1, "profile": args.profile, "label": args.label,
                    "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "meta": json.loads(os.environ.get("BENCH_META_JSON") or "{}"),
                    "suites": {}, "metrics": {}, "gates": {}}
    _, version = http_json("GET", f"{bench.engine}/version", timeout=30)
    result["target"] = {"broker_url": bench.broker, "engine_url": bench.engine, "model": bench.model,
                        "engine_version": version}
    log(f"target {bench.model} vllm={version} via {bench.broker}")
    bench.calibrate()

    runners = {"perf": bench.run_perf,
               "sleepwake": lambda: bench.run_sleepwake(args.sleep_cycles),
               "soak": lambda: bench.run_soak(args.soak_seconds)}
    for name in (s.strip() for s in args.suites.split(",") if s.strip()):
        if name not in runners:
            raise SystemExit(f"unknown suite {name} (have: {', '.join(runners)})")
        suite, metrics, gates = runners[name]()
        result["suites"][name] = suite
        result["metrics"].update(metrics)
        result["gates"].update(gates)

    result["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    doc = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(doc + "\n")
    print(RESULT_BEGIN)
    print(doc)
    print(RESULT_END)
    failed = [k for k, v in result["gates"].items() if not v]
    log("gates: " + ("ALL PASS" if not failed else "FAILED " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
