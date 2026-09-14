"""Generative guidance with selective triggering and caching (idea I2).

Arms implemented here:

  none          -> A0, vanilla ReAct
  advisor       -> A1, graph-free advisor (the control the paper is missing)
  full_raw      -> full graph text injected verbatim (Table 3 row 2)
  full_gen      -> guidance LLM reads the full graph (Table 3 row 3)
  subgraph_gen  -> guidance LLM reads N_h(u_t) (Table 3 row 4 = the paper)

`selective=True` turns any generative arm into its PG-Lite variant: guidance is
regenerated only when the situation actually changed. Everything else is served
from cache at zero token cost.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .graph import ProceduralGraph
from .localize import Localizer, LocalizationResult

ERROR_MARKERS = ("error", "invalid", "failed", "rejected", "not found",
                 "traceback", "exception", "denied", "hata")

GUIDANCE_PROMPT = """You are an execution guide for an AI agent solving the task: {task}

Here is {scope}:
{graph_context}

Current active query / observation:
{observation}

Recent execution trajectory:
{trajectory}

Using the condition, guidance and pitfalls attributes of the transitions above,
state exactly what the agent should do next, what to avoid, and how to recover
from any recent failure. Begin your answer with a single line of the form
`NEXT: <node_id>` naming the procedure to run next."""

ADVISOR_PROMPT = """You are an execution advisor for an AI agent solving the task: {task}

Current active query / observation:
{observation}

Recent execution trajectory:
{trajectory}

