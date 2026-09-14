"""FieldServiceBench-10 — task definitions.

Ten hand-authored scenario spines for a fictional commercial-HVAC field-service
company ("Apex Climate Services"). Three archetypes:

  commit  (FSB-01..04): pick the one authorized repair-visit option and book it
  quote   (FSB-05..07): price a repair from the CURRENT price book and submit
  reserve (FSB-08..10): reserve the correct parts against a work order

Every task is a plain-data spec; builder functions derive, deterministically:
  * seed rows for the task's world cluster        (seed_rows)
  * the natural-language employee prompt          (prompt)
  * the oracle tool-call plan                     (plan)
  * the gold answer + verifier contract           (contract)
  * adversarial-control parameters                (shortcut guess, evidence
    swaps, wrong-target override)

Gold money math uses Decimal over integer cents; nothing gold is ever written
into agent-visible state (world DB or server responses beyond the write the
oracle itself performs).
"""

from decimal import Decimal

NOW = "2026-03-02"          # fixed simulation clock (a Monday)
LABOR_CODE = "LABOR-STD"
LABOR_CURRENT_CENTS = 14800
LABOR_SUPERSEDED_CENTS = 13900


def D(x):
    return Decimal(str(x))


def money(x):
    """Decimal -> exact integer cents."""
    return int(D(x).quantize(Decimal("1")))


def R(table, **row):
    return (table, row)


def C(tool, **args):
    return {"tool": tool, "args": args}


# --------------------------------------------------------------------------
# archetype builders
# --------------------------------------------------------------------------

def build_commit(t):
    """Repair-visit commitment spine."""
    labor_hours = D(t["labor_hours"])
    est = money(D(t["part_price_current"]) * t["part_qty"] + labor_hours * LABOR_CURRENT_CENTS)
    assert est <= t["approval_max"], t["task_id"]  # chosen option is authorized
    booking_id = "BK-0001"  # fresh seed => first generated booking id

    seed = [
        R("customers", id=t["cust"], name=t["cust_name"], tier=t["tier"], region=t["region"], account_status="active"),
        R("sites", id=t["site"], customer_id=t["cust"], name=t["site_name"], address=t["site_addr"]),
        R("sites", id=t["decoy_site"], customer_id=t["cust"], name=t["decoy_site_name"], address=t["decoy_site_addr"]),
        R("assets", id=t["asset"], site_id=t["site"], unit_tag=t["unit"], model=t["model"],
          serial=t["serial"], install_revision=2, install_date="2023-05-11", warranty_until="2028-05-11"),
        R("assets", id=t["decoy_asset"], site_id=t["decoy_site"], unit_tag=t["unit"], model=t["model"],
          serial=t["serial"] + "-D", install_revision=1, install_date="2022-09-02", warranty_until="2027-09-02"),
        R("work_orders", id=t["wo"], customer_id=t["cust"], site_id=t["site"], asset_id=t["asset"],
          kind="repair", status="triaged", priority=t["priority"], description=t["wo_desc"], created_at=NOW),
        R("work_orders", id=t["decoy_wo"], customer_id=t["cust"], site_id=t["decoy_site"], asset_id=t["decoy_asset"],
          kind="repair", status=t["decoy_wo_status"], priority="low", description=t["decoy_wo_desc"], created_at=NOW),
        R("documents", id=t["doc_superseded"], title=f"{t['model']} service bulletin rev{t['doc_rev']-1}",
          kind="service_bulletin", model=t["model"], revision=t["doc_rev"] - 1, status="superseded",
          body=t["doc_superseded_body"]),
        R("documents", id=t["doc_current"], title=f"{t['model']} service bulletin rev{t['doc_rev']}",
          kind="service_bulletin", model=t["model"], revision=t["doc_rev"], status="current",
          body=t["doc_current_body"]),
        R("price_book", id=f"PB-{t['part']}-OLD", code=t["part"], kind="part", revision=1,
          effective_from="2025-10-01", status="superseded", unit_price_cents=t["part_price_superseded"]),
        R("price_book", id=f"PB-{t['part']}-CUR", code=t["part"], kind="part", revision=2,
          effective_from="2026-02-01", status="current", unit_price_cents=t["part_price_current"]),
        R("parts_inventory", part_no=t["part"], description=t["part_desc"], on_hand=t["on_hand"],
          reserved=t["reserved"], quarantined=t["quarantined"], unit_cost_cents=t["part_cost"]),
        R("approvals", id=t["approval"], customer_id=t["cust"], work_order_id=t["wo"],
          max_amount_cents=t["approval_max"], allowed_option="standard", status="approved",
          created_by="d.whitfield"),
        R("email_messages", id=t["email"], folder="inbox", from_addr=t["email_from"],
          to_addr="dispatch@apexclimate.example", subject=t["email_subject"], body=t["email_body"],
          sent_at=NOW + "T08:12:00"),
    ]
    for row in t.get("extra_seed", []):
        seed.append(row)
    for tech in t["techs"]:
        seed.append(R("technicians", **tech))
    for sch in t["schedule"]:
        seed.append(R("schedule", **sch))

    answer = {
        "work_order_id": t["wo"],
        "booking_id": booking_id,
        "tech_id": t["tech"],
        "commit_date": t["date"],
        "option": "standard",
        "part_no": t["part"],
        "est_total_cents": est,
    }
    mutation = C("book_schedule", work_order_id=t["wo"], tech_id=t["tech"],
                 date=t["date"], start_hour=t["start_hour"], hours=t["book_hours"])
    plan = [
        C("list_emails", folder="inbox"),
        C("list_work_orders", customer_id=t["cust"]),
        C("get_asset", asset_id=t["asset"]),
        C("list_documents", kind="service_bulletin", model=t["model"]),
        C("get_document", document_id=t["doc_current"]),
        C("get_price_book", code=t["part"]),
        C("get_price_book", code=LABOR_CODE),
        C("query_parts", part_no=t["part"]),
        C("list_approvals", work_order_id=t["wo"]),
        C("list_technicians", region=t["region"]),
        C("get_schedule", tech_id=t["tech"]),
        mutation,
        C("get_schedule", tech_id=t["tech"]),   # readback
        C("submit_answer", fields=answer),
    ]
    required_reads = [
        C("list_emails", folder="inbox"),
        C("list_work_orders", customer_id=t["cust"]),
        C("get_document", document_id=t["doc_current"]),
        C("get_price_book", code=t["part"]),
        C("get_price_book", code=LABOR_CODE),
        C("query_parts", part_no=t["part"]),
        C("list_approvals", work_order_id=t["wo"]),
    ]
    contract = {
        "task_id": t["task_id"],
        "archetype": "commit",
        "required_reads": required_reads,
        "mutation": mutation,
        "allowlist": {"schedule": [booking_id]},
        "state_assertions": [
            {"sql": f"SELECT COUNT(*) FROM schedule WHERE kind='booking' AND work_order_id='{t['wo']}'",
             "expect": 1},
            {"sql": f"SELECT tech_id || '|' || date || '|' || start_hour || '|' || end_hour "
                    f"FROM schedule WHERE id='{booking_id}'",
             "expect": f"{t['tech']}|{t['date']}|{t['start_hour']}|{t['start_hour'] + t['book_hours']}"},
        ],
        "readback": {"pk": booking_id, "tools": ["get_schedule"]},
        "answer": {
            "fields": answer,
            "types": {"work_order_id": "str", "booking_id": "str", "tech_id": "str",
                      "commit_date": "date", "option": "str", "part_no": "str",
                      "est_total_cents": "int"},
        },
    }
    return {"spec": t, "seed_rows": seed, "prompt": t["prompt"], "plan": plan,
            "contract": contract, "shortcut_guess": t["shortcut_guess"],
            "evidence_swaps": t["evidence_swaps"], "wrong_target": t["wrong_target"]}


