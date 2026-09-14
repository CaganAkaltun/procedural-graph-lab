#!/usr/bin/env python3
"""PG-Lite dashboard — zero-dependency live monitor.

    python dashboard/server.py            # http://127.0.0.1:8777
    python dashboard/server.py --runs runs --port 8777

Reads the JSONL files written by pg/telemetry.py and serves an aggregated view.
Nothing is cached: every poll re-reads the files, so you can watch a run in
progress, kill it, restart it, and the page keeps working.

Only the Python standard library is used, so this runs on a fresh machine with
nothing installed but Python 3.10+.
"""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.path.join(os.path.dirname(HERE), "runs")


# --------------------------------------------------------------------- data --
def list_runs(runs_dir: str) -> List[Dict[str, Any]]:
    if not os.path.isdir(runs_dir):
        return []
    out = []
    for name in sorted(os.listdir(runs_dir), reverse=True):
        if not name.endswith(".jsonl"):
            continue
        path = os.path.join(runs_dir, name)
        st = os.stat(path)
        label, finished, n = name[:-6], False, 0
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    n += 1
                    if '"event": "run_start"' in line or '"event":"run_start"' in line:
                        try:
                            label = json.loads(line).get("label", label)
                        except json.JSONDecodeError:
                            pass
                    if '"event": "run_end"' in line or '"event":"run_end"' in line:
                        finished = True
        except OSError:
            continue
        out.append({"id": name[:-6], "label": label, "events": n,
                    "finished": finished, "mtime": st.st_mtime,
                    "size_kb": round(st.st_size / 1024, 1)})
    return out


def read_events(runs_dir: str, run_id: str) -> List[Dict[str, Any]]:
    path = os.path.join(runs_dir, f"{run_id}.jsonl")
    events = []
    if not os.path.exists(path):
        return events
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # partially written last line while a run is live
    return events


def aggregate(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    arms: Dict[str, Dict[str, Any]] = {}
    evo: List[Dict[str, Any]] = []
    config: Dict[str, Any] = {}
    started = finished = False
    elapsed = 0.0

    for e in events:
        elapsed = max(elapsed, e.get("elapsed", 0.0))
        ev = e.get("event")
        if ev == "run_start":
            config = e.get("config", {})
            started = True
        elif ev == "run_end":
            finished = True
        elif ev == "arm_start":
            arms.setdefault(e["arm"], _blank_arm(e.get("name", e["arm"])))
            arms[e["arm"]]["planned"] = e.get("n_tasks", 0)
        elif ev == "episode_end":
            a = arms.setdefault(e["arm"], _blank_arm(e["arm"]))
            a["episodes"].append({"task": e.get("task_id"), "score": e.get("score", 0),
                                  "steps": e.get("steps", 0), "tokens": e.get("tokens", 0),
                                  "blocks": e.get("guard_blocks", 0),
                                  "elapsed": e.get("elapsed", 0)})
            a["tokens"] += e.get("tokens", 0)
            a["blocks"] += e.get("guard_blocks", 0)
            a["repeats"] += e.get("repeats", 0)
            loc = e.get("loc") or {}
            if loc:
                a["loc"] = loc
        elif ev == "arm_end":
            a = arms.setdefault(e["arm"], _blank_arm(e["arm"]))
            a["final"] = {k: v for k, v in e.items()
                          if k in ("success", "avg_steps", "tokens", "cost_usd",
                                   "guard_blocks", "repeats", "n")}
            a["done"] = True
        elif ev == "evo_round":
            evo.append({"round": e.get("round"), "decision": e.get("decision"),
                        "cand": e.get("cand"), "retained": e.get("retained"),
                        "diff": (e.get("diff") or {}).get("diff"),
                        "graph": e.get("graph_stats") or {}})

    for name, a in arms.items():
        eps = a["episodes"]
        a["n"] = len(eps)
        a["success"] = round(sum(x["score"] for x in eps) / len(eps), 4) if eps else None
        a["avg_steps"] = round(sum(x["steps"] for x in eps) / len(eps), 2) if eps else None
        a["progress"] = round(len(eps) / a["planned"], 3) if a.get("planned") else 0
        a["succ_per_1k"] = (round(a["success"] / (a["tokens"] / 1000), 4)
                            if a["success"] is not None and a["tokens"] else None)
        a["curve"] = _running_mean([x["score"] for x in eps])
        a.pop("episodes_full", None)

    return {"config": config, "arms": arms, "evolution": evo,
            "started": started, "finished": finished, "elapsed": round(elapsed, 1)}


def _blank_arm(name: str) -> Dict[str, Any]:
    return {"name": name, "episodes": [], "tokens": 0, "blocks": 0, "repeats": 0,
            "loc": {}, "final": {}, "done": False, "planned": 0}


def _running_mean(scores: List[float]) -> List[float]:
    out, total = [], 0.0
    for i, s in enumerate(scores, 1):
        total += s
        out.append(round(total / i, 4))
    return out


# ------------------------------------------------------------------ server --
class Handler(BaseHTTPRequestHandler):
    runs_dir = RUNS_DIR

    def log_message(self, *_args):  # silence per-request logging
        return

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")

        if parsed.path == "/api/runs":
            data = {"runs": list_runs(self.runs_dir), "dir": self.runs_dir}
            return self._send(200, json.dumps(data).encode(), "application/json")

        if parsed.path == "/api/run":
            run_id = (qs.get("id") or [""])[0]
            if not run_id:
                runs = list_runs(self.runs_dir)
                if not runs:
                    return self._send(200, b'{"empty": true}', "application/json")
                run_id = runs[0]["id"]
            payload = aggregate(read_events(self.runs_dir, run_id))
            payload["id"] = run_id
            return self._send(200, json.dumps(payload).encode(), "application/json")

        if parsed.path == "/api/tail":
            run_id = (qs.get("id") or [""])[0]
            n = int((qs.get("n") or ["40"])[0])
            events = read_events(self.runs_dir, run_id)[-n:]
            return self._send(200, json.dumps({"events": events}).encode(),
                              "application/json")

        self._send(404, b"not found", "text/plain")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=RUNS_DIR)
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    Handler.runs_dir = os.path.abspath(args.runs)
    os.makedirs(Handler.runs_dir, exist_ok=True)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"PG-Lite dashboard -> http://{args.host}:{args.port}")
    print(f"watching {Handler.runs_dir}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
