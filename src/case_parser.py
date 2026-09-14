"""
Stage 2 (Entity extraction) + Stage 3 (Content mapping) for the CASE side.

The case_information.json file is already labeled/tabular (it came from a
structured "fill this form" source), so pulling it into the Entities schema
is a deterministic parse rather than an LLM call. This is a deliberate design
choice: don't use an LLM where a reliable parser does the job better -- it
removes a whole class of hallucination risk from entity extraction.

The reference *document* (unstructured prose) is where LLM-assisted
extraction earns its keep -- see reference_parser.py.
"""
from __future__ import annotations
import json
from pathlib import Path

from schemas import Entities, Respondent, ReplyPoint, DraftPlan, DraftParagraph


def load_case_information(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_entities(case_info: dict) -> Entities:
    """Deterministic entity extraction from the structured case file."""
    court = case_info["court"]
    parties = case_info["parties"]
    deponent = case_info["deponent"]
    attestation = case_info["attestation"]
    advocate = case_info.get("advocate", {})

    respondents = [
        Respondent(number=r["number"], name=r["name"], status_tag=r["status_tag"])
        for r in parties["respondents"]
    ]

    return Entities(
        forum=court["forum"],
        city=court["city"],
        jurisdiction_type=court["jurisdiction_type"],
        proceeding_type=court["proceeding_type"],
        case_number=court["case_number"],
        year=court["year"],
        petitioner=parties["petitioner"]["name"],
        respondents=respondents,
        filed_on_behalf_of_respondent_number=parties["filed_on_behalf_of_respondent_number"],
        deponent_name=deponent["name"],
        designation=deponent.get("designation"),
        organisation=deponent.get("organisation"),
        address=deponent["address"],
        is_organisation=deponent.get("is_organisation", False),
        verification_verb=deponent["verification_verb"],
        place_of_attestation=attestation["place"],
        date_of_attestation=attestation["date"],
        advocate_firm=advocate.get("firm"),
    )


def extract_reply_points(case_info: dict) -> list[ReplyPoint]:
    return [
        ReplyPoint(
            point_no=p["point_no"],
            heading=p["heading"],
            move=p["move"],
            bullets=p["bullets"],
            exhibit=p.get("exhibit"),
        )
        for p in case_info["reply_points"]
    ]


def build_draft_plan(case_info: dict) -> DraftPlan:
    """Content mapping: place the extracted reply points into the fixed
    paragraph skeleton required by format_rules.json (identity -> denial ->
    preliminary -> substantive(s) -> closing), appending a synthetic
    CLOSING paragraph since the case file's reply points end at the last
    substantive point and the format requires an explicit closing paragraph."""
    entities = extract_entities(case_info)
    reply_points = extract_reply_points(case_info)

    body_paragraphs: list[DraftParagraph] = []
    for rp in reply_points:
        bullets = rp.bullets
        if rp.exhibit:
            # The exhibit's own annexure sentence is composed separately by
            # the generator (in the reference's fixed "Hereto annexed and
            # marked as..." phrasing), so drop any source bullet that just
            # restates the exhibit label -- otherwise it gets said twice.
            label = rp.exhibit.get("label", "")
            bullets = [b for b in bullets if not (label and label in b)]
        body_paragraphs.append(
            DraftParagraph(
                number=rp.point_no,
                move=rp.move,
                source_bullets=bullets,
                exhibit=rp.exhibit,
            )
        )

    # Append the mandatory CLOSING paragraph (not itself a "reply point" in
    # the case file, but required by every part of the format spec).
    closing_number = body_paragraphs[-1].number + 1
    body_paragraphs.append(
        DraftParagraph(
            number=closing_number,
            move="CLOSING",
            source_bullets=case_info.get("prayer_facts", []),
            exhibit=None,
        )
    )

    return DraftPlan(
        entities=entities,
        body_paragraphs=body_paragraphs,
        prayer_facts=case_info.get("prayer_facts", []),
    )
