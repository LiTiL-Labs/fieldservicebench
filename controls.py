"""Adversarial controls as mechanical transforms of the oracle plan.

  noop            submit nothing at all (empty plan)
  shortcut        guess the answer with plausible-but-wrong values, no evidence
  state-only      perform the mutation + submit, skip every evidence read
  wrong-evidence  read superseded documents / wrong part codes instead of the
                  current ones, otherwise identical (submit args unchanged)
  wrong-target    aim the mutation at the decoy work order / part
  omission        (extra detection probe) everything except the mutation

Every control must score < 100 while the oracle scores exactly 100.
"""

import copy

READ_TOOLS = {
    "list_customers", "get_customer", "list_sites", "get_site", "list_assets", "get_asset",
    "list_technicians", "get_technician", "list_work_orders", "get_work_order",
    "query_parts", "get_price_book", "list_approvals", "get_schedule",
    "list_emails", "list_documents", "get_document", "get_quote",
}

CONTROL_NAMES = ["noop", "shortcut", "state-only", "wrong-evidence", "wrong-target", "omission"]


def _is_mutation(task, call):
    m = task["contract"]["mutation"]
    return call["tool"] == m["tool"]


def transform(control, task):
    plan = copy.deepcopy(task["plan"])
    if control == "noop":
        return []
    if control == "shortcut":
        return [{"tool": "submit_answer", "args": {"fields": copy.deepcopy(task["shortcut_guess"])}}]
    if control == "state-only":
        return [c for c in plan if c["tool"] not in READ_TOOLS]
    if control == "wrong-evidence":
        swaps = task["evidence_swaps"]
        out = []
        for c in plan:
            if c["tool"] in READ_TOOLS:
                c = copy.deepcopy(c)
                c["args"] = {k: swaps.get(v, v) if isinstance(v, str) else v
                             for k, v in c["args"].items()}
            out.append(c)
        return out
    if control == "wrong-target":
        out = []
        for c in plan:
            if _is_mutation(task, c):
                c = copy.deepcopy(c)
                c["args"].update(copy.deepcopy(task["wrong_target"]))
            out.append(c)
        return out
    if control == "omission":
        return [c for c in plan if not _is_mutation(task, c)]
    raise ValueError(f"unknown control {control}")
