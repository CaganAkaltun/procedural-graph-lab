"""LLM interface + usage accounting + a deterministic mock for smoke tests.

To run for real, fill in `AnthropicLLM.complete()` (or write your own class with
the same two-method interface). Everything else in the scaffold is provider
agnostic.

Token accounting is deliberately split by *role* (solver / guidance / refiner)
because the whole point of the cost analysis in the report is that the paper
reports only the total.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def rough_tokens(text: str) -> int:
    """~4 chars per token. Good enough for relative comparisons in the mock."""
    return max(1, len(text) // 4)


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens


@dataclass
class UsageTracker:
    by_role: Dict[str, Usage] = field(default_factory=lambda: defaultdict(Usage))
    # USD per 1M tokens; override for your provider/model.
    price_in: float = 0.30
    price_out: float = 2.50

    def record(self, role: str, prompt: str, completion: str) -> None:
        u = self.by_role[role]
        u.calls += 1
        u.prompt_tokens += rough_tokens(prompt)
        u.completion_tokens += rough_tokens(completion)

    def total(self) -> Usage:
        out = Usage()
        for u in self.by_role.values():
            out.add(u)
        return out

    def cost_usd(self) -> float:
        t = self.total()
        return (t.prompt_tokens * self.price_in + t.completion_tokens * self.price_out) / 1e6

    def summary(self) -> Dict[str, object]:
        t = self.total()
        return {
            "calls_total": t.calls,
            "tokens_total": t.total,
            "cost_usd": round(self.cost_usd(), 4),
            **{f"{role}_calls": u.calls for role, u in self.by_role.items()},
            **{f"{role}_tokens": u.total for role, u in self.by_role.items()},
        }


class LLM(Protocol):
    def complete(self, prompt: str, role: str = "solver",
                 system: Optional[str] = None, max_tokens: int = 1024) -> str: ...


class AnthropicLLM:
    """Fill this in to run for real.

    from anthropic import Anthropic
    client = Anthropic()
    msg = client.messages.create(model=self.model, max_tokens=max_tokens,
                                 system=system or "", temperature=0,
                                 messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if b.type == "text")
    """

    def __init__(self, model: str = "claude-haiku-4-5-20251001",
                 tracker: Optional[UsageTracker] = None):
        self.model = model
        self.tracker = tracker or UsageTracker()
        self._client = None

    def complete(self, prompt: str, role: str = "solver",
                 system: Optional[str] = None, max_tokens: int = 1024) -> str:
        raise NotImplementedError(
            "Wire your provider here (see docstring). Keep temperature=0 and "
            "record usage via self.tracker.record(role, prompt, text)."
        )


class GeminiLLM:
    """Google Gemini backend (free tier). Requires `pip install google-genai`
    and a `GEMINI_API_KEY` environment variable — never hardcode the key.
    """

    def __init__(self, model: str = "gemini-3.5-flash-lite",
                 tracker: Optional[UsageTracker] = None,
                 price_in: float = 0.0, price_out: float = 0.0):
        self.model = model
        self.tracker = tracker or UsageTracker()
        self.tracker.price_in = price_in
        self.tracker.price_out = price_out
        self._client = None

    def _client_or_init(self):
        if self._client is None:
            from google import genai
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "Set the GEMINI_API_KEY environment variable before using GeminiLLM."
                )
            self._client = genai.Client(api_key=api_key)
        return self._client

    def complete(self, prompt: str, role: str = "solver",
                 system: Optional[str] = None, max_tokens: int = 1024) -> str:
        client = self._client_or_init()
        from google.genai import types
        config = types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=max_tokens,
            system_instruction=system or None,
        )
        resp = client.models.generate_content(
            model=self.model, contents=prompt, config=config,
        )
        text = resp.text or ""
        usage = getattr(resp, "usage_metadata", None)
        if usage is not None:
            u = self.tracker.by_role[role]
            u.calls += 1
            u.prompt_tokens += usage.prompt_token_count or 0
            u.completion_tokens += usage.candidates_token_count or 0
        else:
            self.tracker.record(role, prompt, text)
        return text


class MockLLM:
    """Deterministic stand-in that plays solver / guidance / refiner.

    The solver is a weak-but-not-stupid policy: it follows an explicit
    'NEXT:' instruction when guidance provides one, otherwise it picks the
    first action it has not tried recently. That is enough for the smoke test
    to show guidance changing behaviour, without pretending to be an LLM.
    """

    def __init__(self, tracker: Optional[UsageTracker] = None, obedience: float = 1.0):
        self.tracker = tracker or UsageTracker()
        self.obedience = obedience
        self._refiner_turn = 0

    def complete(self, prompt: str, role: str = "solver",
                 system: Optional[str] = None, max_tokens: int = 1024) -> str:
        text = getattr(self, f"_{role}")(prompt)
        self.tracker.record(role, (system or "") + prompt, text)
        return text

    # ------------------------------------------------------------- roles ----
    def _solver(self, prompt: str) -> str:
        """Weak policy: obey an explicit `NEXT:` instruction, else pseudo-random.

        The unguided fallback is deterministic given the trajectory (hash-based)
        so runs are reproducible, but it has no procedural knowledge -- which is
        the whole point of the toy comparison.
        """
        hint = re.search(r"NEXT:\s*([A-Za-z0-9_]+)", prompt)
        available = re.findall(r"AVAILABLE_ACTIONS:\s*(.+)", prompt)
        actions = [a.strip() for a in available[-1].split(",")] if available else []
        tried = re.findall(r"^Action:\s*([A-Za-z0-9_]+)", prompt, flags=re.M)
        task_line = (re.search(r"TASK:\s*(.+)", prompt) or re.match(r"", "")).group(0)
        seed = hashlib.sha1((task_line + "|" + "|".join(tried)).encode()).digest()
        obeys = (seed[1] % 100) < int(self.obedience * 100)
        if hint and hint.group(1) in actions and obeys:
            choice = hint.group(1)
        elif actions:
            pool = [a for a in actions if not tried or a != tried[-1]] or actions
            choice = pool[seed[0] % len(pool)]
        else:
            choice = "noop"
        return f"Thought: proceeding.\nAction: {choice}()"

    def _guidance(self, prompt: str) -> str:
        # Pull the first hop-1 transition out of the serialized subgraph and
        # turn it into an imperative instruction.
        m = re.search(r"-> \[([A-Za-z0-9_]+)\]", prompt)
        target = m.group(1) if m else "continue"
        g = re.search(r"\* Guidance: (.+)", prompt)
        p = re.search(r"\* Pitfalls to Avoid: (.+)", prompt)
        lines = [f"NEXT: {target}"]
        if g:
            lines.append(f"How: {g.group(1)}")
        if p:
            lines.append(f"Avoid: {p.group(1)}")
        return "\n".join(lines)

    def _advisor(self, prompt: str) -> str:
        """Graph-free advisor (arm A1): generic, trajectory-only advice."""
        tried = re.findall(r"^Action:\s*([A-Za-z0-9_]+)", prompt, flags=re.M)
        last = tried[-1] if tried else "nothing"
        return (f"You last ran {last}. Re-read the objective, avoid repeating an "
                f"action that produced no new information, and verify before you finish.")

    _REFINER_SCRIPT = [
        # round 1: insert the missing verification step + a hard guard
        """{"add_nodes": [{"id": "Verify", "type": "ACTION",
             "description": "Verify the extracted candidate against the evidence."}],
            "delete_nodes": [],
            "add_edges": [
              {"source": "Extract", "target": "Verify", "relation": "LEADS_TO",
               "condition": "extracted a candidate",
               "guidance": "Verify the extracted answer against the passage.",
               "pitfalls": "Never submit an unverified answer."},
              {"source": "Verify", "target": "Submit", "relation": "LEADS_TO",
               "condition": "verification passed",
               "guidance": "Submit the verified answer.",
               "pitfalls": "Do not search again after verification.",
               "guard": {"kind": "require_before", "tool": "Submit",
                         "requires": ["Verify"]}}],
            "delete_edges": [{"source": "Extract", "target": "Submit"}]}""",
        # round 2: a cosmetic self-loop -- cycle repair removes it, gate ties
        """{"add_nodes": [], "delete_nodes": [],
            "add_edges": [{"source": "Search", "target": "Search",
                           "relation": "LEADS_TO",
                           "guidance": "Search again with a different query.",
                           "pitfalls": "Do not loop forever."}],
            "delete_edges": []}""",
        # round 3: harmful -- removes a required transition, gate must reject
        """{"add_nodes": [], "delete_nodes": [],
            "add_edges": [{"source": "Search", "target": "Extract",
                           "relation": "LEADS_TO",
                           "guidance": "Skip reading and extract directly.",
                           "pitfalls": "None."}],
            "delete_edges": [{"source": "Search", "target": "Read"}]}""",
    ]

    def _refiner(self, prompt: str) -> str:
        """Scripted edit sets: repair, tie, harmful (rejected), then a repeat."""
        idx = self._refiner_turn
        self._refiner_turn += 1
        return self._REFINER_SCRIPT[min(idx, len(self._REFINER_SCRIPT) - 1)]
