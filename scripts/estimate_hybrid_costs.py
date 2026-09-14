"""$0 estimate of per-arm tokens/calls and guard impact from recorded tau-bench retail runs.

Token counts are chars/4 approximations; GPT-4o behaviour is a proxy for flash-lite.
"""
import json
import os
import re
import statistics as st
import sys
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from pg.graph import ProceduralGraph  # noqa: E402
from tau_bench.envs.retail.tools import ALL_TOOLS  # noqa: E402


def T(s):
    return len(s or "") // 4


TOOLS_TOK = T(json.dumps([t.get_info() for t in ALL_TOOLS]))
G = ProceduralGraph.load(os.path.join(ROOT, "graphs", "taubench_expert.json"))
SUB2 = {n: T(G.serialize_local(n, 2)) for n in G.nodes}
SUB1 = {n: T(G.serialize_local(n, 1)) for n in G.nodes}
GUIDE_TMPL, GUIDE_OUT, LEDGER, USER_SYS = 250, 250, 100, 400

TOOL_NODE = {
    "find_user_id_by_email": "Authenticate", "find_user_id_by_name_zip": "Authenticate",
    "get_user_details": "LookupInfo", "get_product_details": "LookupInfo",
    "list_all_product_types": "LookupInfo", "get_order_details": "CheckOrderStatus",
    "cancel_pending_order": "CancelOrder", "modify_pending_order_address": "ModifyOrder",
    "modify_pending_order_items": "ModifyOrder", "modify_pending_order_payment": "ModifyOrder",
    "modify_user_address": "ModifyOrder", "return_delivered_order_items": "ReturnOrder",
    "exchange_delivered_order_items": "ExchangeOrder", "transfer_to_human_agents": "TransferHuman",
}
CONSEQ = {"cancel_pending_order", "modify_pending_order_address", "modify_pending_order_items",
          "modify_pending_order_payment", "modify_user_address",
          "return_delivered_order_items", "exchange_delivered_order_items"}
PRE_AUTH_OK = {"find_user_id_by_email", "find_user_id_by_name_zip", "list_all_product_types",
               "get_product_details", "calculate", "think", "transfer_to_human_agents"}
AFFIRM = re.compile(r"\b(yes|yeah|yep|confirm|confirmed|proceed|go ahead|sure|correct|"
                    r"please do|that's right|ok|okay|sounds good)\b", re.I)


def _args(tc):
    a = tc["function"].get("arguments") or ""
    return a if isinstance(a, str) else json.dumps(a)


def text(m):
    s = m.get("content") or ""
    for tc in m.get("tool_calls") or []:
        s += tc["function"]["name"] + _args(tc)
    return s


def analyse(path):
    runs = json.load(open(path, encoding="utf-8"))
    rows = []
    for r in runs:
        msgs = r["traj"]
        first_user = next((m.get("content") or "" for m in msgs if m["role"] == "user"), "")
        arm = {k: Counter() for k in ("H0", "H1", "H2", "H3", "H4", "H5")}
        node, last_injected, last_tool_sig = "Start", None, None
        last_user, authed = "", False
        conf_viol = auth_viol = blocks = errors = stalls = agent_calls = 0
        tail_cached = paper_cached = agent_prompt = prev_prompt = 0
        static_prefix = TOOLS_TOK + T(msgs[0].get("content"))
        ctx = TOOLS_TOK
        for i, m in enumerate(msgs):
            if m["role"] == "user":
                if i > 1:
                    up = USER_SYS + sum(T(x.get("content")) for x in msgs[:i] if x["role"] in ("user", "assistant"))
                    for a in arm.values():
                        a["user_calls"] += 1
                        a["prompt"] += up
                        a["out"] += T(m.get("content"))
                last_user = m.get("content") or ""
            elif m["role"] == "tool":
                c = m.get("content") or ""
                if c.startswith("Error"):
                    errors += 1
                if m.get("name", "").startswith("find_user_id") and not c.startswith("Error"):
                    authed = True
            elif m["role"] == "assistant":
                agent_calls += 1
                prompt, out = ctx, T(text(m))
                agent_prompt += prompt
                tail_cached += prev_prompt
                paper_cached += min(static_prefix, prompt)
                prev_prompt = prompt
                calls = m.get("tool_calls") or []
                trigger, block = False, False
                if calls:
                    name = calls[0]["function"]["name"]
                    sig = name + _args(calls[0])
                    if sig == last_tool_sig:
                        stalls += 1
                        trigger = True
                    last_tool_sig = sig
                    if name in CONSEQ and not AFFIRM.search(last_user):
                        conf_viol += 1
                        block = True
                    if name not in PRE_AUTH_OK and not authed:
                        auth_viol += 1
                        block = True
                    node_new = TOOL_NODE.get(name, node)
                else:
                    node_new = node
                prev_msg = msgs[i - 1] if i else {}
                if prev_msg.get("role") == "tool" and (prev_msg.get("content") or "").startswith("Error"):
                    trigger = True
                changed = node_new != last_injected
                node = node_new
                guide_prompt = GUIDE_TMPL + T(first_user) + SUB2.get(node, 0) + sum(T(text(x)) for x in msgs[max(0, i - 6):i])

                for k, a in arm.items():
                    a["agent_calls"] += 1
                    a["prompt"] += prompt
                    a["out"] += out
                arm["H1"]["guide_calls"] += 1
                arm["H1"]["prompt"] += guide_prompt + GUIDE_OUT
                arm["H1"]["out"] += GUIDE_OUT
                for k in ("H2", "H3", "H4"):
                    if changed:
                        arm[k]["prompt"] += SUB1.get(node, 0) + LEDGER
                for k in ("H3", "H4"):
                    if trigger:
                        arm[k]["guide_calls"] += 1
                        arm[k]["prompt"] += guide_prompt + GUIDE_OUT
                        arm[k]["out"] += GUIDE_OUT
                for k in ("H4", "H5"):
                    if block:
                        arm[k]["agent_calls"] += 1
                        arm[k]["prompt"] += prompt + 60
                        arm[k]["out"] += out
                if block:
                    blocks += 1
                if changed:
                    last_injected = node
                ctx += out
                continue
            ctx += T(text(m))
        rows.append(dict(reward=r["reward"], arm=arm, conf_viol=conf_viol, auth_viol=auth_viol,
                         blocks=blocks, errors=errors, stalls=stalls, agent_calls=agent_calls,
                         tail_cached=tail_cached, paper_cached=paper_cached, agent_prompt=agent_prompt))
    return rows


