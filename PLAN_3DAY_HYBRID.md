# PG × Pi Hybrid — 3-Day Sprint Plan

**Goal:** test whether Pi-agent architectural ideas (already sketched in
`pi-extension/pg-pi.ts`) make Procedural-Graph guidance on τ-bench retail
**cheaper at no large loss of success** — and find which parameters matter.

**Scope rule for this sprint:** this plan overrides `UYGULAMA_PLANI_FINAL.md`
for 3 days only. Everything in "Cut" (bottom) goes back to the full plan
afterwards.

**Honesty rule:** ~30 paired tasks per arm can only detect *large* success
differences (~20 points). Token/call metrics are low-noise and reliable at
this n. So the sprint's **primary endpoints are efficiency**; success is a
secondary, pilot-grade signal ("no large drop"), not a claim.

---

## 1. Why a hybrid — what Pi does differently

The Python pipeline (paper-style) and the Pi extension make opposite choices
on exactly the knobs that drive cost:

| # | Pi idea (in `pg-pi.ts`) | Paper / current Python | Hybrid lever to measure |
|---|---|---|---|
| P1 | **Template guidance** — `serializeLocal()` renders the subgraph directly, 0 LLM calls (L98) | guidance LLM call every step (`guidance.py::_generate`) | guidance calls & tokens/episode |
| P2 | **Ephemeral tail injection** — `context` hook appends guidance to a *copy* of messages; never persisted (L138–179) | guidance baked into a rebuilt prompt each step | prompt growth per turn, cached-token share |
| P3 | **Selective injection** — `shouldRegenerate` triggers: first step / node changed / error / ambiguous branch / stale (L124) | `selective` exists but still re-injects cached text | injected guidance tokens |
| P4 | **Tool-call gate** — `tool_call` hook blocks with a repair reason (L183) | guards cut from plan | blocked policy violations, wasted turns |
| P5 | **Cheap localization + sticky fallback**, never dump the full graph on a miss (L82) | exact/soft cascade, full-graph fallback when node is None | localization hit rate |
| P6 | **Minimal, stable prefix** (Pi keeps system prompt small and fixed) | n/a | cached prompt tokens (Gemini implicit caching) |

Why this matters on τ-bench specifically: the native tool-calling loop
(`tau_bench/agents/tool_calling_agent.py`) resends the **full history + 5.8 KB
policy wiki + 16 tool schemas every turn**, and the user simulator is a second
LLM. Prompt tokens grow ~quadratically with turns. Anything persisted into
history (e.g. guidance) is paid again on every later turn.

Note: `pg/runner.py` (text ReAct, rebuilds one prompt, keeps last 6 steps) is
**not** reused for τ-bench — it cannot express multi-turn tool calling.

---

## 2. Arms (same test-task subset, same seed, same user-sim model for all)

| Arm | Guidance | Guidance LLM calls/turn | Tests |
|---|---|---|---|
| **H0** | none | 0 | baseline (= C0) |
| **H1** | `G_expert` subgraph → **LLM-generated**, every turn, ephemeral tail | 1 | paper mechanism (≈ C4 with G_expert) |
| **H2** | `G_expert` subgraph → **template** (Pi P1), every turn, ephemeral tail | 0 | is generation needed? |
| **H3** | H2 + **selective injection** (P3) | 0 | fewer injected tokens |
| **H4** | H3 + **tool-call guards** (P4) | 0 | full hybrid |
| H5 *(if quota allows)* | H2 on `shuffle_topology(G_expert)` | 0 | topology control (claim İ1, pilot grade) |

Fixed parameters (not swept): `temperature=0`, `max_num_steps=30` (τ-bench
default), `staleness=4`, user strategy `llm`, one agent model
(`gemini-3.5-flash-lite`), one user-sim model held constant.

## 3. Pre-registered sprint claims (commit to `preregistration.md` before Day 2 runs)

- **E1 — generation is not needed:** tokens(H2) ≤ 0.6 × tokens(H1), and the
  success diff H1−H2 bootstrap CI includes 0.
- **E2 — selective injection pays:** injected guidance tokens(H3) ≤ 0.5 ×
  H2, success CI lower bound > −15 points.
- **E3 — guards prevent violations:** H4 has fewer consequential tool calls
  that break policy (blocked-would-have-executed count) than H3, with
  false-block rate < 20%.
- **E4 — placement matters for cost:** ephemeral-tail injection gives a
  higher cached-token share and lower prompt tokens/episode than persisted
  injection (Day 2 micro-sweep).
- **E5 (optional):** H2 − H5 > 0 on success (topology carries signal).