def build_quote(t):
    labor_hours = D(t["labor_hours"])
    parts_total = money(D(t["part_price_current"]) * t["part_qty"])
    labor_total = money(labor_hours * LABOR_CURRENT_CENTS)
    total = parts_total + labor_total
    assert total <= t["approval_max"], t["task_id"]
    quote_id = "Q-0001"

    seed = [
        R("customers", id=t["cust"], name=t["cust_name"], tier=t["tier"], region=t["region"], account_status="active"),
        R("sites", id=t["site"], customer_id=t["cust"], name=t["site_name"], address=t["site_addr"]),
        R("sites", id=t["decoy_site"], customer_id=t["cust"], name=t["decoy_site_name"], address=t["decoy_site_addr"]),
        R("assets", id=t["asset"], site_id=t["site"], unit_tag=t["unit"], model=t["model"],
          serial=t["serial"], install_revision=3, install_date="2021-04-19", warranty_until="2026-04-19"),
        R("work_orders", id=t["wo"], customer_id=t["cust"], site_id=t["site"], asset_id=t["asset"],
          kind="repair", status=t["wo_status"], priority="high", description=t["wo_desc"], created_at=NOW),
        R("work_orders", id=t["decoy_wo"], customer_id=t["cust"], site_id=t["decoy_site"], asset_id=t["asset"],
          kind="repair", status=t["decoy_wo_status"], priority="low", description=t["decoy_wo_desc"], created_at=NOW),
        R("documents", id=t["doc_superseded"], title=f"{t['model']} service bulletin rev{t['doc_rev']-1}",
          kind="service_bulletin", model=t["model"], revision=t["doc_rev"] - 1, status="superseded",
          body=t["doc_superseded_body"]),
        R("documents", id=t["doc_current"], title=f"{t['model']} service bulletin rev{t['doc_rev']}",
          kind="service_bulletin", model=t["model"], revision=t["doc_rev"], status="current",
          body=t["doc_current_body"]),
        R("price_book", id=f"PB-{t['part']}-OLD", code=t["part"], kind="part", revision=1,
          effective_from="2025-08-01", status="superseded", unit_price_cents=t["part_price_superseded"]),
        R("price_book", id=f"PB-{t['part']}-CUR", code=t["part"], kind="part", revision=2,
          effective_from="2026-02-01", status="current", unit_price_cents=t["part_price_current"]),
        R("parts_inventory", part_no=t["part"], description=t["part_desc"], on_hand=6,
          reserved=0, quarantined=0, unit_cost_cents=t["part_cost"]),
        R("approvals", id=t["approval"], customer_id=t["cust"], work_order_id=t["wo"],
          max_amount_cents=t["approval_max"], allowed_option="any", status="approved",
          created_by="m.okafor"),
        R("email_messages", id=t["email"], folder="inbox", from_addr=t["email_from"],
          to_addr="estimating@apexclimate.example", subject=t["email_subject"], body=t["email_body"],
          sent_at=NOW + "T07:48:00"),
    ]
    for row in t.get("extra_seed", []):
        seed.append(row)

    answer = {
        "quote_id": quote_id,
        "work_order_id": t["wo"],
        "part_no": t["part"],
        "labor_hours": str(labor_hours.normalize()),
        "parts_total_cents": parts_total,
        "labor_total_cents": labor_total,
        "total_cents": total,
        "approval_id": t["approval"],
    }
    mutation = C("create_quote", work_order_id=t["wo"], labor_hours=str(labor_hours.normalize()),
                 parts=[{"part_no": t["part"], "qty": t["part_qty"]}], option="standard", submit=True)
    extra_required = t.get("extra_required_reads", [])
    plan = [
        C("list_emails", folder="inbox"),
        C("list_work_orders", customer_id=t["cust"]),
        C("get_asset", asset_id=t["asset"]),
        C("list_documents", kind="service_bulletin", model=t["model"]),
        C("get_document", document_id=t["doc_current"]),
        C("get_price_book", code=t["part"]),
        C("get_price_book", code=LABOR_CODE),
    ] + extra_required + [
        C("list_approvals", work_order_id=t["wo"]),
        mutation,
        C("get_quote", work_order_id=t["wo"]),   # readback
        C("submit_answer", fields=answer),
    ]
    required_reads = [
        C("list_emails", folder="inbox"),
        C("list_work_orders", customer_id=t["cust"]),
        C("get_document", document_id=t["doc_current"]),
        C("get_price_book", code=t["part"]),
        C("get_price_book", code=LABOR_CODE),
        C("list_approvals", work_order_id=t["wo"]),
    ] + extra_required
    contract = {
        "task_id": t["task_id"],
        "archetype": "quote",
        "required_reads": required_reads,
        "mutation": mutation,
        "allowlist": {"quotes": [quote_id]},
        "state_assertions": [
            {"sql": f"SELECT total_cents FROM quotes WHERE id='{quote_id}'", "expect": total},
            {"sql": f"SELECT status FROM quotes WHERE id='{quote_id}'", "expect": "submitted"},
            {"sql": f"SELECT COUNT(*) FROM quotes WHERE work_order_id='{t['wo']}'", "expect": 1},
        ],
        "readback": {"pk": quote_id, "tools": ["get_quote"]},
        "answer": {
            "fields": answer,
            "types": {"quote_id": "str", "work_order_id": "str", "part_no": "str",
                      "labor_hours": "decimal", "parts_total_cents": "int",
                      "labor_total_cents": "int", "total_cents": "int", "approval_id": "str"},
        },
    }
    return {"spec": t, "seed_rows": seed, "prompt": t["prompt"], "plan": plan,
            "contract": contract, "shortcut_guess": t["shortcut_guess"],
            "evidence_swaps": t["evidence_swaps"], "wrong_target": t["wrong_target"]}


