"""Control graphs.

Two generators the paper never ran, and which together decide whether the
topology of a Procedural Graph carries any information at all.

1. `shuffle_topology` — same nodes, same edge attribute texts, same edge count,
   randomly rewired. If guidance from a shuffled graph works as well as guidance
   from the real one, then the topology is decorative and PG is really
   "domain-specific reminder text, indexed by a detected state".

2. `mine_graph` — induce a graph from observed successful trajectories with a
   frequency-thresholded directly-follows relation. This is the *descriptive*
   counterpart to the LLM refiner. It can only recover behaviour that already
   appears in the log, which is precisely why it is a control and not a
   replacement: if the mined graph matches the LLM-refined one on task success,
   the refiner adds nothing; if it does not, the refiner's ability to invent
   steps that never occurred is real and measured.
"""

from __future__ import annotations

import random
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from .graph import Edge, Node, ProceduralGraph


# ------------------------------------------------------------------ shuffle --
def shuffle_topology(graph: ProceduralGraph, seed: int = 0,
                     keep_terminal: bool = True,
                     max_tries: int = 200) -> ProceduralGraph:
    """Rewire edges at random while preserving node set, edge count and texts.

    Attribute texts travel with the edge, not with the endpoints, so the
    shuffled graph contains exactly the same advice in a scrambled order.
    """
    rng = random.Random(seed)
    g = graph.copy()
    node_ids = list(g.nodes)
    terminals = graph.terminals() if keep_terminal else set()
    sources = [n for n in node_ids if n not in terminals]
    if not sources:
        return g

    for _ in range(max_tries):
        new_edges: List[Edge] = []
        seen = set()
        for e in graph.edges:
            for _try in range(20):
                s = rng.choice(sources)
                t = rng.choice([n for n in node_ids if n != s])
                if (s, t) not in seen:
                    break
            seen.add((s, t))
            new_edges.append(Edge(source=s, target=t, relation=e.relation,
                                  condition=e.condition, guidance=e.guidance,
                                  pitfalls=e.pitfalls, guard=None))
        cand = ProceduralGraph(list(g.nodes.values()), new_edges)
        if not cand.validate(require_terminal_reachability=True):
            return cand
    # Fall back to the last candidate even if imperfect; report it.
    return cand


# --------------------------------------------------------------------- mine --
def mine_graph(successful_actions: Sequence[Sequence[str]],
               node_descriptions: Optional[Dict[str, str]] = None,
               min_freq: int = 2, max_out_degree: int = 3,
               start: str = "Start", end: str = "End") -> ProceduralGraph:
    """Frequency-thresholded directly-follows miner over successful traces.

    Deliberately simple and auditable: a transition enters the graph if it was
    observed at least `min_freq` times, keeping at most `max_out_degree`
    successors per node. This is the classic DFG construction -- with all of its
    known limitations (no concurrency, spurious loops). Those limitations are
    part of the point: PG uses the same representation.
    """
    counts: Counter = Counter()
    nodes = {start, end}
    for actions in successful_actions:
        seq = [start] + [a.split("(")[0].strip() for a in actions] + [end]
        nodes.update(seq)
        for u, v in zip(seq, seq[1:]):
            if u != v:
                counts[(u, v)] += 1

    by_source: Dict[str, List[Tuple[str, int]]] = {}
    for (u, v), c in counts.items():
        if c >= min_freq:
            by_source.setdefault(u, []).append((v, c))

    edges: List[Edge] = []
    for u, succ in by_source.items():
        succ.sort(key=lambda x: -x[1])
        for v, c in succ[:max_out_degree]:
            edges.append(Edge(source=u, target=v, relation="LEADS_TO",
                              condition=None,
                              guidance=f"Observed {c} times in successful runs.",
                              pitfalls=""))

    node_objs = []
    for n in sorted(nodes):
        ntype = "STATUS" if n == start else "TERMINAL" if n == end else "ACTION"
        node_objs.append(Node(n, ntype,
                              (node_descriptions or {}).get(n, f"Procedure {n}.")))
    g = ProceduralGraph(node_objs, edges)

    # Guarantee the structural invariant the evolution loop also enforces:
    # every node must be able to reach a terminal.
    problems = g.validate()
    if problems:
        reach = g._nodes_reaching(g.terminals())
        for n in list(g.nodes):
            if n not in reach and n != end:
                g.edges.append(Edge(source=n, target=end, relation="LEADS_TO",
                                    guidance="Terminate if no successor applies."))
    return g


def annotate_with_llm(graph: ProceduralGraph, llm, task_description: str) -> ProceduralGraph:
    """Optional: let an LLM write condition/guidance/pitfalls for a mined graph.

    Keeps the topology fixed (mined) and varies only the attribute text, which
    isolates 'who decides the structure' from 'who writes the advice'.
    """
    for e in graph.edges:
        prompt = (f"Task: {task_description}\n"
                  f"A procedure transition goes from [{e.source}] to [{e.target}].\n"
                  f"Write three short lines:\ncondition: ...\nguidance: ...\n"
                  f"pitfalls: ...")
        text = llm.complete(prompt, role="refiner", max_tokens=256)
        for line in text.splitlines():
            low = line.lower()
            if low.startswith("condition:"):
                e.condition = line.split(":", 1)[1].strip()
            elif low.startswith("guidance:"):
                e.guidance = line.split(":", 1)[1].strip()
            elif low.startswith("pitfalls:"):
                e.pitfalls = line.split(":", 1)[1].strip()
    return graph
