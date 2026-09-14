"""
Structured intermediate representation used between extraction and generation.

This is the single JSON-serialisable object that flows through the pipeline:
    case_information.json --(case_parser)--> Entities --(content_mapper)--> DraftPlan
    --(generator)--> GeneratedDocument --(docx_builder)--> .docx
    GeneratedDocument --(validators/evaluator)--> EvaluationReport

Keeping this as one explicit schema (rather than passing raw dicts around
implicitly) is what the assignment calls out as a "nice to have": a structured
intermediate JSON representation between extraction and generation.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Respondent:
    number: int
    name: str
    status_tag: str


@dataclass
class Entities:
    """The entity set defined in Section 6 of the format-explainer document."""
    forum: str
    city: str
    jurisdiction_type: str
    proceeding_type: str
    case_number: str
    year: str
    petitioner: str
    respondents: list[Respondent]
    filed_on_behalf_of_respondent_number: int
    deponent_name: str
    designation: Optional[str]
    organisation: Optional[str]
    address: str
    is_organisation: bool
    verification_verb: str
    place_of_attestation: str
    date_of_attestation: str
    advocate_firm: Optional[str] = None

    @property
    def respondent_number(self) -> int:
        return self.filed_on_behalf_of_respondent_number

    @property
    def respondent_name(self) -> str:
        for r in self.respondents:
            if r.number == self.respondent_number:
                return r.name
        raise ValueError("No respondent matches filed_on_behalf_of_respondent_number")

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class ReplyPoint:
    point_no: int
    heading: str
    move: str  # IDENTITY_AND_PERUSAL | BLANKET_DENIAL | PRELIMINARY_POSITION | SUBSTANTIVE_ANSWER | CLOSING
    bullets: list[str]
    exhibit: Optional[dict] = None


@dataclass
class DraftParagraph:
    """One numbered body paragraph, pre-generation."""
    number: int
    move: str
    source_bullets: list[str]
    exhibit: Optional[dict] = None


@dataclass
class DraftPlan:
    """Content-mapping output: case facts placed into the reference's section slots,
    before any prose is generated. This is what content_mapper.py produces."""
    entities: Entities
    body_paragraphs: list[DraftParagraph]
    prayer_facts: list[str]

    @property
    def paragraph_count(self) -> int:
        return len(self.body_paragraphs)


@dataclass
class GeneratedDocument:
    """Final generated text, section by section, plus bookkeeping the
    validators need (which source each paragraph came from, generation mode)."""
    entities: Entities
    paragraphs: list[str]           # final prose, one string per numbered paragraph, in order
    paragraph_moves: list[str]      # move label per paragraph, same order
    prayer_lines: list[str]
    generation_mode: str            # "llm" or "template_fallback"
    exhibits: list[dict] = field(default_factory=list)

    @property
    def paragraph_count(self) -> int:
        return len(self.paragraphs)
