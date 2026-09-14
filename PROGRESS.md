# PG-Probe — Progress Log

Read this before touching the project. Governing plan: `UYGULAMA_PLANI_FINAL.md`
(Turkish; conditions C0–C6, phases, budget, kill criteria). This file tracks
what's actually been done vs. that plan, so any agent picking this up doesn't
have to re-derive state from scratch.

**Repo split:** this is the `3day-hybrid-pi` branch. **`PLAN_3DAY_HYBRID.md`
overrides everything below (the original `UYGULAMA_PLANI_FINAL.md` C0–C6
track) for the duration of this sprint** — read that file first, not the
"Next steps" section here. The original track continues untouched on
`master` (its own `pg/envs/taubench.py` is the text-ReAct/Env-protocol
version; this branch replaces it with a native tool-calling loop). The two
are kept on separate branches deliberately so neither clobbers the other's
`pg/envs/taubench.py`. Per `PLAN_3DAY_HYBRID.md` §6, everything it cuts
returns to the `master` track when this sprint ends.

**Update this file after every meaningful change**: move finished items from
"Next steps" to "Done", note any deviation from the plan and why, and update
"Current state" so the next agent's first read is accurate.

---

## Hybrid sprint status (this branch only)

Design done, code not started: `HYBRID_PG_ARCHITECTURE.md` (critique review,
related work, PG-H architecture, proposed arms H0–H5 replacing the plan's §2,
implementation order — pending user approval). Inherited from `master` at branch-off: `TauBenchEnv` exists but
is the text-ReAct version — `PLAN_3DAY_HYBRID.md` Day 1 §4.2 replaces its
step loop with a native tool-calling one (`context`/`tool_gate` hooks), so
expect `pg/envs/taubench.py` to change substantially here. Track Day-by-day
progress against `PLAN_3DAY_HYBRID.md` §4 directly rather than duplicating
it in this file; update this section with just a one-line status per day.

## Current state (as of branch-off from `master` — see above for what's active here)

- Project root: `pg_lite/` (git repo, own `.venv`, not yet pushed to GitHub).
- LLM provider: **Gemini**, not Anthropic as the plan assumes. `pg/llm.py::GeminiLLM`
  implemented and tested live — model `gemini-3.5-flash-lite`, key loaded from
  a project-local `.env` (gitignored) via `python-dotenv`. `--provider gemini`
  wired into `scripts/run_ablation.py`. `AnthropicLLM` stub still present but unused.
- `scripts/smoke_test.py` passes with `MockLLM` — the pre-existing skeleton
  (`pg/graph.py`, `localize.py`, `guidance.py`, `runner.py`, `refiner.py`,
  `evolve.py`, `stats.py`, `telemetry.py`, `dashboard/`) is intact and untouched.