def report(path):
    rows = analyse(path)
    n = len(rows)
    print(f"\n=== {os.path.basename(path)}  runs={n}  mean reward={st.mean(r['reward'] for r in rows):.3f}")
    print(f"tools schema ~{TOOLS_TOK} tok; subgraph h2 mean ~{st.mean(SUB2.values()):.0f} tok, h1 ~{st.mean(SUB1.values()):.0f} tok")
    base = None
    print("| arm | agent calls | guidance calls | user-sim calls | total LLM calls | prompt tok | output tok | total tok | vs H0 tok | vs H0 calls |")
    for k in ("H0", "H1", "H2", "H3", "H4", "H5"):
        ac = st.mean(r["arm"][k]["agent_calls"] for r in rows)
        gc = st.mean(r["arm"][k]["guide_calls"] for r in rows)
        uc = st.mean(r["arm"][k]["user_calls"] for r in rows)
        pt = st.mean(r["arm"][k]["prompt"] for r in rows)
        ot = st.mean(r["arm"][k]["out"] for r in rows)
        calls, tot = ac + gc + uc, pt + ot
        if base is None:
            base = (tot, calls)
        print(f"| {k} | {ac:.1f} | {gc:.1f} | {uc:.1f} | {calls:.1f} | {pt:,.0f} | {ot:,.0f} | {tot:,.0f} | "
              f"{(tot / base[0] - 1) * 100:+.0f}% | {(calls / base[1] - 1) * 100:+.0f}% |")
    ap = sum(r["agent_prompt"] for r in rows)
    print(f"cacheable agent-prompt share: guidance at tail {sum(r['tail_cached'] for r in rows) / ap:.1%} | "
          f"paper layout (guidance before history) {sum(r['paper_cached'] for r in rows) / ap:.1%}")
    fails = [r for r in rows if r["reward"] < 1]
    succ = [r for r in rows if r["reward"] >= 1]
    def share(rs, key):
        return sum(1 for r in rs if r[key] > 0) / max(len(rs), 1)
    print(f"episodes with tool errors: {share(rows, 'errors'):.1%}; with repeated identical call: {share(rows, 'stalls'):.1%}")
    print(f"consequential call w/o affirmative prior user msg: fails {share(fails, 'conf_viol'):.1%} | successes {share(succ, 'conf_viol'):.1%}")
    print(f"tool call before authentication:                   fails {share(fails, 'auth_viol'):.1%} | successes {share(succ, 'auth_viol'):.1%}")
    ub = sum(1 for r in fails if r["conf_viol"] or r["auth_viol"]) / n
    print(f"upper bound on guard-fixable episodes (failed AND flagged) = {ub:.1%} of all runs")


for f in ("gpt-4o-retail.json", "sonnet-35-new-retail.json"):
    report(os.path.join(ROOT, ".taubench_src", "historical_trajectories", f))
