# PG-H — Hybrid Procedural Graph: critique review, related work, architecture

Scope: τ-bench retail, Gemini flash-lite, branch `3day-hybrid-pi`. Builds on
`PLAN_3DAY_HYBRID.md`; §4 below proposes replacement arms for its §2.
Paper references (§, Table) point to arXiv:2609.09153v1.

---

## 1. Realistic re-check of the 21 weaknesses

| # | Weakness | Verdict | Kind | Direct perf. effect if fixed? | Decision |
|---|---|---|---|---|---|
| 1 | No graph-free advisor control | Valid | Evaluation | No | Experimental control only |
| 2 | No topology control | Valid | Evaluation | No | Experimental control only |
| 3 | No compliance measure | Valid | Evaluation | Indirect | Reused as a runtime signal in P4 |
| 4 | Exact-match localization, full-graph fallback | Valid but **narrower** than first stated: tool steps match fine (ACTION nodes = tool names); the gap is text-only turns and REASONING/STATUS nodes — on τ-bench, every reply to the user | Accuracy | **Yes** | **P1** |
| 5 | Token/latency overhead | **Partly** valid: PG also shortens runs (GDPval 28.2→18.6 steps; EnterpriseArena tool calls −82%); some modes use fewer tokens than baseline (Table 10) | Efficiency | **Yes** (cost) | **P5** |
| 6 | Guidance regenerated every step | Valid | Efficiency | **Yes** (cost) | **P5** |
| 7 | Layout defeats prefix caching | **Partly** valid: paper never says caching was used; cost-only, and only on providers with prefix caching | Efficiency | **Yes** (cost), none on accuracy | **P5** |
| 8 | Evolution cost unreported | Valid | Reporting | No | Measure, don't "fix" |
| 9 | Noisy acceptance gate | Valid | Evolution quality | Yes, only when evolving | **P6 (Tier 2)** |
| 10 | Wins inside CIs | **Mostly unfair**: overlapping *unpaired* CIs don't imply no difference under a paired design; a sign test over 24 settings is a legitimate aggregate. Valid residue: single run, small test sets | Reporting | No | Drop |
| 11 | Graph can hurt, no runtime safeguard | Valid: −28.6 points on MultiChallenge is far outside ±~13 noise at n=56 | Accuracy | **Yes** | **P4** |
| 12 | Cross-table inconsistency, no code | Valid | Reporting | No | Drop |
| 13 | Judge from solver family | **Weak**: only 2 of 7 benchmarks use an LLM judge; τ-bench/ALFWorld/BFCL are scored by program | Reporting | No | Drop |
| 14 | Advice only, no enforcement | Valid for policy domains; soft guidance is defensible for open-ended tasks | Accuracy | **Yes** (τ-bench) | **P2** |
| 15 | Relation types / conditions inert | Valid | Design | Enabler | Merged into P1/P2 |
| 16 | Guidance sees last 3 steps | Valid for multi-turn | Accuracy | **Yes** | **P3** |
| 17 | Refiner loses early failures | Valid | Evolution quality | Yes, only when evolving | **P7 (Tier 2)** |
| 18 | No tool-catalog check | Valid, trivial | Accuracy (small) | Yes | Quick fix inside P1 |
| 19 | Rejection memory grows | **Weak** in practice (≤10 rounds) | Cost | Negligible | Drop |
| 20 | Graph size ∝ tool catalog | Valid for BFCL (131 nodes); irrelevant for retail (12 nodes) | Scale | Not here | Out of scope |
| 21 | No transfer / cheap guidance model | Open question, not a flaw | Efficiency | Maybe, risky | Optional later |

**Calibration against τ-bench's own failure analysis** (GPT-4o, retail, 40
failed tasks): wrong argument/information ≈50%, wrong decision/policy ≈25%,
partial resolution of compound requests ≈19%; 4 of 40 came from user-instruction
issues.
- P2 targets policy decisions; P3 targets compound requests and recalled IDs;
  P1/P4/P5 improve the quality and cost of guidance itself.
