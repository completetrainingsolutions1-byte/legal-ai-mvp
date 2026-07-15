"""
Document Extraction -- converts an uploaded document into numbered
paragraphs that can be cited by the analysis agent (e.g. "[P4]").

Supports .txt, .pdf, .docx. This is intentionally simple for the MVP --
large documents (100+ pages) would need chunking/summarization passes
not implemented here; see architecture doc for scope notes.

CONFIDENTIALITY NOTE: extracted text is NOT written to any of this
system's shared logs (review_queue.json, crm_sync_log.jsonl, etc).
It stays in memory for the current session only, unless the caller
explicitly saves it. This is a deliberate scope boundary given the
sensitivity of full document content -- see architecture doc.
"""

import os


def extract_paragraphs(file_path):
    """
    Returns a list of (paragraph_id, text) tuples, e.g.
    [("P1", "This Agreement is made..."), ("P2", "1. Definitions...")]
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".txt":
        return _extract_txt(file_path)
    elif ext == ".pdf":
        return _extract_pdf(file_path)
    elif ext == ".docx":
        return _extract_docx(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Supported: .txt, .pdf, .docx")


def _extract_txt(file_path):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        raw = f.read()
    chunks = [c.strip() for c in raw.split("\n\n") if c.strip()]
    return [(f"P{i+1}", chunk) for i, chunk in enumerate(chunks)]


def _extract_pdf(file_path):
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    paragraphs = []
    para_num = 1
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
        if not chunks and text.strip():
            chunks = [text.strip()]
        for chunk in chunks:
            paragraphs.append((f"P{para_num} (page {page_num})", chunk))
            para_num += 1
    return paragraphs


def _extract_docx(file_path):
    import docx

    doc = docx.Document(file_path)
    paragraphs = []
    para_num = 1
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            paragraphs.append((f"P{para_num}", text))
            para_num += 1
    return paragraphs


def format_for_prompt(paragraphs):
    """Formats extracted paragraphs into a single tagged string for the LLM."""
    return "\n\n".join(f"[{pid}] {text}" for pid, text in paragraphs)