def build_reserve(t):
    avail_before = t["on_hand"] - t["reserved"] - t["quarantined"]
    assert avail_before >= t["qty"], t["task_id"]
    avail_after = avail_before - t["qty"]
    res_id = "RSV-0001"

    seed = [
        R("customers", id=t["cust"], name=t["cust_name"], tier=t["tier"], region=t["region"], account_status="active"),
        R("sites", id=t["site"], customer_id=t["cust"], name=t["site_name"], address=t["site_addr"]),
        R("sites", id=t["decoy_site"], customer_id=t["cust"], name=t["decoy_site_name"], address=t["decoy_site_addr"]),
        R("assets", id=t["asset"], site_id=t["site"], unit_tag=t["unit"], model=t["model"],
          serial=t["serial"], install_revision=1, install_date="2024-02-08", warranty_until="2029-02-08"),
        R("work_orders", id=t["wo"], customer_id=t["cust"], site_id=t["site"], asset_id=t["asset"],
          kind=t["wo_kind"], status=t["wo_status"], priority=t["priority"], description=t["wo_desc"], created_at=NOW),
        R("work_orders", id=t["decoy_wo"], customer_id=t["cust"], site_id=t["decoy_site"], asset_id=t["asset"],
          kind="repair", status=t["decoy_wo_status"], priority="low", description=t["decoy_wo_desc"], created_at=NOW),
        R("documents", id=t["doc_superseded"], title=f"{t['model']} service bulletin rev{t['doc_rev']-1}",
          kind="service_bulletin", model=t["model"], revision=t["doc_rev"] - 1, status="superseded",
          body=t["doc_superseded_body"]),
        R("documents", id=t["doc_current"], title=f"{t['model']} service bulletin rev{t['doc_rev']}",
          kind="service_bulletin", model=t["model"], revision=t["doc_rev"], status="current",
          body=t["doc_current_body"]),
        R("price_book", id=f"PB-{t['part']}-CUR", code=t["part"], kind="part", revision=2,
          effective_from="2026-02-01", status="current", unit_price_cents=t["part_price_current"]),
        R("parts_inventory", part_no=t["part"], description=t["part_desc"], on_hand=t["on_hand"],
          reserved=t["reserved"], quarantined=t["quarantined"], unit_cost_cents=t["part_cost"]),
        R("email_messages", id=t["email"], folder="inbox", from_addr=t["email_from"],
          to_addr="parts@apexclimate.example", subject=t["email_subject"], body=t["email_body"],
          sent_at=NOW + "T06:55:00"),
    ]
    for row in t.get("extra_seed", []):
        seed.append(row)

    answer = {
        "reservation_id": res_id,
        "work_order_id": t["wo"],
        "part_no": t["part"],
        "qty": t["qty"],
        "available_after": avail_after,
    }
    mutation = C("reserve_parts", work_order_id=t["wo"], part_no=t["part"], qty=t["qty"])
    plan = [
        C("list_emails", folder="inbox"),
        C("list_work_orders", customer_id=t["cust"]),
        C("get_asset", asset_id=t["asset"]),
        C("list_documents", kind="service_bulletin", model=t["model"]),
        C("get_document", document_id=t["doc_current"]),
        C("query_parts", part_no=t["part"]),
        mutation,
        C("query_parts", part_no=t["part"]),     # readback
        C("submit_answer", fields=answer),
    ]
    required_reads = [
        C("list_emails", folder="inbox"),
        C("list_work_orders", customer_id=t["cust"]),
        C("get_document", document_id=t["doc_current"]),
        C("query_parts", part_no=t["part"]),
    ]
    contract = {
        "task_id": t["task_id"],
        "archetype": "reserve",
        "required_reads": required_reads,
        "mutation": mutation,
        "allowlist": {"parts_inventory": [t["part"]], "reservations": [res_id]},
        "state_assertions": [
            {"sql": f"SELECT reserved FROM parts_inventory WHERE part_no='{t['part']}'",
             "expect": t["reserved"] + t["qty"]},
            {"sql": f"SELECT qty FROM reservations WHERE id='{res_id}'", "expect": t["qty"]},
            {"sql": f"SELECT work_order_id FROM reservations WHERE id='{res_id}'", "expect": t["wo"]},
        ],
        "readback": {"pk": t["part"], "tools": ["query_parts"]},
        "answer": {
            "fields": answer,
            "types": {"reservation_id": "str", "work_order_id": "str", "part_no": "str",
                      "qty": "int", "available_after": "int"},
        },
    }
    return {"spec": t, "seed_rows": seed, "prompt": t["prompt"], "plan": plan,
            "contract": contract, "shortcut_guess": t["shortcut_guess"],
            "evidence_swaps": t["evidence_swaps"], "wrong_target": t["wrong_target"]}


# --------------------------------------------------------------------------
# task specs
# --------------------------------------------------------------------------

