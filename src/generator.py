"""
Stage 4 (Document generation).

Turns a DraftPlan (structured facts already placed into the right slots) into
actual prose, paragraph by paragraph, in the drafting style fixed by the
reference document -- i.e. using the phrase bank in format_rules.json.

Three modes, auto-selected by what's configured (or forced via
GENERATION_PROVIDER env var / the provider argument):
  - "anthropic": calls the Claude API (ANTHROPIC_API_KEY).
  - "huggingface": calls a model through the Hugging Face Inference API
    (HF_TOKEN + HF_MODEL), via huggingface_hub.InferenceClient.chat_completion.
  - "template_fallback": deterministic string composition using the same
    phrase bank, no network call at all. Used when no provider is
    configured, so the app still produces a full result (this is the
    "pre-run demo mode / cached output" path called out in the assignment
    brief).

All three modes are constrained to only use facts present in the DraftPlan --
this is what keeps the hallucination-check dimension meaningful: the
evaluator can flag anything in the output that isn't traceable to input.
Smaller open models (typical on the HF free tier) follow the "don't invent
anything" instruction less reliably than Claude, so the hallucination
validator is more likely to actually fire on that path -- worth knowing
before you demo it.
"""
from __future__ import annotations
import os
import json
from schemas import DraftPlan, DraftParagraph, GeneratedDocument

MOVE_INSTRUCTIONS = {
    "IDENTITY_AND_PERUSAL": (
        "Open with the deponent's standing to reply (person vs organisation phrasing, "
        "per the deponent rule), that the petition and documents have been perused, and "
        "competence to affirm the affidavit. Use the fixed phrases for paragraph 1."
    ),
    "BLANKET_DENIAL": (
        "Deny every allegation not specifically admitted, and state the petition is "
        "misconceived and liable to be dismissed in limine. Use the blanket-denial fixed phrases."
    ),
    "PRELIMINARY_POSITION": (
        "State the preliminary legal position: the petition is misconceived, the "
        "impugned action was lawful and no right has been infringed. Use the "
        "preliminary-position fixed phrases and weave in the supplied facts."
    ),
    "SUBSTANTIVE_ANSWER": (
        "Answer the specific allegation using the supplied facts only. Use the "
        "substantive-answer fixed phrases. If an exhibit is supplied, reference it exactly "
        "as given (label and description), in the reference document's exhibit-reference style."
    ),
    "CLOSING": (
        "Close with the standard closing move: in the premises aforesaid, the petition "
        "deserves to be dismissed with costs."
    ),
}


def _phrase_bank_for(move: str, format_rules: dict) -> list[str]:
    key = {
        "IDENTITY_AND_PERUSAL": "paragraph_1",
        "BLANKET_DENIAL": "blanket_denial",
        "PRELIMINARY_POSITION": "preliminary_position",
        "SUBSTANTIVE_ANSWER": "substantive_answer",
        "CLOSING": "closing",
    }[move]
    return format_rules["fixed_phrases"][key]


def _deponent_clause_role(plan: DraftPlan) -> str:
    e = plan.entities
    rule = json.load(open(os.path.join(os.path.dirname(__file__), "..", "data", "format_rules.json")))["deponent_rule"]
    if e.is_organisation:
        return rule["organisation_template"].format(designation=e.designation, n=e.respondent_number)
    return rule["person_template"].format(n=e.respondent_number)


# ---------------------------------------------------------------------------
# Template fallback (deterministic, no network)
# ---------------------------------------------------------------------------

def _lower_first(s: str) -> str:
    return s[0].lower() + s[1:] if s else s


def _compose_paragraph_template(dp: DraftParagraph, plan: DraftPlan) -> str:
    e = plan.entities
    facts = " ".join(dp.source_bullets)

    if dp.move == "IDENTITY_AND_PERUSAL":
        role = "the Respondent No.{0}".format(e.respondent_number) if not e.is_organisation \
            else "the {0} of the Respondent No.{1}".format(e.designation, e.respondent_number)
        return (
            f"I say that I am {role} in the above {e.proceeding_type.title()} and am well "
            f"acquainted with the facts and circumstances of the case. I have perused the "
            f"Petition and the documents annexed thereto and am competent to affirm this "
            f"Affidavit in Reply. {facts}"
        )
    if dp.move == "BLANKET_DENIAL":
        return (
            f"At the outset, I deny each and every allegation, contention and submission "
            f"made in the {e.proceeding_type.title()}, save and except those specifically "
            f"admitted herein. I say that the {e.proceeding_type.title()} is misconceived, "
            f"devoid of merits and is liable to be dismissed in limine. {facts}"
        )
    if dp.move == "PRELIMINARY_POSITION":
        return (
            f"I say that {_lower_first(facts)} The action complained of has been taken strictly in "
            f"accordance with law and after following due procedure. No legal, "
            f"constitutional or fundamental right of the Petitioner has been infringed."
        )
    if dp.move == "SUBSTANTIVE_ANSWER":
        text = (
            f"With reference to the averments made in the Petition, I say that the same "
            f"are false, incorrect and denied. {facts}"
        )
        if dp.exhibit:
            text += (
                f" Hereto annexed and marked as {dp.exhibit['label']} is a copy of the "
                f"{dp.exhibit['description']}."
            )
        return text
    if dp.move == "CLOSING":
        return (
            f"In the premises aforesaid, I say that the {e.proceeding_type.title()} "
            f"deserves to be dismissed with costs."
        )
    raise ValueError(f"Unknown move: {dp.move}")


