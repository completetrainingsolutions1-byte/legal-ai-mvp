"""
Document Analysis Assistant -- produces a structured, three-layer
summary for uploaded legal documents:

  1. Executive Summary  -- key facts any attorney can read in 2 minutes
  2. Type-Specific Summary -- structured fields extracted from the text
     (e.g. Monthly Rent, Security Deposit for a lease)
  3. AI Insights -- risk rating, missing clauses, negotiation
     opportunities, and attorney follow-up questions

SCOPE: currently configured for Lease and NDA only (see
document_type_profiles.json). This is a representative subset of
fields per type, not the full 20+ field spec a real enterprise
platform might have -- scoped to what most directly drives an
attorney's initial read of a document.

MOCK MODE HONESTY: structured field extraction in mock mode uses
regex patterns tuned to this project's synthetic sample documents --
it will NOT generalize well to arbitrary real documents. Live mode
uses a real LLM call and generalizes properly. This gap is real and
intentional -- see architecture doc.

Unlike the Intake Triage Agent, this is NOT an autonomous tool-use
loop -- it's a single-pass assistant a human explicitly invokes.

CONFIDENTIALITY: results are NOT written to review_queue.json or
crm_sync_log.jsonl. Document content and analysis stay session-scoped.
"""

import os
import re
import json

MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"

PROFILES_PATH = os.path.join(os.path.dirname(__file__), "document_type_profiles.json")
with open(PROFILES_PATH) as f:
    DOCUMENT_TYPE_PROFILES = json.load(f)

GENERIC_RISK_KEYWORDS = {
    "indemnification": "Indemnification clause -- may create broad liability exposure.",
    "indemnify": "Indemnification clause -- may create broad liability exposure.",
    "non-compete": "Non-compete clause -- enforceability varies significantly by state.",
    "automatically renew": "Auto-renewal clause -- may bind the parties longer than expected if notice deadlines are missed.",
    "arbitration": "Mandatory arbitration clause -- limits ability to litigate in court.",
    "limitation of liability": "Limitation of liability clause -- caps potential recovery.",
    "liquidated damages": "Liquidated damages clause -- pre-set damages amount, worth verifying it's reasonable.",
    "governing law": "Governing law clause -- specifies which state's law applies to disputes.",
    "confidentiality": "Confidentiality obligation -- note the duration and scope.",
}

NOT_SPECIFIED = "Not specified in document"


def _keyword_present(keyword, text_lower):
    """
    Word-boundary-aware keyword check -- prevents false positives like
    'rent' matching inside 'current', or 'pet' matching inside
    'competitor'. This replaced a naive substring check after it
    produced exactly those false positives during testing.
    """
    pattern = r"\b" + re.escape(keyword.lower()) + r"\b"
    return re.search(pattern, text_lower) is not None

# ---------------------------------------------------------------------
# MOCK MODE: regex patterns tuned to this project's synthetic samples
# ---------------------------------------------------------------------

MOCK_FIELD_PATTERNS = {
    "lease": {
        "Property": r"premises located at ([^.]+?)\.",
        "Landlord": r'between ([^(]+?)\s*\("Landlord"\)',
        "Tenant": r'and ([^(]+?)\s*\("Tenant"\)',
        "Monthly Rent": r"monthly rent of \$?([\d,]*\d)",
        "Security Deposit": r"security deposit of \$?([\d,]*\d)",
        "Late Fee": r"late fee of \$?([\d,]*\d)",
        "Renewal Terms": r"(automatically renew[^.]+\.)",
        "Governing Law": r"governed by the laws of (?:the State of )?([^.]+)\.",
    },
    "nda": {
        "Disclosing Party": r'between ([^(]+?)\s*\("Disclosing Party"\)',
        "Receiving Party": r'and ([^(]+?)\s*\("Receiving Party"\)',
        "Confidentiality Period": r"effect for a period of ([^,]+?),?\s*from",
        "Residuals Clause": r"(Receiving Party may use general knowledge[^.]+\.)",
        "Injunctive Relief": r"(entitled to seek injunctive relief[^.]*\.)",
        "Governing Law": r"governed by the laws of (?:the State of )?([^.]+)\.",
    },
}

