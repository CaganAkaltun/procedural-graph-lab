"""Run telemetry: append-only JSONL that the dashboard tails.

One file per run under `runs/`. Every line is a self-contained JSON event, so
the dashboard can be started, stopped and restarted at any time, and a crashed
run still leaves a readable trace.

Event types
-----------
run_start    config of the whole run
arm_start    an experimental arm begins
episode_end  one task finished (score, steps, tokens, guards, localization)
arm_end      arm summary (success, tokens, cost, guidance stats)
evo_round    one self-evolution round (decision, candidate vs retained)
note         free-form message
run_end      run finished
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Optional


class RunLogger:
    def __init__(self, run_dir: str = "runs", run_id: Optional[str] = None,
                 label: str = ""):
        os.makedirs(run_dir, exist_ok=True)
        self.run_id = run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
        self.label = label or self.run_id
        self.path = os.path.join(run_dir, f"{self.run_id}.jsonl")
        self._t0 = time.time()

    def emit(self, event: str, **fields: Any) -> None:
        rec: Dict[str, Any] = {
            "ts": round(time.time(), 3),
            "elapsed": round(time.time() - self._t0, 2),
            "run_id": self.run_id,
            "label": self.label,
            "event": event,
        }
        rec.update(fields)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    # convenience wrappers -------------------------------------------------
    def run_start(self, config: Dict[str, Any]) -> None:
        self.emit("run_start", config=config)

    def arm_start(self, arm: str, name: str, n_tasks: int) -> None:
        self.emit("arm_start", arm=arm, name=name, n_tasks=n_tasks)

    def episode_end(self, arm: str, task_id: str, score: float, steps: int,
                    tokens: int, guard_blocks: int, repeats: int,
                    loc: Optional[Dict[str, Any]] = None) -> None:
        self.emit("episode_end", arm=arm, task_id=task_id, score=score, steps=steps,
                  tokens=tokens, guard_blocks=guard_blocks, repeats=repeats,
                  loc=loc or {})

    def arm_end(self, arm: str, summary: Dict[str, Any]) -> None:
        payload = {k: v for k, v in summary.items() if k != "arm"}
        self.emit("arm_end", arm=arm, **payload)

    def evo_round(self, rnd: int, decision: str, cand: Optional[float],
                  retained: Optional[float], diff: Optional[Dict[str, Any]] = None,
                  graph_stats: Optional[Dict[str, Any]] = None) -> None:
        self.emit("evo_round", round=rnd, decision=decision, cand=cand,
                  retained=retained, diff=diff or {}, graph_stats=graph_stats or {})

    def note(self, message: str, **fields: Any) -> None:
        self.emit("note", message=message, **fields)

    def run_end(self, **fields: Any) -> None:
        self.emit("run_end", **fields)


class NullLogger(RunLogger):
    """Drop-in that writes nothing (default when telemetry is disabled)."""

    def __init__(self) -> None:  # noqa: D107
        self.run_id = "null"
        self.label = "null"
        self.path = os.devnull
        self._t0 = time.time()

    def emit(self, event: str, **fields: Any) -> None:  # noqa: D102
        return
