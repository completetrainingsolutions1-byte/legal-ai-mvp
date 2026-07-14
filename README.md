# Legal AI Multi-Agent System (Portfolio MVP)

A multi-agent AI system for law firm intake triage and correspondence
drafting, built with the Anthropic API. Designed around one core
principle: **the system recommends, a human decides.**

## What this is

Three components working together:

- **Drafting Agent** — generates correspondence drafts (demand letters,
  client updates) from structured facts. Never invents missing details —
  flags them with `[VERIFY: ...]` instead.
- **Intake Triage Agent** — reads a raw client inquiry, classifies the
  case type, checks it against the firm's intake rules, and recommends
  next steps. Uses a real tool-use loop (classify → check rules →
  check case history → recommend), not a single prompt.
- **Orchestrator** — reads an incoming request, decides which agent
  should handle it, and routes accordingly. Escalates to a human instead
  of guessing when a request doesn't clearly fit either path.

Every output from every path is marked `needs_human_review: true` —
this is enforced in code, not a setting the AI can turn off.

## Why this exists

Most "AI demo" projects show a single prompt-response chatbot. This
project exists to demonstrate something different: a system with
genuine multi-step reasoning, tool use, routing logic, and — most
importantly — the guardrails and failure-mode thinking that a real
deployment (especially in a regulated field like legal services)
actually requires.

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full design
document, including failure modes considered and what's explicitly
out of scope for this MVP.

## Firm-specific configuration

All firm-specific business rules — practice areas handled, minimum
claim values, jurisdictions — live in `firm_config.json`, not in code.
Onboarding a different firm means editing that file, not the program.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env
# add your ANTHROPIC_API_KEY to .env, leave MOCK_MODE=true for now

python3 drafting_agent.py        # standalone drafting agent test
python3 intake_triage_agent.py   # standalone triage agent test
python3 orchestrator.py          # full routing pipeline test
```

Set `MOCK_MODE=false` in `.env` to use the real Claude API instead of
the mock heuristics (requires a valid Anthropic API key).

## What's intentionally NOT built (yet)

- No real client data — all test cases are synthetic
- No live email/SMS/website integration — inputs are simulated
- No review-queue UI — human review is currently log-file based
- No multi-firm/multi-tenant support

These are named deliberately in the architecture doc rather than
glossed over — see Section 9 ("Explicitly Deferred").

## Stack

Python 3.10+, Anthropic API (`anthropic` SDK), no framework — the
orchestration/routing logic is hand-written so the decision-making is
fully inspectable rather than hidden inside a library.
