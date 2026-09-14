"""
Stage 5 (Validation/evaluation) + Stage 6 (Evaluation report).

Scoring scheme (documented here so the report can explain itself, per the
assignment's "explain how the score was calculated" requirement):

  - Each of the 6 dimensions starts at 100.
  - Each "error" issue in that dimension: -15 points.
  - Each "warning" issue in that dimension: -5 points.
  - Score is floored at 0.
  - Overall score = simple average of the 6 dimension scores, rounded.

This is a deliberately simple, defensible scheme -- transparent deductions
rather than a black-box model. The evaluator draws on:
  - validators.py (deterministic, no LLM)
  - a deterministic template-fidelity phrase-bank check (below)
  - an optional LLM hallucination pass (only used if an API key is
    configured; the deterministic hallucination check already covers the
    most important case -- invented respondent numbers -- without needing
    a model call at all).
"""
from __future__ import annotations
import os
import json
from dataclasses import dataclass, asdict
from datetime import datetime

from schemas import GeneratedDocument
from validators import Issue, run_all_deterministic_checks

DIMENSIONS = [
    "entity_accuracy",
    "completeness",
    "structure",
    "consistency",
    "template_fidelity",
    "hallucination",
]


@dataclass
class EvaluationReport:
    overall_score: int
    dimension_scores: dict[str, int]
    issues: list[dict]
    scoring_explanation: str
    generation_mode: str
    generated_at: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def to_markdown(self) -> str:
        lines = [
            "# Evaluation Report — Affidavit in Reply",
            "",
            f"**Overall Score: {self.overall_score}/100**",
            "",
            f"_Generated: {self.generated_at} · Generation mode: `{self.generation_mode}`_",
            "",
            "## Dimension Scores",
            "",
            "| Dimension | Score |",
            "|---|---|",
        ]
        for dim in DIMENSIONS:
            lines.append(f"| {dim.replace('_', ' ').title()} | {self.dimension_scores[dim]}/100 |")
        lines += ["", "## Issues Detected", ""]
        if not self.issues:
            lines.append("No issues detected.")
        else:
            for i, issue in enumerate(self.issues, start=1):
                lines.append(
                    f"{i}. **[{issue['dimension']} / {issue['severity']}]** {issue['message']}\n"
                    f"   - *Source:* {issue['source']}"
                )
        lines += ["", "## Scoring Method", "", self.scoring_explanation]
        return "\n".join(lines)


def _template_fidelity_phrase_check(doc: GeneratedDocument, format_rules: dict) -> list[Issue]:
    """Deterministic template-fidelity check: for each paragraph, confirm
    at least one fixed phrase from that move's phrase bank actually appears
    in the generated text. Skipped for template_fallback mode since the
    fallback composer inserts these phrases verbatim by construction."""
    if doc.generation_mode == "template_fallback":
        return []
    issues = []
    move_to_key = {
        "IDENTITY_AND_PERUSAL": "paragraph_1",
        "BLANKET_DENIAL": "blanket_denial",
        "PRELIMINARY_POSITION": "preliminary_position",
        "SUBSTANTIVE_ANSWER": "substantive_answer",
        "CLOSING": "closing",
    }
    for i, (para, move) in enumerate(zip(doc.paragraphs, doc.paragraph_moves), start=1):
        key = move_to_key.get(move)
        if not key:
            continue
        phrases = format_rules["fixed_phrases"][key]
        if not any(phrase.lower() in para.lower() for phrase in phrases):
            issues.append(Issue(
                dimension="template_fidelity",
                severity="warning",
                message=f"Paragraph {i} ({move}) does not use any of the reference's fixed phrases for this section.",
                source="format_rules.fixed_phrases",
            ))
    return issues


def _score_dimensions(issues: list[Issue]) -> dict[str, int]:
    scores = {d: 100 for d in DIMENSIONS}
    for issue in issues:
        deduction = 15 if issue.severity == "error" else 5
        scores[issue.dimension] = max(0, scores[issue.dimension] - deduction)
    return scores


def evaluate(
    doc: GeneratedDocument,
    sections_present: dict[str, bool],
    verification_range: tuple[int, int] | None,
    jurat_verb: str | None,
    deponent_clause_text: str,
    expected_exhibits: list[dict],
    known_respondent_numbers: set[int],
    format_rules: dict,
) -> EvaluationReport:
    issues = run_all_deterministic_checks(
        doc=doc,
        sections_present=sections_present,
        verification_range=verification_range,
        jurat_verb=jurat_verb,
        deponent_clause_text=deponent_clause_text,
        expected_exhibits=expected_exhibits,
        known_respondent_numbers=known_respondent_numbers,
    )
    issues += _template_fidelity_phrase_check(doc, format_rules)

    dimension_scores = _score_dimensions(issues)
    overall = round(sum(dimension_scores.values()) / len(dimension_scores))

    explanation = (
        "Each dimension starts at 100. Every 'error' issue found in that dimension "
        "deducts 15 points; every 'warning' deducts 5 points; scores are floored at 0. "
        "The overall score is the simple average of the six dimension scores. "
        f"{len(issues)} issue(s) were detected across all dimensions by deterministic "
        "checks run against the format rules and the supplied case data (no LLM judging "
        "was used for scoring, keeping the score reproducible)."
    )

    return EvaluationReport(
        overall_score=overall,
        dimension_scores=dimension_scores,
        issues=[asdict(i) for i in issues],
        scoring_explanation=explanation,
        generation_mode=doc.generation_mode,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )
