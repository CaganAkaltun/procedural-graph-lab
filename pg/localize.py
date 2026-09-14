"""Localization: Match(a_{t-1}, V).

The paper uses exact string matching of the last procedure to a node id, and
falls back to the *full graph* when that fails -- which its own Table 3 shows
can be worse than no graph at all (ALFWorld 54.48 vs 72.58 baseline).

`SoftMatchLocalizer` implements the three-stage cascade of idea I3:

    exact  ->  typed (alias / tool-signature)  ->  semantic (embedding cosine)
    ->  sticky (keep previous node)            ->  none

and records hit-rate telemetry that the paper never reports.

The default embedder is a dependency-free TF-IDF-ish bag of words so the
scaffold runs anywhere; swap in real sentence embeddings for the real runs.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from .graph import ProceduralGraph

_TOKEN = re.compile(r"[a-z0-9]+")


def _tok(text: str) -> List[str]:
    return _TOKEN.findall((text or "").lower())


class BagOfWordsEmbedder:
    """Deterministic, dependency-free similarity. Replace for production runs."""

    def __init__(self, corpus: List[str]):
        self.df: Counter = Counter()
        for doc in corpus:
            self.df.update(set(_tok(doc)))
        self.n_docs = max(len(corpus), 1)

    def _vec(self, text: str) -> Dict[str, float]:
        tf = Counter(_tok(text))
        if not tf:
            return {}
        out = {}
        for term, count in tf.items():
            idf = math.log((self.n_docs + 1) / (self.df.get(term, 0) + 1)) + 1.0
            out[term] = (count / len(tf)) * idf
        return out

    def similarity(self, a: str, b: str) -> float:
        va, vb = self._vec(a), self._vec(b)
        if not va or not vb:
            return 0.0
        dot = sum(v * vb.get(k, 0.0) for k, v in va.items())
        na = math.sqrt(sum(v * v for v in va.values()))
        nb = math.sqrt(sum(v * v for v in vb.values()))
        return dot / (na * nb) if na and nb else 0.0


@dataclass
class LocalizationResult:
    node: Optional[str]
    stage: str            # exact | typed | semantic | sticky | none
    score: float = 1.0
    changed: bool = False  # did the active node change vs previous step?


class Localizer:
    """mode='exact' reproduces the paper; mode='soft' is PG-Lite (I3)."""

    def __init__(self, graph: ProceduralGraph, mode: str = "exact",
                 aliases: Optional[Dict[str, str]] = None, threshold: float = 0.55,
                 sticky: bool = True):
        self.graph = graph
        self.mode = mode
        self.aliases = {k.lower(): v for k, v in (aliases or {}).items()}
        self.threshold = threshold
        self.sticky = sticky
        self.counts: Counter = Counter()
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        self._lower = {nid.lower(): nid for nid in self.graph.nodes}
        docs = [f"{n.id} {n.description}" for n in self.graph.nodes.values()]
        self._embedder = BagOfWordsEmbedder(docs) if docs else None
        self._docs = {n.id: f"{n.id.replace('_', ' ')} {n.description}"
                      for n in self.graph.nodes.values()}

    def rebind(self, graph: ProceduralGraph) -> None:
        self.graph = graph
        self._rebuild_index()

    # ------------------------------------------------------------------ api --
    def locate(self, last_action: Optional[str], last_observation: str = "",
               prev_node: Optional[str] = None) -> LocalizationResult:
        name = (last_action or "").strip()
        res = self._locate_inner(name, last_observation, prev_node)
        self.counts[res.stage] += 1
        res.changed = res.node != prev_node
        return res

    def _locate_inner(self, name: str, obs: str,
                      prev_node: Optional[str]) -> LocalizationResult:
        if not name:
            return LocalizationResult("Start" if "Start" in self.graph.nodes else None,
                                      "exact" if "Start" in self.graph.nodes else "none")
        head = name.split("(")[0].strip()

        # stage 1: exact (the paper's Match)
        if head in self.graph.nodes:
            return LocalizationResult(head, "exact", 1.0)
        if self.mode == "exact":
            return LocalizationResult(None, "none", 0.0)

        # stage 2: typed / alias / case-insensitive / snake-camel normalisation
        low = head.lower()
        if low in self._lower:
            return LocalizationResult(self._lower[low], "typed", 0.95)
        if low in self.aliases and self.aliases[low] in self.graph.nodes:
            return LocalizationResult(self.aliases[low], "typed", 0.9)
        squashed = low.replace("_", "").replace("-", "")
        for cand_low, cand in self._lower.items():
            if cand_low.replace("_", "") == squashed:
                return LocalizationResult(cand, "typed", 0.85)

        # stage 3: semantic
        if self._embedder is not None:
            probe = f"{head} {name} {obs[:300]}"
            best, best_s = None, 0.0
            for nid, doc in self._docs.items():
                s = self._embedder.similarity(probe, doc)
                if s > best_s:
                    best, best_s = nid, s
            if best is not None and best_s >= self.threshold:
                return LocalizationResult(best, "semantic", round(best_s, 3))

        # stage 4: sticky -- keep the previous node instead of dumping the full
        # graph (Table 3 shows full-graph guidance can be actively harmful).
        if self.sticky and prev_node in self.graph.nodes:
            return LocalizationResult(prev_node, "sticky", 0.5)
        return LocalizationResult(None, "none", 0.0)

    # ---------------------------------------------------------------- stats --
    def stats(self) -> Dict[str, float]:
        total = sum(self.counts.values()) or 1
        hits = self.counts["exact"] + self.counts["typed"] + self.counts["semantic"]
        return {
            "steps": total,
            "hit_rate": round(hits / total, 3),
            "fallback_rate": round((self.counts["sticky"] + self.counts["none"]) / total, 3),
            "hard_fail_rate": round(self.counts["none"] / total, 3),
            **{f"stage_{k}": v for k, v in self.counts.items()},
        }

    def reset_stats(self) -> None:
        self.counts.clear()
