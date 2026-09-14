#!/usr/bin/env python3
"""Validation-gate power analysis — zero API cost, pure Monte Carlo.

Question: how much of the paper's self-evolution trajectory is signal and how
much is the arithmetic of comparing a fresh noisy score against a cached noisy
score?

The paper's rule (Eq. 5) is:

    accept  iff  S_val(candidate) >= S_val(retained_cached)

where `retained_cached` is the score measured *when that graph was accepted*,
not re-measured this round. With |D_val| = 20 binary episodes that cached score
is itself a noisy draw — and because a graph only becomes `retained` by
producing a high draw, the cached score is upward biased. Every later candidate
therefore faces an inflated bar (a ratchet), and the final reported validation
score overstates the returned graph's true quality.

This script quantifies three things:

  1. false-accept rate: P(commit) when the candidate is truly identical
  2. ratchet / winner's curse: reported validation score minus true success rate
     of the returned graph, after K rounds
  3. how much a paired re-evaluation gate (common random numbers) fixes it

Usage:
    python scripts/gate_power_analysis.py
    python scripts/gate_power_analysis.py --n-val 20 --rounds 10 --trials 20000
"""

from __future__ import annotations

import argparse
import random
import statistics
from typing import List, Tuple


def draw(p: float, n: int, rng: random.Random) -> float:
    """Observed success rate of n independent binary episodes."""
    return sum(1 for _ in range(n) if rng.random() < p) / n


def draw_paired(p_a: float, p_b: float, n: int, rng: random.Random,
                rho: float = 0.6) -> Tuple[float, float]:
    """Two arms on the SAME validation tasks (common random numbers).

    `rho` is the fraction of episodes whose outcome is determined by shared task
    difficulty rather than by the graph, which is what makes paired comparison
    lower variance than two independent evaluations.
    """
    a = b = 0
    for _ in range(n):
        if rng.random() < rho:                       # task difficulty dominates
            shared = rng.random()
            a += shared < p_a
            b += shared < p_b
        else:                                        # graph-specific outcome
            a += rng.random() < p_a
            b += rng.random() < p_b
    return a / n, b / n


# --------------------------------------------------------------- experiment 1
def false_accept(p: float, n: int, trials: int, rng: random.Random) -> float:
    """Paper's gate, single round, candidate truly identical to retained."""
    hits = 0
    for _ in range(trials):
        retained = draw(p, n, rng)
        cand = draw(p, n, rng)
        hits += cand >= retained          # ties accepted, per Eq. 5
    return hits / trials


def power(p: float, delta: float, n: int, trials: int, rng: random.Random) -> float:
    """P(commit) when the candidate is genuinely better by `delta`."""
    hits = 0
    for _ in range(trials):
        retained = draw(p, n, rng)
        cand = draw(min(1.0, p + delta), n, rng)
        hits += cand >= retained
    return hits / trials


# --------------------------------------------------------------- experiment 2
def ratchet(p: float, n: int, rounds: int, trials: int, rng: random.Random,
            paired: bool = False) -> dict:
    """K rounds where every candidate is truly identical to the retained graph.

    Nothing improves. Anything the loop reports is pure selection noise.
    """
    reported: List[float] = []
    commits: List[int] = []
    for _ in range(trials):
        retained_obs = draw(p, n, rng)      # initial reference evaluation
        n_commit = 0
        for _ in range(rounds):
            if paired:
                cand_obs, ret_obs = draw_paired(p, p, n, rng)
                accept = cand_obs >= ret_obs        # re-evaluate BOTH each round
            else:
                cand_obs = draw(p, n, rng)
                accept = cand_obs >= retained_obs   # paper: cached reference
            if accept:
                retained_obs = cand_obs
                n_commit += 1
        reported.append(retained_obs)
        commits.append(n_commit)
    return {
        "true_p": p,
        "mean_reported": statistics.mean(reported),
        "inflation": statistics.mean(reported) - p,
        "p95_reported": sorted(reported)[int(0.95 * len(reported)) - 1],
        "mean_commits": statistics.mean(commits),
        "share_with_ge1_commit": sum(1 for c in commits if c >= 1) / len(commits),
    }


