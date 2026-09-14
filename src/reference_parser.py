"""
Stage 1 (Template / document understanding).

Reads the reference Affidavit in Reply and identifies where each of the
10 fixed parts (per format_rules.json / the format-explainer doc) sits in
the raw text, plus a light entity pull from the reference document itself.

This is intentionally regex/heuristic-based rather than an LLM call: the
document is highly templated (fixed section markers like "PRAYER",
"VERIFICATION", "VERSUS", numbered paragraphs), so a structural parser is
both cheaper and more reliable than asking an LLM to relocate sections.
An LLM is far more useful downstream, in generator.py, where actual prose
has to be composed rather than located.
"""
from __future__ import annotations
import re
from pathlib import Path


SECTION_MARKERS = [
    "forum_heading",
    "jurisdiction",
    "case_number",
    "cause_title",
    "affidavit_title",
    "deponent_clause",
    "numbered_paragraphs",
    "prayer",
    "jurat",
    "verification",
]


def load_reference(path: str | Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_reference_structure(text: str) -> dict:
    """Returns a dict mapping each of the 10 parts to the raw text span
    found in the reference document, plus a few entities pulled straight
    from the reference (used only to sanity-check our understanding of the
    format -- the reference is NOT the source of truth for the new
    document's content, which comes entirely from case_information.json)."""

    result = {}

    m = re.search(r"^(IN THE HIGH COURT.*)$", text, re.MULTILINE)
    result["forum_heading"] = m.group(1).strip() if m else None

    m = re.search(r"^([A-Z ]+JURISDICTION)$", text, re.MULTILINE)
    result["jurisdiction"] = m.group(1).strip() if m else None

    m = re.search(r"^(\w[\w ]* NO\. \S+ OF \d{4})$", text, re.MULTILINE)
    result["case_number"] = m.group(1).strip() if m else None

    m = re.search(r"(.+?)\n\nVERSUS\n\n(.+?)\n\nAFFIDAVIT", text, re.DOTALL)
    result["cause_title"] = m.group(0).strip() if m else None

    m = re.search(r"^(AFFIDAVIT IN REPLY ON BEHALF OF RESPONDENT NO\. ?\d+)$", text, re.MULTILINE)
    result["affidavit_title"] = m.group(1).strip() if m else None

    m = re.search(r"(I, .+?do hereby solemnly affirm and state as under:)", text, re.DOTALL)
    result["deponent_clause"] = m.group(1).strip() if m else None

    paras = re.findall(r"^\d+\.\s.+?(?=\n\n\d+\.|\n\nPRAYER)", text, re.MULTILINE | re.DOTALL)
    result["numbered_paragraphs"] = [p.strip() for p in paras]
    result["paragraph_count_detected"] = len(paras)

    m = re.search(r"(PRAYER\n.*?)\n\nSolemnly", text, re.DOTALL)
    result["prayer"] = m.group(1).strip() if m else None

    m = re.search(r"(Solemnly affirmed.*?DEPONENT)", text, re.DOTALL)
    result["jurat"] = m.group(1).strip() if m else None
    result["jurat_verb"] = "Solemnly affirmed" if m and "Solemnly affirmed" in m.group(1) else (
        "Sworn" if m and "Sworn" in m.group(1) else None
    )

    m = re.search(r"(VERIFICATION\n.*?DEPONENT)", text, re.DOTALL)
    result["verification"] = m.group(1).strip() if m else None
    m2 = re.search(r"paragraphs (\d+) to (\d+)", text)
    result["verification_range"] = (int(m2.group(1)), int(m2.group(2))) if m2 else None

    m = re.search(r"the Respondent No\.(\d+) above named", text)
    result["deponent_clause_respondent_number"] = int(m.group(1)) if m else None

    return result


def sections_present(parsed: dict) -> dict[str, bool]:
    """Boolean presence check for each of the 10 parts, used by the
    structure/completeness validators."""
    return {
        "forum_heading": bool(parsed.get("forum_heading")),
        "jurisdiction": bool(parsed.get("jurisdiction")),
        "case_number": bool(parsed.get("case_number")),
        "cause_title": bool(parsed.get("cause_title")),
        "affidavit_title": bool(parsed.get("affidavit_title")),
        "deponent_clause": bool(parsed.get("deponent_clause")),
        "numbered_paragraphs": bool(parsed.get("numbered_paragraphs")),
        "prayer": bool(parsed.get("prayer")),
        "jurat": bool(parsed.get("jurat")),
        "verification": bool(parsed.get("verification")),
    }
"""
if __name__ == "__main__":
    text = load_reference("/Users/amanthakur/Documents/WORK/Projects/Brainwonders/legal-doc-agent/data/reference_affidavit.txt")
    result = parse_reference_structure(text)
    print(result)
"""