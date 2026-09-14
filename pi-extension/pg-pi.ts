/**
 * pg-pi — Procedural Graph guidance for the Pi coding agent (pi.dev).
 *
 * Maps the three components of arXiv:2609.09153 onto Pi's extension hooks:
 *
 *   guidance injection  ->  `context`   (fires before each LLM call, messages
 *                                        are a deep copy and safe to modify)
 *   hard preconditions  ->  `tool_call` (can block: {block, reason, terminate})
 *   trajectory logging  ->  `turn_end` + `tool_execution_end` + session JSONL
 *
 * Why this matters for the experiment: Pi exposes only four tools
 * (read / write / edit / bash), so the paper's exact-string localizer can never
 * match a node id. Localization here is necessarily semantic — which is exactly
 * the SoftMatch hypothesis (idea I3) under its hardest test.
 *
 * Install:  copy to ~/.pi/agent/extensions/pg-pi.ts  (or pass with `pi -e`)
 * Configure: PG_GRAPH=/path/to/graph.json  PG_MODE=subgraph|full|off
 *            PG_SELECTIVE=1  PG_GUARDS=1  PG_LOG=/path/to/trace.jsonl
 */

import { isToolCallEventType } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";

type Guard =
  | { kind: "require_before"; tool: string; pattern?: string; requires: string[] }
  | { kind: "forbid_pattern"; tool: string; pattern: string; reason?: string };

interface Edge {
  source: string;
  target: string;
  relation?: string;
  condition?: string | null;
  guidance?: string;
  pitfalls?: string;
  guard?: Guard;
  /** words/phrases that indicate the agent is at `source` (semantic localizer) */
  cues?: string[];
}

interface PGNode { id: string; type?: string; description?: string; cues?: string[] }
interface PG { nodes: PGNode[]; edges: Edge[] }

const GRAPH_PATH = process.env.PG_GRAPH ?? ".pi/pg/graph.json";
const MODE = process.env.PG_MODE ?? "subgraph";       // subgraph | full | off
const SELECTIVE = process.env.PG_SELECTIVE !== "0";
const GUARDS = process.env.PG_GUARDS !== "0";
const LOG_PATH = process.env.PG_LOG ?? ".pi/pg/trace.jsonl";
const HOPS = Number(process.env.PG_HOPS ?? 2);

let graph: PG = { nodes: [], edges: [] };
let activeNode = "Start";
let prevNode = "";
let cached = "";
let age = 0;
const visited: string[] = [];
const telemetry = {
  steps: 0, guidanceCalls: 0, cacheHits: 0,
  locExact: 0, locSemantic: 0, locSticky: 0,
  guardBlocks: 0, edgeVisits: {} as Record<string, number>,
};

function log(event: Record<string, unknown>): void {
  try {
    fs.mkdirSync(LOG_PATH.replace(/\/[^/]+$/, ""), { recursive: true });
    fs.appendFileSync(LOG_PATH, JSON.stringify({ t: Date.now(), ...event }) + "\n");
  } catch { /* logging must never break a run */ }
}

function loadGraph(): void {
  try {
    graph = JSON.parse(fs.readFileSync(GRAPH_PATH, "utf-8"));
  } catch {
    graph = { nodes: [{ id: "Start" }, { id: "End", type: "TERMINAL" }], edges: [] };
  }
}

function outEdges(node: string): Edge[] {
  return graph.edges.filter((e) => e.source === node);
}

/** Semantic localization: score each node by cue overlap with the recent text. */
function localize(recent: string): { node: string; stage: string } {
  const text = recent.toLowerCase();
  let best = "", bestScore = 0;
  for (const n of graph.nodes) {
    if (text.includes(n.id.toLowerCase())) return { node: n.id, stage: "exact" };
    const cues = n.cues ?? [];
    const score = cues.filter((c) => text.includes(c.toLowerCase())).length /
                  Math.max(cues.length, 1);
    if (score > bestScore) { best = n.id; bestScore = score; }
  }
  if (bestScore >= 0.5) return { node: best, stage: "semantic" };
  // Sticky: never dump the full graph on a miss — Table 3 of the paper shows
  // full-graph guidance can score below the no-graph baseline.
  return { node: activeNode, stage: "sticky" };
}

function serializeLocal(node: string, hops = HOPS): string {
  const lines: string[] = [];
  const seen = new Set([node]);
  let frontier = [node];
  const meta = graph.nodes.find((n) => n.id === node);
  lines.push(`Active procedure: [${node}] — ${meta?.description ?? ""}`);
  for (let h = 1; h <= hops; h++) {
    const next: string[] = [];
    lines.push(h === 1 ? "Immediate transitions:" : `Horizon (hop ${h}):`);
    for (const u of frontier) {
      for (const e of outEdges(u)) {
        lines.push(`- [${e.source}] -> [${e.target}] (when: ${e.condition ?? "always"})`);
        if (e.guidance) lines.push(`  * do: ${e.guidance}`);
        if (e.pitfalls) lines.push(`  * avoid: ${e.pitfalls}`);
        if (e.guard) lines.push(`  * hard constraint: ${JSON.stringify(e.guard)}`);
        const key = `${e.source}->${e.target}`;
        telemetry.edgeVisits[key] = (telemetry.edgeVisits[key] ?? 0) + 1;
        if (!seen.has(e.target)) { seen.add(e.target); next.push(e.target); }
      }
    }
    frontier = next;
    if (!frontier.length) break;
  }
  return lines.join("\n");
}