# --------------------------------------------------------------- experiment 3
def best_round_vs_returned(p: float, n_val: int, n_test: int, rounds: int,
                           trials: int, rng: random.Random) -> dict:
    """Gap between the best checkpoint's TEST score and the returned graph's.

    Selection happens on validation; the paper additionally reports a test score
    for each accepted checkpoint (Figure 4 green diamonds) and notes that the
    best one reached 95.0% while the returned graph scored 85.0%. Under an
    all-neutral null -- every candidate truly identical -- how large is that gap
    by chance alone?
    """
    gaps, n_ckpt = [], []
    for _ in range(trials):
        retained_val = draw(p, n_val, rng)
        tests = [draw(p, n_test, rng)]           # baseline checkpoint
        for _ in range(rounds):
            cand_val = draw(p, n_val, rng)
            if cand_val >= retained_val:         # accepted -> gets a test score
                retained_val = cand_val
                tests.append(draw(p, n_test, rng))
        gaps.append(max(tests) - tests[-1])
        n_ckpt.append(len(tests))
    return {"mean_gap": statistics.mean(gaps),
            "p95_gap": sorted(gaps)[int(0.95 * len(gaps)) - 1],
            "mean_checkpoints": statistics.mean(n_ckpt)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-val", type=int, default=20, help="validation episodes")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--trials", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    print("=" * 74)
    print(f"Validation-gate power analysis  (n_val={args.n_val}, "
          f"rounds={args.rounds}, trials={args.trials})")
    print("=" * 74)

    print("\n1. FALSE ACCEPT — candidate is truly IDENTICAL to the retained graph")
    print("   (the gate should ideally be near 50%; ties are accepted, so it is not)")
    print(f"   {'true p':>8} {'P(commit)':>12}")
    for p in (0.3, 0.5, 0.7, 0.85):
        print(f"   {p:>8.2f} {false_accept(p, args.n_val, args.trials, rng):>12.3f}")

    print("\n2. POWER — candidate is genuinely better by delta")
    print(f"   {'true p':>8} {'delta':>8} {'P(commit)':>12}")
    for p, d in ((0.5, 0.05), (0.5, 0.10), (0.5, 0.20),
                 (0.85, 0.05), (0.85, 0.10)):
        print(f"   {p:>8.2f} {d:>8.2f} "
              f"{power(p, d, args.n_val, args.trials, rng):>12.3f}")

    print(f"\n3. RATCHET — {args.rounds} rounds, EVERY candidate truly neutral")
    print("   Any reported gain here is selection noise, not learning.")
    for p in (0.5, 0.7):
        cached = ratchet(p, args.n_val, args.rounds, args.trials // 4, rng, paired=False)
        pair = ratchet(p, args.n_val, args.rounds, args.trials // 4, rng, paired=True)
        print(f"\n   true success rate = {p:.2f}")
        print(f"     paper's gate (cached reference):")
        print(f"       reported val score  : {cached['mean_reported']:.3f} "
              f"(+{cached['inflation']:.3f} inflation, p95 "
              f"{cached['p95_reported']:.3f})")
        print(f"       committed edits     : {cached['mean_commits']:.2f} per run; "
              f"{100 * cached['share_with_ge1_commit']:.0f}% of runs commit >=1")
        print(f"     paired gate (re-evaluate both, common random numbers):")
        print(f"       reported val score  : {pair['mean_reported']:.3f} "
              f"(+{pair['inflation']:.3f} inflation)")
        print(f"       committed edits     : {pair['mean_commits']:.2f} per run")

    print("\n4. 'BEST ROUND' vs 'RETURNED GRAPH' gap under an all-neutral null")
    print("   The paper reports 85.0% returned vs 95.0% best round (= 10 points).")
    for p in (0.5, 0.7, 0.85):
        g = best_round_vs_returned(p, args.n_val, args.n_val, args.rounds,
                                   args.trials // 4, rng)
        print(f"   true p={p:.2f}: mean gap {100 * g['mean_gap']:.1f} points, "
              f"p95 gap {100 * g['p95_gap']:.1f} points "
              f"({g['mean_checkpoints']:.1f} checkpoints scored on test)")

    print("\n" + "=" * 74)
    print("Read this as: with 20 binary validation episodes, a loop in which")
    print("NOTHING improves still commits edits, still shows a rising validation")
    print("curve, and still produces a double-digit 'best round vs returned' gap.")
    print("Re-evaluating the retained graph each round on the same tasks removes")
    print("most of the inflation at the cost of one extra rollout per round.")
    print("=" * 74)


if __name__ == "__main__":
    main()
