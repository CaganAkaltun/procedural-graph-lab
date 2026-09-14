#!/usr/bin/env python3
"""Run the offline self-evolution loop with dashboard telemetry.

    python scripts/run_evolution.py --rounds 6 --train 30 --val 20 \
        --init graphs/toy_expert.json --label "toy-evolution"

`--init scratch` starts from the minimal Start->End skeleton (the paper's
Mode 5). Any other value is treated as a built-in graph name or a file path.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pg.evolve import evolve
from pg.graph import ProceduralGraph
from pg.guidance import ARMS
from pg.llm import MockLLM, UsageTracker
from pg.telemetry import RunLogger


def load_env(name: str):
    if name == "toy":
        from pg.envs.toy import ToyResearchEnv, correct_graph, expert_graph, ACTIONS
        return {"factory": ToyResearchEnv, "actions": ACTIONS,
                "desc": ToyResearchEnv().description,
                "graphs": {"expert": expert_graph, "correct": correct_graph}}
    raise SystemExit(f"unknown env {name!r}: register it in scripts/run_evolution.py")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="toy")
    ap.add_argument("--init", default="expert",
                    help="'scratch' | built-in graph name | path to graph.json")
    ap.add_argument("--arm", default="A5", choices=sorted(ARMS))
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--train", type=int, default=30)
    ap.add_argument("--val", type=int, default=20)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--allow-cycles", action="store_true")
    ap.add_argument("--provider", default="mock", choices=["mock", "anthropic"])
    ap.add_argument("--obedience", type=float, default=0.8)
    ap.add_argument("--run-dir", default="runs")
    ap.add_argument("--label", default="evolution")
    ap.add_argument("--out", default="results/evolution.json")
    args = ap.parse_args()

    spec = load_env(args.env)
    if args.init == "scratch":
        g0 = ProceduralGraph.skeleton()
    elif os.path.exists(args.init):
        g0 = ProceduralGraph.load(args.init)
    else:
        g0 = spec["graphs"][args.init]()

    tracker = UsageTracker()
    if args.provider == "mock":
        llm = MockLLM(tracker, obedience=args.obedience)
    else:
        from pg.llm import AnthropicLLM
        llm = AnthropicLLM(tracker=tracker)

    logger = RunLogger(args.run_dir, label=args.label)
    logger.run_start(vars(args))
    print(f"telemetry -> {logger.path}   (dashboard: python dashboard/server.py)")

    train_ids = [f"train{i:04d}" for i in range(args.train)]
    val_ids = [f"val{i:04d}" for i in range(args.val)]

    result = evolve(g0, llm, spec["factory"], train_ids, val_ids, ARMS[args.arm],
                    spec["desc"], spec["actions"], rounds=args.rounds,
                    batch_size=args.batch, allow_cycles=args.allow_cycles,
                    max_steps=args.max_steps, logger=logger)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(result.to_json())
    graph_out = os.path.splitext(args.out)[0] + "_graph.json"
    result.graph.save(graph_out)
    logger.run_end(out=args.out, graph=graph_out,
                   retained_score=result.retained_score)

    print(f"\nretained validation score: {result.retained_score:.3f}")
    print(f"final graph: {result.graph.stats()}")
    print(f"wrote {args.out} and {graph_out}")
    print(f"cost so far: ${tracker.cost_usd():.4f}")


if __name__ == "__main__":
    main()
