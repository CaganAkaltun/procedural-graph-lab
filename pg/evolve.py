"""Offline self-evolution loop (Algorithm 1) with a more robust validation gate.

Differences from the paper, all deliberate (see report sections 2.4 / 2.6):

  * common random numbers: candidate and retained graph are evaluated on the
    *same* validation task list, so the comparison is paired;
  * two-stage sequential gate: obviously-bad candidates are rejected after a
    handful of episodes instead of a full rollout;
  * the retained score and the last-evaluated score are tracked separately and
    both are logged, so a rejected candidate can never masquerade as the
    current checkpoint in the results table.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .graph import ProceduralGraph
from .guidance import GuidanceConfig
from .refiner import RejectionMemory, RejectionRecord, propose_edits
from .runner import EpisodeResult, run_arm
from .stats import paired_bootstrap, sequential_gate
from .telemetry import NullLogger, RunLogger


@dataclass
class RoundLog:
    round: int
    decision: str                 # accept | reject | invalid | duplicate
    reason: str = ""
    train_score: Optional[float] = None
    cand_val_score: Optional[float] = None
    retained_val_score: Optional[float] = None
    diff: Optional[Dict[str, float]] = None
    delta: Optional[Dict[str, Any]] = None
    graph_stats: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvolutionResult:
    graph: ProceduralGraph
    history: List[RoundLog]
    retained_score: float

    def to_json(self) -> str:
        return json.dumps({
            "retained_score": self.retained_score,
            "graph": self.graph.to_dict(),
            "history": [vars(h) for h in self.history],
        }, indent=2, ensure_ascii=False)


def evolve(graph0: ProceduralGraph, llm, env_factory: Callable[[], Any],
           train_ids: List[str], val_ids: List[str], cfg: GuidanceConfig,
           task_desc: str, tools: List[str], rounds: int = 5,
           batch_size: int = 10, allow_cycles: bool = True,
           max_steps: int = 20, verbose: bool = True,
           logger: Optional[RunLogger] = None) -> EvolutionResult:

    log = logger or NullLogger()
    retained = graph0.copy()
    val0 = run_arm(env_factory, val_ids, llm, retained, cfg, max_steps,
                   logger=log, arm_id="evo/baseline-val")
    retained_scores = [val0["per_task"][t] for t in val_ids]
    retained_score = val0["success"]
    memory = RejectionMemory()
    history: List[RoundLog] = []

    if verbose:
        print(f"[gate] baseline validation score = {retained_score:.3f}")

    for k in range(1, rounds + 1):
        start = ((k - 1) * batch_size) % max(len(train_ids), 1)
        batch = (train_ids * 2)[start:start + batch_size]

        train = run_arm(env_factory, batch, llm, retained, cfg, max_steps,
                        logger=log, arm_id=f"evo/round{k}-train")
        episodes: List[EpisodeResult] = train["episodes"]

        delta, err, _raw = propose_edits(llm, retained, episodes, task_desc, tools, memory)
        if delta is None:
            memory.add(RejectionRecord(k, {}, f"unparseable edits: {err}"))
            history.append(RoundLog(k, "invalid", err or "parse failure",
                                    train_score=train["success"],
                                    retained_val_score=retained_score))
            log.evo_round(k, "invalid", None, retained_score)
            if verbose:
                print(f"[round {k}] invalid edit set: {err}")
            continue

        if memory.contains_similar(delta):
            history.append(RoundLog(k, "duplicate", "edit already rejected",
                                    train_score=train["success"],
                                    retained_val_score=retained_score,
                                    delta=delta))
            log.evo_round(k, "duplicate", None, retained_score)
            if verbose:
                print(f"[round {k}] duplicate of a previously rejected edit -> skip")
            continue

        candidate, diag = retained.apply_edits(delta, allow_cycles=allow_cycles)
        if not diag.ok:
            memory.add(RejectionRecord(k, delta, "structural: " + "; ".join(diag.errors)))
            history.append(RoundLog(k, "invalid", "; ".join(diag.errors),
                                    train_score=train["success"],
                                    retained_val_score=retained_score, delta=delta))
            log.evo_round(k, "invalid", None, retained_score)
            if verbose:
                print(f"[round {k}] structurally invalid -> no validation rollout")
            continue

        prev_retained = retained_score
        val = run_arm(env_factory, val_ids, llm, candidate, cfg, max_steps,
                      logger=log, arm_id=f"evo/round{k}-val")
        cand_scores = [val["per_task"][t] for t in val_ids]
        decision, diff = sequential_gate(cand_scores, retained_scores)

        rlog = RoundLog(k, decision, reason="validation gate",
                        train_score=train["success"], cand_val_score=val["success"],
                        retained_val_score=retained_score, diff=diff, delta=delta,
                        graph_stats=candidate.stats())

        if decision == "accept":
            retained, retained_score, retained_scores = candidate, val["success"], cand_scores
            if verbose:
                print(f"[round {k}] ACCEPT  val {rlog.cand_val_score:.3f} "
                      f"(diff {diff['diff']:+.3f}, CI [{diff['ci_low']:+.3f},"
                      f"{diff['ci_high']:+.3f}])")
        else:
            memory.add(RejectionRecord(k, delta, decision, val["success"]))
            if verbose:
                print(f"[round {k}] {decision.upper()}  val {rlog.cand_val_score:.3f} "
                      f"vs retained {retained_score:.3f} (diff {diff['diff']:+.3f})")
        history.append(rlog)
        log.evo_round(k, decision, val["success"], prev_retained, diff,
                      candidate.stats())

    return EvolutionResult(retained, history, retained_score)
