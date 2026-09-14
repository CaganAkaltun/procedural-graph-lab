"""Paired statistics -- the part the paper is thinnest on.

All arms run on the same task list, so every comparison is paired. Use
`paired_bootstrap` for continuous scores, `mcnemar` for binary outcomes, and
`holm` to control the family-wise error rate over the planned comparisons.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Sequence, Tuple


def paired_bootstrap(a: Sequence[float], b: Sequence[float], n_boot: int = 10000,
                     seed: int = 0) -> Dict[str, float]:
    """Bootstrap the paired mean difference (a - b)."""
    assert len(a) == len(b) and len(a) > 0, "arms must cover the same tasks"
    rng = random.Random(seed)
    diffs = [x - y for x, y in zip(a, b)]
    n = len(diffs)
    observed = sum(diffs) / n
    means = []
    for _ in range(n_boot):
        s = sum(diffs[rng.randrange(n)] for _ in range(n)) / n
        means.append(s)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot) - 1]
    # two-sided p: fraction of resamples on the other side of zero, doubled
    if observed >= 0:
        p = 2 * sum(1 for m in means if m <= 0) / n_boot
    else:
        p = 2 * sum(1 for m in means if m >= 0) / n_boot
    return {"diff": round(observed, 4), "ci_low": round(lo, 4),
            "ci_high": round(hi, 4), "p": round(min(p, 1.0), 5), "n": n}


def mcnemar(a: Sequence[float], b: Sequence[float], threshold: float = 0.5
            ) -> Dict[str, float]:
    """Exact-ish McNemar for paired binary outcomes (a wins / b wins counts)."""
    assert len(a) == len(b)
    a_only = sum(1 for x, y in zip(a, b) if x >= threshold > y)
    b_only = sum(1 for x, y in zip(a, b) if y >= threshold > x)
    n = a_only + b_only
    if n == 0:
        return {"a_only": 0, "b_only": 0, "p": 1.0}
    # two-sided binomial test with p=0.5
    k = min(a_only, b_only)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return {"a_only": a_only, "b_only": b_only, "p": round(min(2 * tail, 1.0), 5)}


def holm(pvals: Dict[str, float], alpha: float = 0.05) -> Dict[str, Dict[str, float]]:
    """Holm-Bonferroni over the planned comparisons."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, rejected_so_far = {}, True
    for i, (name, p) in enumerate(items):
        thresh = alpha / (m - i)
        reject = rejected_so_far and p <= thresh
        rejected_so_far = reject
        out[name] = {"p": p, "threshold": round(thresh, 5), "significant": reject}
    return out


def sequential_gate(candidate_scores: List[float], baseline_scores: List[float],
                    first_stage: int = 5, margin: float = 0.15
                    ) -> Tuple[str, Dict[str, float]]:
    """Cheap two-stage acceptance test (idea I6).

    Stage 1 looks at the first `first_stage` paired episodes. If the candidate
    is already worse by more than `margin`, reject without paying for the rest
    of the validation rollout. Otherwise use the full paired comparison.
    """
    n1 = min(first_stage, len(candidate_scores))
    early = paired_bootstrap(candidate_scores[:n1], baseline_scores[:n1], n_boot=2000)
    if early["diff"] < -margin:
        return "early_reject", early
    full = paired_bootstrap(candidate_scores, baseline_scores)
    decision = "accept" if full["diff"] >= 0 else "reject"
    return decision, full
