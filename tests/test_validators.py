"""
Sanity tests for the deterministic validators (Stage 5). These deliberately
corrupt a correct GeneratedDocument in each of the ways described as
examples in the assignment brief (Section 7) and assert the corresponding
check fires. Run with: python3 tests/test_validators.py
"""
import os
import sys
import json
import copy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import case_parser
import generator
import validators

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _build_clean_doc():
    with open(os.path.join(DATA_DIR, "format_rules.json")) as f:
        format_rules = json.load(f)
    case_info = case_parser.load_case_information(os.path.join(DATA_DIR, "case_information.json"))
    plan = case_parser.build_draft_plan(case_info)
    return generator.generate_template_fallback(plan)


def test_respondent_number_mismatch():
    doc = _build_clean_doc()
    doc = copy.deepcopy(doc)
    doc.paragraphs[0] = doc.paragraphs[0].replace("Respondent No.2", "Respondent No.3")
    issues = validators.check_respondent_number_consistency(doc)
    assert len(issues) == 1, f"expected 1 issue, got {issues}"
    print("PASS: respondent number mismatch is caught ->", issues[0].message)


def test_verification_range_mismatch():
    doc = _build_clean_doc()
    issues = validators.check_verification_paragraph_range(doc, verification_range=(1, doc.paragraph_count - 1))
    assert len(issues) == 1
    print("PASS: verification range mismatch is caught ->", issues[0].message)


def test_verb_agreement_mismatch():
    doc = _build_clean_doc()
    issues = validators.check_verb_agreement(doc, jurat_verb="Sworn")  # doc uses 'solemnly affirm' -> expects 'Solemnly affirmed'
    assert len(issues) == 1
    print("PASS: verb agreement mismatch is caught ->", issues[0].message)


def test_missing_section():
    sections = {"forum_heading": True, "verification": False}
    issues = validators.check_required_sections_present(sections)
    assert len(issues) == 1
    print("PASS: missing section is caught ->", issues[0].message)


def test_exhibit_not_referenced():
    doc = _build_clean_doc()
    doc = copy.deepcopy(doc)
    doc.paragraphs = [p.replace("EXHIBIT-'A'", "") for p in doc.paragraphs]
    issues = validators.check_exhibit_reference_present(doc, expected_exhibits=[{"label": "EXHIBIT-'A'"}])
    assert len(issues) == 1
    print("PASS: unreferenced exhibit is caught ->", issues[0].message)


def test_invented_respondent_number():
    doc = _build_clean_doc()
    doc = copy.deepcopy(doc)
    doc.paragraphs[0] += " This also concerns Respondent No.9."
    issues = validators.check_no_invented_respondent_numbers(doc, known_numbers={1, 2})
    assert len(issues) == 1
    print("PASS: invented respondent number is caught ->", issues[0].message)


def test_clean_document_has_no_issues():
    doc = _build_clean_doc()
    issues = validators.check_respondent_number_consistency(doc)
    issues += validators.check_verification_paragraph_range(doc, (1, doc.paragraph_count))
    issues += validators.check_no_invented_respondent_numbers(doc, known_numbers={1, 2})
    assert len(issues) == 0, f"clean document should have no issues, got {issues}"
    print("PASS: clean document produces zero false positives")


if __name__ == "__main__":
    test_respondent_number_mismatch()
    test_verification_range_mismatch()
    test_verb_agreement_mismatch()
    test_missing_section()
    test_exhibit_not_referenced()
    test_invented_respondent_number()
    test_clean_document_has_no_issues()
    print("\nAll validator sanity tests passed.")