# Static, doc-type-grounded content for mock mode -- see live mode for
# genuinely generated versions of these based on actual document content.
MOCK_NEGOTIATION_OPPORTUNITIES = {
    "lease": [
        "Consider negotiating a longer notice period before auto-renewal to avoid unintentionally extending the lease.",
        "The late fee terms could be softened with a short grace period.",
        "Clarify whether tenant improvements or alterations are permitted.",
    ],
    "nda": [
        "The confidentiality period could be negotiated shorter if the underlying relationship is short-term.",
        "Standard exclusions (publicly known, independently developed information) should be added if missing.",
        "Consider whether a mutual return/destruction obligation should be added.",
    ],
}

MOCK_ATTORNEY_QUESTIONS = {
    "lease": [
        "Does the client intend to stay past the initial term, given the automatic renewal clause?",
        "Has the client confirmed what 'normal wear and tear' means for deposit deductions?",
        "Are there any planned pets, given the restrictive pet policy?",
    ],
    "nda": [
        "Should exclusions for publicly known or independently developed information be added?",
        "Is a destruction certification needed given the absence of a return/destruction clause?",
        "Should the residuals clause be narrowed to prevent overly broad future use of retained knowledge?",
    ],
}


def detect_document_type(paragraphs):
    """Scores each profile by detection keyword matches; returns (key, confidence)."""
    full_text = " ".join(text for _, text in paragraphs).lower()
    scores = {dt: sum(1 for kw in p["detection_keywords"] if _keyword_present(kw, full_text))
              for dt, p in DOCUMENT_TYPE_PROFILES.items()}
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]
    if best_score == 0:
        return None, "low"
    return best_type, ("high" if best_score >= 3 else "medium")


def _get_profile(doc_type):
    return DOCUMENT_TYPE_PROFILES.get(doc_type)


def compute_risk_rating(num_findings, num_missing):
    """Simple heuristic -- mock mode only. Live mode asks the model directly."""
    total = num_findings + (num_missing * 1.5)  # missing clauses weighted slightly higher
    if total <= 3:
        return "Low"
    elif total <= 7:
        return "Medium"
    return "High"


def extract_structured_fields_mock(doc_type, full_text):
    """Regex-based field extraction -- tuned to this project's sample docs."""
    patterns = MOCK_FIELD_PATTERNS.get(doc_type, {})
    profile = _get_profile(doc_type)
    fields_by_category = {}

    for field_spec in profile["summary_fields"]:
        name, category = field_spec["name"], field_spec["category"]
        pattern = patterns.get(name)
        value = NOT_SPECIFIED
        if pattern:
            m = re.search(pattern, full_text, re.IGNORECASE)
            if m:
                value = m.group(1).strip()
                if name in ("Monthly Rent", "Security Deposit", "Late Fee") and value.replace(",", "").isdigit():
                    value = f"${value}"
        fields_by_category.setdefault(category, {})[name] = value

    return fields_by_category