- **Honest limit:** the largest bucket (picking a wrong-but-valid item or
  argument) is barely touched by any of these.

**Environment check (verified in `tau_bench/envs/retail/tools/`):** the tools
already reject non-pending cancel/modify, non-delivered return/exchange,
invalid cancel reasons, unknown order/item/payment IDs, insufficient gift-card
balance, and a second items modification (status changes after the first).
So hard guards on those rules mostly save a wasted turn. The rules the
environment **cannot** see — and where guards can change the reward — are:
authentication first, explicit confirmation, collecting all items before the
single modify/exchange call, and one user per conversation.

---

## 2. Kept problems → related work → applicability

### P1 — Localization by string match; full-graph fallback on miss

| Architecture | Mechanism | Evidence |
|---|---|---|
| SOP-Agent | Tracks position in a decision graph; exposes only child actions as function calls; branch chosen by the LLM's own call | 99.8% vs ReAct 67.4% on its customer-service benchmark; brittle to SOP errors and compound conditions |
| StateFlow | Separates process grounding (states; transitions by rules or LLM) from sub-task solving | Higher success at lower cost on InterCode SQL, ALFWorld |
| COVENANT | Controller owns traversal, shows only the active node; verify-repair-commit | +29.9 points avg (GuideBench, ToolSandbox, τ-bench); 1.26× model calls, 2.48× wall clock; regressed on airline policy conditions |
| FlowAgent | Controllers supervise the path while the LLM handles out-of-workflow queries | Compliance + flexibility on three datasets |

**Decision**
- **Adopt** state-driven localization (StateFlow): node comes from a
  tool→node map plus task state, not text matching.