function shouldRegenerate(node: string, recent: string): string | null {
  if (!SELECTIVE) return "always";
  if (!cached) return "first_step";
  if (node !== prevNode) return "node_changed";
  if (/error|failed|not found|traceback|no such file/i.test(recent)) return "error_observed";
  if (outEdges(node).length > 1) return "ambiguous_branch";
  if (age >= 4) return "stale";
  return null;
}

export default function activate(pi: any) {
  loadGraph();

  // 1) Guidance injection — fires before every LLM call.
  pi.on("context", async (event: any) => {
    if (MODE === "off") return;
    telemetry.steps += 1;
    const messages = event.messages ?? [];
    const recent = JSON.stringify(messages.slice(-4)).slice(-4000);

    const loc = localize(recent);
    telemetry[`loc${loc.stage[0].toUpperCase()}${loc.stage.slice(1)}` as
      "locExact" | "locSemantic" | "locSticky"] += 1;
    activeNode = loc.node;

    const reason = shouldRegenerate(activeNode, recent);
    let block: string;
    if (reason === null) {
      telemetry.cacheHits += 1;
      age += 1;
      block = cached;
    } else {
      telemetry.guidanceCalls += 1;
      age = 0;
      block = MODE === "full"
        ? graph.edges.map((e) => `[${e.source}]->[${e.target}]: ${e.guidance ?? ""}`).join("\n")
        : serializeLocal(activeNode);
      cached = block;
    }
    prevNode = activeNode;
    if (!visited.includes(activeNode)) visited.push(activeNode);
    log({ kind: "guidance", node: activeNode, stage: loc.stage, reason, regenerated: reason !== null });

    return {
      messages: [
        ...messages,
        {
          role: "user",
          customType: "pg-guidance",
          display: false,
          content:
            "PROCEDURAL GUIDANCE (advisory, from the procedural graph — " +
            "you may deviate with a stated reason):\n" + block,
        },
      ],
    };
  });

  // 2) Hard preconditions — tool_call can block.
  pi.on("tool_call", async (event: any) => {
    if (!GUARDS) return;
    for (const e of graph.edges) {
      const g = e.guard;
      if (!g || g.tool !== event.toolName) continue;
      const cmd = isToolCallEventType("bash", event)
        ? String(event.input.command ?? "")
        : JSON.stringify(event.input ?? {});
      if (g.kind === "forbid_pattern" && new RegExp(g.pattern, "i").test(cmd)) {
        telemetry.guardBlocks += 1;
        log({ kind: "guard_block", edge: `${e.source}->${e.target}`, cmd });
        return { block: true, reason: g.reason ?? `Blocked by procedural guard on [${e.source}->${e.target}]. ${e.pitfalls ?? ""}` };
      }
      if (g.kind === "require_before") {
        if (g.pattern && !new RegExp(g.pattern, "i").test(cmd)) continue;
        const missing = g.requires.filter((r) => !visited.includes(r));
        if (missing.length) {
          telemetry.guardBlocks += 1;
          log({ kind: "guard_block", edge: `${e.source}->${e.target}`, missing, cmd });
          return {
            block: true,
            reason: `Procedural guard: this step requires ${missing.join(", ")} first. ${e.pitfalls ?? ""}`,
          };
        }
      }
    }
  });

  // 3) Trajectory logging for the offline refiner.
  pi.on("tool_execution_end", async (event: any) => {
    log({ kind: "tool", name: event.toolName, isError: event.isError, node: activeNode });
  });

  pi.on("turn_end", async (event: any) => {
    log({ kind: "turn", index: event.turnIndex, node: activeNode });
  });

  pi.on("session_shutdown", async () => {
    log({ kind: "telemetry", ...telemetry });
  });

  // Convenience commands.
  pi.registerCommand("pg-stats", {
    description: "Show procedural-graph telemetry for this session",
    handler: async (_args: string, ctx: any) => {
      const hit = telemetry.steps
        ? ((telemetry.locExact + telemetry.locSemantic) / telemetry.steps).toFixed(2)
        : "n/a";
      ctx.ui.notify(
        `PG: steps=${telemetry.steps} guidance_calls=${telemetry.guidanceCalls} ` +
        `cache_hits=${telemetry.cacheHits} loc_hit_rate=${hit} ` +
        `guard_blocks=${telemetry.guardBlocks}`, "info");
    },
  });

  pi.registerCommand("pg-reload", {
    description: "Reload the procedural graph from disk",
    handler: async (_args: string, ctx: any) => {
      loadGraph();
      cached = "";
      ctx.ui.notify(`PG reloaded: ${graph.nodes.length} nodes, ${graph.edges.length} edges`, "info");
    },
  });
}
