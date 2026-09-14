#!/usr/bin/env python3
"""End-to-end smoke test with the mock LLM -- no API key needed.

Exercises: graph construction -> structural validation -> localization cascade
-> all five arms -> paired statistics -> one self-evolution run with the robust
gate -> edge-level credit report.

The absolute numbers mean nothing (the solver is a mock). What this proves is
that every moving part is wired correctly before you spend money on real calls.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pg.envs.toy import ToyResearchEnv, expert_graph, correct_graph, ACTIONS
from pg.graph import ProceduralGraph
from pg.guidance import ARMS
from pg.llm import MockLLM, UsageTracker
from pg.runner import run_arm
from pg.stats import holm, mcnemar, paired_bootstrap
from pg.evolve import evolve

TASKS = [f"t{i:03d}" for i in range(30)]
VAL = [f"v{i:03d}" for i in range(12)]


def header(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main():
    header("1. Graph construction and structural validation")
    g = expert_graph()
    print("expert graph stats:", g.stats())
    problems = g.validate()
    print("validation problems:", problems or "none")

    broken, diag = g.apply_edits({"add_edges": [{"source": "Search", "target": "Ghost"}]})
    print("bad edit accepted?", diag.ok, "| errors:", diag.errors)

    header("2. Localization cascade (exact vs soft)")
    from pg.localize import Localizer
    for mode in ("exact", "soft"):
        loc = Localizer(g, mode=mode)
        probes = [("Search", "Search returned 3 passages."),
                  ("search", "lowercase variant"),
                  ("run_search_query", "a tool name that is not a node id"),
                  ("Browse", "distractor action")]
        out = [f"{a}->{loc.locate(a, o, 'Start').node}/{loc.locate(a, o, 'Start').stage}"
               for a, o in probes]
        print(f"  {mode:6s}: " + "  ".join(out))
        print(f"          stats: {loc.stats()}")

    header("3. Five arms on a correct graph (solver obeys guidance 80% of the time)")
    g_ok = correct_graph()
    rows = {}
    for arm in ("A0", "A1", "A2", "A3", "A4", "A5"):
        tracker = UsageTracker()
        llm = MockLLM(tracker, obedience=0.8)
        cfg = ARMS[arm]
        res = run_arm(ToyResearchEnv, TASKS, llm,
                      g_ok.copy() if cfg.mode != "none" else None, cfg, max_steps=12)
        rows[arm] = res
        gs = res["guidance"]
        print(f"  {arm} {cfg.name:38s} success={res['success']:.3f} "
              f"steps={res['avg_steps']:5.2f} tokens={res['tokens']:7d} "
              f"guid_calls={gs.get('guidance_calls', 0):3d} "
              f"cache_hit={gs.get('cache_hit_rate', 0):.2f} "
              f"loc_hit={gs.get('loc_hit_rate', float('nan')):.2f} "
              f"blocks={res['guard_blocks']}")

    header("4. Paired statistics (the comparison the paper does not run)")
    a0 = [rows["A0"]["per_task"][t] for t in TASKS]
    pvals = {}
    for x, y in (("A1", "A0"), ("A2", "A1"), ("A3", "A2"), ("A4", "A3")):
        ax = [rows[x]["per_task"][t] for t in TASKS]
        ay = [rows[y]["per_task"][t] for t in TASKS]
        bs = paired_bootstrap(ax, ay)
        mc = mcnemar(ax, ay)
        pvals[f"{x}-{y}"] = bs["p"]
        print(f"  {x} - {y}: diff={bs['diff']:+.3f} "
              f"CI[{bs['ci_low']:+.3f},{bs['ci_high']:+.3f}] "
              f"boot_p={bs['p']:.4f} mcnemar_p={mc['p']:.4f}")
    print("  Holm-Bonferroni:", json.dumps(holm(pvals), indent=None))

    header("5. Cost-efficiency (success per 1k tokens)")
    for arm, res in rows.items():
        eff = res["success"] / (res["tokens"] / 1000) if res["tokens"] else 0
        print(f"  {arm}: success={res['success']:.3f} tokens={res['tokens']:7d} "
              f"success_per_1k_tok={eff:.4f}")

    header("6. Self-evolution from the FLAWED expert prior (paper's Mode 1 -> Mode 3)")
    tracker = UsageTracker()
    llm = MockLLM(tracker, obedience=0.8)
    result = evolve(expert_graph(), llm, ToyResearchEnv, TASKS, VAL,
                    ARMS["A5"], ToyResearchEnv().description, ACTIONS,
                    rounds=4, batch_size=8, allow_cycles=False, max_steps=12)
    print(f"  retained validation score: {result.retained_score:.3f}")
    print(f"  final graph: {result.graph.stats()}")
    for h in result.history:
        print(f"   round {h.round}: {h.decision:10s} "
              f"cand={h.cand_val_score} retained={h.retained_val_score}")

    header("7. Edge-level credit assignment on the evolved graph")
    final_cfg = ARMS["A5"]
    res = run_arm(ToyResearchEnv, TASKS, MockLLM(UsageTracker(), obedience=0.8),
                  result.graph, final_cfg, max_steps=12)
    eps = res["episodes"]
    credit = result.graph.credit_report([e.visited_edges for e in eps],
                                        [e.score for e in eps])
    print(f"  evolved-graph success on train tasks: {res['success']:.3f} "
          f"(guard blocks: {res['guard_blocks']})")
    for row in credit[:6]:
        print(f"   {row['edge']:32s} visits={row['visits']:3d} "
              f"cond={row['cond_success']} lift={row['lift']}")

    header("SMOKE TEST PASSED")
    print("All components ran. Wire pg/llm.py::AnthropicLLM and add a real env "
          "wrapper in pg/envs/ to run the actual experiment.")


if __name__ == "__main__":
    main()