def extract_structured_fields_live(doc_type, document_text):
    import anthropic

    profile = _get_profile(doc_type)
    field_names = [f["name"] for f in profile["summary_fields"]]
    # Tool schema property keys must match ^[a-zA-Z0-9_.-]{1,64}$ -- field
    # names like "Disclosing Party" contain spaces, so map to safe keys.
    key_for_name = {name: re.sub(r"[^a-zA-Z0-9_.-]", "_", name) for name in field_names}
    name_for_key = {key: name for name, key in key_for_name.items()}

    tool = {
        "name": "submit_structured_summary",
        "description": "Submit extracted field values for this document.",
        "input_schema": {
            "type": "object",
            "properties": {key: {"type": "string"} for key in name_for_key},
            "required": list(name_for_key.keys()),
        },
    }

    client = anthropic.Anthropic()
    prompt = f"""Extract these specific fields from the document below. If a
field is not addressed in the document, respond with exactly:
"{NOT_SPECIFIED}" for that field -- do not guess or infer.

Fields to extract: {', '.join(field_names)}

Document:
{document_text}

Call submit_structured_summary with your extracted values."""

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        tools=[tool],
        messages=[{"role": "user", "content": prompt}],
    )

    extracted = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_structured_summary":
            extracted = {name_for_key[key]: value for key, value in block.input.items()}

    fields_by_category = {}
    for field_spec in profile["summary_fields"]:
        name, category = field_spec["name"], field_spec["category"]
        fields_by_category.setdefault(category, {})[name] = extracted.get(name, NOT_SPECIFIED)

    return fields_by_category


def analyze_document_mock(paragraphs, doc_type=None):
    profile = _get_profile(doc_type)
    risk_keywords = profile["risk_keywords"] if profile else GENERIC_RISK_KEYWORDS
    full_text = " ".join(text for _, text in paragraphs)
    full_text_lower = full_text.lower()

    findings = []
    seen_descriptions = set()
    for pid, text in paragraphs:
        text_lower = text.lower()
        for keyword, description in risk_keywords.items():
            if _keyword_present(keyword, text_lower) and description not in seen_descriptions:
                findings.append({"citation": pid, "keyword": keyword, "finding": description})
                seen_descriptions.add(description)

    missing = []
    if profile:
        for clause in profile["expected_clauses"]:
            if not any(_keyword_present(kw, full_text_lower) for kw in clause["satisfied_by"]):
                missing.append(clause["description"])

    structured_summary = extract_structured_fields_mock(doc_type, full_text) if profile else {}
    risk_rating = compute_risk_rating(len(findings), len(missing))

    type_label = profile["display_name"] if profile else "General/Unrecognized document type"
    summary = (
        f"[MOCK] Document type: {type_label}. {len(paragraphs)} paragraphs analyzed. "
        f"{len(findings)} notable provision(s) flagged via keyword matching "
        f"(mock mode -- live mode would provide genuine contextual analysis)."
    )

    return {
        "summary": summary,
        "doc_type_label": type_label,
        "structured_summary": structured_summary,
        "risk_rating": risk_rating,
        "findings": findings,
        "missing_considerations": missing,
        "negotiation_opportunities": MOCK_NEGOTIATION_OPPORTUNITIES.get(doc_type, []),
        "attorney_questions": MOCK_ATTORNEY_QUESTIONS.get(doc_type, []),
        "detected_type": doc_type,
    }


