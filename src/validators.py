"""
Deterministic checks -- no LLM involved. These satisfy the assignment's
"must have": at least three deterministic checks, run against the generated
document, independent of any model call. They also do most of the actual
scoring work in evaluator.py; the LLM (when available) only adds a soft
hallucination-language check on top.

Each check returns an Issue (or None) so the evaluator can aggregate them
into the report's issue list with a source/rule reference, as the brief
asks for ("the source or reference for each detected issue").
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from schemas import GeneratedDocument


@dataclass
class Issue:
    dimension: str        # entity_accuracy | completeness | structure | consistency | template_fidelity | hallucination
    severity: str          # "error" | "warning"
    message: str
    source: str             # which rule / part of the spec this comes from


def check_respondent_number_consistency(doc: GeneratedDocument) -> list[Issue]:
    """Consistency: the respondent number must be identical everywhere it
    appears (deponent clause, paragraph 1, affidavit title -- represented
    here via entities.respondent_number vs. numbers mentioned in the body
    text)."""
    issues = []
    expected = doc.entities.respondent_number
    pattern = re.compile(r"Respondent No\.?\s*(\d+)", re.IGNORECASE)
    for i, para in enumerate(doc.paragraphs, start=1):
        for match in pattern.finditer(para):
            found = int(match.group(1))
            if found != expected:
                issues.append(Issue(
                    dimension="consistency",
                    severity="error",
                    message=(
                        f"Paragraph {i} refers to Respondent No.{found}, but the affidavit "
                        f"is filed on behalf of Respondent No.{expected}."
                    ),
                    source="format_rules.invariants (respondent number consistency)",
                ))
    return issues


def check_verification_paragraph_range(doc: GeneratedDocument, verification_range: Optional[tuple[int, int]]) -> list[Issue]:
    """Invariant 2 from format_rules.json: verification range must equal
    the actual number of body paragraphs (1 to N)."""
    issues = []
    n = doc.paragraph_count
    if verification_range is None:
        issues.append(Issue(
            dimension="structure",
            severity="error",
            message="No verification paragraph range found in the document.",
            source="format_rules.invariants.verification_range",
        ))
        return issues
    start, end = verification_range
    if start != 1 or end != n:
        issues.append(Issue(
            dimension="consistency",
            severity="error",
            message=(
                f"Verification reads 'paragraphs {start} to {end}' but the body has "
                f"{n} paragraphs; it should read 'paragraphs 1 to {n}'."
            ),
            source="format_rules.invariants.verification_range",
        ))
    return issues


def check_verb_agreement(doc: GeneratedDocument, jurat_verb: Optional[str]) -> list[Issue]:
    """Invariant 1: verification verb in the deponent clause must match the
    jurat verb (e.g. 'solemnly affirm' -> 'Solemnly affirmed')."""
    issues = []
    verb_map = {
        "solemnly affirm": "Solemnly affirmed",
        "swear and affirm": "Sworn",
    }
    expected_jurat_verb = verb_map.get(doc.entities.verification_verb.lower())
    if expected_jurat_verb is None:
        issues.append(Issue(
            dimension="consistency",
            severity="warning",
            message=f"Unrecognised verification verb '{doc.entities.verification_verb}'; cannot check jurat agreement.",
            source="format_rules.deponent_rule.verb_agreement",
        ))
        return issues
    if jurat_verb and jurat_verb != expected_jurat_verb:
        issues.append(Issue(
            dimension="consistency",
            severity="error",
            message=(
                f"Deponent clause implies verb '{doc.entities.verification_verb}' "
                f"(-> jurat should read '{expected_jurat_verb}') but jurat reads '{jurat_verb}'."
            ),
            source="format_rules.deponent_rule.verb_agreement",
        ))
    return issues


def check_required_sections_present(sections_present: dict[str, bool]) -> list[Issue]:
    """Structure: all 10 required parts must be present."""
    issues = []
    for part, present in sections_present.items():
        if not present:
            issues.append(Issue(
                dimension="structure",
                severity="error",
                message=f"Required section '{part}' is missing from the generated document.",
                source="format_rules.parts_in_order",
            ))
    return issues


def check_deponent_clause_role_phrasing(doc: GeneratedDocument, deponent_clause_text: str) -> list[Issue]:
    """Deponent rule: an organisation respondent must be represented by an
    officer ('the <designation> of the Respondent No.N above named'), never
    'I am the Respondent No.N'."""
    issues = []
    e = doc.entities
    if e.is_organisation:
        forbidden = f"I am the Respondent No.{e.respondent_number}"
        if forbidden.lower() in deponent_clause_text.lower():
            issues.append(Issue(
                dimension="template_fidelity",
                severity="error",
                message=(
                    "Respondent is an organisation but the deponent clause phrases the "
                    "deponent as if they personally are the respondent, instead of an "
                    "officer acting for it."
                ),
                source="format_rules.deponent_rule",
            ))
        if not e.designation or e.designation.lower() not in deponent_clause_text.lower():
            issues.append(Issue(
                dimension="entity_accuracy",
                severity="error",
                message="Deponent's designation is missing from the deponent clause for an organisation respondent.",
                source="format_rules.deponent_rule",
            ))
    return issues


def check_exhibit_reference_present(doc: GeneratedDocument, expected_exhibits: list[dict]) -> list[Issue]:
    """Completeness: every exhibit supplied in the case data must actually
    be referenced somewhere in the body text."""
    issues = []
    body_text = " ".join(doc.paragraphs)
    for ex in expected_exhibits:
        label = ex.get("label", "")
        if label and label not in body_text:
            issues.append(Issue(
                dimension="completeness",
                severity="error",
                message=f"Exhibit {label} is supplied in the case data but not referenced in the generated body text.",
                source="case_information.reply_points[].exhibit",
            ))
    return issues


def check_no_invented_respondent_numbers(doc: GeneratedDocument, known_numbers: set[int]) -> list[Issue]:
    """Hallucination (lightweight, deterministic): flags any respondent
    number mentioned in the body that doesn't correspond to any respondent
    supplied in the case data at all (stronger than pure consistency check,
    catches e.g. 'Respondent No.5' out of nowhere)."""
    issues = []
    pattern = re.compile(r"Respondent No\.?\s*(\d+)", re.IGNORECASE)
    body_text = " ".join(doc.paragraphs)
    for match in pattern.finditer(body_text):
        found = int(match.group(1))
        if found not in known_numbers:
            issues.append(Issue(
                dimension="hallucination",
                severity="error",
                message=f"Body text refers to Respondent No.{found}, which does not appear in the supplied case data.",
                source="case_information.parties.respondents",
            ))
    return issues


def run_all_deterministic_checks(
    doc: GeneratedDocument,
    sections_present: dict[str, bool],
    verification_range: Optional[tuple[int, int]],
    jurat_verb: Optional[str],
    deponent_clause_text: str,
    expected_exhibits: list[dict],
    known_respondent_numbers: set[int],
) -> list[Issue]:
    issues: list[Issue] = []
    issues += check_respondent_number_consistency(doc)
    issues += check_verification_paragraph_range(doc, verification_range)
    issues += check_verb_agreement(doc, jurat_verb)
    issues += check_required_sections_present(sections_present)
    issues += check_deponent_clause_role_phrasing(doc, deponent_clause_text)
    issues += check_exhibit_reference_present(doc, expected_exhibits)
    issues += check_no_invented_respondent_numbers(doc, known_respondent_numbers)
    return issues