COMMIT_TASKS = [
    # ------------------------------------------------------------- FSB-01
    {
        "task_id": "FSB-01",
        "cust": "C-101", "cust_name": "Blue Harbor Properties", "tier": "gold", "region": "north",
        "site": "S-1001", "site_name": "Riverside Plaza", "site_addr": "14 Riverside Plaza, Hartford",
        "decoy_site": "S-1002", "decoy_site_name": "Riverside Place", "decoy_site_addr": "9 Riverside Place, Hartford",
        "asset": "A-7001", "decoy_asset": "A-7002", "unit": "RTU-7", "model": "Trane XV-500", "serial": "TXV5-88141",
        "wo": "WO-5001", "wo_desc": "RTU-7 compressor contactor failure; unit down",
        "decoy_wo": "WO-5002", "decoy_wo_status": "open",
        "decoy_wo_desc": "RTU-7 intermittent fault code E-41 (monitor)",
        "priority": "high",
        "doc_current": "DOC-9002", "doc_superseded": "DOC-9001", "doc_rev": 2,
        "doc_current_body": ("Rev2 supersedes rev1: CNT-440 kit discontinued. Use P-3001 (CNT-440R "
                             "contactor kit) qty 1. Labor 3.5h including control-board reflash. "
                             "EPA-608 Universal certification required for this procedure."),
        "doc_superseded_body": ("Rev1: replace contactor with kit P-3000 (CNT-440) qty 1. Labor 3.0h."),
        "part": "P-3001", "part_desc": "CNT-440R contactor kit", "part_qty": 1,
        "part_price_current": 41200, "part_price_superseded": 38500, "part_cost": 30500,
        "on_hand": 4, "reserved": 1, "quarantined": 2,
        "labor_hours": "3.5",
        "approval": "APR-101", "approval_max": 120000,
        "techs": [
            {"id": "T-21", "name": "Marta Ruiz", "region": "north", "skills": "repair,maintenance",
             "cert_type": "EPA-608 Universal", "cert_expires": "2026-01-15",
             "std_rate_cents": 13200, "ot_rate_cents": 19800},
            {"id": "T-22", "name": "Devon Park", "region": "north", "skills": "repair",
             "cert_type": "EPA-608 Universal", "cert_expires": "2027-06-30",
             "std_rate_cents": 12100, "ot_rate_cents": 18150},
        ],
        "schedule": [
            {"id": "SCH-101", "tech_id": "T-21", "date": "2026-03-03", "start_hour": 8, "end_hour": 16,
             "kind": "shift", "work_order_id": None},
            {"id": "SCH-102", "tech_id": "T-22", "date": "2026-03-03", "start_hour": 8, "end_hour": 16,
             "kind": "blackout", "work_order_id": None},
            {"id": "SCH-103", "tech_id": "T-22", "date": "2026-03-04", "start_hour": 8, "end_hour": 16,
             "kind": "shift", "work_order_id": None},
            {"id": "SCH-104", "tech_id": "T-22", "date": "2026-03-04", "start_hour": 8, "end_hour": 10,
             "kind": "booking", "work_order_id": "WO-5900"},
            {"id": "SCH-105", "tech_id": "T-22", "date": "2026-03-03", "start_hour": 16, "end_hour": 20,
             "kind": "overtime", "work_order_id": None},
            {"id": "SCH-106", "tech_id": "T-22", "date": "2026-03-05", "start_hour": 8, "end_hour": 16,
             "kind": "shift", "work_order_id": None},
        ],
        "tech": "T-22", "date": "2026-03-04", "start_hour": 10, "book_hours": 4,
        "email": "EM-101", "email_from": "dana.ortiz@blueharbor.example",
        "email_subject": "RTU-7 down at Riverside Plaza — need a committed date",
        "email_body": ("Hi dispatch — RTU-7 at Riverside Plaza is down hard (contactor per the fault log). "
                       "I need a committed repair date and a cost ceiling I can forward to my property "
                       "manager today. Please don't quote me off last year's price list again. — Dana"),
        "prompt": ("Dana Ortiz at Blue Harbor Properties just emailed — rooftop unit RTU-7 at Riverside "
                   "Plaza is down. She wants a committed repair date and a cost ceiling for her property "
                   "manager. Check the current service bulletin for the unit, confirm parts and a properly "
                   "certified tech, book the visit, then report back: the work order, the booking id, who "
                   "is going, the commit date, the option used, the part number, and the all-in estimate "
                   "in cents."),
        "shortcut_guess": {"work_order_id": "WO-5001", "booking_id": "BK-0001", "tech_id": "T-21",
                           "commit_date": "2026-03-03", "option": "overtime", "part_no": "P-3000",
                           "est_total_cents": 75700},
        "evidence_swaps": {"DOC-9002": "DOC-9001", "P-3001": "P-3000"},
        "wrong_target": {"work_order_id": "WO-5002"},
    },
    # ------------------------------------------------------------- FSB-02
    {
        "task_id": "FSB-02",
        "cust": "C-102", "cust_name": "Mercantile Exchange Center", "tier": "silver", "region": "south",
        "site": "S-1011", "site_name": "Harbor Point Tower", "site_addr": "200 Harbor Point Dr, Norfolk",
        "decoy_site": "S-1012", "decoy_site_name": "Harbor Pointe Mall", "decoy_site_addr": "88 Harbor Pointe Way, Norfolk",
        "asset": "A-7011", "decoy_asset": "A-7012", "unit": "RTU-2", "model": "York ZX-120", "serial": "YZX120-33109",
        "wo": "WO-5011", "wo_desc": "RTU-2 blower motor grind; vibration shutdown",
        "decoy_wo": "WO-5012", "decoy_wo_status": "open",
        "decoy_wo_desc": "RTU-2 belt squeal on startup (monitor)",
        "priority": "high",
        "doc_current": "DOC-9012", "doc_superseded": "DOC-9011", "doc_rev": 3,
        "doc_current_body": ("Rev3: blower motor MTR-770 discontinued. Use P-3011 (MTR-775 blower motor) "
                             "qty 1. Labor 5.0h including alignment and vibration verification."),
        "doc_superseded_body": ("Rev2: replace blower motor with P-3010 (MTR-770) qty 1. Labor 4.0h."),
        "part": "P-3011", "part_desc": "MTR-775 blower motor", "part_qty": 1,
        "part_price_current": 66800, "part_price_superseded": 61200, "part_cost": 51000,
        "on_hand": 2, "reserved": 0, "quarantined": 0,
        "labor_hours": "5.0",
        "approval": "APR-102", "approval_max": 150000,
        "techs": [
            {"id": "T-23", "name": "Priya Nair", "region": "south", "skills": "repair",
             "cert_type": "EPA-608 Universal", "cert_expires": "2027-03-31",
             "std_rate_cents": 12600, "ot_rate_cents": 18900},
            {"id": "T-24", "name": "Gus Malone", "region": "south", "skills": "repair",
             "cert_type": "EPA-608 Universal", "cert_expires": "2026-02-20",
             "std_rate_cents": 13400, "ot_rate_cents": 20100},
        ],
        "schedule": [
            {"id": "SCH-111", "tech_id": "T-24", "date": "2026-03-03", "start_hour": 8, "end_hour": 16,
             "kind": "shift", "work_order_id": None},
            {"id": "SCH-112", "tech_id": "T-23", "date": "2026-03-03", "start_hour": 16, "end_hour": 20,
             "kind": "overtime", "work_order_id": None},
            {"id": "SCH-113", "tech_id": "T-23", "date": "2026-03-04", "start_hour": 8, "end_hour": 16,
             "kind": "blackout", "work_order_id": None},
            {"id": "SCH-114", "tech_id": "T-23", "date": "2026-03-05", "start_hour": 8, "end_hour": 16,
             "kind": "shift", "work_order_id": None},
        ],
        "tech": "T-23", "date": "2026-03-05", "start_hour": 8, "book_hours": 5,
        "email": "EM-102", "email_from": "facilities@mercantilex.example",
        "email_subject": "RTU-2 vibration shutdown — Harbor Point Tower",
        "email_body": ("Our RTU-2 tripped on vibration again and the floor is without cooling. Send us a "
                       "firm date and a not-to-exceed number. The building owner will not approve overtime "
                       "rates. — Facilities, Mercantile Exchange Center"),
        "prompt": ("Facilities at Mercantile Exchange Center emailed about RTU-2 at Harbor Point Tower — "
                   "vibration shutdown, no cooling on the floor. They want a firm date and a not-to-exceed "
                   "figure, and the owner won't approve overtime rates. Work out the honest option from the "
                   "current bulletin, price book, stock, certs, and the customer's approval, book it, and "
                   "report: work order, booking id, tech, commit date, option, part number, and the total "
                   "estimate in cents."),
        "shortcut_guess": {"work_order_id": "WO-5011", "booking_id": "BK-0001", "tech_id": "T-24",
                           "commit_date": "2026-03-03", "option": "overtime", "part_no": "P-3010",
                           "est_total_cents": 116800},
        "evidence_swaps": {"DOC-9012": "DOC-9011", "P-3011": "P-3010"},
        "wrong_target": {"work_order_id": "WO-5012"},
    },
    # ------------------------------------------------------------- FSB-03
    {
        "task_id": "FSB-03",
        "cust": "C-103", "cust_name": "Alder & Main Retail Group", "tier": "gold", "region": "north",
        "site": "S-1021", "site_name": "Alder Street Gallery", "site_addr": "5 Alder St, Hartford",
        "decoy_site": "S-1022", "decoy_site_name": "Alder Street Annex", "decoy_site_addr": "7 Alder St, Hartford",
        "asset": "A-7021", "decoy_asset": "A-7022", "unit": "RTU-4", "model": "Carrier 48TC-09", "serial": "C48TC9-55623",
        "wo": "WO-5021", "wo_desc": "RTU-4 expansion valve stuck; cooling loss",
        "decoy_wo": "WO-5022", "decoy_wo_status": "open",
        "decoy_wo_desc": "RTU-4 drain pan rust (cosmetic, monitor)",
        "priority": "high",
        "doc_current": "DOC-9022", "doc_superseded": "DOC-9021", "doc_rev": 2,
        "doc_current_body": ("Rev2: VLV-921 (P-3021) is supply-constrained and remaining stock is under "
                             "quality hold. Approved alternate is P-3022 (VLV-921A) qty 1. Labor 2.5h."),
        "doc_superseded_body": ("Rev1: replace expansion valve with P-3021 (VLV-921) qty 1. Labor 2.5h."),
        "part": "P-3022", "part_desc": "VLV-921A expansion valve (alternate)", "part_qty": 1,
        "part_price_current": 28900, "part_price_superseded": 26100, "part_cost": 21000,
        "on_hand": 2, "reserved": 0, "quarantined": 0,
        "labor_hours": "2.5",
        "approval": "APR-103", "approval_max": 80000,
        "extra_seed": [
            R("parts_inventory", part_no="P-3021", description="VLV-921 expansion valve",
              on_hand=3, reserved=0, quarantined=3, unit_cost_cents=19900),
            R("price_book", id="PB-P-3021-CUR", code="P-3021", kind="part", revision=2,
              effective_from="2026-02-01", status="current", unit_price_cents=27400),
        ],
        "techs": [
            {"id": "T-25", "name": "Owen Beck", "region": "north", "skills": "repair",
             "cert_type": "EPA-608 Universal", "cert_expires": "2027-01-31",
             "std_rate_cents": 12400, "ot_rate_cents": 18600},
        ],
        "schedule": [
            {"id": "SCH-121", "tech_id": "T-25", "date": "2026-03-03", "start_hour": 8, "end_hour": 16,
             "kind": "shift", "work_order_id": None},
            {"id": "SCH-122", "tech_id": "T-25", "date": "2026-03-03", "start_hour": 16, "end_hour": 20,
             "kind": "overtime", "work_order_id": None},
        ],
        "tech": "T-25", "date": "2026-03-03", "start_hour": 8, "book_hours": 3,
        "email": "EM-103", "email_from": "gm@aldermainretail.example",
        "email_subject": "Cooling loss at Alder Street Gallery (RTU-4)",
        "email_body": ("Gallery is getting warm — RTU-4 lost cooling and our guests are noticing. We need "
                       "someone out fast with the right valve. Please confirm a date and ceiling. — GM"),
        "prompt": ("The GM at Alder & Main Retail Group emailed — RTU-4 at Alder Street Gallery lost "
                   "cooling and they want someone out fast with the right valve. Work from the current "
                   "service bulletin (note the supply situation), verify what's actually reservable in "
                   "stock, book the earliest honest visit within the customer's approval, and report: "
                   "work order, booking id, tech, commit date, option, the part number you committed, "
                   "and the estimate in cents."),
        "shortcut_guess": {"work_order_id": "WO-5021", "booking_id": "BK-0001", "tech_id": "T-25",
                           "commit_date": "2026-03-03", "option": "standard", "part_no": "P-3021",
                           "est_total_cents": 64400},
        "evidence_swaps": {"DOC-9022": "DOC-9021", "P-3022": "P-3021"},
        "wrong_target": {"work_order_id": "WO-5022"},
    },
    # ------------------------------------------------------------- FSB-04
    {
        "task_id": "FSB-04",
        "cust": "C-104", "cust_name": "Crestline Foods", "tier": "platinum", "region": "east",
        "site": "S-1031", "site_name": "Crestline Cold Storage — Dock B", "site_addr": "1 Cold Chain Way, Dock B, Albany",
        "decoy_site": "S-1032", "decoy_site_name": "Crestline Cold Storage — Dock C", "decoy_site_addr": "1 Cold Chain Way, Dock C, Albany",
        "asset": "A-7031", "decoy_asset": "A-7032", "unit": "CU-4", "model": "Heatcraft KLP-66", "serial": "HKLP66-77841",
        "wo": "WO-5031", "wo_desc": "CU-4 compressor failure; Dock B freezer at risk",
        "decoy_wo": "WO-5032", "decoy_wo_status": "triaged",
        "decoy_wo_desc": "CU-4 noisy bearings (routine)",
        "priority": "critical",
        "doc_current": "DOC-9032", "doc_superseded": "DOC-9031", "doc_rev": 2,
        "doc_current_body": ("Rev2: compressor P-3031 (COMP-3300) qty 1 replaces all earlier part numbers. "
                             "Labor 6.0h including evacuation and recharge."),
        "doc_superseded_body": ("Rev1: replace compressor with P-3030 (COMP-3250) qty 1. Labor 6.0h."),
        "part": "P-3031", "part_desc": "COMP-3300 compressor", "part_qty": 1,
        "part_price_current": 152000, "part_price_superseded": 149500, "part_cost": 118000,
        "on_hand": 1, "reserved": 0, "quarantined": 0,
        "labor_hours": "6.0",
        "approval": "APR-104", "approval_max": 245000,
        "techs": [
            {"id": "T-27", "name": "Rosa Ibarra", "region": "east", "skills": "repair",
             "cert_type": "EPA-608 Universal", "cert_expires": "2026-12-31",
             "std_rate_cents": 12900, "ot_rate_cents": 19350},
            {"id": "T-28", "name": "Hank Lowe", "region": "east", "skills": "repair",
             "cert_type": "EPA-608 Universal", "cert_expires": "2026-01-30",
             "std_rate_cents": 13600, "ot_rate_cents": 20400},
        ],
        "schedule": [
            {"id": "SCH-131", "tech_id": "T-28", "date": "2026-03-03", "start_hour": 8, "end_hour": 16,
             "kind": "shift", "work_order_id": None},
            {"id": "SCH-132", "tech_id": "T-27", "date": "2026-03-03", "start_hour": 8, "end_hour": 16,
             "kind": "shift", "work_order_id": None},
            {"id": "SCH-133", "tech_id": "T-27", "date": "2026-03-03", "start_hour": 9, "end_hour": 15,
             "kind": "blackout", "work_order_id": None},
            {"id": "SCH-134", "tech_id": "T-27", "date": "2026-03-03", "start_hour": 16, "end_hour": 22,
             "kind": "overtime", "work_order_id": None},
            {"id": "SCH-135", "tech_id": "T-27", "date": "2026-03-04", "start_hour": 8, "end_hour": 16,
             "kind": "shift", "work_order_id": None},
        ],
        "tech": "T-27", "date": "2026-03-04", "start_hour": 8, "book_hours": 6,
        "email": "EM-104", "email_from": "ops@crestlinefoods.example",
        "email_subject": "CRITICAL: Dock B freezer compressor down",
        "email_body": ("CU-4 at Dock B is dead and we have product at risk. There is a second CU-4 at "
                       "Dock C with a minor noise issue — do NOT send the crew there, Dock B is the "
                       "emergency. Confirm date and ceiling ASAP. — Ops"),
        "prompt": ("Crestline Foods has a critical one: CU-4 at Dock B (Crestline Cold Storage) lost its "
                   "compressor with product at risk. They warn there's a look-alike unit at Dock C with a "
                   "minor issue — don't book against that one. Confirm the right work order, use the "
                   "current bulletin and pricing, check certs and blackout windows, book the visit inside "
                   "the customer's approval, and report: work order, booking id, tech, commit date, "
                   "option, part number, and estimate in cents."),
        "shortcut_guess": {"work_order_id": "WO-5032", "booking_id": "BK-0001", "tech_id": "T-28",
                           "commit_date": "2026-03-03", "option": "overtime", "part_no": "P-3030",
                           "est_total_cents": 238300},
        "evidence_swaps": {"DOC-9032": "DOC-9031", "P-3031": "P-3030"},
        "wrong_target": {"work_order_id": "WO-5032"},
    },
]

