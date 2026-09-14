"""A deterministic toy environment with real procedural structure.

Purpose: exercise the whole pipeline without API keys, and give the smoke test
something where ordering actually matters (which is exactly the regime where
the paper claims Procedural Graphs help).

Rules:
  * `Search` must precede `Read`
  * `Read` must precede `Extract`
  * `Verify` must precede `Submit` (otherwise Submit fails and ends the episode)
  * repeated actions waste steps
Score is 1.0 for a verified submit, 0.0 otherwise.
"""

from __future__ import annotations

from typing import List, Tuple

ACTIONS = ["Search", "Read", "Extract", "Verify", "Submit", "Browse"]


BASE_DESCRIPTION = ("Answer a multi-hop question: search for evidence, read it, "
                    "extract the answer, verify it, then submit.")


class ToyResearchEnv:
    """Each task id yields a slightly different question, so solver prompts --
    and therefore the mock policy's deterministic choices -- differ per task."""

    def __init__(self, difficulty: int = 1):
        self.difficulty = difficulty
        self.reset("t0")

    # ------------------------------------------------------------------ api --
    @property
    def description(self) -> str:
        return f"{BASE_DESCRIPTION} [question id: {getattr(self, 'task_id', 'n/a')}]"

    def reset(self, task_id: str) -> str:
        self.task_id = task_id
        self.done = False
        self.success = False
        self.history: List[str] = []
        self.state = {"searched": False, "read": False, "extracted": False,
                      "verified": False}
        return "You are given a question. No evidence gathered yet."

    def actions(self) -> List[str]:
        return list(ACTIONS)

    def step(self, action: str) -> Tuple[str, bool]:
        self.history.append(action)
        s = self.state

        if action == "Search":
            s["searched"] = True
            return "Search returned 3 candidate passages.", False
        if action == "Browse":
            return "Browse returned nothing useful (distractor action).", False
        if action == "Read":
            if not s["searched"]:
                return "Error: nothing to read, no search has been run.", False
            s["read"] = True
            return "Read the top passage; it mentions a bridge entity.", False
        if action == "Extract":
            if not s["read"]:
                return "Error: no passage in memory to extract from.", False
            s["extracted"] = True
            return "Extracted a candidate answer from the passage.", False
        if action == "Verify":
            if not s["extracted"]:
                return "Error: nothing extracted, verification is meaningless.", False
            s["verified"] = True
            return "Verification passed: the candidate answer matches the evidence.", False
        if action == "Submit":
            self.done = True
            if s["verified"]:
                self.success = True
                return "Submitted a verified answer. Task complete.", True
            return "Submitted an unverified answer. Rejected. Task failed.", True
        return f"Unknown action {action!r}.", False

    def score(self) -> float:
        return 1.0 if self.success else 0.0


def expert_graph():
    """A small hand-written PG for the toy env (paper's 'expert prior')."""
    from ..graph import Edge, Node, ProceduralGraph
    nodes = [
        Node("Start", "STATUS", "Question received, no evidence yet."),
        Node("Search", "ACTION", "Run a search to retrieve candidate passages."),
        Node("Read", "ACTION", "Read the retrieved passages."),
        Node("Extract", "ACTION", "Extract the candidate answer from the passage."),
        Node("Submit", "ACTION", "Submit the final answer."),
        Node("End", "TERMINAL", "Episode finished."),
    ]
    edges = [
        Edge("Start", "Search", condition="no evidence gathered",
             guidance="Start by searching for evidence.",
             pitfalls="Do not answer before any evidence exists."),
        Edge("Search", "Read", condition="search returned",
             guidance="Read the top passage and look for the bridge entity.",
             pitfalls="Do not skip reading; the bridge entity lives in the text."),
        Edge("Read", "Extract", condition="read the top passage",
             guidance="Extract the candidate answer.",
             pitfalls="Do not extract before reading."),
        Edge("Extract", "Submit", condition="extracted a candidate",
             guidance="Submit the answer.",
             pitfalls="Answer concisely."),
        Edge("Submit", "End", guidance="Finish."),
    ]
    return ProceduralGraph(nodes, edges)


def correct_graph():
    """The repaired PG: the Verify step is present and enforced by a guard."""
    from ..graph import Edge, Node
    g = expert_graph()
    g.nodes["Verify"] = Node("Verify", "ACTION",
                             "Verify the extracted candidate against the evidence.")
    g.edges = [e for e in g.edges if not (e.source == "Extract" and e.target == "Submit")]
    g.edges.insert(3, Edge("Extract", "Verify", condition="extracted a candidate",
                           guidance="Verify the extracted answer against the passage.",
                           pitfalls="Never submit an unverified answer."))
    g.edges.insert(4, Edge("Verify", "Submit", condition="verification passed",
                           guidance="Submit the verified answer.",
                           pitfalls="Do not search again after verification.",
                           guard={"kind": "require_before", "tool": "Submit",
                                  "requires": ["Verify"]}))
    return g