def generate_template_fallback(plan: DraftPlan) -> GeneratedDocument:
    paragraphs, moves, exhibits = [], [], []
    for dp in plan.body_paragraphs:
        paragraphs.append(_compose_paragraph_template(dp, plan))
        moves.append(dp.move)
        if dp.exhibit:
            exhibits.append(dp.exhibit)

    prayer_lines = [
        "dismiss the present {0} with costs;".format(plan.entities.proceeding_type.title()),
        "refuse any interim or ad-interim relief sought by the Petitioner; and",
        "grant such other and further reliefs as this Hon'ble Court may deem fit and "
        "proper in the facts and circumstances of the case.",
    ]

    return GeneratedDocument(
        entities=plan.entities,
        paragraphs=paragraphs,
        paragraph_moves=moves,
        prayer_lines=prayer_lines,
        generation_mode="template_fallback",
        exhibits=exhibits,
    )


# ---------------------------------------------------------------------------
# LLM-backed generation -- provider-agnostic
# ---------------------------------------------------------------------------

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_HF_MODEL = "meta-llama/Llama-3.1-8B-Instruct"


def detect_provider() -> str | None:
    """Picks a provider based on what's configured, honouring an explicit
    GENERATION_PROVIDER override ('anthropic' | 'huggingface') if set.
    Returns None if nothing is configured -> caller should use the
    template fallback."""
    forced = os.environ.get("GENERATION_PROVIDER", "").strip().lower()
    if forced in ("anthropic", "huggingface"):
        return forced
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("HF_TOKEN"):
        return "huggingface"
    return None


def _provider_sdk_available(provider: str) -> bool:
    try:
        if provider == "anthropic":
            import anthropic  # noqa: F401
        elif provider == "huggingface":
            import huggingface_hub  # noqa: F401
        else:
            return False
        return True
    except ImportError:
        return False


def _call_claude(prompt: str, model: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _call_huggingface(prompt: str, model: str) -> str:
    """Uses the HF Inference API's OpenAI-compatible chat_completion
    interface. Works with any instruction-tuned chat model hosted on the
    free Inference API (e.g. meta-llama/Llama-3.1-8B-Instruct,
    mistralai/Mistral-7B-Instruct-v0.3) as long as HF_TOKEN has access to it."""
    from huggingface_hub import InferenceClient
    client = InferenceClient(model=model, token=os.environ.get("HF_TOKEN"))
    resp = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


PROVIDER_CALLERS = {
    "anthropic": _call_claude,
    "huggingface": _call_huggingface,
}

PROVIDER_DEFAULT_MODELS = {
    "anthropic": DEFAULT_ANTHROPIC_MODEL,
    "huggingface": DEFAULT_HF_MODEL,
}


def _build_paragraph_prompt(dp: DraftParagraph, plan: DraftPlan, format_rules: dict) -> str:
    e = plan.entities
    phrase_bank = _phrase_bank_for(dp.move, format_rules)
    return f"""You are drafting one numbered paragraph of an Affidavit in Reply for an Indian court, \
in formal legal drafting style. Follow these rules strictly:

- Use ONLY the facts given below. Do not invent names, dates, statutes, or events not supplied.
- Naturally incorporate these fixed phrases used in this section: {json.dumps(phrase_bank)}
- Proceeding type: {e.proceeding_type}. Respondent number replying: {e.respondent_number}.
- Instruction for this paragraph's move ({dp.move}): {MOVE_INSTRUCTIONS[dp.move]}
- Supplied facts for this paragraph: {json.dumps(dp.source_bullets)}
- Exhibit for this paragraph, if any (reference exactly, do not alter wording): {json.dumps(dp.exhibit)}
- Output ONLY the paragraph body text (no paragraph number, no heading, no preamble/explanation).
"""


def generate_llm(plan: DraftPlan, format_rules: dict, provider: str, model: str | None = None) -> GeneratedDocument:
    if provider not in PROVIDER_CALLERS:
        raise ValueError(f"Unknown provider: {provider}")
    call = PROVIDER_CALLERS[provider]
    model = model or PROVIDER_DEFAULT_MODELS[provider]

    paragraphs, moves, exhibits = [], [], []
    for dp in plan.body_paragraphs:
        prompt = _build_paragraph_prompt(dp, plan, format_rules)
        text = call(prompt, model)
        paragraphs.append(text)
        moves.append(dp.move)
        if dp.exhibit:
            exhibits.append(dp.exhibit)

    prayer_lines = [
        f"dismiss the present {plan.entities.proceeding_type.title()} with costs;",
        "refuse any interim or ad-interim relief sought by the Petitioner; and",
        "grant such other and further reliefs as this Hon'ble Court may deem fit and "
        "proper in the facts and circumstances of the case.",
    ]

    return GeneratedDocument(
        entities=plan.entities,
        paragraphs=paragraphs,
        paragraph_moves=moves,
        prayer_lines=prayer_lines,
        generation_mode=f"llm:{provider}",
        exhibits=exhibits,
    )


def generate(plan: DraftPlan, format_rules: dict, provider: str | None = None, model: str | None = None) -> GeneratedDocument:
    """Entry point.

    - provider=None (default): auto-detect from environment (GENERATION_PROVIDER,
      else ANTHROPIC_API_KEY, else HF_TOKEN). Falls back to the deterministic
      template composer if nothing is configured or the call fails.
    - provider="anthropic" / "huggingface": force a specific provider.
    - provider="template": force the deterministic fallback regardless of
      what's configured (useful for demos / tests).
    """
    if provider == "template":
        return generate_template_fallback(plan)

    provider = provider or detect_provider()
    if provider and _provider_sdk_available(provider):
        try:
            return generate_llm(plan, format_rules, provider=provider, model=model)
        except Exception as exc:  # network / API / auth error -> don't crash the demo
            print(f"[generator] {provider} generation failed ({exc}); using template fallback.")
            return generate_template_fallback(plan)
    return generate_template_fallback(plan)
