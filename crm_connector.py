"""
CRM Connector — the integration point between this system and a firm's
actual practice management software (Clio, MyCase, Lawmatics,
PracticePanther, Filevine, etc.)

WHY THIS IS A STUB, NOT A REAL INTEGRATION:
Every firm uses a different CRM, each with its own API, auth model, and
data schema. Building a real integration means picking ONE specific
system and getting real API credentials for it — that's a firm-specific
onboarding step, not something a portfolio demo can do generically.

WHAT THIS DOES INSTEAD:
Constructs the exact payload that WOULD be sent to a real CRM, and logs
it, so the integration point is concrete and inspectable rather than
just described. Swapping this stub for a real API call later (e.g.
Clio's REST API) means implementing _send_to_clio() below and pointing
push_to_crm() at it — the rest of the system doesn't need to change,
since it only depends on this function's interface, not its internals.
"""

import json
import os
from datetime import datetime, timezone

from intake_criteria_data import FIRM_NAME

CRM_LOG_PATH = os.path.join(os.path.dirname(__file__), "outputs", "crm_sync_log.jsonl")


def build_crm_payload(action: str, item: dict) -> dict:
    """
    Builds the payload that would be sent to the firm's CRM for a given
    review queue action. Shape is intentionally generic (name, contact
    info, matter type, notes) since most CRMs' "create matter/lead"
    endpoints expect roughly this shape, regardless of vendor.
    """
    result = item["result"]
    client_info = result.get("client_provided", {})

    payload = {
        "action": action,  # "create_matter" | "log_decline" | "flag_for_review"
        "source_system": "Legal AI Intake System (portfolio demo)",
        "firm": FIRM_NAME,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "contact": {
            "name": client_info.get("name", ""),
            "phone": client_info.get("phone", ""),
            "email": client_info.get("email", ""),
        },
        "source_channel": result.get("source", "unspecified"),
        "original_inquiry": result.get("input_preview", ""),
    }

    agent_result = result.get("agent_result")
    if result.get("routed_to") == "intake_triage_agent" and agent_result:
        payload["matters"] = [
            {
                "case_type": issue["case_type"],
                "ai_recommendation": issue["recommendation"],
                "ai_confidence": issue["confidence"],
                "ai_reasoning": issue["reasoning"],
            }
            for issue in agent_result["issues"]
        ]
    elif result.get("routed_to") == "drafting_agent" and agent_result:
        payload["draft_document_type"] = agent_result.get("document_type")

    return payload


def push_to_crm(action: str, item: dict) -> dict:
    """
    Simulates pushing an approved/rejected item to the firm's CRM.

    In a real deployment, this function's body would call the specific
    CRM's API (e.g. requests.post(CLIO_API_URL, json=payload,
    headers=auth_headers)). Here, it logs what WOULD be sent and
    returns a mock confirmation — the integration seam is real, the
    network call is not.
    """
    payload = build_crm_payload(action, item)

    os.makedirs(os.path.dirname(CRM_LOG_PATH), exist_ok=True)
    with open(CRM_LOG_PATH, "a") as f:
        f.write(json.dumps(payload, default=str) + "\n")

    return {
        "status": "simulated_success",
        "message": (
            f"[SIMULATED] Would sync to {FIRM_NAME}'s CRM system here. "
            f"No real API call was made — see payload below."
        ),
        "payload": payload,
    }
