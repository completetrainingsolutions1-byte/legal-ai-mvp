"""
Loads firm-specific intake rules from firm_config.json.

This is the key change from the original version: NONE of a firm's
actual business rules (practice areas, claim minimums, jurisdictions)
live in this code anymore. They live in firm_config.json, which a
non-technical staff member can edit directly.

Onboarding a new firm = giving them this file to fill out.
Nothing in this .py file needs to change per firm.
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "firm_config.json")


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


# Loaded once at import time. If firm_config.json changes, restart the
# program to pick up new rules (a live-reload option is a nice-to-have,
# not required for the MVP).
_config = _load_config()

FIRM_NAME = _config["firm_name"]
INTAKE_CRITERIA = _config["practice_areas"]
PRACTICE_AREAS_NOT_HANDLED = _config["not_handled"]
PAST_CASE_EXAMPLES = _config["past_case_examples"]


def check_intake_criteria(case_type: str, claim_value: float, state: str) -> dict:
    """
    TOOL: Checks a case against THIS firm's rules, loaded from
    firm_config.json. Behavior is identical to before; only the source
    of the rules changed (config file instead of hardcoded Python).
    """
    if case_type in PRACTICE_AREAS_NOT_HANDLED:
        return {
            "meets_criteria": False,
            "reason": f"{FIRM_NAME} does not handle {case_type.replace('_', ' ')} matters.",
        }

    if case_type not in INTAKE_CRITERIA:
        return {
            "meets_criteria": False,
            "reason": f"Unrecognized case type '{case_type}' — flag for human classification.",
        }

    rules = INTAKE_CRITERIA[case_type]

    if state not in rules["allowed_states"]:
        return {
            "meets_criteria": False,
            "reason": f"{FIRM_NAME} does not handle {case_type.replace('_', ' ')} matters outside {rules['allowed_states']}.",
        }

    if claim_value < rules["min_claim_value"]:
        return {
            "meets_criteria": False,
            "reason": (
                f"Claim value ${claim_value} is below {FIRM_NAME}'s minimum "
                f"of ${rules['min_claim_value']} for {case_type} matters."
            ),
        }

    return {
        "meets_criteria": True,
        "reason": f"Meets {FIRM_NAME}'s intake criteria for {case_type} matters.",
        "notes": rules.get("notes", ""),
    }


def search_similar_cases(case_type: str) -> dict:
    """TOOL: Returns past similar case outcomes, for context."""
    examples = PAST_CASE_EXAMPLES.get(case_type, [])
    if not examples:
        return {"found": False, "examples": []}
    return {"found": True, "examples": examples}


def reload_config():
    """
    Call this if firm_config.json changes during a long-running process
    (e.g., a web server) and you want new rules without a restart.
    """
    global _config, FIRM_NAME, INTAKE_CRITERIA, PRACTICE_AREAS_NOT_HANDLED, PAST_CASE_EXAMPLES
    _config = _load_config()
    FIRM_NAME = _config["firm_name"]
    INTAKE_CRITERIA = _config["practice_areas"]
    PRACTICE_AREAS_NOT_HANDLED = _config["not_handled"]
    PAST_CASE_EXAMPLES = _config["past_case_examples"]