QUOTE_TASKS = [
    # ------------------------------------------------------------- FSB-05
    {
        "task_id": "FSB-05",
        "cust": "C-105", "cust_name": "Granite View Partners", "tier": "silver", "region": "east",
        "site": "S-1041", "site_name": "Granite View Offices", "site_addr": "40 Granite View Rd, Albany",
        "decoy_site": "S-1042", "decoy_site_name": "Granite View Annex", "decoy_site_addr": "44 Granite View Rd, Albany",
        "asset": "A-7041", "unit": "AHU-1", "model": "Daikin MFD-40", "serial": "DMFD40-11458",
        "wo": "WO-5041", "wo_status": "triaged", "wo_desc": "AHU-1 supply-fan bearing failure",
        "decoy_wo": "WO-5042", "decoy_wo_status": "completed",
        "decoy_wo_desc": "AHU-1 filter change (done last week)",
        "doc_current": "DOC-9042", "doc_superseded": "DOC-9041", "doc_rev": 2,
        "doc_current_body": ("Rev2: bearing set P-3041 (BRG-512) qty 2. Labor 3.0h including shaft "
                             "runout check. Supersedes BRG-510."),
        "doc_superseded_body": ("Rev1: bearing set P-3040 (BRG-510) qty 2. Labor 2.5h."),
        "part": "P-3041", "part_desc": "BRG-512 bearing set", "part_qty": 2,
        "part_price_current": 11800, "part_price_superseded": 9400, "part_cost": 8600,
        "labor_hours": "3.0",
        "approval": "APR-105", "approval_max": 100000,
        "email": "EM-105", "email_from": "pm@graniteview.example",
        "email_subject": "Quote needed — AHU-1 bearing job",
        "email_body": ("Please send a firm quote for the AHU-1 bearing job at Granite View Offices. "
                       "Last time someone quoted us off an old rate sheet and it blew up in approvals. "
                       "— PM, Granite View Partners"),
        "prompt": ("Granite View Partners wants a firm quote for the AHU-1 bearing failure at Granite "
                   "View Offices — they were burned once by a quote built on an old rate sheet. Use the "
                   "current service bulletin and the current price book, stay inside the approved cap "
                   "for the work order, submit the quote, and report: quote id, work order, part number, "
                   "labor hours, parts total, labor total, grand total (cents), and the approval id."),
        "shortcut_guess": {"quote_id": "Q-0001", "work_order_id": "WO-5041", "part_no": "P-3040",
                           "labor_hours": "2.5", "parts_total_cents": 18800, "labor_total_cents": 34750,
                           "total_cents": 53550, "approval_id": "APR-105"},
        "evidence_swaps": {"DOC-9042": "DOC-9041", "P-3041": "P-3040"},
        "wrong_target": {"work_order_id": "WO-5042"},
    },
    # ------------------------------------------------------------- FSB-06
    {
        "task_id": "FSB-06",
        "cust": "C-106", "cust_name": "Lakeside Grocers Co-op", "tier": "gold", "region": "west",
        "site": "S-1051", "site_name": "Lakeside Market #4", "site_addr": "12 Lakeshore Ave, Spokane",
        "decoy_site": "S-1052", "decoy_site_name": "Lakeside Market #7", "decoy_site_addr": "90 Lakeshore Ave, Spokane",
        "asset": "A-7051", "unit": "RCC-1", "model": "Emerson XC-900", "serial": "EXC900-66214",
        "wo": "WO-5051", "wo_status": "triaged", "wo_desc": "RCC-1 rack controller failure; cases warming",
        "decoy_wo": "WO-5052", "decoy_wo_status": "open",
        "decoy_wo_desc": "Case door gasket wear (routine)",
        "doc_current": "DOC-9052", "doc_superseded": "DOC-9051", "doc_rev": 3,
        "doc_current_body": ("Rev3: controller replacement — OEM P-3051 (CTL-900) or reman P-3052 "
                             "(CTL-900R) are both approved for the XC-900. Labor 2.0h either way."),
        "doc_superseded_body": ("Rev2: replace controller with OEM P-3051 (CTL-900) qty 1. Labor 2.0h."),
        "part": "P-3052", "part_desc": "CTL-900R reman controller", "part_qty": 1,
        "part_price_current": 36900, "part_price_superseded": 36900, "part_cost": 24000,
        "labor_hours": "2.0",
        "approval": "APR-106", "approval_max": 70000,
        "extra_seed": [
            R("parts_inventory", part_no="P-3051", description="CTL-900 OEM controller",
              on_hand=3, reserved=0, quarantined=0, unit_cost_cents=55200),
            R("price_book", id="PB-P-3051-OLD", code="P-3051", kind="part", revision=2,
              effective_from="2025-08-01", status="superseded", unit_price_cents=71900),
            R("price_book", id="PB-P-3051-CUR", code="P-3051", kind="part", revision=3,
              effective_from="2026-02-01", status="current", unit_price_cents=74500),
        ],
        "extra_required_reads": [
            C("get_price_book", code="P-3051"),
        ],
        "email": "EM-106", "email_from": "manager.store4@lakesidegrocers.example",
        "email_subject": "RCC-1 controller — quote please (corporate prefers OEM)",
        "email_body": ("RCC-1 is down and the cases are warming. Corporate says they'd prefer OEM parts "
                       "if possible, but I only have approval authority up to our standing cap for this "
                       "work order. Send a quote we can actually approve. — Store Manager #4"),
        "prompt": ("Lakeside Grocers' store #4 needs a quote for the failed RCC-1 rack controller. The "
                   "manager says corporate prefers OEM, but also that the quote must fit their standing "
                   "approval cap for this work order — check both part options in the current bulletin "
                   "and price book, pick the one that can actually be approved, submit the quote, and "
                   "report: quote id, work order, part number, labor hours, parts total, labor total, "
                   "grand total (cents), and approval id."),
        "shortcut_guess": {"quote_id": "Q-0001", "work_order_id": "WO-5051", "part_no": "P-3051",
                           "labor_hours": "2.0", "parts_total_cents": 74500, "labor_total_cents": 29600,
                           "total_cents": 104100, "approval_id": "APR-106"},
        "evidence_swaps": {"DOC-9052": "DOC-9051", "P-3052": "P-3051"},
        "wrong_target": {"work_order_id": "WO-5052"},
    },
    # ------------------------------------------------------------- FSB-07
    {
        "task_id": "FSB-07",
        "cust": "C-107", "cust_name": "Summit Wellness Centers", "tier": "silver", "region": "south",
        "site": "S-1061", "site_name": "Summit Downtown", "site_addr": "300 Meridian St, Norfolk",
        "decoy_site": "S-1062", "decoy_site_name": "Summit Westlake", "decoy_site_addr": "18 Westlake Blvd, Norfolk",
        "asset": "A-7061", "unit": "RTU-12", "model": "Lennox LGH-240", "serial": "LLGH240-90112",
        "wo": "WO-5061", "wo_status": "scheduled", "wo_desc": "RTU-12 no-heat call; ignition fault",
        "decoy_wo": "WO-5062", "decoy_wo_status": "open",
        "decoy_wo_desc": "RTU-12 thermostat drift (monitor)",
        "doc_current": "DOC-9062", "doc_superseded": "DOC-9061", "doc_rev": 4,
        "doc_current_body": ("Rev4: ignition module P-3061 (IGN-210) qty 1. Labor 4.5h — rev4 adds the "
                             "gas-train re-certification now required after ignition-module replacement."),
        "doc_superseded_body": ("Rev3: replace ignition module P-3061 (IGN-210) qty 1. Labor 2.0h."),
        "part": "P-3061", "part_desc": "IGN-210 ignition module", "part_qty": 1,
        "part_price_current": 21300, "part_price_superseded": 21300, "part_cost": 15400,
        "labor_hours": "4.5",
        "approval": "APR-107", "approval_max": 95000,
        "email": "EM-107", "email_from": "facilities@summitwellness.example",
        "email_subject": "No heat at Summit Downtown — quote for ignition repair",
        "email_body": ("RTU-12 at Summit Downtown has no heat. A tech quoted 2 hours over the phone from "
                       "memory — please send a written quote with the correct current labor standard. "
                       "— Facilities"),
        "prompt": ("Summit Wellness needs a written quote for the no-heat ignition fault on RTU-12 at "
                   "Summit Downtown. Someone ballparked 2 hours from memory — verify the labor standard "
                   "in the current bulletin (it changed recently), price it at current rates inside the "
                   "approval cap, submit the quote, and report: quote id, work order, part number, labor "
                   "hours, parts total, labor total, grand total (cents), and approval id."),
        "shortcut_guess": {"quote_id": "Q-0001", "work_order_id": "WO-5061", "part_no": "P-3061",
                           "labor_hours": "2.0", "parts_total_cents": 21300, "labor_total_cents": 29600,
                           "total_cents": 50900, "approval_id": "APR-107"},
        "evidence_swaps": {"DOC-9062": "DOC-9061"},
        "wrong_target": {"work_order_id": "WO-5062"},
    },
]

