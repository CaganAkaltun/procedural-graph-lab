"""ReAct solver loop with pluggable guidance, guards and telemetry."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

from .graph import Edge, ProceduralGraph
from .guidance import GuidanceConfig, GuidanceManager
from .llm import UsageTracker
from .telemetry import NullLogger, RunLogger

ACTION_RE = re.compile(r"Action:\s*([A-Za-z0-9_]+)\s*\((.*?)\)", re.S)

SOLVER_PROMPT = """You are solving the following task.

TASK: {task}

AVAILABLE_ACTIONS: {actions}

{guidance_block}Current trajectory:
{trajectory}

Output exactly one Thought line and one Action line:
Thought: <reasoning>
Action: <action_name>(<args>)
"""


class Env(Protocol):
    """Minimal environment interface. Wrap ALFWorld / HotpotQA / tau-bench here."""

    def reset(self, task_id: str) -> str: ...
    def actions(self) -> List[str]: ...
    def step(self, action: str) -> Tuple[str, bool]: ...
    def score(self) -> float: ...
    @property
    def description(self) -> str: ...


@dataclass
class EpisodeResult:
    task_id: str
    score: float
    steps: int
    trajectory: List[Tuple[str, str]] = field(default_factory=list)
    visited_edges: List[Tuple[str, str, str]] = field(default_factory=list)
    guard_blocks: int = 0
    false_blocks: int = 0
    repeats: int = 0
    guidance_stats: Dict[str, Any] = field(default_factory=dict)

    def as_row(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id, "score": self.score, "steps": self.steps,
            "guard_blocks": self.guard_blocks, "repeats": self.repeats,
        }


def _check_guards(graph: ProceduralGraph, action: str, visited_nodes: List[str]
                  ) -> Optional[str]:
    """Guard-PG: turn edge conditions into executable preconditions (idea I4).

    Supported kinds:
      require_before : tool X may only run after every node in `requires`
      forbid_repeat  : tool X may not run twice in a row
    Returns a repair message when the call must be blocked, else None.
    """
    for edge, guard in graph.all_guards():
        kind = guard.get("kind")
        tool = guard.get("tool")
        if tool and tool != action:
            continue
        if kind == "require_before":
            missing = [r for r in guard.get("requires", []) if r not in visited_nodes]
            if missing:
                return (f"BLOCKED by procedural guard on edge "
                        f"[{edge.source}->{edge.target}]: '{action}' requires "
                        f"{missing} to run first. {edge.pitfalls}")
        elif kind == "forbid_repeat":
            if visited_nodes and visited_nodes[-1] == action:
                return (f"BLOCKED by procedural guard: '{action}' was just executed "
                        f"and produced no new information. {edge.pitfalls}")
    return None


def run_episode(env: Env, task_id: str, llm, graph: Optional[ProceduralGraph],
                cfg: GuidanceConfig, max_steps: int = 20,
                guidance_mgr: Optional[GuidanceManager] = None) -> EpisodeResult:
    obs = env.reset(task_id)
    task = env.description

    mgr = guidance_mgr
    if mgr is None and cfg.mode != "none":
        assert graph is not None, "graph required for guided arms"
        mgr = GuidanceManager(graph, llm, cfg)
    if mgr is not None:
        mgr.reset_episode()

    trajectory: List[Tuple[str, str]] = []
    visited_nodes: List[str] = []
    visited_edges: List[Tuple[str, str, str]] = []
    last_action: Optional[str] = None
    guard_blocks = 0
    repeats = 0
    done = False
    steps = 0

    for steps in range(1, max_steps + 1):
        guidance_block = ""
        if mgr is not None:
            g = mgr.step(task, trajectory, last_action, obs, task_id)
            if g.text:
                guidance_block = f"PROCEDURAL GUIDANCE:\n{g.text}\n\n"
            if g.node:
                visited_nodes.append(g.node)
                for key in g.active_edges:
                    visited_edges.append(key)
                    if graph is not None:
                        matching = [e for e in graph.edges if e.key == key]
                        if matching:
                            graph.note_visit(matching[0])

        traj_text = "\n".join(f"Action: {a}\nObservation: {o}" for a, o in trajectory[-6:])
        prompt = SOLVER_PROMPT.format(task=task, actions=", ".join(env.actions()),
                                      guidance_block=guidance_block,
                                      trajectory=traj_text or "(empty)")
        raw = llm.complete(prompt, role="solver")
        m = ACTION_RE.search(raw)
        action = m.group(1) if m else "noop"

        if last_action == action:
            repeats += 1

        if cfg.guards and graph is not None:
            repair = _check_guards(graph, action, visited_nodes + [a for a, _ in trajectory])
            if repair is not None:
                guard_blocks += 1
                trajectory.append((action, repair))
                obs, last_action = repair, action
                continue

        obs, done = env.step(action)
        trajectory.append((action, obs))
        last_action = action
        if done:
            break

    return EpisodeResult(
        task_id=task_id, score=env.score(), steps=steps, trajectory=trajectory,
        visited_edges=visited_edges, guard_blocks=guard_blocks, repeats=repeats,
        guidance_stats=mgr.stats() if mgr is not None else {},
    )


def run_arm(env_factory, task_ids: List[str], llm, graph: Optional[ProceduralGraph],
            cfg: GuidanceConfig, max_steps: int = 20,
            logger: Optional[RunLogger] = None, arm_id: str = "") -> Dict[str, Any]:
    """Run one experimental arm over a fixed task list (paired design).

    Pass a RunLogger to stream per-episode telemetry for the dashboard.
    """
    tracker: UsageTracker = getattr(llm, "tracker", UsageTracker())
    log = logger or NullLogger()
    arm_id = arm_id or cfg.name
    before = tracker.total().total
    mgr = None
    if cfg.mode != "none":
        assert graph is not None
        mgr = GuidanceManager(graph, llm, cfg)

    log.arm_start(arm_id, cfg.name, len(task_ids))
    results: List[EpisodeResult] = []
    for tid in task_ids:
        env = env_factory()
        ep_before = tracker.total().total
        res = run_episode(env, tid, llm, graph, cfg, max_steps, guidance_mgr=mgr)
        results.append(res)
        log.episode_end(arm_id, tid, res.score, res.steps,
                        tracker.total().total - ep_before, res.guard_blocks,
                        res.repeats, mgr.stats() if mgr is not None else {})

    scores = [r.score for r in results]
    summary = {
        "arm": cfg.name,
        "n": len(results),
        "success": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "avg_steps": round(sum(r.steps for r in results) / max(len(results), 1), 2),
        "repeats": sum(r.repeats for r in results),
        "guard_blocks": sum(r.guard_blocks for r in results),
        "tokens": tracker.total().total - before,
        "guidance": mgr.stats() if mgr is not None else {},
        "per_task": {r.task_id: r.score for r in results},
    }
    log.arm_end(arm_id, {k: v for k, v in summary.items() if k != "per_task"})
    summary["episodes"] = results
    return summary