Every outcome is reportable; a null on E1 ("LLM-generated guidance is worth
its cost") is as useful as a positive.

---

## 4. Day-by-day

### Day 1 — Wrapper + hybrid hooks (build day)

1. **Spike (first hour):** run τ-bench's own `ToolCallingAgent` on 1 retail
   task through litellm with Gemini (agent + user sim). Confirms tool-schema
   conversion works before writing anything. *Fallback if litellm+Gemini tool
   calling breaks:* call `google-genai` directly with function declarations.
2. **`pg/envs/taubench.py`** — own copy of the tool-calling loop with two hooks:
   - `context(messages) -> messages` (Pi P2: returns a copy + tail guidance;
     the stored history never contains guidance unless `placement="persist"`)
   - `tool_gate(action) -> Optional[str]` (Pi P4: if blocked, append the
     assistant tool call + a tool message with the repair reason; do **not**
     call `env.step`)
   - Usage per call by role (`agent` / `guidance` / `user`) via a litellm
     success callback: prompt, completion, and cached tokens
     (`prompt_tokens_details.cached_tokens` when present).
3. **`pg/hybrid.py`** — Python port of the Pi pieces:
   - `TOOL_TO_NODE`: `find_user_id_by_*`→Authenticate, `get_order_details`→
     CheckOrderStatus, `get_user_details`/`get_product_details`/
     `list_all_product_types`→LookupInfo, `cancel_pending_order`→CancelOrder,
     `modify_pending_order_*`/`modify_user_address`→ModifyOrder,
     `return_delivered_order_items`→ReturnOrder,
     `exchange_delivered_order_items`→ExchangeOrder,
     `transfer_to_human_agents`→TransferHuman; `think`/`calculate` = sticky.
   - Text (respond) turns: cue matching; fill the empty `cues` in
     `graphs/taubench_expert.json` (e.g. ConfirmAction: "confirm", "yes",
     "proceed"); miss → sticky, never full graph.
   - `template_guidance(node, hops)` → reuse `ProceduralGraph.serialize_local`.
   - `should_inject(...)` → the Pi trigger set.
   - Guards: consequential tools (`cancel_*`, `modify_*`, `return_*`,
     `exchange_*`) require Authenticate + CheckOrderStatus visited **and**
     a user confirmation in the last user turn; forbid a second
     `modify_pending_order_items` / `exchange_*` on the same order (verify
     against `wiki.md`). Log every block + whether the call would have been
     valid (false-block estimate).
4. **`scripts/run_hybrid.py`** — arms H0–H5, seeded test-task subset,
   per-episode JSONL append, `--resume` keyed on (arm, task), per-episode
   try/except → `n_failed`, client-side rate limiter + exponential backoff on
   429. Set `PYTHONUTF8=1` (Windows codepage issue already hit once).

**Exit criterion (end of Day 1):** H0 and H2 each finish 3 test tasks clean;
calls/episode and tokens/episode (by role) measured.
**Decision at end of Day 1:** from measured calls/episode × arms × N, check
it fits your Gemini quota (AI Studio shows your limits). If not: enable
billing with a hard cap *or* drop N from 30 to 20 — decide, don't drift.

### Day 2 — Micro-sweep, then launch the main run

1. **Micro-sweep on 5 *train* tasks** (never tune on test), H2 only:
   placement ∈ {ephemeral tail, persisted in history, system prefix} at
   hops=2, then hops=1 with the best placement → 4 configs × 5 tasks.
   Pick by tokens/episode + cached share; **freeze** config (write it into
   `preregistration.md` with E1–E5, commit).
2. Implement/verify guards on 2–3 hand-picked tasks known to need
   confirmation (check no false blocks on the golden path).
3. **Main run, unattended:** H0–H4 × 30 test tasks (seeded subset), then H5 if
   quota remains. Watch the dashboard; resume on any crash.

**Checkpoint (end of Day 2):** ≥60% of main-run episodes done. If not: drop
H5 first, then shrink N to 20 — all arms keep the *same* tasks.

### Day 3 — Finish, analyze, write up

1. **Morning:** finish remaining episodes. **Hard stop at noon** — analyze
   what exists; only tasks completed by *every* arm enter paired stats.
2. **`scripts/report_hybrid.py`** (reuse `pg/stats.py`):
   per-arm table — success (pass^1), tokens by role, cached share, LLM calls,
   turns, guidance injections, guard blocks/false blocks, localization hit
   rate, success per 1k tokens; paired diffs via `paired_bootstrap` +
   `mcnemar`, `holm` across E1–E5; cost–success Pareto.
   If time: `conformance.check` node-sequence fitness per guided arm.
3. **`results/HYBRID_PILOT.md`**: verdict per E1–E5, the frozen config, what
   to carry into the full plan (e.g. "C4 should use template guidance" or
   "generation earns its cost"), and the measured $/episode for budgeting the
   full run. Update `PROGRESS.md`.
4. Afternoon remainder = buffer.

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| Free-tier rate/day limits (429s) | limiter + backoff + `--resume`; quota decision at end of Day 1 |
| litellm ↔ Gemini tool-call quirks | Day 1 spike first; `google-genai` fallback |
| Nondeterminism (Gemini at temp 0, user sim) | paired design, same tasks/seed; label success results "pilot" |
| Confirmation guard misfires | log false blocks; disable that guard kind if >20% |
| Implicit caching not reported | fall back to prompt-token counts; drop cached-share from E4 |

## 6. Cut from this sprint (deferred to the full plan, not dropped)

`G_llm` refiner · `G_mined` / C6 · C1 fixed text · C2 advisor · HotpotQA
negative control · full 115 tasks × 2 seeds · TOST · C0–C6 ARMS rename ·
slides · dashboard features · node-scoped tool exposure and history
compaction (Pi-style progressive disclosure — good next experiments).

**Deviation from `UYGULAMA_PLANI_FINAL.md` §0/§2:** guards and the Pi track
were cut there; they are reintroduced here by explicit decision, per that
plan's own rule — they test E3/E4 and add **zero** extra LLM calls.