RESERVE_TASKS = [
    # ------------------------------------------------------------- FSB-08
    {
        "task_id": "FSB-08",
        "cust": "C-108", "cust_name": "Parkview Medical Plaza", "tier": "platinum", "region": "east",
        "site": "S-1071", "site_name": "Parkview Tower A", "site_addr": "7 Parkview Dr, Tower A, Albany",
        "decoy_site": "S-1072", "decoy_site_name": "Parkview Tower B", "decoy_site_addr": "7 Parkview Dr, Tower B, Albany",
        "asset": "A-7071", "unit": "AHU-3", "model": "Munters DSC-700", "serial": "MDSC700-42318",
        "wo": "WO-5071", "wo_kind": "repair", "wo_status": "triaged", "priority": "high",
        "wo_desc": "AHU-3 desiccant wheel seal leak",
        "decoy_wo": "WO-5072", "decoy_wo_status": "completed",
        "decoy_wo_desc": "AHU-3 sensor calibration (done)",
        "doc_current": "DOC-9072", "doc_superseded": "DOC-9071", "doc_rev": 2,
        "doc_current_body": ("Rev2: seal kit P-3071 (SEL-770) qty 2 per desiccant wheel. SEL-760 "
                             "(P-3070) is no longer stocked and must not be substituted."),
        "doc_superseded_body": ("Rev1: seal kit P-3070 (SEL-760) qty 2 per wheel."),
        "part": "P-3071", "part_desc": "SEL-770 seal kit", "qty": 2,
        "part_price_current": 6400, "part_cost": 4300,
        "on_hand": 5, "reserved": 1, "quarantined": 2,
        "email": "EM-108", "email_from": "chief@parkviewmedical.example",
        "email_subject": "AHU-3 seals — Tower A humidity excursion",
        "email_body": ("Tower A surgery wing humidity is drifting; AHU-3 wheel seals are leaking. "
                       "We have 5 kits on the shelf per the last inventory report, so this should be "
                       "easy — please reserve what the job needs. — Chief Engineer"),
        "prompt": ("Parkview Medical Plaza's chief engineer emailed about AHU-3 at Tower A — desiccant "
                   "wheel seals are leaking and he wants the parts reserved for the job. He's assuming "
                   "everything on the shelf is usable; check the current bulletin for the correct kit "
                   "and quantity, account for stock that isn't actually reservable, place the "
                   "reservation, and report: reservation id, work order, part number, quantity, and "
                   "how many remain available after your reservation."),
        "shortcut_guess": {"reservation_id": "RSV-0001", "work_order_id": "WO-5071", "part_no": "P-3070",
                           "qty": 2, "available_after": 3},
        "evidence_swaps": {"DOC-9072": "DOC-9071", "P-3071": "P-3070"},
        "wrong_target": {"part_no": "P-3070"},
    },
    # ------------------------------------------------------------- FSB-09
    {
        "task_id": "FSB-09",
        "cust": "C-109", "cust_name": "Harbor Lights Hotel", "tier": "gold", "region": "west",
        "site": "S-1081", "site_name": "Harbor Lights Resort", "site_addr": "1 Marina Point, Spokane",
        "decoy_site": "S-1082", "decoy_site_name": "Harbor Lights Marina", "decoy_site_addr": "2 Marina Point, Spokane",
        "asset": "A-7081", "unit": "RTU-9", "model": "Rheem RK-180", "serial": "RRK180-33097",
        "wo": "WO-5081", "wo_kind": "repair", "wo_status": "triaged", "priority": "critical",
        "wo_desc": "RTU-9 gas valve failure",
        "decoy_wo": "WO-5082", "decoy_wo_status": "open",
        "decoy_wo_desc": "Marina clubhouse thermostat (routine)",
        "doc_current": "DOC-9082", "doc_superseded": "DOC-9081", "doc_rev": 5,
        "doc_current_body": ("Rev5: gas valve P-3081 (VALVE-2210) qty 1 for RK-180 serials "
                             "RRK180-30000 and up. VALVE-2201 (P-3082) is NOT compatible with these "
                             "serials and remains only for pre-30000 units."),
        "doc_superseded_body": ("Rev4: gas valve P-3082 (VALVE-2201) qty 1 for RK-180."),
        "part": "P-3081", "part_desc": "VALVE-2210 gas valve", "qty": 1,
        "part_price_current": 18700, "part_cost": 13100,
        "on_hand": 2, "reserved": 0, "quarantined": 1,
        "extra_seed": [
            R("parts_inventory", part_no="P-3082", description="VALVE-2201 gas valve (legacy)",
              on_hand=6, reserved=0, quarantined=0, unit_cost_cents=11200),
            R("price_book", id="PB-P-3082-CUR", code="P-3082", kind="part", revision=2,
              effective_from="2026-02-01", status="current", unit_price_cents=15900),
        ],
        "email": "EM-109", "email_from": "chief.engineer@harborlights.example",
        "email_subject": "RTU-9 gas valve — pretty sure it takes a VALVE-2201",
        "email_body": ("RTU-9 at the resort is out — gas valve. We've always used VALVE-2201 on these, "
                       "so please reserve one from stock. Guests are complaining about cold rooms. "
                       "— Chief Engineer"),
        "prompt": ("Harbor Lights Hotel's chief engineer is confident RTU-9 takes a VALVE-2201 and wants "
                   "one reserved from stock. Check that against the current service bulletin for the "
                   "unit's serial range before reserving anything — the wrong gas valve is a safety "
                   "issue. Reserve the correct part and report: reservation id, work order, part "
                   "number, quantity, and how many remain available afterwards."),
        "shortcut_guess": {"reservation_id": "RSV-0001", "work_order_id": "WO-5081", "part_no": "P-3082",
                           "qty": 1, "available_after": 5},
        "evidence_swaps": {"DOC-9082": "DOC-9081", "P-3081": "P-3082"},
        "wrong_target": {"part_no": "P-3082"},
    },
    # ------------------------------------------------------------- FSB-10
    {
        "task_id": "FSB-10",
        "cust": "C-110", "cust_name": "Foundry District Lofts", "tier": "silver", "region": "north",
        "site": "S-1091", "site_name": "Foundry Building E", "site_addr": "55 Foundry Way, Bldg E, Hartford",
        "decoy_site": "S-1092", "decoy_site_name": "Foundry Building F", "decoy_site_addr": "55 Foundry Way, Bldg F, Hartford",
        "asset": "A-7091", "unit": "MU-1", "model": "Greenheck MUA-5", "serial": "GMUA5-71204",
        "wo": "WO-5091", "wo_kind": "maintenance", "wo_status": "open", "priority": "medium",
        "wo_desc": "MU-1 quarterly PM: filter set + belt inspection",
        "decoy_wo": "WO-5092", "decoy_wo_status": "completed",
        "decoy_wo_desc": "MU-1 annual inspection (done)",
        "doc_current": "DOC-9092", "doc_superseded": "DOC-9091", "doc_rev": 2,
        "doc_current_body": ("Rev2: after the dust-load study the MUA-5 PM now requires filter set "
                             "P-3091 (FLT-88) qty 4 per visit (doubled from rev1)."),
        "doc_superseded_body": ("Rev1: PM filter set P-3091 (FLT-88) qty 2 per visit."),
        "part": "P-3091", "part_desc": "FLT-88 filter set", "qty": 4,
        "part_price_current": 2900, "part_cost": 1700,
        "on_hand": 8, "reserved": 3, "quarantined": 1,
        "email": "EM-110", "email_from": "hoa@foundrylofts.example",
        "email_subject": "MU-1 quarterly PM — please stage filters",
        "email_body": ("Please stage the filters for the MU-1 quarterly PM at Building E. Last quarter "
                       "you reserved 2 sets and the tech had to come back for the rest — please follow "
                       "the updated PM standard this time. — HOA Board"),
        "prompt": ("Foundry District Lofts' HOA wants filters staged for the MU-1 quarterly PM at "
                   "Building E — last time too few were reserved because someone used the old PM "
                   "standard. Check the current bulletin for the right quantity, account for what's "
                   "already reserved or quarantined in stock, place the reservation, and report: "
                   "reservation id, work order, part number, quantity, and how many remain available "
                   "afterwards."),
        "shortcut_guess": {"reservation_id": "RSV-0001", "work_order_id": "WO-5091", "part_no": "P-3091",
                           "qty": 2, "available_after": 5},
        "evidence_swaps": {"DOC-9092": "DOC-9091"},
        "wrong_target": {"work_order_id": "WO-5092"},
    },
]