State exactly what the agent should do next, what to avoid, and how to recover
from any recent failure."""


@dataclass
class GuidanceConfig:
    mode: str = "subgraph_gen"     # none | advisor | full_raw | full_gen | subgraph_gen
    selective: bool = False        # PG-Lite trigger policy
    hops: int = 2                  # h in the paper
    window: int = 3                # w in the paper
    staleness: int = 4             # regenerate after this many reused steps
    localizer_mode: str = "exact"  # exact (paper) | soft (PG-Lite, idea I3)
    guards: bool = False           # Guard-PG (idea I4)
    name: str = "custom"


ARMS: Dict[str, GuidanceConfig] = {
    "A0": GuidanceConfig(mode="none", name="A0 vanilla ReAct"),
    "A1": GuidanceConfig(mode="advisor", name="A1 graph-free advisor"),
    "A2": GuidanceConfig(mode="subgraph_gen", localizer_mode="exact",
                         name="A2 PG (paper replication)"),
    "A3": GuidanceConfig(mode="subgraph_gen", selective=True, localizer_mode="exact",
                         name="A3 PG + selective/cached guidance"),
    "A4": GuidanceConfig(mode="subgraph_gen", selective=True, localizer_mode="soft",
                         name="A4 PG-Lite (selective + SoftMatch)"),
    "A5": GuidanceConfig(mode="subgraph_gen", selective=True, localizer_mode="soft",
                         guards=True, name="A5 PG-Lite + guards"),
    "FULL_RAW": GuidanceConfig(mode="full_raw", name="full graph, raw injection"),
    "FULL_GEN": GuidanceConfig(mode="full_gen", name="full graph, generative"),
}


@dataclass
class GuidanceStep:
    text: str
    node: Optional[str]
    stage: str
    regenerated: bool
    reason: str
    active_edges: List[Tuple[str, str, str]] = field(default_factory=list)


class GuidanceManager:
    def __init__(self, graph: ProceduralGraph, llm, cfg: GuidanceConfig):
        self.graph = graph
        self.llm = llm
        self.cfg = cfg
        self.localizer = Localizer(graph, mode=cfg.localizer_mode)
        self._cache: Dict[str, str] = {}
        self._prev_node: Optional[str] = None
        self._age = 0
        self.trigger_counts: Counter = Counter()
        self.cache_hits = 0
        self.cache_misses = 0

    # ------------------------------------------------------------ lifecycle --
    def reset_episode(self) -> None:
        self._cache.clear()
        self._prev_node = None
        self._age = 0

    def rebind(self, graph: ProceduralGraph) -> None:
        self.graph = graph
        self.localizer.rebind(graph)
        self.reset_episode()

    # ------------------------------------------------------------------ api --
    def step(self, task: str, trajectory: List[Tuple[str, str]],
             last_action: Optional[str], last_obs: str, task_id: str = "") -> GuidanceStep:
        if self.cfg.mode == "none":
            return GuidanceStep("", None, "n/a", False, "disabled")

        loc = self.localizer.locate(last_action, last_obs, self._prev_node)
        active_edges = [e.key for _, e in self.graph.neighborhood(loc.node or "", 1)]

        if self.cfg.mode == "full_raw":
            return GuidanceStep(self.graph.serialize_full(), loc.node, loc.stage,
                                False, "static", active_edges)

        regenerate, reason = self._should_regenerate(loc, last_obs)
        key = self._cache_key(task_id, loc, last_obs)

        if not regenerate and key in self._cache:
            self.cache_hits += 1
            self._age += 1
            self.trigger_counts["cached"] += 1
            self._prev_node = loc.node
            return GuidanceStep(self._cache[key], loc.node, loc.stage, False,
                                "cache", active_edges)

        self.cache_misses += 1
        self.trigger_counts[reason] += 1
        text = self._generate(task, trajectory, loc, last_obs)
        self._cache[key] = text
        self._age = 0
        self._prev_node = loc.node
        return GuidanceStep(text, loc.node, loc.stage, True, reason, active_edges)

    # ------------------------------------------------------------- internals --
    def _should_regenerate(self, loc: LocalizationResult, last_obs: str) -> Tuple[bool, str]:
        if not self.cfg.selective:
            return True, "always"
        if self._prev_node is None:
            return True, "first_step"
        if loc.changed:
            return True, "node_changed"
        if self._has_error(last_obs):
            return True, "error_observed"
        if loc.node and self.graph.out_degree(loc.node) > 1 and \
                not self._condition_matches(loc.node, last_obs):
            return True, "ambiguous_branch"
        if self._age >= self.cfg.staleness:
            return True, "stale"
        return False, "cached"

    @staticmethod
    def _has_error(obs: str) -> bool:
        low = (obs or "").lower()
        return any(m in low for m in ERROR_MARKERS)

    def _condition_matches(self, node: str, obs: str) -> bool:
        low = (obs or "").lower()
        for e in self.graph.out_edges(node):
            if e.condition and any(tok in low for tok in e.condition.lower().split()[:4]):
                return True
        return False

    def _cache_key(self, task_id: str, loc: LocalizationResult, last_obs: str) -> str:
        raw = f"{task_id}|{loc.node}|{int(self._has_error(last_obs))}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def _generate(self, task: str, trajectory: List[Tuple[str, str]],
                  loc: LocalizationResult, last_obs: str) -> str:
        traj = "\n".join(f"Action: {a}\nObservation: {o}"
                         for a, o in trajectory[-self.cfg.window:])
        if self.cfg.mode == "advisor":
            prompt = ADVISOR_PROMPT.format(task=task, observation=last_obs, trajectory=traj)
            return self.llm.complete(prompt, role="advisor")
        if self.cfg.mode == "full_gen" or loc.node is None:
            scope = "the complete Procedural Graph governing the task"
            ctx = self.graph.serialize_full()
        else:
            scope = "the local neighbourhood of the agent's active procedure"
            ctx = self.graph.serialize_local(loc.node, self.cfg.hops)
        prompt = GUIDANCE_PROMPT.format(task=task, scope=scope, graph_context=ctx,
                                        observation=last_obs, trajectory=traj)
        return self.llm.complete(prompt, role="guidance")

    # ---------------------------------------------------------------- stats --
    def stats(self) -> Dict[str, Any]:
        total = self.cache_hits + self.cache_misses
        return {
            "guidance_calls": self.cache_misses,
            "guidance_steps": total,
            "cache_hit_rate": round(self.cache_hits / total, 3) if total else 0.0,
            "triggers": dict(self.trigger_counts),
            **{f"loc_{k}": v for k, v in self.localizer.stats().items()},
        }