def analyze_document_live(paragraphs, doc_type=None):
    import anthropic

    profile = _get_profile(doc_type)
    doc_type_label = profile["display_name"] if profile else "General/unspecified document type"
    expected_clauses_str = ", ".join(c["description"] for c in profile["expected_clauses"]) if profile else "standard contract risk areas"
    document_text = "\n\n".join(f"[{pid}] {text}" for pid, text in paragraphs)

    system_prompt = f"""You are a legal document analysis assistant supporting
a law firm's attorneys and staff. You help attorneys understand documents
faster -- you do NOT provide legal advice or make legal conclusions.

Document text is tagged with paragraph IDs like [P4]. ALWAYS cite the
specific paragraph ID(s) when referencing document content.

This document has been identified as a: {doc_type_label}
Pay particular attention to: {expected_clauses_str}

Describe what a clause says and why it might warrant attorney attention,
not its ultimate legal effect. If an expected consideration is not
addressed anywhere, flag it as a possible gap."""

    client = anthropic.Anthropic()
    prompt = f"""Analyze this document and provide:
1. A brief executive summary (2-4 sentences)
2. Notable provisions/potential risk areas, each with a paragraph citation
3. Any expected considerations for this document type that appear MISSING
4. An overall risk rating (Low/Medium/High) with a one-sentence reason
5. 2-3 negotiation opportunities that might benefit the client
6. 2-3 follow-up questions an attorney should ask the client

Document:
{document_text}

Respond in this exact format:
SUMMARY: <summary>

RISK_RATING: <Low/Medium/High> - <reason>

FINDINGS:
- [P#] <finding>

MISSING:
- <missing consideration>

NEGOTIATION:
- <opportunity>

QUESTIONS:
- <question>
"""

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")

    def _section(name, next_names):
        pattern = rf"{name}:(.+?)(?={'|'.join(next_names)}|$)"
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else ""

    summary = _section("SUMMARY", ["RISK_RATING:"])
    risk_section = _section("RISK_RATING", ["FINDINGS:"])
    risk_rating = risk_section.split("-")[0].strip() if risk_section else "Unknown"

    findings = []
    for line in _section("FINDINGS", ["MISSING:"]).split("\n"):
        m = re.match(r"-\s*\[(\w[\w\s()]*)\]\s*(.+)", line.strip())
        if m:
            findings.append({"citation": m.group(1).strip(), "keyword": None, "finding": m.group(2).strip()})

    missing = [l.strip().lstrip("- ").strip() for l in _section("MISSING", ["NEGOTIATION:"]).split("\n") if l.strip().lstrip("- ").strip()]
    negotiation = [l.strip().lstrip("- ").strip() for l in _section("NEGOTIATION", ["QUESTIONS:"]).split("\n") if l.strip().lstrip("- ").strip()]
    questions = [l.strip().lstrip("- ").strip() for l in _section("QUESTIONS", []).split("\n") if l.strip().lstrip("- ").strip()]

    structured_summary = extract_structured_fields_live(doc_type, document_text) if profile else {}

    return {
        "summary": summary,
        "doc_type_label": doc_type_label,
        "structured_summary": structured_summary,
        "risk_rating": risk_rating,
        "findings": findings,
        "missing_considerations": missing,
        "negotiation_opportunities": negotiation,
        "attorney_questions": questions,
        "detected_type": doc_type,
    }


def analyze_document(paragraphs, doc_type=None):
    if MOCK_MODE:
        return analyze_document_mock(paragraphs, doc_type)
    return analyze_document_live(paragraphs, doc_type)


def answer_question_mock(paragraphs, question):
    question_words = set(w.lower() for w in question.split() if len(w) > 3)
    best_matches = []
    for pid, text in paragraphs:
        text_words = set(w.lower() for w in text.split())
        overlap = len(question_words & text_words)
        if overlap > 0:
            best_matches.append((overlap, pid, text))
    best_matches.sort(reverse=True)

    if not best_matches:
        return {"answer": "[MOCK] No paragraphs matched keywords from this question.", "citations": []}

    top = best_matches[:2]
    citations = [pid for _, pid, _ in top]
    excerpt = " / ".join(text[:150] for _, _, text in top)
    return {"answer": f"[MOCK] Most relevant section(s): {excerpt}...", "citations": citations}


def answer_question_live(paragraphs, question):
    import anthropic

    document_text = "\n\n".join(f"[{pid}] {text}" for pid, text in paragraphs)
    client = anthropic.Anthropic()
    prompt = f"""Document:
{document_text}

Question: {question}

Answer using ONLY information in the document. Cite paragraph ID(s). If
the document doesn't address the question, say so."""

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=800,
        system="You are a legal document Q&A assistant. Answer only from the provided document text, always citing paragraph IDs.",
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    citations = re.findall(r"\[(\w[\w\s()]*)\]", text)
    return {"answer": text, "citations": citations}


def answer_question(paragraphs, question):
    if MOCK_MODE:
        return answer_question_mock(paragraphs, question)
    return answer_question_live(paragraphs, question)