"""Offline refiner: propose Delta-G from contrasted trajectories.

Adds edge-level credit assignment (idea I5) to the paper's prompt: the refiner
is told which edges were actually active and how they correlate with success,
instead of being handed raw trajectories only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .graph import ProceduralGraph
from .runner import EpisodeResult

REFINER_PROMPT = """You are optimizing a Procedural Graph for an agent.

Task context: {task}
Refinement mode: {mode}
Available tool actions (ACTION nodes must match one of these): {tools}

Current Procedural Graph (JSON):
{graph_json}

Edge-level credit report (visits, success rate conditioned on visiting,
lift over the base rate; unvisited edges are prune candidates):
{credit}

High-scoring trajectories:
{good}

Low-scoring trajectories:
{bad}

Previously rejected candidates (do not repeat these edits):
{rejected}

Propose edits. Rules:
1. ACTION nodes must match the available tool list.
2. Give every added edge a `condition` (or null), a `guidance` string and a
   `pitfalls` string.
3. Optionally add a `guard` object to enforce a hard precondition, e.g.
   {{"kind": "require_before", "tool": "Submit", "requires": ["Verify"]}}
4. Stay general; do not overfit to one trajectory.
5. Preserve existing node ids. Every node must have a directed path to a
   terminal node.

Output ONLY a raw JSON block:
{{"add_nodes": [...], "delete_nodes": [...], "add_edges": [...], "delete_edges": [...]}}
"""


@dataclass
class RejectionRecord:
    round: int
    delta: Dict[str, Any]
    reason: str
    score: Optional[float] = None


@dataclass
class RejectionMemory:
    records: List[RejectionRecord] = field(default_factory=list)

    def add(self, rec: RejectionRecord) -> None:
        self.records.append(rec)

    def serialize(self, max_records: int = 5) -> str:
        if not self.records:
            return "(none)"
        out = []
        for r in self.records[-max_records:]:
            out.append(f"- round {r.round}: {r.reason}"
                       + (f" (val={r.score:.3f})" if r.score is not None else "")
                       + f" edits={json.dumps(r.delta)[:400]}")
        return "\n".join(out)

    def contains_similar(self, delta: Dict[str, Any]) -> bool:
        sig = _delta_signature(delta)
        return any(_delta_signature(r.delta) == sig for r in self.records)


def _delta_signature(delta: Dict[str, Any]) -> str:
    parts = []
    for key in ("add_nodes", "delete_nodes", "add_edges", "delete_edges"):
        items = delta.get(key) or []
        norm = sorted(json.dumps(
            {k: v for k, v in i.items() if k in ("id", "source", "target", "relation")}
            if isinstance(i, dict) else i, sort_keys=True) for i in items)
        parts.append(f"{key}:{norm}")
    return "|".join(parts)


def tail_tokens(text: str, max_tokens: int = 6000) -> str:
    """Keep the END of the trajectory context (paper's Tail_{L_max})."""
    max_chars = max_tokens * 4
    return text if len(text) <= max_chars else text[-max_chars:]


def format_episodes(episodes: List[EpisodeResult], limit: int = 3) -> str:
    if not episodes:
        return "(none)"
    blocks = []
    for ep in episodes[:limit]:
        lines = [f"[task {ep.task_id}] score={ep.score} steps={ep.steps}"]
        for a, o in ep.trajectory[-8:]:
            lines.append(f"  Action: {a} | Obs: {o[:160]}")
        blocks.append("\n".join(lines))
    return tail_tokens("\n".join(blocks))


def parse_delta(text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Extract the JSON edit block; returns (delta, error)."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        return None, "no JSON object found"
    try:
        delta = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        return None, f"json decode error: {exc}"
    for key in ("add_nodes", "delete_nodes", "add_edges", "delete_edges"):
        delta.setdefault(key, [])
        if not isinstance(delta[key], list):
            return None, f"field {key} is not a list"
    return delta, None


def propose_edits(llm, graph: ProceduralGraph, episodes: List[EpisodeResult],
                  task: str, tools: List[str], memory: RejectionMemory,
                  mode: str = "scratch_incremental", threshold: float = 0.5
                  ) -> Tuple[Optional[Dict[str, Any]], Optional[str], str]:
    good = [e for e in episodes if e.score >= threshold]
    bad = [e for e in episodes if e.score < threshold]
    credit = graph.credit_report([e.visited_edges for e in episodes],
                                 [e.score for e in episodes])
    credit_txt = "\n".join(
        f"- {r['edge']}: visits={r['visits']} cond={r['cond_success']} lift={r['lift']}"
        for r in credit[:12]) or "(no edges)"

    prompt = REFINER_PROMPT.format(
        task=task, mode=mode, tools=", ".join(tools),
        graph_json=json.dumps(graph.to_dict(), ensure_ascii=False)[:6000],
        credit=credit_txt,
        good=format_episodes(good), bad=format_episodes(bad),
        rejected=memory.serialize(),
    )
    raw = llm.complete(prompt, role="refiner", max_tokens=4096)
    delta, err = parse_delta(raw)
    return delta, err, raw
