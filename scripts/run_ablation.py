#!/usr/bin/env python3
"""Run the 5-arm ablation and emit a results table + paired statistics.

    python scripts/run_ablation.py --arms A0 A1 A2 A3 A4 --episodes 40 \
        --graph graphs/toy_correct.json --out results/run1.json

Swap `--env` once you add a real wrapper in pg/envs/ (ALFWorld, HotpotQA,
tau-bench). Every arm runs on the *same* task list, which is what makes the
paired bootstrap / McNemar analysis valid.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pg.graph import ProceduralGraph
from pg.guidance import ARMS
from pg.llm import MockLLM, UsageTracker
from pg.runner import run_arm
from pg.stats import holm, mcnemar, paired_bootstrap
from pg.telemetry import RunLogger

ENVS = {}


def _register_envs():
    from pg.envs.toy import ToyResearchEnv, correct_graph, expert_graph
    ENVS["toy"] = {"factory": ToyResearchEnv,
                   "graphs": {"correct": correct_graph, "expert": expert_graph}}
    try:
        from pg.envs.taubench import TauBenchEnv
        ENVS["taubench"] = {"factory": TauBenchEnv, "graphs": {},
                            "task_ids": TauBenchEnv.task_ids}
    except ImportError:
        pass  # tau-bench not installed -- see PROGRESS.md for setup
    # Add your wrappers here, e.g.:
    # from pg.envs.alfworld import AlfWorldEnv, alfworld_graph
    # ENVS["alfworld"] = {"factory": AlfWorldEnv,
    #                     "graphs": {"expert": alfworld_graph}}


def build_llm(provider: str, obedience: float):
    tracker = UsageTracker()
    if provider == "mock":
        return MockLLM(tracker, obedience=obedience)
    if provider == "gemini":
        from pg.llm import GeminiLLM
        return GeminiLLM(tracker=tracker)
    from pg.llm import AnthropicLLM
    return AnthropicLLM(tracker=tracker)


def main() -> None:
    _register_envs()
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", default=["A0", "A1", "A2", "A3", "A4"])
    ap.add_argument("--env", default="toy", choices=sorted(ENVS))
    ap.add_argument("--graph", default="correct",
                    help="built-in graph name or a path to a graph .json")
    ap.add_argument("--episodes", type=int, default=40)
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--provider", default="mock", choices=["mock", "anthropic", "gemini"])
    ap.add_argument("--obedience", type=float, default=0.8,
                    help="mock-only: how often the mock solver follows guidance")
    ap.add_argument("--out", default="results/ablation.json")
    ap.add_argument("--run-dir", default="runs",
                    help="where to stream JSONL telemetry for the dashboard")
    ap.add_argument("--label", default="", help="human-readable run label")
    args = ap.parse_args()

    spec = ENVS[args.env]
    if os.path.exists(args.graph):
        graph = ProceduralGraph.load(args.graph)
    else:
        graph = spec["graphs"][args.graph]()
    problems = graph.validate()
    if problems:
        print("WARNING: graph validation problems:", problems)

    if "task_ids" in spec:
        tasks = spec["task_ids"](args.episodes, seed=1)  # TODO(P4): wire --seed
    else:
        tasks = [f"task{i:04d}" for i in range(args.episodes)]
    rows, per_task = {}, {}
    logger = RunLogger(args.run_dir, label=args.label or f"{args.env}/{args.graph}")
    logger.run_start(vars(args))
    print(f"telemetry -> {logger.path}   (dashboard: python dashboard/server.py)")

    for arm in args.arms:
        cfg = ARMS[arm]
        llm = build_llm(args.provider, args.obedience)
        res = run_arm(spec["factory"], tasks, llm,
                      graph.copy() if cfg.mode != "none" else None,
                      cfg, max_steps=args.max_steps, logger=logger, arm_id=arm)
        res["cost_usd"] = round(llm.tracker.cost_usd(), 4)
        res["usage"] = llm.tracker.summary()
        per_task[arm] = [res["per_task"][t] for t in tasks]
        res.pop("episodes")
        rows[arm] = res

    print("\n| arm | success | steps | tokens | guid.calls | cache hit | loc hit | "
          "succ/1k tok | $ |")
    print("|---|---|---|---|---|---|---|---|---|")
    for arm, r in rows.items():
        g = r["guidance"]
        eff = r["success"] / (r["tokens"] / 1000) if r["tokens"] else 0
        print(f"| {arm} | {r['success']:.3f} | {r['avg_steps']:.2f} | {r['tokens']} | "
              f"{g.get('guidance_calls', 0)} | {g.get('cache_hit_rate', 0):.2f} | "
              f"{g.get('loc_hit_rate', float('nan')):.2f} | {eff:.4f} | {r['cost_usd']} |")

    comparisons, pvals = {}, {}
    order = list(rows)
    for x, y in zip(order[1:], order[:-1]):
        bs = paired_bootstrap(per_task[x], per_task[y])
        mc = mcnemar(per_task[x], per_task[y])
        comparisons[f"{x}-{y}"] = {"bootstrap": bs, "mcnemar": mc}
        pvals[f"{x}-{y}"] = bs["p"]
        print(f"\n{x} - {y}: diff={bs['diff']:+.3f} "
              f"CI[{bs['ci_low']:+.3f},{bs['ci_high']:+.3f}] "
              f"boot_p={bs['p']:.4f} mcnemar_p={mc['p']:.4f}")
    if pvals:
        print("\nHolm-Bonferroni:", json.dumps(holm(pvals), indent=2))

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"config": vars(args), "arms": rows, "per_task": per_task,
                   "comparisons": comparisons,
                   "holm": holm(pvals) if pvals else {}}, fh, indent=2)
    logger.run_end(out=args.out, arms=list(rows))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
