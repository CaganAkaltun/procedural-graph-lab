# PG-Probe — Progress Log

Read this before touching the project. Governing plan: `UYGULAMA_PLANI_FINAL.md`
(Turkish; conditions C0–C6, phases, budget, kill criteria). This file tracks
what's actually been done vs. that plan, so any agent picking this up doesn't
have to re-derive state from scratch.

**Update this file after every meaningful change**: move finished items from
"Next steps" to "Done", note any deviation from the plan and why, and update
"Current state" so the next agent's first read is accurate.

---

## Current state

- Project root: `pg_lite/` (git repo, own `.venv`, not yet pushed to GitHub).
- LLM provider: **Gemini**, not Anthropic as the plan assumes. `pg/llm.py::GeminiLLM`
  implemented and tested live — model `gemini-3.5-flash-lite`, key loaded from
  a project-local `.env` (gitignored) via `python-dotenv`. `--provider gemini`
  wired into `scripts/run_ablation.py`. `AnthropicLLM` stub still present but unused.
- `scripts/smoke_test.py` passes with `MockLLM` — the pre-existing skeleton
  (`pg/graph.py`, `localize.py`, `guidance.py`, `runner.py`, `refiner.py`,
  `evolve.py`, `stats.py`, `telemetry.py`, `dashboard/`) is intact and untouched.
- No real environment wrapper yet (τ-bench retail, per the plan's Faz 0/P2)
  and no `G_expert` graph written.

## Deviations from `UYGULAMA_PLANI_FINAL.md`

- **Provider:** plan specifies Anthropic (`pg/llm.py::AnthropicLLM`, prompt P1).
  We use Gemini free tier instead. Any prompt/cost numbers in the plan that
  assume Anthropic pricing don't apply — Gemini free tier is $0, so the
  budget section (§7) and TOST/cost analysis need re-deriving once real
  episodes run, not assumed from the doc.
- Everything else in the plan (7 conditions, τ-bench choice, phases, stats
  plan, kill criteria) is unchanged and still the target.

## Done

- [x] Deduplicated the source files that became `pg_lite/` (see chat history
      for details — not relevant to future implementation work).
- [x] Set up `pg_lite/` as a standalone project: git init, `.venv`,
      `requirements.txt`, `.vscode/settings.json`.
- [x] Implemented and live-tested `GeminiLLM` in `pg/llm.py`.
- [x] `.env` / `.env.example` + `python-dotenv` loading for the API key.

## Next steps (in plan order — see §4 Faz planı)

1. **Faz 0 remainder:**
   - [ ] Install/configure τ-bench, list the 115 retail tasks, verify a
     deterministic `task_ids(n, seed)`.
   - [ ] Write `G_expert` by hand from the τ-bench retail policy doc
     (`graphs/taubench_expert.json`, 10–14 nodes).
   - [ ] Exit criterion: `run_ablation.py --env taubench --arms C0 C4 --episodes 3`
     runs clean end-to-end on Gemini.
2. **P2 — `pg/envs/taubench.py`**: implement the `Env` protocol
   (`reset`/`actions`/`step`/`score`, deterministic `task_ids`), register in
   `scripts/run_ablation.py::_register_envs()`.
3. **P3 — C1 fixed-guidance mode + ARMS registry**: add `mode="fixed"` to
   `pg/guidance.py`, rebuild `ARMS` as C0–C6 per §3.2 of the plan (currently
   the skeleton still uses the older A0–A5 naming from `README.md`).
4. **P4 — `--seed` / `--max-cost` / `--resume` flags** in `run_ablation.py`,
   plus per-episode failure isolation (`n_failed`, doesn't count against mean).
5. **P5 — `scripts/build_graphs.py`**: derive `G_llm` (refiner), `G_mined`
   (`pg/controls.py::mine_graph`), `G_shuf` (`pg/controls.py::shuffle_topology`)
   from the same bootstrap trace pool.
6. Faz 1 bootstrap run (C0, 40 tasks) once envs/graphs exist — this is the
   first step that actually costs anything, though Gemini free tier should
   make it $0.
7. **P6/P7** — `scripts/analyze_conformance.py`, `scripts/make_report.py`
   (deferred until real results exist).

## Notes for whoever (human or agent) picks this up next

- Don't reintroduce guards, edge credit, population evolution, BAI gate, FSM,
  DECLARE/LTL, or Behavior Trees — explicitly cut per plan §0 and §2.
- `pm4py` is intentionally not a dependency — conformance checking in
  `pg/conformance.py` is dependency-free by design.
- Kill criterion from plan §7: if no condition separates from C0 by ≥3 points
  in the pilot, do not spend budget on the full run — write up the
  conformance/gate-power/localization telemetry as an analysis note instead.
