"""tau-bench retail domain wrapper, implementing pg/runner.py's Env protocol.

Requires the tau-bench package (see PROGRESS.md for install steps -- it is
not vendored into this repo). The retail agent talks to an LLM-simulated
user via litellm; tool calls carry JSON kwargs, e.g.

    Action: get_order_details({"order_id": "W1234567"})
    Action: respond({"content": "Can you confirm your email?"})

`respond` is how the agent talks to the (simulated) customer; every other
action name is one of the retail domain's tools (cancel/modify/return/
exchange order, lookups, etc. -- see tau_bench.envs.retail.tools).
"""

from __future__ import annotations

import json
import random
from typing import List, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from tau_bench.envs import get_env
from tau_bench.envs.retail.tasks_test import TASKS_TEST
from tau_bench.envs.retail.tasks_train import TASKS_TRAIN
from tau_bench.envs.retail.tasks_dev import TASKS_DEV
from tau_bench.types import Action, RESPOND_ACTION_NAME

_SPLITS = {"test": TASKS_TEST, "train": TASKS_TRAIN, "dev": TASKS_DEV}


class TauBenchEnv:
    """Wraps tau_bench.envs.retail.MockRetailDomainEnv.

    task_id is the string form of an index into the chosen task split (see
    `task_ids()`). The user simulator's dollar cost (litellm-tracked, not
    token-tracked -- it isn't our own LLM object) is exposed per episode via
    `user_cost_usd` so callers can report it separately from agent tokens.
    """

    def __init__(self, user_model: str = "gemini-3.5-flash-lite",
                 user_provider: str = "gemini", task_split: str = "test"):
        self.user_model = user_model
        self.user_provider = user_provider
        self.task_split = task_split
        self._env = get_env("retail", user_strategy="llm", user_model=user_model,
                             task_split=task_split, user_provider=user_provider,
                             task_index=0)
        self.task_id = "0"
        self.done = False
        self._last_reward = 0.0
        self.user_cost_usd = 0.0

    @staticmethod
    def task_ids(n: int, seed: int = 1, task_split: str = "test") -> List[str]:
        """Deterministic n-task subset of the split, as index strings."""
        total = len(_SPLITS[task_split])
        n = min(n, total)
        idx = list(range(total))
        random.Random(seed).shuffle(idx)
        return [str(i) for i in idx[:n]]

    @property
    def description(self) -> str:
        task = self._env.task
        return (f"Retail support conversation (task {self.task_id}). Follow the "
                f"retail agent policy: authenticate the user first (email, or "
                f"name+zip), and confirm explicitly before any cancel/modify/"
                f"return/exchange. Underlying scenario: {task.instruction}")

    def reset(self, task_id: str) -> str:
        self.task_id = task_id
        self.done = False
        self._last_reward = 0.0
        self.user_cost_usd = 0.0
        resp = self._env.reset(task_index=int(task_id))
        return resp.observation

    def actions(self) -> List[str]:
        return [t["function"]["name"] for t in self._env.tools_info] + [RESPOND_ACTION_NAME]

    def step(self, action: str, args: str = "") -> Tuple[str, bool]:
        try:
            kwargs = json.loads(args) if args.strip() else {}
            if not isinstance(kwargs, dict):
                raise ValueError("args must be a JSON object")
        except (json.JSONDecodeError, ValueError) as e:
            return f"Error: could not parse args as a JSON object ({e}).", False

        try:
            resp = self._env.step(Action(name=action, kwargs=kwargs))
        except Exception as e:  # malformed/unknown action from the solver
            return f"Error: {e}", False

        self.done = resp.done
        if resp.done:
            self._last_reward = resp.reward
            self.user_cost_usd = self._env.user.get_total_cost()
        return resp.observation, resp.done

    def score(self) -> float:
        return self._last_reward