def build_all_tasks():
    tasks = {}
    for t in COMMIT_TASKS:
        tasks[t["task_id"]] = build_commit(t)
    for t in QUOTE_TASKS:
        tasks[t["task_id"]] = build_quote(t)
    for t in RESERVE_TASKS:
        tasks[t["task_id"]] = build_reserve(t)
    return tasks


TASKS = build_all_tasks()
TASK_IDS = sorted(TASKS)

# Baseline noise rows shared by all tasks (world realism; no task depends on them).
NOISE_ROWS = [
    R("config", key="now", value=NOW),
    R("customers", id="C-900", name="Interbay Logistics", tier="bronze", region="west", account_status="active"),
    R("customers", id="C-901", name="Old Town Theatres", tier="silver", region="east", account_status="active"),
    R("sites", id="S-9001", customer_id="C-900", name="Interbay Warehouse 3", address="800 Pier Rd, Spokane"),
    R("sites", id="S-9002", customer_id="C-901", name="Old Town Playhouse", address="12 Stage Ln, Albany"),
    R("assets", id="A-9001", site_id="S-9001", unit_tag="RTU-1", model="Trane XV-500",
      serial="TXV5-10001", install_revision=1, install_date="2020-06-15", warranty_until="2025-06-15"),
    R("assets", id="A-9002", site_id="S-9002", unit_tag="AHU-9", model="Daikin MFD-40",
      serial="DMFD40-10002", install_revision=1, install_date="2019-11-03", warranty_until="2024-11-03"),
    R("technicians", id="T-30", name="Sam Oyelaran", region="west", skills="repair,maintenance",
      cert_type="EPA-608 Universal", cert_expires="2027-09-30", std_rate_cents=12700, ot_rate_cents=19050),
    R("technicians", id="T-31", name="Lou Ferrante", region="east", skills="maintenance",
      cert_type="EPA-608 Type II", cert_expires="2027-02-28", std_rate_cents=11800, ot_rate_cents=17700),
    R("work_orders", id="WO-5900", customer_id="C-900", site_id="S-9001", asset_id="A-9001",
      kind="repair", status="scheduled", priority="medium", description="RTU-1 economizer actuator",
      created_at="2026-02-27"),
    R("approvals", id="APR-900", customer_id="C-900", work_order_id="WO-5900",
      max_amount_cents=200000, allowed_option="any", status="approved", created_by="j.syllas"),
    R("parts_inventory", part_no="P-1001", description="BELT-A38 drive belt", on_hand=12,
      reserved=0, quarantined=0, unit_cost_cents=1400),
    R("parts_inventory", part_no="P-1002", description="FILT-2020 panel filter", on_hand=40,
      reserved=4, quarantined=0, unit_cost_cents=900),
    R("parts_inventory", part_no="P-1003", description="CAP-45UF capacitor", on_hand=5,
      reserved=0, quarantined=5, unit_cost_cents=2100),
    R("price_book", id="PB-LABOR-OLD", code=LABOR_CODE, kind="labor", revision=1,
      effective_from="2025-09-01", status="superseded", unit_price_cents=LABOR_SUPERSEDED_CENTS),
    R("price_book", id="PB-LABOR-CUR", code=LABOR_CODE, kind="labor", revision=2,
      effective_from="2026-02-01", status="current", unit_price_cents=LABOR_CURRENT_CENTS),
    R("price_book", id="PB-P-1001-CUR", code="P-1001", kind="part", revision=2,
      effective_from="2026-02-01", status="current", unit_price_cents=2200),
    R("price_book", id="PB-P-1002-CUR", code="P-1002", kind="part", revision=2,
      effective_from="2026-02-01", status="current", unit_price_cents=1500),
    R("documents", id="DOC-1001", title="Warranty policy", kind="policy", model="",
      revision=6, status="current", body="Standard warranty terms rev6."),
    R("documents", id="DOC-1002", title="Trane XV-500 spec sheet", kind="spec_sheet",
      model="Trane XV-500", revision=1, status="current", body="Nominal 15 tons, R-410A."),
    R("email_messages", id="EM-901", folder="inbox", from_addr="ops@interbay.example",
      to_addr="dispatch@apexclimate.example", subject="Q2 maintenance window",
      body="Can we lock the Q2 maintenance window for Warehouse 3?", sent_at="2026-03-01T16:20:00"),
    R("email_messages", id="EM-902", folder="inbox", from_addr="boxoffice@oldtown.example",
      to_addr="dispatch@apexclimate.example", subject="Noise complaint follow-up",
      body="AHU-9 is still rattling during matinees.", sent_at="2026-03-01T18:02:00"),
    R("reservations", id="RSV-SEED-1", work_order_id="WO-5900", part_no="P-1002", qty=4,
      created_at="2026-02-28"),
    R("schedule", id="SCH-900", tech_id="T-30", date="2026-03-03", start_hour=8, end_hour=16,
      kind="shift", work_order_id=None),
    R("schedule", id="SCH-901", tech_id="T-31", date="2026-03-04", start_hour=8, end_hour=16,
      kind="shift", work_order_id=None),
]