- **τ-bench installed**: cloned from `github.com/sierra-research/tau-bench`
  into `.taubench_src/` (gitignored — third-party repo with its own `.git`,
  not vendored into this repo) and `pip install -e .taubench_src` into the
  venv. Retail domain confirmed: 500 train tasks, 115 test tasks (matches the
  plan's target). Note: `.taubench_src/setup.py` needed a one-line local patch
  (`open("README.md")` → `open("README.md", encoding="utf-8")`) to install on
  Windows with a non-UTF8 default codepage — that patch lives only in the
  gitignored clone, not in this repo, so re-cloning on another machine may
  need it reapplied.
- **`graphs/taubench_expert.json` written**: 12 nodes / 17 edges, hand-derived
  from `.taubench_src/tau_bench/envs/retail/wiki.md` (the retail policy doc).
  Validates clean via `pg.graph.ProceduralGraph.load(...).validate()`. No
  `guard` fields used (guards are out of scope per plan §0/§2) — pure
  `LEADS_TO` edges with guidance/pitfalls. Flow: `Start → Authenticate →
  IdentifyIntent → {LookupInfo | CheckOrderStatus → ConfirmAction →
  Cancel/Modify/Return/Exchange | TransferHuman} → back to IdentifyIntent
  (multi-request) → End`.
- **`pg/envs/taubench.py` written (P2)**: `TauBenchEnv` implements
  `pg/runner.py`'s `Env` protocol (`reset`/`actions`/`step`/`score`), wrapping
  `tau_bench.envs.retail.MockRetailDomainEnv`. Registered in
  `scripts/run_ablation.py::_register_envs()` under `"taubench"`, with
  `TauBenchEnv.task_ids(n, seed)` plugged in as the env's task-list source
  (replacing the generic `task{i:04d}` placeholder for this env only).
  `pg/runner.py::Env.step` was extended to take an optional `args: str`
  (the JSON object between the parens in the solver's `Action: name(args)`
  line) — `pg/envs/toy.py` updated to accept-and-ignore it, so the toy smoke
  test is unaffected. tau-bench tool calls are `Action: tool_name({"k":"v"})`;
  talking to the simulated user is `Action: respond({"content": "..."})`.
  User-simulator cost is tracked separately (`TauBenchEnv.user_cost_usd`, a
  litellm dollar figure) since it isn't produced by our own `LLM` object.
- **Caveat surfaced during P2, not yet resolved on this branch:** a separate
  planning document (`PLAN_3DAY_HYBRID.md`, now moved to the `3day-hybrid-pi`
  branch) argues this text-ReAct approach can't drive tau-bench's native
  multi-turn tool-calling loop well and proposes a different architecture.
  That's being explored in isolation on the other branch; this branch's
  `TauBenchEnv` is the ReAct/Env-protocol version and is what P3 onward should
  build on **on master**.

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
- [x] τ-bench cloned + installed into `.venv` (see Current state for the
      Windows encoding patch note).
- [x] `graphs/taubench_expert.json` (`G_expert`) written and validated.
- [x] **P2** — `pg/envs/taubench.py` (`TauBenchEnv`) written and registered.

## Next steps (in plan order — see §4 Faz planı)

1. **Faz 0 exit criterion (not yet run live):**
   `run_ablation.py --env taubench --arms A0 A2 --graph
   graphs/taubench_expert.json --episodes 3 --provider gemini` should run
   clean end-to-end. (Arm names are still A0–A5 until P3 renames them.)
   Worth doing before P3, since it's the first real check that `TauBenchEnv`
   actually works against a live Gemini call, not just imports cleanly.
2. **P3 — C1 fixed-guidance mode + ARMS registry**: add `mode="fixed"` to
   `pg/guidance.py`, rebuild `ARMS` as C0–C6 per §3.2 of the plan (currently
   the skeleton still uses the older A0–A5 naming from `README.md`).
3. **P4 — `--seed` / `--max-cost` / `--resume` flags** in `run_ablation.py`,
   plus per-episode failure isolation (`n_failed`, doesn't count against mean).
4. **P5 — `scripts/build_graphs.py`**: derive `G_llm` (refiner), `G_mined`
   (`pg/controls.py::mine_graph`), `G_shuf` (`pg/controls.py::shuffle_topology`)
   from the same bootstrap trace pool.
5. Faz 1 bootstrap run (C0, 40 tasks) once envs/graphs exist — this is the
   first step that actually costs anything, though Gemini free tier should
   make it $0.
6. **P6/P7** — `scripts/analyze_conformance.py`, `scripts/make_report.py`
   (deferred until real results exist).

## Notes for whoever (human or agent) picks this up next

- Don't reintroduce guards, edge credit, population evolution, BAI gate, FSM,
  DECLARE/LTL, or Behavior Trees — explicitly cut per plan §0 and §2.
- `pm4py` is intentionally not a dependency — conformance checking in
  `pg/conformance.py` is dependency-free by design.
- Kill criterion from plan §7: if no condition separates from C0 by ≥3 points
  in the pilot, do not spend budget on the full run — write up the
  conformance/gate-power/localization telemetry as an analysis note instead.
