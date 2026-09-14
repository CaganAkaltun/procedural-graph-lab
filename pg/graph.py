"""Procedural Graph: data structure, edit application, structural validation.

Mirrors the formalism of arXiv:2609.09153 (G = (V, R, E, Phi)) and adds two
things the paper does not have:

  * an optional executable `guard` field on each edge (Guard-PG / idea I4)
  * edge-visit bookkeeping so the refiner can do edge-level credit assignment
    (idea I5)

Everything is plain stdlib so the scaffold runs anywhere.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

RELATIONS = ("LEADS_TO", "TRIGGERS", "PROVIDES_INPUT_FOR", "CONVERGES_TO", "REQUIRES")
NODE_TYPES = ("ACTION", "STATUS", "REASONING", "TERMINAL")


@dataclass
class Node:
    id: str
    type: str = "ACTION"
    description: str = ""
    # optional lexical cues used by the semantic localizer (and by the Pi
    # extension, which shares this JSON format)
    cues: List[str] = field(default_factory=list)

    def validate(self) -> List[str]:
        problems = []
        if not self.id:
            problems.append("node with empty id")
        if self.type not in NODE_TYPES:
            problems.append(f"node {self.id}: invalid type {self.type!r}")
        return problems


@dataclass
class Edge:
    source: str
    target: str
    relation: str = "LEADS_TO"
    condition: Optional[str] = None
    guidance: str = ""
    pitfalls: str = ""
    # Guard-PG extension. Example:
    #   {"kind": "require_before", "tool": "submit", "requires": ["verify"]}
    #   {"kind": "forbid_tool",    "tool": "fund_raising_request",
    #    "unless_state": "no_pending_request"}
    guard: Optional[Dict[str, Any]] = None

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.source, self.relation, self.target)

    def validate(self) -> List[str]:
        problems = []
        if self.relation not in RELATIONS:
            problems.append(f"edge {self.source}->{self.target}: unknown relation {self.relation!r}")
        return problems


@dataclass
class GraphDiagnostics:
    """Result of PrepareCandidate (Algorithm 1, step `d_k`)."""

    ok: bool = True
    errors: List[str] = field(default_factory=list)
    repaired_cycles: List[Tuple[str, str]] = field(default_factory=list)

    def __bool__(self) -> bool:  # truthy when the candidate is usable
        return self.ok


class ProceduralGraph:
    def __init__(self, nodes: Iterable[Node] = (), edges: Iterable[Edge] = ()):
        self.nodes: Dict[str, Node] = {n.id: n for n in nodes}
        self.edges: List[Edge] = list(edges)
        # telemetry (idea I5)
        self.edge_visits: Dict[Tuple[str, str, str], int] = defaultdict(int)

    # ------------------------------------------------------------------ io --
    @classmethod
    def skeleton(cls) -> "ProceduralGraph":
        """Minimal init used by the paper's Mode 4/5 ("scratch")."""
        return cls(
            nodes=[Node("Start", "STATUS", "Task received."),
                   Node("End", "TERMINAL", "Task finished.")],
            edges=[Edge("Start", "End", "LEADS_TO", guidance="Solve the task.")],
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProceduralGraph":
        """Tolerant loader: unknown keys are ignored so the same JSON file can
        be shared with the TypeScript Pi extension."""
        nf = {f for f in Node.__dataclass_fields__}
        ef = {f for f in Edge.__dataclass_fields__}
        return cls(
            nodes=[Node(**{k: v for k, v in n.items() if k in nf}) for n in d.get("nodes", [])],
            edges=[Edge(**{k: v for k, v in e.items() if k in ef}) for e in d.get("edges", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [asdict(n) for n in self.nodes.values()],
            "edges": [asdict(e) for e in self.edges],
        }

    @classmethod
    def load(cls, path: str) -> "ProceduralGraph":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)

    def copy(self) -> "ProceduralGraph":
        return ProceduralGraph.from_dict(json.loads(json.dumps(self.to_dict())))

    # -------------------------------------------------------------- queries --
    def out_edges(self, node_id: str) -> List[Edge]:
        return [e for e in self.edges if e.source == node_id]

    def in_edges(self, node_id: str) -> List[Edge]:
        return [e for e in self.edges if e.target == node_id]

    def out_degree(self, node_id: str) -> int:
        return len(self.out_edges(node_id))

    def terminals(self) -> Set[str]:
        return {n for n in self.nodes if self.out_degree(n) == 0}

    def neighborhood(self, node_id: str, hops: int = 2) -> List[Tuple[int, Edge]]:
        """Directed out-neighborhood N_h(u): (hop_index, edge) pairs."""
        if node_id not in self.nodes:
            return []
        seen: Set[str] = {node_id}
        frontier = [node_id]
        out: List[Tuple[int, Edge]] = []
        for hop in range(1, hops + 1):
            nxt: List[str] = []
            for u in frontier:
                for e in self.out_edges(u):
                    out.append((hop, e))
                    if e.target not in seen:
                        seen.add(e.target)
                        nxt.append(e.target)
            frontier = nxt
            if not frontier:
                break
        return out

    def guards_for(self, node_id: str) -> List[Tuple[Edge, Dict[str, Any]]]:
        return [(e, e.guard) for e in self.out_edges(node_id) if e.guard]

    def all_guards(self) -> List[Tuple[Edge, Dict[str, Any]]]:
        return [(e, e.guard) for e in self.edges if e.guard]

    def stats(self) -> Dict[str, Any]:
        visited = sum(1 for e in self.edges if self.edge_visits.get(e.key, 0) > 0)
        return {
            "n_nodes": len(self.nodes),
            "n_edges": len(self.edges),
            "n_guards": len(self.all_guards()),
            "edges_visited": visited,
            "edge_utilization": round(visited / len(self.edges), 3) if self.edges else 0.0,
        }

    # --------------------------------------------------------- serialization --
    def serialize_local(self, active: str, hops: int = 2, max_edges: int = 24) -> str:
        """Paper-style local graph context (Appendix B.5 serializer)."""
        node = self.nodes.get(active)
        if node is None:
            return "Active Cognitive Node: <unknown>\n(no localized context available)"
        lines = [
            f"Active Cognitive Node: [{node.id}] (Type: {node.type})",
            f"Description: {node.description}",
            "",
        ]
        by_hop: Dict[int, List[Edge]] = defaultdict(list)
        for hop, e in self.neighborhood(active, hops)[:max_edges]:
            by_hop[hop].append(e)
        headers = {1: "Immediate Transition Options (Hop 1):", 2: "Subsequent Horizon (Hop 2):"}
        for hop in sorted(by_hop):
            lines.append(headers.get(hop, f"Horizon (Hop {hop}):"))
            for e in by_hop[hop]:
                cond = e.condition if e.condition else "unconditional"
                lines.append(f"- Transition: [{e.source}] -> [{e.target}] (Condition: {cond})")
                if e.guidance:
                    lines.append(f"  * Guidance: {e.guidance}")
                if e.pitfalls:
                    lines.append(f"  * Pitfalls to Avoid: {e.pitfalls}")
                if e.guard:
                    lines.append(f"  * Hard constraint: {json.dumps(e.guard, ensure_ascii=False)}")
            lines.append("")
        return "\n".join(lines).strip()

    def serialize_full(self) -> str:
        lines = ["Full Procedural Graph:"]
        for e in self.edges:
            cond = e.condition if e.condition else "unconditional"
            lines.append(f"- [{e.source}] -{e.relation}-> [{e.target}] (Condition: {cond})")
            if e.guidance:
                lines.append(f"  * Guidance: {e.guidance}")
            if e.pitfalls:
                lines.append(f"  * Pitfalls: {e.pitfalls}")
        return "\n".join(lines)

    # ---------------------------------------------------------------- edits --
    def apply_edits(self, delta: Dict[str, Any], allow_cycles: bool = True
                    ) -> Tuple["ProceduralGraph", GraphDiagnostics]:
        """PrepareCandidate: apply Delta-G to a copy, then run structural checks.

        Order (per paper): delete edges & nodes first, then add nodes & edges.
        `delete_edges` removes every edge with the given (source, target)
        regardless of relation, so attribute revision = delete + re-add.
        """
        diag = GraphDiagnostics()
        g = self.copy()

        try:
            for spec in delta.get("delete_edges", []) or []:
                s, t = spec["source"], spec["target"]
                g.edges = [e for e in g.edges if not (e.source == s and e.target == t)]
            for nid in delta.get("delete_nodes", []) or []:
                g.nodes.pop(nid, None)
                g.edges = [e for e in g.edges if e.source != nid and e.target != nid]
            for spec in delta.get("add_nodes", []) or []:
                n = Node(id=spec["id"], type=spec.get("type", "ACTION"),
                         description=spec.get("description", ""))
                g.nodes[n.id] = n
            for spec in delta.get("add_edges", []) or []:
                g.edges.append(Edge(
                    source=spec["source"], target=spec["target"],
                    relation=spec.get("relation", "LEADS_TO"),
                    condition=spec.get("condition"),
                    guidance=spec.get("guidance", ""),
                    pitfalls=spec.get("pitfalls", ""),
                    guard=spec.get("guard"),
                ))
        except (KeyError, TypeError) as exc:
            diag.ok = False
            diag.errors.append(f"malformed edit: {exc}")
            return g, diag

        if not allow_cycles:
            removed = g._repair_cycles()
            diag.repaired_cycles = removed

        problems = g.validate(require_terminal_reachability=True)
        if problems:
            diag.ok = False
            diag.errors.extend(problems)
        return g, diag

    def _repair_cycles(self) -> List[Tuple[str, str]]:
        """Remove cycle-closing (back) edges via DFS. Returns removed (s, t)."""
        color: Dict[str, int] = {n: 0 for n in self.nodes}
        removed: List[Tuple[str, str]] = []

        def dfs(u: str) -> None:
            color[u] = 1
            for e in list(self.out_edges(u)):
                v = e.target
                if v not in color:
                    continue
                if color[v] == 1:  # back edge
                    self.edges = [x for x in self.edges if x is not e]
                    removed.append((e.source, e.target))
                elif color[v] == 0:
                    dfs(v)
            color[u] = 2

        for n in list(color):
            if color[n] == 0:
                dfs(n)
        return removed

    # ----------------------------------------------------------- validation --
    def validate(self, require_terminal_reachability: bool = True) -> List[str]:
        problems: List[str] = []
        for n in self.nodes.values():
            problems.extend(n.validate())
        for e in self.edges:
            problems.extend(e.validate())
            if e.source not in self.nodes:
                problems.append(f"edge endpoint missing: {e.source}")
            if e.target not in self.nodes:
                problems.append(f"edge endpoint missing: {e.target}")
        if not self.nodes:
            problems.append("empty graph")
            return problems
        terms = self.terminals()
        if not terms:
            problems.append("no terminal node (every node has out-degree > 0)")
        elif require_terminal_reachability:
            reach = self._nodes_reaching(terms)
            orphan = sorted(set(self.nodes) - reach)
            if orphan:
                problems.append(f"nodes without a path to a terminal: {orphan[:5]}")
        return problems

    def _nodes_reaching(self, targets: Set[str]) -> Set[str]:
        rev: Dict[str, List[str]] = defaultdict(list)
        for e in self.edges:
            rev[e.target].append(e.source)
        seen = set(targets)
        q = deque(targets)
        while q:
            u = q.popleft()
            for p in rev.get(u, []):
                if p not in seen:
                    seen.add(p)
                    q.append(p)
        return seen

    # ----------------------------------------------------------- telemetry --
    def note_visit(self, edge: Edge) -> None:
        self.edge_visits[edge.key] += 1

    def credit_report(self, episode_edges: List[List[Tuple[str, str, str]]],
                      scores: List[float]) -> List[Dict[str, Any]]:
        """Edge-level credit assignment (idea I5).

        lift = P(success | edge visited) - P(success)
        Unvisited edges get lift None and are prune candidates.
        """
        base = sum(scores) / len(scores) if scores else 0.0
        rows = []
        for e in self.edges:
            visits, wins = 0, 0.0
            for keys, s in zip(episode_edges, scores):
                if e.key in keys:
                    visits += 1
                    wins += s
            rows.append({
                "edge": f"{e.source} -{e.relation}-> {e.target}",
                "visits": visits,
                "cond_success": round(wins / visits, 3) if visits else None,
                "lift": round(wins / visits - base, 3) if visits else None,
            })
        rows.sort(key=lambda r: (r["visits"] == 0, r["lift"] if r["lift"] is not None else 0))
        return rows
