"""
Drafting Agent — generates legal correspondence drafts (demand letters,
client correspondence) from structured facts.

Design principles (see architecture doc, Section 5):
- Never invents facts. Anything not explicitly provided is marked
  [VERIFY: ...] rather than guessed.
- Single-pass generation (no tool use) — this agent's job is drafting,
  not decision-making. Decision-making lives in the Intake Triage Agent.
- MOCK_MODE lets us build and test the full flow without a live API key.
"""

import os
import json
from datetime import datetime, timezone

MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"

REQUIRED_FIELDS = [
    "document_type",      # e.g. "demand_letter", "client_correspondence"
    "client_name",
    "recipient_name",
    "matter_summary",     # short factual description of the situation
    "requested_outcome",  # what the letter should ask for
]

SYSTEM_PROMPT = """You are a legal drafting assistant supporting a law firm's staff.
You draft correspondence (demand letters, client letters, decline letters)
from the facts provided.

STRICT RULES:
1. Use ONLY the facts explicitly provided in the input. Never invent names,
   dates, dollar amounts, or events that were not given to you.
2. If a fact needed to complete the letter is missing, insert a clear
   placeholder in this exact format: [VERIFY: description of missing fact]
   Do not guess or infer a plausible-sounding value.
3. This draft is for attorney review before it is sent. Do not include
   any final legal conclusions ("you are liable," "you must pay") —
   phrase claims and requests neutrally, as a draft awaiting review.
4. For document_type "decline_letter": this letter is FROM the firm TO
   a prospective client the firm cannot represent. Do NOT use "on behalf
   of" framing (that's for demand letters representing an existing
   client). Be polite, brief, and include a note that the person should
   seek other counsel and that deadlines continue to run regardless.
5. Output the letter only. No preamble, no explanation, no markdown formatting.
"""


class ValidationError(Exception):
    pass


def validate_input(facts: dict) -> list:
    """Returns a list of missing required fields. Empty list = valid."""
    missing = [f for f in REQUIRED_FIELDS if not facts.get(f)]
    return missing


def build_user_prompt(facts: dict) -> str:
    return f"""Draft a {facts['document_type']} using only these facts:

Client: {facts['client_name']}
Recipient: {facts['recipient_name']}
Matter summary: {facts['matter_summary']}
Requested outcome: {facts['requested_outcome']}
Additional context: {facts.get('additional_context', 'None provided')}

Remember: use [VERIFY: ...] for anything not given above. Do not invent details."""


def call_claude_mock(user_prompt: str, facts: dict) -> str:
    """
    Simulates a Claude response so we can test the full pipeline
    without a live API key. This mimics realistic behavior, including
    a deliberately-missing fact to prove the [VERIFY] pattern works.
    """
    today = datetime.now().strftime("%B %d, %Y")

    if facts["document_type"] == "decline_letter":
        # Different framing: this letter is FROM the firm TO the
        # prospective client, not "on behalf of" anyone.
        return f"""{today}

{facts['recipient_name']}

Re: {facts['matter_summary']}

Dear {facts['recipient_name']},

Thank you for reaching out to us regarding the matter described above.
After reviewing the information you provided, we have determined that
we are unable to represent you in this matter.

{facts['requested_outcome']}

{facts.get('additional_context', '')}

We wish you the best in resolving this matter and encourage you to
seek the advice of another attorney, if needed. Please note that this
message does not constitute legal advice, and any deadlines that may
apply to your situation continue to run regardless of this letter.

This draft has not been reviewed by an attorney and should not be sent
in its current form.

Sincerely,
[VERIFY: attorney name / signature block]
"""

    return f"""{today}

{facts['recipient_name']}

Re: {facts['matter_summary']}

Dear {facts['recipient_name']},

This letter is written on behalf of {facts['client_name']} regarding the
above-referenced matter. {facts['matter_summary']}

[VERIFY: date of incident]

{facts['client_name']} requests the following: {facts['requested_outcome']}

Please respond within [VERIFY: response deadline, e.g. 14 days] of receipt
of this letter.

This draft has not been reviewed by an attorney and should not be sent
in its current form.

Sincerely,
[VERIFY: attorney name / signature block]
"""


def call_claude_live(user_prompt: str) -> str:
    """Real API call — used once MOCK_MODE is off and a key is present."""
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def draft_document(facts: dict) -> dict:
    """
    Main entry point. Returns a result dict with the draft plus metadata
    for logging (see architecture doc, Section 4 — everything gets logged).
    """
    missing = validate_input(facts)
    if missing:
        raise ValidationError(f"Missing required fields: {missing}")

    user_prompt = build_user_prompt(facts)

    if MOCK_MODE:
        draft_text = call_claude_mock(user_prompt, facts)
        model_used = "mock"
    else:
        draft_text = call_claude_live(user_prompt)
        model_used = "claude-sonnet-5"

    contains_verify_flags = "[VERIFY:" in draft_text

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "document_type": facts["document_type"],
        "client_name": facts["client_name"],
        "model_used": model_used,
        "draft_text": draft_text,
        "needs_human_review": True,  # always true — see architecture doc Section 6
        "contains_verify_flags": contains_verify_flags,
    }
    return result


def save_result(result: dict, output_dir: str = "outputs") -> str:
    """Saves the draft + a JSON log entry. Returns the draft file path."""
    os.makedirs(output_dir, exist_ok=True)
    safe_client = result["client_name"].replace(" ", "_")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    draft_path = os.path.join(output_dir, f"draft_{safe_client}_{stamp}.txt")
    with open(draft_path, "w") as f:
        f.write(result["draft_text"])

    log_path = os.path.join(output_dir, "run_log.jsonl")
    with open(log_path, "a") as f:
        log_entry = {k: v for k, v in result.items() if k != "draft_text"}
        log_entry["draft_file"] = draft_path
        f.write(json.dumps(log_entry) + "\n")

    return draft_path


if __name__ == "__main__":
    from sample_inputs import SAMPLE_CASES

    for case in SAMPLE_CASES:
        print(f"\n{'='*60}")
        print(f"Processing: {case['client_name']} — {case['document_type']}")
        print("=" * 60)
        try:
            result = draft_document(case)
            path = save_result(result)
            print(f"✓ Draft saved to: {path}")
            print(f"  Needs human review: {result['needs_human_review']}")
            print(f"  Contains [VERIFY] flags: {result['contains_verify_flags']}")
            print(f"\n--- Draft preview ---\n{result['draft_text']}")
        except ValidationError as e:
            print(f"✗ Validation failed: {e}")
