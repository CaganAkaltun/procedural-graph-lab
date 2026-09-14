# Weak sides of the Procedural Graph approach (arXiv:2609.09153v1)

Step 1 of the hybrid analysis. Section/table numbers refer to the paper.
**Realistic verdicts (valid / partly valid / weak) and which items were kept
as solvable problems P1–P7 are in `HYBRID_PG_ARCHITECTURE.md` §1** — read that
table before citing any item below; #10, #13 and #19 were judged mostly unfair
or negligible on review.

---

## A. What causes the gain is never isolated

**1. No control for "an extra LLM call, but no graph"**
- **Problem:** PG adds a second LLM (the guidance model) that writes fresh advice at every step. None of the baselines write new advice with an LLM at each step; they inject stored or retrieved text (Table 6). "The graph helps" and "a second opinion every step helps" are mixed together.
- **Why:** Table 3 changes graph scope and raw-vs-generated guidance, but a graph is always present. No setup gives the same guidance model only the task and trajectory.

**2. No test that the graph's structure matters**
- **Problem:** The core claim is that *connected* transitions beat independent tips (§3.2). Never tested against the same edge texts with shuffled connections, or as a flat list of tips.
- **Why:** Without that control, the graph may just be a container for domain tips.

**3. No measure of whether the agent follows the graph**
- **Problem:** Guidance "biases without dictating" (§3.2), but how often the agent's action matches the recommended transition, or whether following it relates to success, is never reported.
- **Why:** Evidence is single hand-picked traces (App. C.3, F); the authors say these "do not establish how frequently each behavior occurs."

**4. Node-matching accuracy never reported; a miss triggers the worst setup**
- **Problem:** The current node is found by exact string match of the last action to a node id (Eq. 2); on failure the guidance model gets the entire graph.
- **Why:** Full-graph generated guidance is the worst setup on ALFWorld (54.48 vs 72.58 with no graph, Table 3). Reasoning/status nodes and text-only turns have no tool name to match.

## B. Cost and latency

**5. Large token and latency overhead, missing from the main results**
- **Problem:** Table 1 reports accuracy only. Against no graph: +85% tokens on MultiChallenge, +33% GDPval, +55% ALFWorld (Table 3); HotpotQA 1.6–2.7× tokens and 1.75–2.2× latency (Table 9).
- **Why:** PG is never compared against baselines given the same token budget.

**6. Guidance regenerated every step, even when nothing changed**
- **Problem:** One guidance call per step regardless of node, observation or error changes.
- **Why:** No caching or trigger rule; authors list selective generation as future work (§6).

**7. Prompt layout defeats prompt caching**
- **Problem:** In the solver prompt (App. B.5) guidance, which changes every step, sits before the trajectory, so the cached history prefix can't be reused.
- **Why:** Histories are long (19–30 steps ALFWorld, ~368k tokens/sample GDPval).

**8. Self-evolution cost never reported**
- **Problem:** Each round = training episodes + full validation run (1,000 samples on HotpotQA), up to 10 rounds, plus an 8,192-token refiner call.
- **Why:** Only final accuracy is shown.

## C. Statistical reliability

**9. Acceptance gate easily fooled by noise**
- **Problem:** Candidate kept if validation score ≥ the stored score, ties included (Eq. 5); scored once, no paired test, incumbent never re-scored.
- **Why:** Stored score is upward-biased (it already won); ties let neutral edits pile up; with 20 validation episodes decisions "turn on one or two episodes" (§5.4).

**10. Most main-table wins inside confidence intervals**
- **Problem:** e.g. τ-bench Sonnet 73.91 [65.84, 81.99] vs ExpeL 71.30 [63.05, 79.56]; small test sets; no repeated runs.
- **Why:** The sign test counts any win equally; no per-task paired test. *(On review: mostly unfair — see architecture doc §1.)*

**11. A graph can badly hurt, with no run-time protection**
- **Problem:** MultiChallenge expert graph drops success 87.50 → 58.93; one-time update → 53.57 (Table 2); HotpotQA scratch one-time build 69.49 vs 71.21.
- **Why:** Guidance always injected as authoritative; Modes 1, 2, 4 have no validation; nothing backs off at run time.

**12. Hard to reproduce or compare across tables**
- **Problem:** Same no-graph baseline differs across tables (Flash MultiChallenge 81.33 / 87.50 / 80.27); unspecified "fixed subsets"; Table 1 graph construction mode not stated; code unpublished.
- **Why:** Numbers can't be combined or checked independently.

**13. Judge and solvers can share a model family**
- **Problem:** HotpotQA and MultiChallenge judged by Gemini 3.1 Pro while two solvers are Gemini.
- **Why:** Possible same-family bias, uncontrolled. *(On review: weak — only 2 of 7 benchmarks.)*

## D. Design limitations

**14. Rules are only advice**
- **Problem:** Hard rules (τ-bench explicit confirmation; EnterpriseArena single pending request) exist only as `pitfalls` text.
- **Why:** "Soft integration" by design (§3.2); one ignored pitfall fails a policy episode.

**15. Edge types and conditions barely do anything**
- **Problem:** The serializer does not print relation labels (App. B.5); example conditions are just tool names.
- **Why:** Conditions are free text no code checks.

**16. Guidance model sees only the last 3 steps**
- **Problem:** w = 3 (§4).
- **Why:** Key facts older than 3 steps (authenticated, confirmed, pending request) are invisible; guidance can contradict the solver.

**17. Refiner can't see early failures**
- **Problem:** Joined trajectories are cut from the beginning (§3.3, Alg. 1).
- **Why:** Earlier trajectories and early in-episode mistakes are dropped.

**18. Validator doesn't check node names against real tools**
- **Problem:** Tool-name matching is only requested in the refiner prompt (App. B.6).
- **Why:** An invented node name is never matched → silent full-graph fallback (#4).

**19. Rejection record grows without limit**
- **Problem:** Every rejected candidate is passed back to the refiner (§3.3, App. B.6).
- **Why:** No cap described. *(On review: negligible at ≤10 rounds.)*

**20. Graph size grows with the tool list**
- **Problem:** BFCL graph 131 nodes / 265 edges (Table 7).
- **Why:** Nodes map one-to-one to tools; no neighbourhood size limit described.

**21. Transfer to other models untested**
- **Problem:** Construction/evolution only on Gemini 3.5 Flash (App. D.3); solver = guidance = refiner model.
- **Why:** Left to future work (§6); also the obvious unexplored cost lever.
