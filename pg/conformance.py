"""Conformance checking between a Procedural Graph and observed trajectories.

This answers the question the paper never asks: **does the agent actually
follow the graph?**

Process mining's heavy machinery (alignments, pm4py) is unnecessary here,
because a Procedural Graph is a directly-follows graph over a small node set.
For that class of model the standard quality dimensions reduce to simple,
auditable counts:

    fitness    = observed transitions that the graph permits / all observed
                 transitions                     ("does the log fit the model?")
    precision  = graph transitions that were actually taken / all graph
                 transitions                     ("does the model over-permit?")
    compliance = per-episode fitness, so you can correlate following-the-graph
                 with succeeding

Why these three and not just fitness: a maximally permissive graph (every node
connected to every node) scores fitness 1.0 and is worthless. Fitness without
precision is not evidence of anything -- a point the paper's evaluation misses
entirely because it only ever measures downstream task success.

No external dependencies. If you later want alignment-based conformance, swap
in pm4py behind the same interface.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .graph import ProceduralGraph


@dataclass
class ConformanceReport:
    fitness: float
    precision: float
    f1: float
    n_transitions: int
    n_allowed: int
    unobserved_edges: List[str] = field(default_factory=list)
    violating_transitions: List[Tuple[str, str, int]] = field(default_factory=list)
    per_episode_fitness: List[float] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "fitness": round(self.fitness, 4),
            "precision": round(self.precision, 4),
            "f1": round(self.f1, 4),
            "n_transitions": self.n_transitions,
            "n_unobserved_edges": len(self.unobserved_edges),
            "top_violations": self.violating_transitions[:5],
        }


def _to_node_sequence(actions: Sequence[str], graph: ProceduralGraph,
                      localizer=None) -> List[str]:
    """Map a raw action sequence onto graph nodes.

    With no localizer, exact node-id matching is used and unmatched actions are
    dropped -- which is itself informative: the drop rate is the fraction of the
    trajectory the paper's Match() cannot see at all.
    """
    out = []
    prev = None
    for a in actions:
        head = (a or "").split("(")[0].strip()
        if localizer is not None:
            res = localizer.locate(head, "", prev)
            node = res.node
        else:
            node = head if head in graph.nodes else None
        if node is not None:
            out.append(node)
            prev = node
    return out


def check(graph: ProceduralGraph,
          episodes: Iterable[Sequence[str]],
          localizer=None) -> ConformanceReport:
    """`episodes` is an iterable of action-name sequences (one per episode)."""
    allowed = {(e.source, e.target) for e in graph.edges}
    observed: Counter = Counter()
    per_ep: List[float] = []
    total = fitting = 0

    for actions in episodes:
        seq = _to_node_sequence(actions, graph, localizer)
        ep_total = ep_fit = 0
        for u, v in zip(seq, seq[1:]):
            if u == v:
                continue                      # self-repetition is not a transition
            observed[(u, v)] += 1
            ep_total += 1
            if (u, v) in allowed:
                ep_fit += 1
        total += ep_total
        fitting += ep_fit
        if ep_total:
            per_ep.append(ep_fit / ep_total)

    fitness = fitting / total if total else 0.0
    used = {k for k in observed if k in allowed}
    precision = len(used) / len(allowed) if allowed else 0.0
    f1 = (2 * fitness * precision / (fitness + precision)
          if (fitness + precision) else 0.0)

    unobserved = [f"{s} -> {t}" for (s, t) in sorted(allowed - used)]
    violations = sorted(((u, v, c) for (u, v), c in observed.items()
                         if (u, v) not in allowed),
                        key=lambda x: -x[2])

    return ConformanceReport(fitness=fitness, precision=precision, f1=f1,
                             n_transitions=total, n_allowed=len(allowed),
                             unobserved_edges=unobserved,
                             violating_transitions=violations,
                             per_episode_fitness=per_ep)


def compliance_vs_outcome(graph: ProceduralGraph,
                          episodes: Sequence[Sequence[str]],
                          scores: Sequence[float],
                          localizer=None) -> Dict[str, Any]:
    """Does following the graph correlate with succeeding?

    This is the diagnostic that decides how to read the whole experiment:

      high compliance + high success  -> the graph plausibly steers behaviour
      low  compliance + high success  -> the gain cannot come from the topology
                                         (supports the shuffled-graph control)
      high compliance + low  success  -> the graph is followed but wrong
    """
    rep = check(graph, episodes, localizer)
    per_ep = []
    for actions in episodes:
        r = check(graph, [actions], localizer)
        per_ep.append(r.fitness)

    hi = [s for f, s in zip(per_ep, scores) if f >= 0.8]
    lo = [s for f, s in zip(per_ep, scores) if f < 0.8]
    return {
        **rep.summary(),
        "mean_compliance": round(sum(per_ep) / len(per_ep), 4) if per_ep else 0.0,
        "success_high_compliance": round(sum(hi) / len(hi), 4) if hi else None,
        "success_low_compliance": round(sum(lo) / len(lo), 4) if lo else None,
        "n_high": len(hi), "n_low": len(lo),
        "compliance_gap": (round(sum(hi) / len(hi) - sum(lo) / len(lo), 4)
                           if hi and lo else None),
    }