- **Adopt** abstention on low confidence instead of full-graph fallback
  (paper's Table 3 + FLARE-style "act only when confident").
- **Reject** hard tool filtering / controller-owned traversal (SOP-Agent,
  COVENANT) as default: τ-bench users stack and switch requests, and COVENANT
  regressed on exactly the policy-dependent conditions retail has. Branch
  pruning is shown to the agent as a hint, not enforced.

### P2 — Rules are advice only

| Architecture | Mechanism | Evidence |
|---|---|---|
| ToolGuard (IBM, EMNLP'25 Industry) | Compile policy doc → per-tool guard code, run before each call | τ-bench airline, preliminary |
| AgentSpec | DSL rules: trigger + predicate + enforcement | Millisecond overhead; >90% of unsafe code executions prevented |
| PolicyGuard (2026) | Verifier sub-agent with full dialogue context, gives actionable feedback | τ²-bench airline pass^4 +12/+6/+12 points across three vendors; blocks ~half as often as argument-level guards |
| Blueprint First v2 (2026) | Deterministic engine; LLM only at bounded nodes; preconditions refuse to proceed | ALFWorld 97.0 vs ReAct 91.0, ScienceWorld 56.7 vs 43.3 (Claude Sonnet 4); authors: payoff "in proportion to how procedurally well-defined the workflow is"; v2 no longer reports τ-bench |
| COTA (2026) | Non-binding advice; actor replans | Constructive intervention clearly beats forced action selection |

**Decision**
- **Adopt** deterministic pre-execution guards (ToolGuard/AgentSpec), limited
  to rules the environment can't see and code can check (authentication).
- **Adapt** PolicyGuard for dialogue rules (confirmation, item completeness):
  deterministic check first; an LLM verifier only when the check is undecidable.
- **Adopt** non-binding repair (COTA): a block returns a reason as the tool
  result and the agent replans.
- **Reject** a full blueprint engine: hand-coded per intent, removes what makes
  PG learnable; its own v2 says gains shrink when tasks are less fixed. Borrow
  only its precondition node, which is our guard.

### P3 — Guidance sees only the last 3 raw steps

| Architecture | Mechanism | Evidence |
|---|---|---|
| IRMA | `<memory>` pins user requests; constraint checklist; tool suggestions (extra LLM calls) | GPT-4o retail pass^1 58.3 vs function calling 60.5 (**no gain**); overall pass^5 reported 12.7% above function calling |
| Magentic-One | Task Ledger (facts, plan) + per-step Progress Ledger (done? loop? progress?) + stall counter | Competitive on GAIA, AssistantBench, WebArena |
| ACE | Itemized context with deterministic delta merges | Avoids "context collapse" from repeated LLM rewriting; +10.6% on agents |

**Decision**
- **Adopt** a Task Ledger (Magentic-One), built **deterministically** from tool
  outputs with ACE-style merges — zero LLM calls.
- **Adapt** IRMA memory: pin the user's verbatim requests; no per-turn extraction call.
- **Reject** IRMA's constraint-checklist call: the graph already is the
  constraint source, and it didn't raise retail pass^1.

### P4 — No safeguard when guidance is wrong or ignored

| Architecture | Mechanism | Evidence |
|---|---|---|
| Magentic-One | Stall counter over the progress ledger triggers reflection + replanning | See above |
| COTA | 0.5B comparator; intervenes only when sampled alternatives beat the proposal | ALFWorld 82.8→90.3 (Qwen3-8B); ~1.38× time; evaluated on τ³-retail |
| FLARE | Retrieve only when generation confidence is low | Better factuality with fewer retrievals |

**Decision**
- **Adopt** a deterministic Progress Monitor: repeated identical call, repeated
  error, N turns without ledger change, deviation streak from recommended next nodes.
- Policy: stall or error → escalate to LLM recovery guidance; deviation streak
  without errors → de-escalate to a one-line hint (graph may not fit this
  task); low localization confidence → abstain.
- **Reject** COTA's trained comparator for now: needs model training and
  counterfactual rollouts, not possible with the Gemini API in this sprint.

### P5 — Always-on guidance cost

| Architecture | Mechanism |
|---|---|
| FLARE | Trigger extra work only on need |
| Gemini implicit caching | Shared prompt prefix gets discounted cached tokens; Google advises putting changing content at the end |
| Pi | <1k-token system prompt, 4 tools, extension hooks for context injection and tool blocking |

**Decision — adopt all:** template rendering by default (0 calls); LLM
guidance only on P4 triggers; guidance appended at the tail and never stored in
history; ledger line replaces the raw trajectory window.

### P6 — Noisy acceptance gate (Tier 2, post-sprint)

| Architecture | Mechanism | Evidence |
|---|---|---|
| GEPA (ICLR'26 oral) | Reflective mutation from traces; Pareto frontier over per-task scores | Up to 35× fewer rollouts than GRPO |
| RoboPhD (2026) | Elo tournaments on training data, no validation split | Beat GEPA and hill-climbing at a 1,500-eval budget |
| This repo | Paired CRN evaluation + `pg/stats.py::sequential_gate` | Already implemented |

**Decision:** **adopt** GEPA-style per-task Pareto retention on top of the
existing paired gate; **defer** Elo (needs many candidates).

### P7 — Refiner sees tail-truncated, unattributed failures (Tier 2, post-sprint)

| Source | Mechanism | Evidence |
|---|---|---|
| Who&When (ICML'25) | Automated failure attribution | Best method: failing agent 53.5%, failing **step** only 14.2% → LLM step attribution is unreliable |
| `.taubench_src/auto_error_identification.py` | Labels fault author (user/agent/environment) and type (wrong tool, wrong argument, partial goal) | Local, ready |
| ACE | Delta edits, dedupe, no monolithic rewrite | See above |

**Decision:** **adopt** fault filtering (drop user-simulator faults), anchor
refiner excerpts at deterministic events (guard blocks, tool errors, ledger
mismatches) instead of tail truncation; keep PG's delta-edit format.

---

## 3. PG-H architecture

**Principle:** keep PG's core (graph → localized guidance → evolution). Move
everything code can check out of the LLM (StateFlow / Blueprint lesson); keep
the LLM for judgment and out-of-procedure flexibility (PG / FlowAgent lesson).

```
             tool result / user message
                        │
                        ▼
      TaskLedger.update()          deterministic, 0 LLM calls        (P3)
                        ▼
      ProgressMonitor.update()     loops, errors, stalls, deviation   (P4)
                        ▼
      StateLocalizer.locate()      tool→node map + ledger + cues      (P1)
          │ confidence < τ ──────► abstain (no guidance)
                        ▼
      GuidancePolicy.decide()      template (0 calls) | LLM on trigger (P4/P5)
                        ▼
      context hook: append guidance at tail, never stored             (P5)
                        ▼
      Agent LLM (native tool calling)
                        ▼ proposed tool call
      GuardLayer.check()           ledger predicates + confirmation   (P2)
          ├─ block ─► tool message with repair reason → agent replans
          └─ pass  ─► env.step()
```

| Component | File | Borrowed from | Fixes paper weakness |
|---|---|---|---|
| Schema: `Node.tools`, `Edge.when` (named predicates), guard kinds, relation printed, tool-catalog validation | `pg/graph.py` | StateFlow, ToolGuard | #4, #15, #18 |
| TaskLedger + retail parsers | `pg/ledger.py` (new) | Magentic-One, IRMA, ACE | #16 |
| Predicate registry (named functions, no `eval`) | `pg/predicates.py` (new) | AgentSpec | #14, #15 |
| StateLocalizer (`mode="state"`) + abstain | `pg/localize.py` | StateFlow, FLARE | #4 |
| GuidancePolicy: `template` mode, triggers, ledger line | `pg/guidance.py` | FLARE, Pi | #5, #6, #7, #11 |
| ProgressMonitor | `pg/monitor.py` (new) | Magentic-One | #3, #11 |
| GuardLayer | `pg/guards.py` (new) | ToolGuard, AgentSpec, PolicyGuard, COTA | #14 |
| Native tool-calling loop, `context` + `tool_gate` hooks | `pg/envs/taubench.py` | Pi, τ-bench ToolCallingAgent | enables all |

### 3.1 Graph schema

```json
{"id": "CheckOrderStatus", "type": "ACTION",
 "tools": ["get_order_details"], "cues": ["order status", "order id"]}

{"source": "ConfirmAction", "target": "CancelOrder", "relation": "LEADS_TO",
 "when": ["authenticated", "order_pending", "user_confirmed"],
 "guidance": "...", "pitfalls": "...",
 "guard": {"kind": "require", "tool": "cancel_pending_order",
           "predicates": ["authenticated", "user_confirmed"]}}
```

Conditions become names from a fixed predicate registry. The refiner may
choose predicate names but cannot write code — evolution stays safe and the
validator can check every name.

### 3.2 TaskLedger (retail)

| Field | Updated from |
|---|---|
| `user_id` | `find_user_id_by_email` / `find_user_id_by_name_zip` result |
| `payment_methods`, `order_ids` | `get_user_details` JSON |
| `orders[id]` = status, items, payment | `get_order_details` JSON |
| `done_actions[(tool, order_id)]` | consequential call whose result doesn't start with `Error` |
| `pending_confirmation` | agent message listing action details; resolved by next user message |
| `requests` | first user message verbatim, plus later messages with a new request |

Rendered as one compact block (~100 tokens):

```
STATE: user=yusuf_rossi_9620 (authenticated) | orders: #W2378156 delivered [2 items]
done: none | awaiting confirmation: exchange #W2378156 | open request: "exchange a couple of items"
```

### 3.3 Guards (retail)

| Guard | Tools | Check | Env already enforces? | Priority |
|---|---|---|---|---|
| G1 authenticated | all user/order tools except `find_user_id_*` | `ledger.user_id` set | No | High |
| G2 explicit confirmation | cancel, modify_*, return, exchange | an agent message listing the action's order/items precedes a user affirmative | No | High |
| G3 item completeness | `modify_pending_order_items`, `exchange_delivered_order_items` | the confirmed message named every item ID in the call | No | Medium (heuristic) |
| G4 status fetched | cancel, modify_*, return, exchange | `get_order_details` called for that order this conversation | Rejects wrong status, not skipped check | Low: repair text only |
| G5 IDs / payment / once-only | as above | ledger | **Yes** | Low: repair text only, no block |

A block never ends the turn silently: it returns
`BLOCKED: <rule>. <what to do>` as the tool result, and the agent replans.

### 3.4 Guidance policy

| Situation | Action | Guidance LLM calls |
|---|---|---|
| Localization confidence < 0.5 | Abstain | 0 |
| Node unchanged, no trigger | Inject nothing new | 0 |
| Node changed | Template: active node + outgoing edges whose `when` isn't false + ledger line | 0 |
| Tool error, guard block, or stall | LLM recovery guidance (subgraph + ledger + last error) | 1 |
| ≥2 outgoing edges with undecidable `when` | LLM branch guidance | 1 |
| Deviation streak ≥3 without errors | One-line hint | 0 |

Branch pruning example: at `ConfirmAction` with a delivered order, only the
Return/Exchange edges are shown — a soft fix for "wrong decision" failures.

### 3.5 $0 offline validation before any API spend

Replay `.taubench_src/historical_trajectories/gpt-4o-retail.json` (460 runs =
115 tasks × 4 trials, mean reward 0.604) and `sonnet-35-new-retail.json`
through Ledger + Localizer + Guards, with no model calls:
- ledger parse failures (target 0)
- share of turns localized vs abstained
- guard precision proxy: a block inside a reward=1 run is a false block (that
  run succeeded, so the call was acceptable); blocks in reward=0 runs are
  candidate true catches
- consequential calls without prior explicit confirmation, split by reward

**Go/no-go per guard:** false blocks ≤2% of that guard's checked calls in
successful runs; otherwise relax or drop it before live runs.

---

## 4. Experiment arms (proposed replacement for `PLAN_3DAY_HYBRID.md` §2)

| Arm | Setup | Question |
|---|---|---|
| H0 | No guidance, no guards | Baseline |
| H1 | Paper PG: exact match, full-graph fallback, LLM guidance every turn | Replication |
| H2 | PG + ledger + state localizer + abstain, template guidance | P1+P3+P5: better and cheaper guidance? |
| H3 | H2 + monitor + LLM guidance on triggers only | P4: does selective LLM help over template? |
| H4 | H3 + guards = full PG-H | P2 on top of guidance |
| H5 | Ledger + guards only, no guidance | Control: is the gain just guards? |

If H5 ≈ H4, graph guidance isn't what helps — a publishable finding, not a failure.

## 5. Implementation order (sprint Days 1–2)

| Step | Work | Est. |
|---|---|---|
| 1 | `pg/graph.py` schema, tool-catalog validation, relation printing | 1h |
| 2 | `pg/ledger.py` + `pg/predicates.py` | 3h |
| 3 | `scripts/replay_historical.py` (§3.5) → go/no-go on guards | 1.5h |
| 4 | `pg/localize.py` StateLocalizer | 1h |
| 5 | `pg/guards.py` | 1.5h |
| 6 | `pg/monitor.py` | 0.75h |
| 7 | `pg/guidance.py` policy | 1.5h |
| 8 | `pg/envs/taubench.py` native loop + hooks (already in sprint plan) | 3h |
| 9 | `graphs/taubench_expert.json`: tools, cues, `when`, guards | 1h |
| 10 | Mock smoke test for all arms | 1h |

≈15h of build, then pilot runs. Step 3 comes before any live API call.

## 6. Risks and honest limits

- The largest τ-bench failure bucket (≈50% wrong argument/info) is mostly
  untouched, and the environment already enforces most hard data rules — so
  expect P2's gain to come from confirmation/authentication/completeness only.
- Ledger parsers are hand-written per domain (the same manual cost Blueprint
  First admits); evolution can't create them.
- Deterministic confirmation detection is heuristic; the replay decides whether
  it is precise enough.
- Literature gains come from GPT-4o, Claude and GPT-5.x. Flash-lite may gain
  more — in the paper, PG lifted τ-bench by +13.1 points on Gemini 3.5 Flash
  vs +7.8 on Sonnet 4.6 — or may ignore guidance more often.
- A flash-lite user simulator adds noise; τ-bench and IRMA both report
  simulator-caused failures.
- The predicate registry limits what evolution can express — a deliberate
  safety trade-off.

## 7. Feasibility and expected impact ($0 estimate)

Produced by `scripts/estimate_hybrid_costs.py`, which replays τ-bench's
recorded retail runs (GPT-4o: 460 runs, reward 0.604; Claude 3.5 Sonnet: 920
runs, reward 0.692) and adds each arm's extra calls and tokens. Tokens are
chars/4 approximations; strong-model behaviour is a proxy for flash-lite.
Assumptions: guidance output 250 tokens, guidance prompt template 250 tokens,
ledger line 100 tokens, user-simulator system prompt 400 tokens.

### 7.1 Tokens and calls per episode

| Arm | LLM calls (GPT-4o / Sonnet) | Total tokens (GPT-4o / Sonnet) | vs H0 tokens | vs H0 calls |
|---|---|---|---|---|
| H0 no guidance | 21.4 / 19.7 | 82.3k / 89.0k | — | — |
| H1 paper PG | 35.7 / 33.5 | 109.0k / 117.7k | +32% | +67% / +70% |
| H2 ledger + template | 21.4 / 19.7 | 83.5k / 90.2k | +1% | 0% |
| H3 + triggered LLM guidance | 22.0 / 20.3 | 84.7k / 91.4k | +3% | +3% |
| H4 full PG-H | 22.2 / 20.4 | 85.8k / 92.0k | +4% / +3% | +4% / +3% |
| H5 guards only | 21.6 / 19.8 | 83.5k / 89.6k | +1% | 0–1% |

**PG-H (H4) vs paper PG (H1):** about 21–22% fewer total tokens, 38–39% fewer
LLM calls, 96% fewer guidance calls (14.3 → 0.6 per episode), and 64–78% fewer
output tokens. That means ~1.6× more episodes per free-tier request quota.

**Caching:** guidance at the tail leaves 91% of the agent prompt as a reusable
prefix, vs 73–80% with the paper's layout. With Gemini's 75% cached-token
discount, that is roughly 20–30% lower billed prompt cost on a paid tier.

**Speed (estimate, not measured):** latency tracks call count and output
tokens, so PG-H should run close to no-guidance speed (+3–4%) and roughly
35–45% faster than paper PG.

### 7.2 What the replay says about guards

| Signal | GPT-4o | Sonnet 3.5 |
|---|---|---|
| Episodes with ≥1 tool error (trigger opportunities) | 38.7% | 37.5% |
| Consequential call without an affirmative user message just before — failed runs | 17.0% | 6.4% |
| Same — **successful** runs (would be false blocks) | 9.7% | 5.2% |
| Tool call before authentication (failed / successful) | 0% / 0% | 0.4% / 0.8% |
| Upper bound of guard-fixable episodes (failed and flagged) | 6.7% | 2.1% |

- A keyword confirmation check would wrongly block 5–10% of successful
  episodes → **too imprecise to hard-block**. G2 must be a soft warning or
  LLM-verified (PolicyGuard style) — the replay go/no-go in §3.5 is needed.
- Strong models almost never skip authentication → G1 only matters if
  flash-lite does.
- For strong models the guard ceiling is small (≤7% of runs); weaker models
  may violate more — only the pilot can tell.

### 7.3 Expected success-rate effect (hypotheses, not claims)

| Comparison | Expectation | Basis |
|---|---|---|
| H2/H3 vs H1 | About the same success (±5 points) at ~21% fewer tokens | Same graph content, delivered without per-step generation |
| H4 vs H0 | +5 to +13 points **if** the paper's effect transfers to flash-lite | Paper: +13.1 points on τ-bench with Gemini 3.5 Flash, +7.8 with Sonnet 4.6 |
| H4 vs H3 (guards) | 0–5 points for strong models; unknown for flash-lite | Replay ceiling 2–7% of runs |
| P3 ledger | A few points | Targets compound-request failures (~19% of τ-bench failures) |

With ~30 paired tasks per arm, only large success differences are detectable;
the token and call savings above are the reliable result.

### 7.4 Implementation effort

| Step | Difficulty | Est. | Main risk |
|---|---|---|---|
| Graph schema + validation | Easy | 1h | — |
| Ledger + predicates | Easy–medium | 3h | Confirmation detection |
| Replay go/no-go script | Easy | 1.5h | Partly done (cost estimate exists) |
| State localizer | Easy | 1h | — |
| Guards | Medium | 1.5h | False blocks (see §7.2) |
| Progress monitor | Easy | 0.75h | — |
| Guidance policy | Medium | 1.5h | Trigger tuning |
| Native tool-calling loop | Medium–hard | 3h | litellm ↔ Gemini tool calling, rate limits |
| Graph annotations | Easy | 1h | — |
| Smoke tests | Easy | 1h | — |

Total ≈15h (about 2 working days, roughly 800–1,000 lines). Nothing is
research-hard; the risks are the live Gemini loop and confirmation detection.

## Sources

- [Blueprint First, Model Second (arXiv:2508.02721)](https://arxiv.org/abs/2508.02721)
- [Towards Enforcing Company Policy Adherence in Agentic Workflows / ToolGuard (arXiv:2507.16459)](https://arxiv.org/abs/2507.16459)
- [PolicyGuard (arXiv:2606.29225)](https://arxiv.org/abs/2606.29225)
- [AgentSpec (arXiv:2503.18666)](https://arxiv.org/abs/2503.18666)
- [StateFlow (arXiv:2403.11322)](https://arxiv.org/abs/2403.11322)
- [SOP-Agent (arXiv:2501.09316)](https://arxiv.org/abs/2501.09316)
- [FlowAgent (arXiv:2502.14345)](https://arxiv.org/abs/2502.14345)
- [COVENANT (arXiv:2607.25400)](https://arxiv.org/html/2607.25400)
- [Magentic-One (arXiv:2411.04468)](https://arxiv.org/abs/2411.04468)
- [IRMA — Input Reformulation on τ-bench (arXiv:2508.20931)](https://arxiv.org/abs/2508.20931)
- [ACE — Agentic Context Engineering (arXiv:2510.04618)](https://arxiv.org/abs/2510.04618)
- [FLARE — Active Retrieval Augmented Generation (arXiv:2305.06983)](https://arxiv.org/abs/2305.06983)
- [COTA — Don't Solve, Just Compare (arXiv:2608.21027)](https://arxiv.org/html/2608.21027)
- [GEPA (arXiv:2507.19457)](https://arxiv.org/abs/2507.19457)
- [RoboPhD (arXiv:2604.04347)](https://arxiv.org/abs/2604.04347)
- [Which Agent Causes Task Failures and When? (arXiv:2505.00212)](https://arxiv.org/abs/2505.00212)
- [τ-bench (arXiv:2406.12045)](https://arxiv.org/abs/2406.12045)
- [Gemini API context caching](https://ai.google.dev/gemini-api/docs/caching)
- [Pi: The Minimal Agent Within OpenClaw (Armin Ronacher)](https://lucumr.pocoo.org/2026/1/31/pi/)
